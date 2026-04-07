"""
03_fetch_esa_jaxa_csa.py

Phase 1, step 3: pull experiment catalogs from ESA, JAXA, and CSA.

None of these agencies expose a public REST API for their experiment
databases, so this script will:
  - Use SerpAPI to search each agency's experiments domain
  - Or browser-automate the catalog pages
  - Or parse published PDF reports as a fallback

Output:
  - data/raw/esa_experiments.json
  - data/raw/jaxa_experiments.json
  - data/raw/csa_experiments.json
  - data/processed/esa_jaxa_csa_experiments.csv

Status: STUB.

See SPACE_HEALTH_SPECS.md sections 2.3, 2.4, 2.5.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import get_env, load_env  # noqa: E402


def fetch_esa() -> list[dict]:
    # TODO: Browser automation against https://eea.spaceflight.esa.int
    # The EEA returns 401 to direct API calls — needs cookies / session.
    return []


def fetch_jaxa() -> list[dict]:
    # TODO: Scrape https://humans-in-space.jaxa.jp/en/bss/experiment/
    return []


def fetch_csa() -> list[dict]:
    # TODO: Scrape https://www.asc-csa.gc.ca/eng/sciences/experiments/
    return []


def main() -> None:
    load_env()
    _ = get_env("SERPAPI_KEY")  # required once implemented

    # TODO: Call fetch_esa(), fetch_jaxa(), fetch_csa() and save outputs.
    print("Script not yet implemented. See SPACE_HEALTH_SPECS.md Sections 2.3-2.5.")


if __name__ == "__main__":
    main()
