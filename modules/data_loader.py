"""
Dashboard data loader.

Reads CSVs out of data/processed/ and exposes them to app.py with
@st.cache_data so re-renders are cheap. Returns empty DataFrames when a
particular file does not exist yet, so the dashboard renders even with a
partial pipeline run.

Status: STUB — implement once Phase 1 outputs are stable.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

PROCESSED_DIR = Path(__file__).resolve().parent.parent / "data" / "processed"


def _safe_read(name: str) -> pd.DataFrame:
    path = PROCESSED_DIR / name
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except Exception:
        return pd.DataFrame()


def load_osdr_experiments() -> pd.DataFrame:
    return _safe_read("osdr_experiments.csv")


def load_all_experiments() -> pd.DataFrame:
    return _safe_read("all_experiments.csv")


def load_classified_experiments() -> pd.DataFrame:
    return _safe_read("classified_experiments.csv")


def load_clinical_trials() -> pd.DataFrame:
    return _safe_read("clinical_trials.csv")


def load_publication_counts() -> pd.DataFrame:
    return _safe_read("publication_counts.csv")


def load_approved_therapies() -> pd.DataFrame:
    return _safe_read("approved_therapies.csv")
