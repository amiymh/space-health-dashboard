"""
02_fetch_research_explorer.py

Phase 1, step 2: pull the broader NASA Space Station Research Explorer
catalog (4,000+ investigations including non-omics work that is missing from
OSDR).

The Research Explorer has no public API, so this script will use SerpAPI to
search for `site:nasa.gov/mission/station/research-explorer` against the
SNIH disease keywords (and a generic catalog crawl), then scrape the
resulting investigation pages.

Output:
  - data/raw/research_explorer.json
  - data/processed/research_explorer.csv

Status: STUB.

See SPACE_HEALTH_SPECS.md section 2.2 / 3.2.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import get_env, load_env  # noqa: E402


def main() -> None:
    load_env()
    _ = get_env("SERPAPI_KEY")  # required once implemented

    # TODO: For each disease area, run a SerpAPI search:
    #   site:nasa.gov/mission/station/research-explorer "{keyword}"
    # TODO: Collect investigation URLs, deduplicate.
    # TODO: For each URL, fetch the page and extract title, summary, PI,
    #       sponsoring agency, mission, and any linked publications.
    # TODO: Save raw JSON to data/raw/research_explorer.json.
    # TODO: Flatten to data/processed/research_explorer.csv.

    print("Script not yet implemented. See SPACE_HEALTH_SPECS.md Section 2.2 and 3.2.")


if __name__ == "__main__":
    main()
