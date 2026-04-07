"""
01_fetch_nasa_osdr.py

Phase 1, step 1: pull the full NASA OSDR experiment catalog.

Flow:
  1. GET https://osdr.nasa.gov/geode-py/ws/api/experiments  (list of ~928 URLs)
  2. For every experiment URL, GET the full record with 0.5s rate limiting
  3. Extract a flat record with the fields the dashboard needs
  4. Checkpoint every 50 experiments to data/checkpoints/osdr_checkpoint.json
     so an interrupted run can resume
  5. Write the final result to data/raw/osdr_experiments.json (full payload)
     and data/processed/osdr_experiments.csv (flat table)

The script is safe to re-run: it picks up where the checkpoint left off.

See SPACE_HEALTH_SPECS.md sections 2.1 and 3.2 for the spec.
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
    CHECKPOINT_DIR,
    OSDR_CHECKPOINT_EVERY,
    OSDR_EXPERIMENTS_API,
    OSDR_REQUEST_DELAY_SEC,
    PROCESSED_DIR,
    RAW_DIR,
    REQUEST_HEADERS,
    load_json,
    save_json,
)

CHECKPOINT_FILE = CHECKPOINT_DIR / "osdr_checkpoint.json"
RAW_OUTPUT = RAW_DIR / "osdr_experiments.json"
CSV_OUTPUT = PROCESSED_DIR / "osdr_experiments.csv"

CSV_COLUMNS = [
    "osID",
    "title",
    "objectives",
    "approach",
    "results",
    "sponsoringAgency",
    "researchAreas",
    "nasaPrograms",
    "factors",
    "publications_count",
    "publication_titles",
    "principal_investigator",
    "pi_institution",
    "all_people",
    "releaseDate",
    "source_url",
]


# ---------------------------------------------------------------------------
# HTTP session with retries
# ---------------------------------------------------------------------------
def make_session() -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=4,
        backoff_factor=1.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(["GET"]),
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.headers.update(REQUEST_HEADERS)
    return session


# ---------------------------------------------------------------------------
# Field extraction
# ---------------------------------------------------------------------------
def _annotation(value: Any) -> str:
    """Pull the annotationValue out of an OSDR ontology dict."""
    if isinstance(value, dict):
        return value.get("annotationValue") or value.get("name") or ""
    return str(value) if value is not None else ""


def _join_annotations(values: Any) -> str:
    if not isinstance(values, list):
        return ""
    return "; ".join(filter(None, (_annotation(v) for v in values)))


def _extract_people(people: Any) -> tuple[str, str, str]:
    """
    Return (principal_investigator, pi_institution, all_people_joined).

    OSDR person records nest as:
        {"person": {"firstName": ..., "lastName": ...},
         "institution": {"annotationValue": ...},
         "roles": [{"annotationValue": "Principal Investigator"}, ...]}
    """
    if not isinstance(people, list):
        return "", "", ""

    pi_name = ""
    pi_inst = ""
    all_names: list[str] = []

    for entry in people:
        if not isinstance(entry, dict):
            continue
        person = entry.get("person") or {}
        first = (person.get("firstName") or "").strip()
        middle = (person.get("middleName") or "").strip()
        last = (person.get("lastName") or "").strip()
        full = " ".join(part for part in (first, middle, last) if part).strip()
        if full:
            all_names.append(full)

        roles = entry.get("roles") or []
        role_names = [_annotation(r).lower() for r in roles]
        institution = _annotation(entry.get("institution"))

        if not pi_name and any("principal investigator" in r for r in role_names):
            pi_name = full
            pi_inst = institution

    # Fallback: first listed person if no explicit PI
    if not pi_name and people:
        first_entry = people[0] if isinstance(people[0], dict) else {}
        person = first_entry.get("person") or {}
        first = (person.get("firstName") or "").strip()
        last = (person.get("lastName") or "").strip()
        pi_name = f"{first} {last}".strip()
        pi_inst = _annotation(first_entry.get("institution"))

    return pi_name, pi_inst, "; ".join(all_names)


def _extract_publications(pubs: Any) -> tuple[int, str]:
    if not isinstance(pubs, list):
        return 0, ""
    titles = []
    for p in pubs:
        if isinstance(p, dict):
            title = p.get("title") or p.get("citation") or ""
            if title:
                titles.append(title.strip())
    return len(pubs), " | ".join(titles)


def parse_experiment(payload: dict[str, Any], source_url: str) -> dict[str, Any]:
    """Flatten the OSDR experiment payload into one row."""
    fields_list = payload.get("fields") or []
    record = fields_list[0] if fields_list else payload

    pi_name, pi_inst, all_people = _extract_people(record.get("people"))
    pub_count, pub_titles = _extract_publications(record.get("publications"))

    return {
        "osID": record.get("osID") or record.get("experimentID") or "",
        "title": (record.get("title") or "").strip(),
        "objectives": (record.get("objectives") or "").strip(),
        "approach": (record.get("approach") or "").strip(),
        "results": (record.get("results") or "").strip(),
        "sponsoringAgency": _annotation(record.get("sponsoringAgency")),
        "researchAreas": _join_annotations(record.get("researchAreas")),
        "nasaPrograms": _join_annotations(record.get("nasaPrograms")),
        "factors": _join_annotations(record.get("factors")),
        "publications_count": pub_count,
        "publication_titles": pub_titles,
        "principal_investigator": pi_name,
        "pi_institution": pi_inst,
        "all_people": all_people,
        "releaseDate": (record.get("releaseDate") or "").strip(),
        "source_url": source_url,
    }


# ---------------------------------------------------------------------------
# Catalog discovery
# ---------------------------------------------------------------------------
def fetch_experiment_urls(session: requests.Session) -> list[str]:
    print(f"[osdr] GET {OSDR_EXPERIMENTS_API}")
    resp = session.get(OSDR_EXPERIMENTS_API, timeout=60)
    resp.raise_for_status()
    payload = resp.json()

    items = payload.get("data") if isinstance(payload, dict) else payload
    if not isinstance(items, list):
        raise RuntimeError(f"Unexpected experiments API shape: {type(payload).__name__}")

    urls: list[str] = []
    for item in items:
        if isinstance(item, dict) and item.get("experiment"):
            urls.append(item["experiment"])
        elif isinstance(item, str):
            urls.append(item)
    return urls


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def write_csv(rows: list[dict[str, Any]]) -> None:
    with CSV_OUTPUT.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def main() -> None:
    session = make_session()

    # Resume from checkpoint if present
    checkpoint = load_json(CHECKPOINT_FILE, default={}) or {}
    raw_records: list[dict[str, Any]] = checkpoint.get("raw", [])
    flat_records: list[dict[str, Any]] = checkpoint.get("flat", [])
    failed: list[dict[str, str]] = checkpoint.get("failed", [])
    done_ids = {r.get("osID") for r in flat_records if r.get("osID")}

    if flat_records:
        print(f"[osdr] Resuming — {len(flat_records)} experiments already fetched")

    urls = fetch_experiment_urls(session)
    total = len(urls)
    print(f"[osdr] Catalog contains {total} experiments")

    for idx, url in enumerate(urls, start=1):
        osid = url.rstrip("/").rsplit("/", 1)[-1]
        if osid in done_ids:
            continue

        try:
            resp = session.get(url, timeout=60)
            resp.raise_for_status()
            payload = resp.json()
        except Exception as exc:
            print(f"[osdr]   FAIL {idx}/{total} {osid}: {exc}")
            failed.append({"osID": osid, "url": url, "error": str(exc)})
            time.sleep(OSDR_REQUEST_DELAY_SEC)
            continue

        flat = parse_experiment(payload, source_url=url)
        # Use the URL-derived id if the payload doesn't carry one
        if not flat.get("osID"):
            flat["osID"] = osid

        title_preview = (flat["title"] or "<no title>")[:70]
        print(f"[osdr] Fetching experiment {idx}/{total}: {flat['osID']} — {title_preview}")

        raw_records.append({"source_url": url, "payload": payload})
        flat_records.append(flat)
        done_ids.add(flat["osID"])

        if len(flat_records) % OSDR_CHECKPOINT_EVERY == 0:
            save_json(CHECKPOINT_FILE, {
                "raw": raw_records,
                "flat": flat_records,
                "failed": failed,
            })
            print(f"[osdr]   checkpoint saved at {len(flat_records)} records")

        time.sleep(OSDR_REQUEST_DELAY_SEC)

    # Final outputs
    save_json(RAW_OUTPUT, raw_records)
    write_csv(flat_records)
    save_json(CHECKPOINT_FILE, {
        "raw": raw_records,
        "flat": flat_records,
        "failed": failed,
    })

    print()
    print(f"[osdr] Done. {len(flat_records)} experiments saved.")
    print(f"[osdr]   raw  → {RAW_OUTPUT}")
    print(f"[osdr]   csv  → {CSV_OUTPUT}")
    if failed:
        print(f"[osdr]   {len(failed)} experiments failed (see checkpoint)")


if __name__ == "__main__":
    main()
