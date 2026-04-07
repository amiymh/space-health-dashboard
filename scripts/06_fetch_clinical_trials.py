"""
06_fetch_clinical_trials.py

Phase 3, step 1: pull space-related clinical trials from ClinicalTrials.gov v2
for each of the 10 SNIH disease areas.

For every disease area we issue one query that combines:
  - the space keywords  (microgravity OR spaceflight OR ...)
  - the disease keywords  (heart OR cardiac OR ...)

We page through the v2 API until exhausted, dedupe by NCT ID across disease
areas, and write:
  - data/raw/clinical_trials.json   — raw API responses
  - data/processed/clinical_trials.csv  — flat table for the dashboard

See SPACE_HEALTH_SPECS.md section 2.6.
"""

from __future__ import annotations

import csv
import sys
import time
from pathlib import Path
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import (  # noqa: E402
    CLINICAL_TRIALS_API,
    CLINICAL_TRIALS_DELAY_SEC,
    DISEASE_AREAS,
    PROCESSED_DIR,
    RAW_DIR,
    REQUEST_HEADERS,
    SPACE_KEYWORDS,
    all_keywords,
    save_json,
)

RAW_OUTPUT = RAW_DIR / "clinical_trials.json"
CSV_OUTPUT = PROCESSED_DIR / "clinical_trials.csv"

CSV_COLUMNS = [
    "nct_id",
    "title",
    "status",
    "phase",
    "conditions",
    "interventions",
    "lead_sponsor",
    "start_date",
    "disease_areas",
    "url",
]

PAGE_SIZE = 100
MAX_PAGES_PER_QUERY = 20  # safety stop


def make_session() -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=4,
        backoff_factor=1.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(["GET"]),
    )
    session.mount("https://", HTTPAdapter(max_retries=retry))
    session.headers.update(REQUEST_HEADERS)
    return session


def build_query(disease_keywords: list[str]) -> str:
    """
    Combine space + disease terms with boolean operators.

    Multi-word phrases are wrapped in quotes so the API treats them as one
    token.
    """
    def quote(term: str) -> str:
        return f'"{term}"' if " " in term else term

    space_clause = " OR ".join(quote(t) for t in SPACE_KEYWORDS)
    disease_clause = " OR ".join(quote(t) for t in disease_keywords)
    return f"({space_clause}) AND ({disease_clause})"


def fetch_trials_for_query(session: requests.Session, query: str) -> list[dict[str, Any]]:
    studies: list[dict[str, Any]] = []
    page_token: str | None = None

    for page in range(MAX_PAGES_PER_QUERY):
        params: dict[str, Any] = {
            "query.term": query,
            "pageSize": PAGE_SIZE,
            "format": "json",
        }
        if page_token:
            params["pageToken"] = page_token

        try:
            resp = session.get(CLINICAL_TRIALS_API, params=params, timeout=60)
            resp.raise_for_status()
            payload = resp.json()
        except Exception as exc:
            print(f"[trials]   page {page + 1} failed: {exc}")
            break

        batch = payload.get("studies") or []
        studies.extend(batch)

        page_token = payload.get("nextPageToken")
        if not page_token or not batch:
            break

        time.sleep(CLINICAL_TRIALS_DELAY_SEC)

    return studies


def parse_study(study: dict[str, Any]) -> dict[str, Any]:
    proto = study.get("protocolSection") or {}
    ident = proto.get("identificationModule") or {}
    status = proto.get("statusModule") or {}
    design = proto.get("designModule") or {}
    cond = proto.get("conditionsModule") or {}
    arms = proto.get("armsInterventionsModule") or {}
    sponsor = proto.get("sponsorCollaboratorsModule") or {}

    nct_id = ident.get("nctId", "")
    title = (
        ident.get("officialTitle")
        or ident.get("briefTitle")
        or ""
    ).strip()

    phases = design.get("phases") or []
    interventions = [
        (i or {}).get("name", "")
        for i in (arms.get("interventions") or [])
        if (i or {}).get("name")
    ]

    return {
        "nct_id": nct_id,
        "title": title,
        "status": status.get("overallStatus", ""),
        "phase": ", ".join(phases),
        "conditions": "; ".join(cond.get("conditions") or []),
        "interventions": "; ".join(interventions),
        "lead_sponsor": ((sponsor.get("leadSponsor") or {}).get("name") or ""),
        "start_date": ((status.get("startDateStruct") or {}).get("date") or ""),
        "url": f"https://clinicaltrials.gov/study/{nct_id}" if nct_id else "",
    }


def main() -> None:
    session = make_session()

    raw_by_area: dict[str, list[dict[str, Any]]] = {}
    by_nct: dict[str, dict[str, Any]] = {}
    counts_by_area: dict[str, int] = {}

    for area in DISEASE_AREAS:
        keywords = all_keywords(area)
        query = build_query(keywords)
        print(f"[trials] {area}")
        print(f"[trials]   query: {query[:120]}{'...' if len(query) > 120 else ''}")

        studies = fetch_trials_for_query(session, query)
        raw_by_area[area] = studies
        counts_by_area[area] = len(studies)
        print(f"[trials]   {len(studies)} trials")

        for study in studies:
            row = parse_study(study)
            nct = row["nct_id"]
            if not nct:
                continue
            if nct not in by_nct:
                row["disease_areas"] = area
                by_nct[nct] = row
            else:
                existing = by_nct[nct]["disease_areas"].split("; ")
                if area not in existing:
                    existing.append(area)
                    by_nct[nct]["disease_areas"] = "; ".join(existing)

        time.sleep(CLINICAL_TRIALS_DELAY_SEC)

    save_json(RAW_OUTPUT, raw_by_area)

    rows = list(by_nct.values())
    with CSV_OUTPUT.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    print()
    print(f"[trials] {len(rows)} unique trials across all disease areas")
    print(f"[trials]   raw → {RAW_OUTPUT}")
    print(f"[trials]   csv → {CSV_OUTPUT}")
    print()
    print("[trials] Per-area counts (with overlap):")
    for area, n in counts_by_area.items():
        print(f"  {area:42s} {n}")


if __name__ == "__main__":
    main()
