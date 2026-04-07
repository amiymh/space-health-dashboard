"""
04_deduplicate_merge.py

Phase 1, step 4: merge all collected experiment sources into a single
deduplicated master CSV.

Inputs:
  - data/processed/osdr_experiments.csv          (script 01)
  - data/processed/research_explorer.csv         (script 02)
  - data/processed/esa_jaxa_csa_experiments.csv  (script 03)

Output:
  - data/processed/all_experiments.csv

Schema (per SPACE_HEALTH_SPECS.md section 3.2):
  experiment_id, title, description, agency, mission, year, organism,
  tissue, PI, institution, publications_count, source_url, raw_source

Dedup strategy: match on normalized title + PI + year. When duplicates are
found, keep the record with the richest metadata (longest description,
most fields populated).

Status: STUB.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


def main() -> None:
    # Will use scripts.config.PROCESSED_DIR once implemented.
    # TODO: Load each per-source CSV with pandas.
    # TODO: Normalize column names into the unified schema.
    # TODO: Deduplicate on (title, PI, year). Prefer richest record.
    # TODO: Write data/processed/all_experiments.csv.
    print("Script not yet implemented. See SPACE_HEALTH_SPECS.md Section 3.2.")


if __name__ == "__main__":
    main()
