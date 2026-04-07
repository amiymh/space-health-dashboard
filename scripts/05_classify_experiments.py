"""
05_classify_experiments.py

Phase 2: classify every experiment in osdr_experiments.csv against the 10
SNIH disease areas.

Two-stage strategy (free first, then AI fallback):

  1. Keyword stage — match the experiment's title + objectives + approach +
     results against the keyword lists in `scripts/config.py`. Free, instant.
  2. AI stage — for experiments where the keyword stage finds zero matches,
     query Claude (claude-3.5-sonnet) via OpenRouter for a structured
     classification. Rate-limited to 1 req/sec.

Each result records its `classification_source`:
  - "keyword"   — keyword match only
  - "ai"        — AI classification only (no keyword match)
  - "both"      — both ran (only happens if AI is forced for ambiguous cases)
  - "none"      — neither stage produced a result

Inputs:
  - data/processed/osdr_experiments.csv

Outputs:
  - data/processed/classified_experiments.csv
  - data/processed/classification_details.json
  - data/checkpoints/classify_checkpoint.json   (resume state)

Run is safe to interrupt and re-run — it picks up where the checkpoint left
off.

See SPACE_HEALTH_SPECS.md section 3.3.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import Any

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import (  # noqa: E402
    CHECKPOINT_DIR,
    DISEASE_AREAS,
    DISEASE_AREA_NAMES,
    PROCESSED_DIR,
    REQUEST_HEADERS,
    get_env,
    load_env,
    load_json,
    save_json,
)

INPUT_CSV = PROCESSED_DIR / "osdr_experiments.csv"
CSV_OUTPUT = PROCESSED_DIR / "classified_experiments.csv"
DETAILS_JSON = PROCESSED_DIR / "classification_details.json"
CHECKPOINT_FILE = CHECKPOINT_DIR / "classify_checkpoint.json"

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
# Spec asked for claude-3-5-sonnet-20241022, but that model has been
# deprecated on OpenRouter (2026-04). Substituting Sonnet 4.5 — closest
# equivalent for classification accuracy, similar pricing tier.
MODEL = "anthropic/claude-sonnet-4.5"
# Sonnet 4.5's content moderation blocks a small number of microbiology
# titles (pathogen names like "Burkholderia", "Mycobacteria"). Haiku 4.5
# answers them cleanly, so it's our final-tier fallback.
FALLBACK_MODEL = "anthropic/claude-haiku-4.5"
AI_RATE_LIMIT_SEC = 1.0
CHECKPOINT_EVERY = 50

# Confidence assigned to keyword-only matches (the spec wants AI calls to
# carry richer confidence signals; keyword hits are deterministic so they
# get a high but not perfect score)
KEYWORD_CONFIDENCE = 0.9


# ---------------------------------------------------------------------------
# Keyword matching
# ---------------------------------------------------------------------------
def build_keyword_patterns() -> dict[str, list[tuple[str, re.Pattern[str]]]]:
    """
    Pre-compile case-insensitive word-boundary regexes for every keyword in
    every disease area. Multi-word phrases use boundaries on both ends; the
    pattern still tolerates internal whitespace because re.escape preserves
    spaces literally.
    """
    patterns: dict[str, list[tuple[str, re.Pattern[str]]]] = {}
    for area, entry in DISEASE_AREAS.items():
        keywords = entry["primary"] + entry.get("expansions", [])
        compiled: list[tuple[str, re.Pattern[str]]] = []
        for kw in keywords:
            kw_lower = kw.lower().strip()
            if not kw_lower:
                continue
            pattern = re.compile(r"\b" + re.escape(kw_lower) + r"\b", re.IGNORECASE)
            compiled.append((kw, pattern))
        patterns[area] = compiled
    return patterns


def keyword_classify(
    text: str,
    patterns: dict[str, list[tuple[str, re.Pattern[str]]]],
) -> dict[str, list[str]]:
    """Return {disease_area: [matched_keywords]} for every area with hits."""
    if not text:
        return {}
    text_lower = text.lower()
    matches: dict[str, list[str]] = {}
    for area, kw_patterns in patterns.items():
        hits = [kw for kw, pat in kw_patterns if pat.search(text_lower)]
        if hits:
            matches[area] = hits
    return matches


# ---------------------------------------------------------------------------
# OpenRouter / Claude classification
# ---------------------------------------------------------------------------
PROMPT_TEMPLATE = """You are classifying ISS space experiments against health disease areas.

Experiment title: {title}
Description: {description}

Classify against these 10 disease areas:
1. Cardiovascular diseases
2. Kidney diseases
3. Cancer
4. Neurological diseases
5. Eye diseases
6. Rare inherited disorders
7. Women's health
8. Endocrine and metabolic diseases
9. Musculoskeletal diseases
10. Mental health

Return ONLY valid JSON, no markdown:
{{
  "health_related": true,
  "disease_areas": [
    {{"area": "...", "relevance": "direct", "confidence": 0.0, "reasoning": "one sentence"}}
  ],
  "non_health_category": "if not health related, what category: physical science / materials / technology / plant biology / education / other"
}}"""


def make_session() -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=4,
        backoff_factor=2.0,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(["POST"]),
    )
    session.mount("https://", HTTPAdapter(max_retries=retry))
    session.headers.update(REQUEST_HEADERS)
    return session


_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def _strip_fences(text: str) -> str:
    return _FENCE_RE.sub("", text).strip()


def _post_classification(
    session: requests.Session,
    api_key: str,
    title: str,
    description: str,
    model: str = MODEL,
) -> str | None:
    """One round-trip to OpenRouter. Returns content string or None."""
    prompt = PROMPT_TEMPLATE.format(
        title=title or "(no title)",
        description=(description or "(no description)")[:4000],
    )
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 1200,
        "temperature": 0.0,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/amiymh/space-health-dashboard",
        "X-Title": "Space-Health Dashboard",
    }
    resp = session.post(OPENROUTER_URL, json=payload, headers=headers, timeout=120)
    resp.raise_for_status()
    body = resp.json()
    msg = body["choices"][0]["message"]
    content = msg.get("content")
    if content:
        return content
    # Some providers stash JSON in the reasoning trace
    reasoning = msg.get("reasoning")
    if isinstance(reasoning, str) and reasoning:
        return reasoning
    return None


def ai_classify(
    session: requests.Session,
    api_key: str,
    title: str,
    description: str,
) -> dict[str, Any]:
    # Tier 1: Sonnet 4.5 with full description
    content = _post_classification(session, api_key, title, description)

    # Tier 2: Sonnet 4.5 with title only (long descriptions trip moderation
    # on pathogen names like "M. marinum", "virulence")
    if not content:
        time.sleep(1.5)
        content = _post_classification(session, api_key, title, description="")

    # Tier 3: Haiku 4.5 with title only (Sonnet 4.5's moderation also
    # blocks some pathogen-bearing titles outright; Haiku is permissive)
    if not content:
        time.sleep(1.5)
        content = _post_classification(
            session, api_key, title, description="", model=FALLBACK_MODEL
        )

    if not content:
        raise RuntimeError("AI returned empty content after Sonnet+title+Haiku fallbacks")

    cleaned = _strip_fences(content)
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"AI response was not valid JSON: {cleaned[:200]}") from exc

    # Normalize area names to match config exactly (Claude sometimes drops
    # the trailing "diseases" or pluralizes differently)
    normalized_areas: list[dict[str, Any]] = []
    canonical = {a.lower(): a for a in DISEASE_AREA_NAMES}
    for entry in parsed.get("disease_areas") or []:
        if not isinstance(entry, dict):
            continue
        area = (entry.get("area") or "").strip()
        match = canonical.get(area.lower())
        if not match:
            # Loose match — pick the canonical name whose first word matches
            for cname in DISEASE_AREA_NAMES:
                if cname.lower().split()[0] in area.lower():
                    match = cname
                    break
        if not match:
            continue
        normalized_areas.append({
            "area": match,
            "relevance": (entry.get("relevance") or "indirect").lower(),
            "confidence": float(entry.get("confidence") or 0.0),
            "reasoning": (entry.get("reasoning") or "").strip(),
        })

    return {
        "health_related": bool(parsed.get("health_related", bool(normalized_areas))),
        "disease_areas": normalized_areas,
        "non_health_category": (parsed.get("non_health_category") or "").strip(),
    }


# ---------------------------------------------------------------------------
# Result merging
# ---------------------------------------------------------------------------
def build_record(
    osid: str,
    keyword_matches: dict[str, list[str]],
    ai_result: dict[str, Any] | None,
) -> dict[str, Any]:
    details: list[dict[str, Any]] = []

    # Keyword-derived entries
    for area, kws in keyword_matches.items():
        details.append({
            "area": area,
            "relevance": "direct",
            "confidence": KEYWORD_CONFIDENCE,
            "reasoning": f"Keyword match: {', '.join(kws[:4])}",
            "source": "keyword",
        })

    # AI-derived entries — append areas not already keyword-matched
    if ai_result:
        for ai_area in ai_result.get("disease_areas", []):
            if ai_area["area"] in keyword_matches:
                continue
            details.append({**ai_area, "source": "ai"})

    # Source flag
    if keyword_matches and ai_result:
        source = "both"
    elif keyword_matches:
        source = "keyword"
    elif ai_result:
        source = "ai"
    else:
        source = "none"

    # Health-related: any disease area present, or AI explicitly said so
    health_related = bool(details)
    if ai_result is not None and not keyword_matches:
        health_related = bool(ai_result.get("health_related"))

    non_health_category = ""
    if ai_result and not health_related:
        non_health_category = ai_result.get("non_health_category", "") or "unknown"

    # Primary disease area = highest confidence (keyword wins ties at 0.9)
    primary_area = ""
    relevance_type = ""
    if details:
        ranked = sorted(details, key=lambda d: -float(d.get("confidence", 0.0)))
        primary_area = ranked[0]["area"]
        relevance_type = ranked[0].get("relevance", "")

    return {
        "osID": osid,
        "health_related": health_related,
        "disease_areas_list": [d["area"] for d in details],
        "primary_disease_area": primary_area,
        "relevance_type": relevance_type,
        "classification_source": source,
        "non_health_category": non_health_category,
        "details": details,
    }


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------
def save_checkpoint(results: dict[str, dict[str, Any]], api_calls: int) -> None:
    save_json(CHECKPOINT_FILE, {"results": results, "api_calls": api_calls})


def write_outputs(df: pd.DataFrame, results: dict[str, dict[str, Any]]) -> None:
    rows = []
    for _, row in df.iterrows():
        osid = str(row["osID"])
        r = results.get(osid, {})
        merged = row.to_dict()
        merged["health_related"] = r.get("health_related", "")
        merged["disease_areas"] = "; ".join(r.get("disease_areas_list", []))
        merged["primary_disease_area"] = r.get("primary_disease_area", "")
        merged["relevance_type"] = r.get("relevance_type", "")
        merged["classification_source"] = r.get("classification_source", "")
        merged["non_health_category"] = r.get("non_health_category", "")
        rows.append(merged)
    out_df = pd.DataFrame(rows)
    out_df.to_csv(CSV_OUTPUT, index=False)

    details_payload = {
        osid: {
            "primary_disease_area": r.get("primary_disease_area", ""),
            "classification_source": r.get("classification_source", ""),
            "health_related": r.get("health_related"),
            "non_health_category": r.get("non_health_category", ""),
            "details": r.get("details", []),
        }
        for osid, r in results.items()
    }
    save_json(DETAILS_JSON, details_payload)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--retry-none",
        action="store_true",
        help=(
            "Re-process every row currently tagged 'none' or 'incomplete' "
            "in the checkpoint. Existing 'keyword' and 'ai' classifications "
            "are preserved untouched. Requires OPENROUTER_API_KEY — aborts "
            "if the key is missing."
        ),
    )
    args = parser.parse_args()

    load_env()
    api_key = get_env("OPENROUTER_API_KEY")
    if not api_key:
        if args.retry_none:
            raise SystemExit(
                "[classify] FATAL: --retry-none requires OPENROUTER_API_KEY in .env. "
                "Cannot retry unclassified rows without the AI fallback."
            )
        print("[classify] WARNING: no OPENROUTER_API_KEY in .env — AI fallback disabled")

    if not INPUT_CSV.exists():
        raise SystemExit(
            f"[classify] {INPUT_CSV} missing — run scripts/01_fetch_nasa_osdr.py first"
        )

    df = pd.read_csv(INPUT_CSV).fillna("")
    total = len(df)
    print(f"[classify] Loaded {total} experiments from {INPUT_CSV.name}")

    checkpoint = load_json(CHECKPOINT_FILE, default={}) or {}
    results: dict[str, dict[str, Any]] = checkpoint.get("results", {})
    api_calls: int = int(checkpoint.get("api_calls", 0))
    if results:
        print(f"[classify] Resuming — {len(results)} experiments already classified")

    # ------------------------------------------------------------------
    # --retry-none: drop existing 'none' and 'incomplete' entries from
    # the results dict so the main loop reprocesses them. 'keyword' and
    # 'ai' classifications are preserved untouched per the spec.
    # ------------------------------------------------------------------
    retry_queue: set[str] = set()
    if args.retry_none:
        retry_sources = {"none", "incomplete"}
        retry_queue = {
            osid for osid, r in results.items()
            if r.get("classification_source") in retry_sources
        }
        for osid in retry_queue:
            del results[osid]
        print(
            f"[classify] --retry-none: cleared {len(retry_queue)} entries "
            f"({len(results)} remain locked-in)"
        )

    # ------------------------------------------------------------------
    # Fix 5 — handle missing titles up front. Replace the NaN/empty
    # title with a placeholder, mark the record as incomplete, and skip
    # the classification loop entirely. Prevents downstream NaN crashes
    # and ensures the row still appears in the final CSV.
    # ------------------------------------------------------------------
    empty_title_mask = df["title"].astype(str).str.strip() == ""
    for idx in df.index[empty_title_mask]:
        osid = str(df.at[idx, "osID"])
        placeholder = f"[No title — OSDR record {osid}]"
        df.at[idx, "title"] = placeholder
        if osid in results:
            continue
        results[osid] = {
            "osID": osid,
            "health_related": False,
            "disease_areas_list": [],
            "primary_disease_area": "",
            "relevance_type": "",
            "classification_source": "incomplete",
            "non_health_category": "incomplete_record",
            "details": [],
        }
        print(f"[classify] {osid}: empty title — marked incomplete_record")

    patterns = build_keyword_patterns()
    session = make_session() if api_key else None

    # Progress counters used by --retry-none for the [ai-retry] log line
    retry_total = len(retry_queue)
    retry_done = 0
    retry_health = 0
    retry_not_health = 0
    log_prefix = "ai-retry" if args.retry_none else "classify"

    new_count = 0
    for position, (_, row) in enumerate(df.iterrows(), start=1):
        osid = str(row["osID"])
        if osid in results:
            continue

        title = str(row.get("title") or "").strip()
        objectives = str(row.get("objectives") or "").strip()
        approach = str(row.get("approach") or "").strip()
        results_text = str(row.get("results") or "").strip()
        research_areas = str(row.get("researchAreas") or "").strip()
        publication_titles = str(row.get("publication_titles") or "").strip()

        description_parts = [objectives, approach, results_text]
        description = " ".join(p for p in description_parts if p)

        # Keyword matching uses everything we have, including researchAreas
        # tagged by NASA themselves (often more useful than the title alone)
        # and the titles of any publications linked to the experiment — that
        # last field is critical for SSRE rows, which carry no objectives/
        # approach/results but often have rich publication titles.
        keyword_text = " ".join(
            p for p in [title, description, research_areas, publication_titles] if p
        )
        keyword_matches = keyword_classify(keyword_text, patterns)

        # Fix 2 — short-title-no-context routing
        # Titles with fewer than 8 words AND no objectives/approach/results
        # produce too many keyword false positives (e.g. "STS-106 Flight
        # Environmental Data" gets tagged Musculoskeletal). Discard the
        # keyword matches in that case and route to the AI fallback so the
        # model can refuse to classify if there's truly no signal.
        title_word_count = len(title.split())
        no_context = not (objectives or approach or results_text)
        short_unreliable = title_word_count < 8 and no_context
        if short_unreliable and keyword_matches:
            print(
                f"[classify] Classifying {position}/{total}: {osid} — "
                f"short title ({title_word_count} words) with no description, "
                f"discarding keyword matches and routing to AI"
            )
            keyword_matches = {}

        ai_result: dict[str, Any] | None = None
        ai_error_reason: str = ""
        if not keyword_matches and api_key and session is not None:
            print(
                f"[{log_prefix}] Classifying {position}/{total}: {osid} — "
                f"no keyword match, querying AI..."
            )
            try:
                ai_result = ai_classify(session, api_key, title, description)
                api_calls += 1
            except Exception as exc:
                ai_error_reason = str(exc)[:200]
                print(f"[{log_prefix}]   AI error: {ai_error_reason}")
            time.sleep(AI_RATE_LIMIT_SEC)
        else:
            if keyword_matches:
                print(
                    f"[classify] Classifying {position}/{total}: {osid} — "
                    f"keyword match: {', '.join(keyword_matches.keys())}"
                )
            else:
                print(
                    f"[classify] Classifying {position}/{total}: {osid} — "
                    f"no keyword match, no AI fallback"
                )

        record = build_record(osid, keyword_matches, ai_result)

        # If we attempted the AI but it failed entirely (all 3 tiers
        # exhausted) AND there was no keyword match, downgrade the
        # source from 'none' to 'incomplete' so we can distinguish
        # API failures from genuinely-unclassifiable rows.
        if ai_error_reason and record["classification_source"] == "none":
            record["classification_source"] = "incomplete"
            record["non_health_category"] = f"ai_error: {ai_error_reason}"

        results[osid] = record
        new_count += 1

        # --retry-none progress: every record processed counts toward
        # the retry queue total; log the running health/non-health split
        # every CHECKPOINT_EVERY records so the user can see progress
        # at a glance.
        if osid in retry_queue:
            retry_done += 1
            if results[osid].get("health_related"):
                retry_health += 1
            else:
                retry_not_health += 1

        if new_count % CHECKPOINT_EVERY == 0:
            save_checkpoint(results, api_calls)
            print(f"[{log_prefix}]   checkpoint saved at {len(results)} records")
            if retry_total:
                print(
                    f"[ai-retry] Classified {retry_done}/{retry_total} "
                    f"({retry_health} health, {retry_not_health} not-health)"
                )

    save_checkpoint(results, api_calls)
    write_outputs(df, results)
    print_summary(results, api_calls)


def print_summary(results: dict[str, dict[str, Any]], api_calls: int) -> None:
    by_source: dict[str, int] = {}
    by_area: dict[str, int] = {a: 0 for a in DISEASE_AREA_NAMES}
    health_yes = 0
    health_no = 0
    non_health_categories: dict[str, int] = {}

    for r in results.values():
        by_source[r["classification_source"]] = by_source.get(r["classification_source"], 0) + 1
        if r.get("health_related"):
            health_yes += 1
        else:
            health_no += 1
            cat = r.get("non_health_category") or "unknown"
            non_health_categories[cat] = non_health_categories.get(cat, 0) + 1
        for area in r.get("disease_areas_list", []):
            if area in by_area:
                by_area[area] += 1

    print()
    print("=" * 60)
    print(f"[classify] SUMMARY  ({len(results)} experiments)")
    print("=" * 60)
    print(f"  Health-related     : {health_yes}")
    print(f"  Not health-related : {health_no}")
    print()
    print("  Classification source:")
    for src, n in sorted(by_source.items(), key=lambda kv: -kv[1]):
        print(f"    {src:8s} : {n}")
    print()
    print("  Experiments per disease area (multi-tag):")
    for area in DISEASE_AREA_NAMES:
        print(f"    {area:42s} : {by_area[area]}")
    if non_health_categories:
        print()
        print("  Non-health categories:")
        for cat, n in sorted(non_health_categories.items(), key=lambda kv: -kv[1]):
            print(f"    {cat:32s} : {n}")
    print()
    print(f"  Total OpenRouter API calls : {api_calls}")
    print(f"  CSV   → {CSV_OUTPUT}")
    print(f"  JSON  → {DETAILS_JSON}")


if __name__ == "__main__":
    main()
