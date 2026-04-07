"""
Spec 03 section 8 — Compare AI vs NLP classifications.

Reads:
  data/processed/classified_experiments.csv      (AI / OpenRouter Claude)
  data/processed/classified_experiments_nlp.csv  (NLP / SciSpacy + MeSH)

Writes:
  data/processed/classification_comparison.csv

Prints an agreement summary to stdout.

Run with:
    python scripts/11_compare_classifications.py
"""

from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import config  # noqa: E402


AI_CSV = config.PROCESSED_DIR / "classified_experiments.csv"
NLP_CSV = config.PROCESSED_DIR / "classified_experiments_nlp.csv"
OUT_CSV = config.PROCESSED_DIR / "classification_comparison.csv"


def parse_areas(val: object) -> set[str]:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return set()
    s = str(val).strip()
    if not s or s.lower() == "nan":
        return set()
    return {a.strip() for a in s.split(";") if a.strip()}


def coerce_bool(val: object) -> bool:
    if isinstance(val, bool):
        return val
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return False
    return str(val).strip().lower() in ("true", "1", "yes", "t")


def main() -> None:
    print(f"Loading {AI_CSV.relative_to(config.PROJECT_ROOT)}")
    ai = pd.read_csv(AI_CSV)
    print(f"  {len(ai):,} rows")

    print(f"Loading {NLP_CSV.relative_to(config.PROJECT_ROOT)}")
    nlp = pd.read_csv(NLP_CSV)
    print(f"  {len(nlp):,} rows")

    ai_idx = ai.set_index("osID")
    nlp_idx = nlp.set_index("osID")
    common = sorted(set(ai_idx.index) & set(nlp_idx.index))
    print(f"  {len(common):,} experiments in both files")

    rows: list[dict] = []
    agree_health = 0
    agree_exact = 0
    agree_any_overlap = 0

    # Per-area agreement counters: area -> [tp, fp, fn]
    # tp = both; fp = only AI said; fn = only NLP said (relative to AI as "label")
    area_counts: dict[str, dict[str, int]] = defaultdict(lambda: {"both": 0, "ai_only": 0, "nlp_only": 0})

    for osid in common:
        a = ai_idx.loc[osid]
        n = nlp_idx.loc[osid]

        ai_hr = coerce_bool(a.get("health_related"))
        nlp_hr = coerce_bool(n.get("health_related"))
        ai_areas = parse_areas(a.get("disease_areas"))
        nlp_areas = parse_areas(n.get("disease_areas"))

        if ai_hr == nlp_hr:
            agree_health += 1
        if ai_areas == nlp_areas:
            agree_exact += 1
        if ai_areas & nlp_areas:
            agree_any_overlap += 1

        ai_only = ai_areas - nlp_areas
        nlp_only = nlp_areas - ai_areas
        both = ai_areas & nlp_areas

        for area in both:
            area_counts[area]["both"] += 1
        for area in ai_only:
            area_counts[area]["ai_only"] += 1
        for area in nlp_only:
            area_counts[area]["nlp_only"] += 1

        rows.append(
            {
                "osID": osid,
                "title": a.get("title", ""),
                "ai_health_related": ai_hr,
                "nlp_health_related": nlp_hr,
                "ai_disease_areas": "; ".join(sorted(ai_areas)),
                "nlp_disease_areas": "; ".join(sorted(nlp_areas)),
                "agree_health": ai_hr == nlp_hr,
                "agree_areas": ai_areas == nlp_areas,
                "any_overlap": bool(ai_areas & nlp_areas),
                "ai_only_areas": "; ".join(sorted(ai_only)),
                "nlp_only_areas": "; ".join(sorted(nlp_only)),
            }
        )

    out_df = pd.DataFrame(rows)
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    out_df.to_csv(OUT_CSV, index=False)
    print(f"\nWrote {OUT_CSV.relative_to(config.PROJECT_ROOT)}  ({len(out_df):,} rows)")

    n = len(common)
    print()
    print("=" * 70)
    print("Agreement summary")
    print("=" * 70)
    print(f"Total compared                     : {n:,}")
    print(f"Agree on health/not-health         : {agree_health:,}  ({agree_health/n:.1%})")
    print(f"Agree on disease areas (exact set) : {agree_exact:,}  ({agree_exact/n:.1%})")
    print(f"Agree on at least one disease area : {agree_any_overlap:,}  ({agree_any_overlap/n:.1%})")
    print()
    print("Per-disease-area comparison (AI vs NLP):")
    print(f"  {'Area':40s} {'Both':>6s} {'AI only':>8s} {'NLP only':>8s}")
    for area in config.DISEASE_AREA_NAMES:
        c = area_counts.get(area, {"both": 0, "ai_only": 0, "nlp_only": 0})
        print(f"  {area:40s} {c['both']:6d} {c['ai_only']:8d} {c['nlp_only']:8d}")

    # Top 20 disagreements (health_related differs)
    disagrees = out_df[~out_df["agree_health"]].head(20)
    if not disagrees.empty:
        print()
        print("Top 20 disagreements on health/not-health:")
        for _, r in disagrees.iterrows():
            print(
                f"  {r['osID']:10s} AI={r['ai_health_related']!s:5s} "
                f"NLP={r['nlp_health_related']!s:5s} | {str(r['title'])[:60]}"
            )


if __name__ == "__main__":
    main()
