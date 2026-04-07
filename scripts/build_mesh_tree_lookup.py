"""
Build MeSH lookup JSON files used by the NLP classifier (script 10).

Produces two files under scripts/:

1. mesh_tree_lookup.json
   { "D010024": ["C05.116.198.579"], "D003920": ["C18.452.394.750", "C19.246"], ... }
   Maps MeSH Descriptor IDs (D-numbers) to lists of MeSH tree codes.
   Source: dhimmel/mesh tree-numbers.tsv (CC0).

2. mesh_name_to_descriptor.json
   { "osteoporosis": "D010024", "diabetes mellitus": "D003920", ... }
   Lowercased MeSH term (preferred + synonyms) -> MeSH Descriptor ID.
   Source: dhimmel/mesh descriptor-terms.tsv (CC0).

   Why this second file exists: SciSpacy's "mesh" entity linker actually
   returns UMLS CUIs (e.g. "C0029456"), not MeSH Descriptor IDs. We bridge
   CUI results back to D-numbers via canonical name + aliases, since the
   scispacy KB is built from the UMLS 2022 MeSH subset and preserves the
   MeSH preferred terms verbatim.

Safe to re-run. Writes to disk atomically via config.save_json.
"""

from __future__ import annotations

import csv
import io
import sys
from collections import defaultdict
from pathlib import Path

import requests

# Allow running as a script from anywhere
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import config  # noqa: E402


DHIMMEL_BASE = "https://raw.githubusercontent.com/dhimmel/mesh/master/data"
TREE_URL = f"{DHIMMEL_BASE}/tree-numbers.tsv"
DESCRIPTOR_TERMS_URL = f"{DHIMMEL_BASE}/descriptor-terms.tsv"

OUT_TREE_LOOKUP = HERE / "mesh_tree_lookup.json"
OUT_NAME_LOOKUP = HERE / "mesh_name_to_descriptor.json"


def fetch_text(url: str) -> str:
    print(f"  GET {url}")
    r = requests.get(url, timeout=120, headers=config.REQUEST_HEADERS)
    r.raise_for_status()
    return r.text


def build_tree_lookup(tsv_text: str) -> dict[str, list[str]]:
    """Parse tree-numbers.tsv -> {descriptor_id: [tree_numbers]}."""
    lookup: dict[str, list[str]] = defaultdict(list)
    reader = csv.DictReader(io.StringIO(tsv_text), delimiter="\t")
    for row in reader:
        mid = row["mesh_id"].strip()
        tn = row["mesh_tree_number"].strip()
        if not mid or not tn:
            continue
        if tn not in lookup[mid]:
            lookup[mid].append(tn)
    return dict(lookup)


def build_name_lookup(tsv_text: str) -> dict[str, str]:
    """
    Parse descriptor-terms.tsv -> {lowercased_name: descriptor_id}.

    Prefers the RecordPreferredTerm, then ConceptPreferredTerm, then any
    other term. If two descriptors share a term name, the first seen wins
    (we don't try to disambiguate — that's the NER's job).
    """
    lookup: dict[str, str] = {}
    reader = csv.DictReader(io.StringIO(tsv_text), delimiter="\t")
    # Sort preference: record-preferred first, then concept-preferred, then rest
    rows = list(reader)
    priority = {("Y", "Y"): 0, ("N", "Y"): 1}

    def key(row: dict) -> int:
        return priority.get(
            (row.get("RecordPreferredTermYN", "N"), row.get("ConceptPreferredTermYN", "N")),
            2,
        )

    rows.sort(key=key)
    for row in rows:
        name = (row.get("TermName") or "").strip().lower()
        mid = (row.get("DescriptorUI") or "").strip()
        if not name or not mid:
            continue
        lookup.setdefault(name, mid)
    return lookup


def main() -> None:
    print("Downloading dhimmel/mesh lookup tables...")
    tree_text = fetch_text(TREE_URL)
    terms_text = fetch_text(DESCRIPTOR_TERMS_URL)

    print("Parsing tree-numbers.tsv...")
    tree_lookup = build_tree_lookup(tree_text)
    print(f"  descriptors with tree codes: {len(tree_lookup):,}")
    total_codes = sum(len(v) for v in tree_lookup.values())
    print(f"  total tree codes: {total_codes:,}")

    print("Parsing descriptor-terms.tsv...")
    name_lookup = build_name_lookup(terms_text)
    print(f"  unique term names -> descriptors: {len(name_lookup):,}")

    config.save_json(OUT_TREE_LOOKUP, tree_lookup)
    config.save_json(OUT_NAME_LOOKUP, name_lookup)
    print(f"Wrote {OUT_TREE_LOOKUP.relative_to(config.PROJECT_ROOT)}")
    print(f"Wrote {OUT_NAME_LOOKUP.relative_to(config.PROJECT_ROOT)}")

    # Quick sanity: a few well-known diseases should resolve.
    print()
    print("Sanity check:")
    for name in ["osteoporosis", "diabetes mellitus", "hypertension", "breast neoplasms"]:
        did = name_lookup.get(name)
        codes = tree_lookup.get(did, []) if did else []
        print(f"  {name!r:28s} -> {did} {codes}")


if __name__ == "__main__":
    main()
