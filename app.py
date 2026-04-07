"""
Space-Health Dashboard — Streamlit entry point.

Eight tabs per SPACE_HEALTH_SPECS.md section 4.2. This file ships as a
working scaffold: each tab loads whatever processed CSVs exist and shows
either the data or a "run script XX first" hint.

Run: streamlit run app.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from config import DISEASE_AREA_NAMES  # noqa: E402
from modules import data_loader  # noqa: E402

# ---------------------------------------------------------------------------
# Page setup
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Space-Health Dashboard",
    page_icon=":satellite:",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("Space-Health Dashboard")
st.caption(
    "Mapping ISS research to SNIH priority disease areas — KFCRIS · "
    "see SPACE_HEALTH_SPECS.md for the full specification."
)

# ---------------------------------------------------------------------------
# Load data
# ---------------------------------------------------------------------------
osdr_df = data_loader.load_osdr_experiments()
all_exp_df = data_loader.load_all_experiments()
classified_df = data_loader.load_classified_experiments()
trials_df = data_loader.load_clinical_trials()
pubs_df = data_loader.load_publication_counts()
therapies_df = data_loader.load_approved_therapies()

# Pick the most-complete experiment table available
experiments_df = (
    classified_df if not classified_df.empty
    else all_exp_df if not all_exp_df.empty
    else osdr_df
)

# ---------------------------------------------------------------------------
# Sidebar filters
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("Filters")
    selected_diseases = st.multiselect(
        "Disease area",
        options=DISEASE_AREA_NAMES,
        default=[],
        help="Filter experiments tagged with one or more SNIH disease areas. "
             "Empty = show all.",
    )
    st.divider()
    st.caption("Pipeline status")
    st.write(f"OSDR experiments: **{len(osdr_df)}**")
    st.write(f"Merged experiments: **{len(all_exp_df)}**")
    st.write(f"Classified: **{len(classified_df)}**")
    st.write(f"Clinical trials: **{len(trials_df)}**")
    st.write(f"Publication counts: **{len(pubs_df)}**")
    st.write(f"Therapies: **{len(therapies_df)}**")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def empty_state(message: str, script: str) -> None:
    st.info(f"{message}\n\nRun `python scripts/{script}` first.")


# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------
TAB_LABELS = [
    "Overview",
    "Experiment Explorer",
    "Translational Pipeline",
    "Clinical Trials",
    "Approved Therapies",
    "Gap Analysis",
    "Disease Deep-Dive",
    "Sources & Methods",
]
tabs = st.tabs(TAB_LABELS)

# --- Tab 1: Overview -------------------------------------------------------
with tabs[0]:
    st.subheader("Overview")
    if experiments_df.empty:
        empty_state(
            "No experiment data yet.",
            "01_fetch_nasa_osdr.py",
        )
    else:
        col1, col2, col3 = st.columns(3)
        col1.metric("Total experiments", f"{len(experiments_df):,}")
        col2.metric("Disease areas", len(DISEASE_AREA_NAMES))
        col3.metric(
            "Agencies",
            experiments_df.get(
                "sponsoringAgency", pd.Series(dtype=str)
            ).nunique() if "sponsoringAgency" in experiments_df else "—",
        )
        st.write("Sample experiments:")
        st.dataframe(experiments_df.head(20), width="stretch")
        st.caption("Donut / bar / timeline / treemap charts will land here once Phase 2 classification is in.")

# --- Tab 2: Experiment Explorer -------------------------------------------
with tabs[1]:
    st.subheader("Experiment Explorer")
    if experiments_df.empty:
        empty_state("No experiment data yet.", "01_fetch_nasa_osdr.py")
    else:
        st.dataframe(experiments_df, width="stretch", height=600)
        st.download_button(
            "Download CSV",
            data=experiments_df.to_csv(index=False).encode("utf-8"),
            file_name="experiments.csv",
            mime="text/csv",
        )

# --- Tab 3: Translational Pipeline ----------------------------------------
with tabs[2]:
    st.subheader("Translational Pipeline")
    st.caption("ISS Experiments → Publications → Clinical Trials → Approved Therapies")
    if pubs_df.empty or trials_df.empty:
        empty_state(
            "Need publication counts and trials.",
            "06_fetch_clinical_trials.py and scripts/07_fetch_publications.py",
        )
    else:
        st.write("Publications per disease area")
        st.dataframe(pubs_df, width="stretch")
        st.write("Clinical trials per disease area (after dedup)")
        if "disease_areas" in trials_df:
            counts = (
                trials_df["disease_areas"]
                .str.split("; ")
                .explode()
                .value_counts()
                .rename_axis("disease_area")
                .reset_index(name="trial_count")
            )
            st.dataframe(counts, width="stretch")

# --- Tab 4: Clinical Trials -----------------------------------------------
with tabs[3]:
    st.subheader("Clinical Trials")
    if trials_df.empty:
        empty_state("No trials data yet.", "06_fetch_clinical_trials.py")
    else:
        st.dataframe(trials_df, width="stretch", height=600)
        st.caption(f"{len(trials_df)} unique trials.")

# --- Tab 5: Approved Therapies & Devices ----------------------------------
with tabs[4]:
    st.subheader("Approved Therapies & Devices")
    if therapies_df.empty:
        empty_state(
            "No therapies data yet.",
            "08_research_therapies.py",
        )
    else:
        st.dataframe(therapies_df, width="stretch")

# --- Tab 6: Gap Analysis --------------------------------------------------
with tabs[5]:
    st.subheader("Gap Analysis")
    gap_path = PROJECT_ROOT / "data" / "processed" / "gap_analysis.json"
    if not gap_path.exists():
        empty_state(
            "No gap analysis yet.",
            "09_generate_gap_analysis.py",
        )
    else:
        import json

        st.json(json.loads(gap_path.read_text()))

# --- Tab 7: Disease Deep-Dive ---------------------------------------------
with tabs[6]:
    st.subheader("Disease Deep-Dive")
    pick = st.selectbox("Select a disease area", DISEASE_AREA_NAMES)
    st.caption(
        "Per-disease narrative, key experiments, key publications, "
        "trials, therapies, and recommendations will render here once "
        "Phase 4 (script 09) has run."
    )
    if not classified_df.empty and "disease_areas" in classified_df:
        match = classified_df[
            classified_df["disease_areas"].fillna("").str.contains(pick, case=False)
        ]
        st.write(f"{len(match)} experiments classified to **{pick}**")
        st.dataframe(match.head(50), width="stretch")

# --- Tab 8: Sources & Methods ---------------------------------------------
with tabs[7]:
    st.subheader("Sources & Methods")
    st.markdown(
        """
        | Source | URL |
        |---|---|
        | NASA OSDR | https://osdr.nasa.gov |
        | NASA Research Explorer | https://www.nasa.gov/mission/station/research-explorer/ |
        | ESA Erasmus Experiment Archive | https://eea.spaceflight.esa.int |
        | JAXA Space Experiment Database | https://humans-in-space.jaxa.jp/en/bss/experiment/ |
        | CSA Experiments | https://www.asc-csa.gc.ca/eng/sciences/experiments/ |
        | ClinicalTrials.gov | https://clinicaltrials.gov/api/v2/studies |
        | PubMed E-utilities | https://eutils.ncbi.nlm.nih.gov/entrez/eutils/ |
        """
    )
    st.caption(
        "Classification methodology: Claude (via OpenRouter) labels each "
        "experiment against the 10 SNIH disease areas with relevance, "
        "confidence, and reasoning. See SPACE_HEALTH_SPECS.md section 3.3."
    )

# Apply disease filter if any (best-effort across whichever tab uses it)
if selected_diseases and not experiments_df.empty:
    if "disease_areas" in experiments_df:
        experiments_df = experiments_df[
            experiments_df["disease_areas"]
            .fillna("")
            .apply(lambda s: any(d in s for d in selected_diseases))
        ]
