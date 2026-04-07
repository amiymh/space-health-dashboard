"""
09_generate_gap_analysis.py

Phase 4: generate per-disease-area gap analysis using Claude.

For each of the 10 SNIH disease areas, the script feeds the model:
  - the count of ISS experiments tagged to that area (script 05)
  - the count of PubMed publications (script 07)
  - the count of related clinical trials (script 06)
  - the list of known approved therapies (script 08)

The model returns a structured summary:
  - what has been done
  - what is missing
  - prioritized recommendations for SNIH-funded research

Output: data/processed/gap_analysis.json

Status: STUB.

See SPACE_HEALTH_SPECS.md section 3.5.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import get_env, load_env  # noqa: E402


def main() -> None:
    load_env()
    _ = get_env("OPENROUTER_API_KEY")
    # Will use scripts.config.DISEASE_AREAS and PROCESSED_DIR once implemented.

    # TODO: Load classified_experiments.csv, publication_counts.csv,
    #       clinical_trials.csv, approved_therapies.csv.
    # TODO: For each disease area, build a prompt with counts + summaries.
    # TODO: Call Claude via OpenRouter, parse JSON response.
    # TODO: Write data/processed/gap_analysis.json.

    print("Script not yet implemented. See SPACE_HEALTH_SPECS.md Section 3.5.")


if __name__ == "__main__":
    main()
