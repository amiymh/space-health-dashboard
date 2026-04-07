"""
Dashboard data loader.

Reads CSVs out of data/processed/ and exposes them to app.py with
@st.cache_data so re-renders are cheap. Returns empty DataFrames when a
particular file does not exist yet, so the dashboard renders even with a
partial pipeline run.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
CONFIG_DIR = PROJECT_ROOT / "config"


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
    """Primary classification: NLP/MeSH (spec 03). Falls back to AI if missing."""
    nlp = _safe_read("classified_experiments_nlp.csv")
    if not nlp.empty:
        return nlp
    return _safe_read("classified_experiments.csv")


def load_classified_experiments_nlp() -> pd.DataFrame:
    """Deterministic NLP classification (scispacy/pubtator/metamaplite)."""
    return _safe_read("classified_experiments_nlp.csv")


def load_classified_experiments_ai() -> pd.DataFrame:
    """Legacy AI classification (Claude via OpenRouter). Comparison layer only."""
    return _safe_read("classified_experiments.csv")


def load_classification_comparison() -> pd.DataFrame:
    return _safe_read("classification_comparison.csv")


def load_classification_config() -> dict:
    """
    Return the NLP classifier configuration (config/classification_config.json).
    Empty dict if the file is missing.
    """
    path = CONFIG_DIR / "classification_config.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def load_clinical_trials() -> pd.DataFrame:
    return _safe_read("clinical_trials.csv")


def load_trial_experiment_links() -> pd.DataFrame:
    """Trial <-> experiment linkage produced by Spec 04 (script 12)."""
    return _safe_read("trial_experiment_links.csv")


def load_trial_linkage_summary() -> dict:
    """Summary JSON produced alongside trial_experiment_links.csv."""
    path = PROCESSED_DIR / "trial_linkage_summary.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def load_publication_counts() -> pd.DataFrame:
    return _safe_read("publication_counts.csv")


def load_approved_therapies() -> pd.DataFrame:
    return _safe_read("approved_therapies.csv")
