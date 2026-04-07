"""
Spec 05 — Build the tiered classification view.

Merges the deterministic NLP classification (Spec 03) with the legacy AI
classification into a single per-experiment tier label so the dashboard
can show what is "Confirmed", "Probable", "Uncertain", or "Not health-
related" at a glance.

Tier rules (spec section 1):

  Tier 1 — Confirmed       NLP health-rel AND AI health-rel AND >=1 shared area
  Tier 2 — Probable        AI only AND ai_confidence >= 0.7
  Tier 3 — Uncertain       AI only AND ai_confidence <  0.7
  Tier 0 — Not health      Everything else (also catches NLP insufficient_text)

Disease areas:
  Tier 1 -> use NLP areas (more precise — backed by MeSH evidence)
  Tier 2 -> use AI areas (NLP missed it, AI is the only signal)
  Tier 3 -> use AI areas (low confidence, but still the only signal)

Inputs:
  data/processed/classified_experiments_nlp.csv
  data/processed/classified_experiments.csv
  data/processed/classification_details.json   (per-experiment AI confidence)
  data/processed/classification_comparison.csv (optional, only used for sanity)

Outputs:
  data/processed/tiered_classification.csv
  data/processed/tiered_classification_summary.json

This script does NOT modify either source CSV. It's purely additive.

Usage:
  ./venv/bin/python scripts/13_build_tiered_classification.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import config  # noqa: E402


# ---------------------------------------------------------------------------
# Paths + thresholds
# ---------------------------------------------------------------------------
NLP_CSV = config.PROCESSED_DIR / "classified_experiments_nlp.csv"
AI_CSV = config.PROCESSED_DIR / "classified_experiments.csv"
AI_DETAILS_JSON = config.PROCESSED_DIR / "classification_details.json"

OUT_CSV = config.PROCESSED_DIR / "tiered_classification.csv"
OUT_SUMMARY = config.PROCESSED_DIR / "tiered_classification_summary.json"

# Spec section 1 + 3
TIER2_CONFIDENCE = 0.7
PROXY_CONFIDENCE_AI = 0.75
PROXY_CONFIDENCE_KEYWORD = 0.6


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def parse_areas(val: object) -> list[str]:
    """Split a 'Area; Area' string into an ordered list (preserves AI priority)."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return []
    s = str(val).strip()
    if not s or s.lower() == "nan":
        return []
    out: list[str] = []
    for part in s.split(";"):
        p = part.strip()
        if p and p not in out:
            out.append(p)
    return out


def coerce_bool(val: object) -> bool:
    if isinstance(val, bool):
        return val
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return False
    return str(val).strip().lower() in ("true", "1", "yes", "t")


def extract_ai_confidence(
    osid: str,
    details: dict[str, Any],
    ai_source: str,
    ai_health: bool,
) -> float:
    """
    Return a single AI confidence score in [0, 1] for this experiment.

    Priority:
      1. Real per-experiment max confidence from classification_details.json
         (taken across all 'details' entries — i.e. the strongest signal AI
         had for any disease area).
      2. Spec 3 proxy fallback when details are empty/missing:
         - source 'ai'      -> 0.75
         - source 'keyword' -> 0.60
         - everything else  -> 0.50

    Non-health-related experiments still get a confidence (they may still
    have details from earlier classification passes), but it doesn't matter
    because Tier 2/3 only kick in when AI says health-related.
    """
    rec = details.get(osid)
    if rec:
        scores = [
            d.get("confidence")
            for d in rec.get("details", [])
            if isinstance(d, dict) and d.get("confidence") is not None
        ]
        if scores:
            return float(max(scores))

    # Proxy fallback per spec section 3
    src = (ai_source or "").lower()
    if src == "ai":
        return PROXY_CONFIDENCE_AI
    if src == "keyword":
        return PROXY_CONFIDENCE_KEYWORD
    return 0.5 if ai_health else 0.0


def assign_tier(
    nlp_health: bool,
    ai_health: bool,
    nlp_areas: list[str],
    ai_areas: list[str],
    nlp_relevance: str,
    ai_confidence: float,
) -> tuple[int, str, list[str], str]:
    """
    Implement the four-tier rule from spec section 1.

    Returns (tier_int, tier_label, chosen_areas, classification_source).
    """
    # Tier 0 short-circuits — NLP marked it as too short to classify.
    if (nlp_relevance or "").lower() == "insufficient_text":
        return 0, "Not health-related", [], "none"

    if nlp_health and ai_health:
        shared = [a for a in nlp_areas if a in set(ai_areas)]
        if shared:
            # Tier 1 — both methods agree on at least one area.
            # Use NLP areas (the more precise side) but make sure the shared
            # areas come first so the primary is one they agree on.
            ordered = shared + [a for a in nlp_areas if a not in shared]
            return 1, "Confirmed", ordered, "nlp+ai"

    if (not nlp_health) and ai_health:
        if ai_confidence >= TIER2_CONFIDENCE:
            return 2, "Probable", ai_areas, "ai_high"
        return 3, "Uncertain", ai_areas, "ai_low"

    # Includes:
    #  - both False
    #  - NLP True but AI False (rare; demote to Tier 0 — no agreement layer)
    #  - NLP True + AI True but no shared area (both flag as health but
    #    disagree on which area — the spec only counts agreement when areas
    #    overlap, so this falls through to Tier 0)
    return 0, "Not health-related", [], "none"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    print("Loading inputs ...")
    nlp = pd.read_csv(NLP_CSV)
    ai = pd.read_csv(AI_CSV)
    print(f"  NLP rows: {len(nlp):,}")
    print(f"  AI  rows: {len(ai):,}")

    if AI_DETAILS_JSON.exists():
        details = json.loads(AI_DETAILS_JSON.read_text())
        print(f"  AI details: {len(details):,} entries (per-experiment confidence)")
    else:
        details = {}
        print("  AI details: not found (will use spec proxy 0.75/0.60)")

    nlp_idx = nlp.set_index("osID")
    ai_idx = ai.set_index("osID")

    # Master list of every experiment we'll output (use NLP because that's
    # the canonical Spec 03 dataset; AI was generated from the same source)
    all_ids = list(nlp_idx.index)
    if len(all_ids) != 3829:
        print(f"  WARNING: expected 3,829 experiments, got {len(all_ids):,}")

    rows: list[dict[str, Any]] = []
    counts = {0: 0, 1: 0, 2: 0, 3: 0}

    for osid in all_ids:
        n = nlp_idx.loc[osid]
        a = ai_idx.loc[osid] if osid in ai_idx.index else None

        nlp_health = coerce_bool(n.get("health_related"))
        nlp_areas = parse_areas(n.get("disease_areas"))
        nlp_relevance = str(n.get("relevance_type") or "")
        nlp_mesh = str(n.get("mesh_evidence") or "")

        if a is None:
            ai_health = False
            ai_areas: list[str] = []
            ai_source = ""
        else:
            ai_health = coerce_bool(a.get("health_related"))
            ai_areas = parse_areas(a.get("disease_areas"))
            ai_source = str(a.get("classification_source") or "")

        ai_confidence = extract_ai_confidence(
            osid=str(osid),
            details=details,
            ai_source=ai_source,
            ai_health=ai_health,
        )

        tier, tier_label, chosen_areas, source = assign_tier(
            nlp_health=nlp_health,
            ai_health=ai_health,
            nlp_areas=nlp_areas,
            ai_areas=ai_areas,
            nlp_relevance=nlp_relevance,
            ai_confidence=ai_confidence,
        )
        counts[tier] += 1

        primary = chosen_areas[0] if chosen_areas else ""
        rows.append(
            {
                "osID": osid,
                "title": n.get("title"),
                "tier": tier,
                "tier_label": tier_label,
                "health_related": tier in (1, 2, 3),
                "disease_areas": "; ".join(chosen_areas),
                "primary_disease_area": primary,
                "nlp_classified": nlp_health,
                "ai_classified": ai_health,
                "ai_confidence": round(float(ai_confidence), 3),
                "nlp_mesh_evidence": nlp_mesh if tier == 1 else "",
                "classification_source": source,
            }
        )

    out_df = pd.DataFrame(rows)
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    out_df.to_csv(OUT_CSV, index=False)
    print(f"\nWrote {OUT_CSV.relative_to(config.PROJECT_ROOT)}  ({len(out_df):,} rows)")

    # Per-disease-area breakdown
    per_area: dict[str, dict[str, int]] = {}
    for area in config.DISEASE_AREA_NAMES:
        bucket = {"tier_1": 0, "tier_2": 0, "tier_3": 0, "total": 0}
        for _, r in out_df.iterrows():
            if not r["disease_areas"]:
                continue
            areas = parse_areas(r["disease_areas"])
            if area in areas:
                bucket["total"] += 1
                if r["tier"] == 1:
                    bucket["tier_1"] += 1
                elif r["tier"] == 2:
                    bucket["tier_2"] += 1
                elif r["tier"] == 3:
                    bucket["tier_3"] += 1
        per_area[area] = bucket

    total = len(out_df)
    summary = {
        "total_experiments": total,
        "tier_1_confirmed": counts[1],
        "tier_2_probable": counts[2],
        "tier_3_uncertain": counts[3],
        "tier_0_not_health": counts[0],
        "total_health_related_tiered": counts[1] + counts[2] + counts[3],
        "coverage_percent": round(
            (counts[1] + counts[2] + counts[3]) / total * 100 if total else 0.0,
            2,
        ),
        "per_disease_area": per_area,
        "thresholds": {
            "tier2_confidence": TIER2_CONFIDENCE,
            "proxy_confidence_ai": PROXY_CONFIDENCE_AI,
            "proxy_confidence_keyword": PROXY_CONFIDENCE_KEYWORD,
        },
    }
    config.save_json(OUT_SUMMARY, summary)
    print(f"Wrote {OUT_SUMMARY.relative_to(config.PROJECT_ROOT)}")

    # Console report
    print()
    print("=" * 60)
    print("Tiered classification summary")
    print("=" * 60)
    print(f"Total experiments              : {total:,}")
    print(f"Tier 1 — Confirmed (NLP+AI)    : {counts[1]:,}  ({counts[1]/total:.1%})")
    print(f"Tier 2 — Probable (AI ≥0.7)    : {counts[2]:,}  ({counts[2]/total:.1%})")
    print(f"Tier 3 — Uncertain (AI <0.7)   : {counts[3]:,}  ({counts[3]/total:.1%})")
    print(f"Tier 0 — Not health-related    : {counts[0]:,}  ({counts[0]/total:.1%})")
    print()
    print(f"Total health-related (tiers 1-3): {counts[1] + counts[2] + counts[3]:,}")
    print(f"Tiered coverage                 : {summary['coverage_percent']:.1f}%")
    print()
    print(f"  {'Area':40s} {'T1':>5s} {'T2':>5s} {'T3':>5s} {'Total':>6s}")
    for area, b in per_area.items():
        print(
            f"  {area:40s} {b['tier_1']:5d} {b['tier_2']:5d} {b['tier_3']:5d} {b['total']:6d}"
        )


if __name__ == "__main__":
    main()
