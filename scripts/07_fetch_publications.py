"""
07_fetch_publications.py

Phase 3, step 2: count PubMed publications that link space biology research
to each of the 10 SNIH disease areas, plus a baseline total for all space
biology publications.

Uses the NCBI E-utilities esearch endpoint, which is free and unauthenticated.

Output: data/processed/publication_counts.csv
Columns: disease_area, query, publication_count

See SPACE_HEALTH_SPECS.md section 2.7.
"""

from __future__ import annotations

import csv
import sys
import time
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import (  # noqa: E402
    DISEASE_AREAS,
    PROCESSED_DIR,
    PUBMED_DELAY_SEC,
    PUBMED_ESEARCH,
    REQUEST_HEADERS,
    SPACE_KEYWORDS,
    all_keywords,
)

CSV_OUTPUT = PROCESSED_DIR / "publication_counts.csv"


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


def quote(term: str) -> str:
    return f'"{term}"' if " " in term else term


def build_space_clause() -> str:
    return " OR ".join(quote(t) for t in SPACE_KEYWORDS)


def build_disease_clause(area: str) -> str:
    return " OR ".join(quote(t) for t in all_keywords(area))


def pubmed_count(session: requests.Session, term: str) -> int:
    params = {
        "db": "pubmed",
        "term": term,
        "rettype": "count",
        "retmode": "json",
    }
    resp = session.get(PUBMED_ESEARCH, params=params, timeout=60)
    resp.raise_for_status()
    payload = resp.json()
    return int(payload.get("esearchresult", {}).get("count", 0))


def main() -> None:
    session = make_session()

    space_clause = build_space_clause()

    rows: list[dict[str, object]] = []

    # Baseline: all space biology publications
    baseline_query = f"({space_clause})"
    print("[pubmed] baseline space biology")
    baseline = pubmed_count(session, baseline_query)
    print(f"[pubmed]   {baseline} total")
    rows.append({
        "disease_area": "ALL space biology (baseline)",
        "query": baseline_query,
        "publication_count": baseline,
    })
    time.sleep(PUBMED_DELAY_SEC)

    for area in DISEASE_AREAS:
        disease_clause = build_disease_clause(area)
        query = f"({space_clause}) AND ({disease_clause})"
        print(f"[pubmed] {area}")
        try:
            count = pubmed_count(session, query)
        except Exception as exc:
            print(f"[pubmed]   query failed: {exc}")
            count = -1
        print(f"[pubmed]   {count} publications")
        rows.append({
            "disease_area": area,
            "query": query,
            "publication_count": count,
        })
        time.sleep(PUBMED_DELAY_SEC)

    with CSV_OUTPUT.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(
            fh, fieldnames=["disease_area", "query", "publication_count"]
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    print()
    print(f"[pubmed] Done → {CSV_OUTPUT}")


if __name__ == "__main__":
    main()
