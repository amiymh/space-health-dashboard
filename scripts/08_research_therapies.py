"""
08_research_therapies.py

Phase 3, step 3: research approved drugs and devices that trace back to
ISS / microgravity research, per SNIH disease area.

There is no single FDA API for this — the script combines:
  - SerpAPI search for known space-derived drug/device candidates
  - Claude (via OpenRouter) to extract evidence chains from the results
  - Manual curation of well-known examples (protein crystallography, salmonella
    vaccine, water purification tech, LSAH monitoring, etc.)

Output:
  - data/processed/approved_therapies.csv
  Columns: name, type (drug/device), disease_area, approval_year,
           approving_body, evidence_chain, sources

Status: STUB.

See SPACE_HEALTH_SPECS.md section 2.8 and 3.4.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import get_env, load_env  # noqa: E402


def main() -> None:
    load_env()
    _ = get_env("SERPAPI_KEY")
    _ = get_env("OPENROUTER_API_KEY")

    # TODO: Curated seed list of known space-derived therapies.
    # TODO: For each, run SerpAPI search to surface FDA / EMA references.
    # TODO: Use Claude to compose the ISS → discovery → approval evidence chain.
    # TODO: Write data/processed/approved_therapies.csv.

    print("Script not yet implemented. See SPACE_HEALTH_SPECS.md Sections 2.8 and 3.4.")


if __name__ == "__main__":
    main()
