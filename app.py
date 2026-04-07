"""
Space-Health Dashboard — Streamlit entry point.

Eight tabs per SPACE_HEALTH_SPECS.md section 4.2.

Run: streamlit run app.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
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
    "Mapping ISS research to SNIH priority disease areas — "
    "see SPACE_HEALTH_SPECS.md for methodology."
)


# ---------------------------------------------------------------------------
# Data loading + normalisation
# ---------------------------------------------------------------------------
def _normalise_classified(classified: pd.DataFrame) -> pd.DataFrame:
    if classified.empty:
        return classified
    classified = classified.copy()
    # CSV stores booleans as the strings "True"/"False"
    classified["health_related"] = (
        classified["health_related"]
        .astype(str)
        .str.lower()
        .map({"true": True, "false": False})
        .fillna(False)
    )
    for col in ("disease_areas", "primary_disease_area", "non_health_category"):
        if col in classified.columns:
            classified[col] = classified[col].fillna("")
    return classified


@st.cache_data(show_spinner=False)
def load_all() -> dict[str, pd.DataFrame]:
    nlp = _normalise_classified(data_loader.load_classified_experiments_nlp())
    ai = _normalise_classified(data_loader.load_classified_experiments_ai())
    trials = data_loader.load_clinical_trials()
    pubs = data_loader.load_publication_counts()
    therapies = data_loader.load_approved_therapies()
    links = data_loader.load_trial_experiment_links()
    tiered = data_loader.load_tiered_classification()
    if not tiered.empty:
        tiered["health_related"] = (
            tiered["health_related"].astype(str).str.lower().map({"true": True, "false": False}).fillna(False)
        )
        tiered["nlp_classified"] = (
            tiered["nlp_classified"].astype(str).str.lower().map({"true": True, "false": False}).fillna(False)
        )
        tiered["ai_classified"] = (
            tiered["ai_classified"].astype(str).str.lower().map({"true": True, "false": False}).fillna(False)
        )
        for col in ("disease_areas", "primary_disease_area", "nlp_mesh_evidence", "classification_source"):
            if col in tiered.columns:
                tiered[col] = tiered[col].fillna("")

    return {
        "classified_nlp": nlp,
        "classified_ai": ai,
        "trials": trials,
        "pubs": pubs,
        "therapies": therapies,
        "links": links,
        "tiered": tiered,
    }


@st.cache_data(show_spinner=False)
def load_link_summary() -> dict:
    return data_loader.load_trial_linkage_summary()


@st.cache_data(show_spinner=False)
def load_tiered_summary() -> dict:
    return data_loader.load_tiered_classification_summary()


@st.cache_data(show_spinner=False)
def load_class_config() -> dict:
    return data_loader.load_classification_config()


data = load_all()
classified_nlp_df: pd.DataFrame = data["classified_nlp"]
classified_ai_df: pd.DataFrame = data["classified_ai"]
trials_df: pd.DataFrame = data["trials"]
pubs_df: pd.DataFrame = data["pubs"]
therapies_df: pd.DataFrame = data["therapies"]
links_df: pd.DataFrame = data["links"]
tiered_df: pd.DataFrame = data["tiered"]
link_summary: dict = load_link_summary()
tiered_summary: dict = load_tiered_summary()

class_config = load_class_config()
active_nlp_backend = class_config.get("backend", "scispacy")

# Friendly label per spec section 9.4
BACKEND_BADGES = {
    "scispacy": "SciSpacy en_ner_bc5cdr_md + MeSH Entity Linker",
    "pubtator": "PubTator Central API",
    "metamaplite": "NLM MetaMapLite with UMLS 2024AA",
}
active_backend_label = BACKEND_BADGES.get(active_nlp_backend, active_nlp_backend)


# Strip the baseline row for per-disease views
pubs_per_area = (
    pubs_df[pubs_df["disease_area"].isin(DISEASE_AREA_NAMES)].copy()
    if not pubs_df.empty
    else pd.DataFrame(columns=["disease_area", "publication_count"])
)
baseline_pubs = (
    int(pubs_df.loc[pubs_df["disease_area"] == "ALL space biology (baseline)",
                    "publication_count"].iloc[0])
    if not pubs_df.empty
    else 0
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def explode_disease_column(df: pd.DataFrame, col: str = "disease_areas") -> pd.DataFrame:
    """Return a long-format DataFrame: one row per (record, disease_area)."""
    if df.empty or col not in df.columns:
        return pd.DataFrame(columns=[*df.columns, col])
    out = df.copy()
    out[col] = out[col].fillna("").astype(str)
    out = out.assign(**{col: out[col].str.split("; ")}).explode(col)
    out[col] = out[col].str.strip()
    return out[out[col].astype(bool)]


def disease_count_table(df: pd.DataFrame, col: str = "disease_areas") -> pd.DataFrame:
    long = explode_disease_column(df, col=col)
    if long.empty:
        return pd.DataFrame({"disease_area": DISEASE_AREA_NAMES,
                             "count": [0] * len(DISEASE_AREA_NAMES)})
    counts = (long[col].value_counts()
              .rename_axis("disease_area")
              .reset_index(name="count"))
    # Force every disease area to appear, even at zero
    full = pd.DataFrame({"disease_area": DISEASE_AREA_NAMES})
    return full.merge(counts, on="disease_area", how="left").fillna({"count": 0})


def filter_by_diseases(df: pd.DataFrame, selected: list[str],
                       col: str = "disease_areas") -> pd.DataFrame:
    if not selected or df.empty or col not in df.columns:
        return df
    pattern = "|".join(map(pd.io.common.re.escape, selected))  # type: ignore
    return df[df[col].fillna("").str.contains(pattern, regex=True)]


def empty_state(message: str, script: str) -> None:
    st.info(f"{message}\n\nRun `python scripts/{script}` first.")


# ---------------------------------------------------------------------------
# Sidebar filters
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("Classification")
    method_options = ["NLP / MeSH (default)", "AI Extended"]
    if classified_nlp_df.empty:
        # NLP file missing — fall back to AI so the dashboard still renders
        method_options = ["AI Extended"]
    method = st.radio(
        "Method",
        options=method_options,
        index=0,
        help=(
            "NLP/MeSH is the primary method — fully deterministic, uses "
            "biomedical named-entity recognition to find disease terms and "
            "maps them to SNIH areas via MeSH codes. AI Extended uses "
            "Claude (an AI model) which infers disease relevance from "
            "context. AI catches more experiments but is less precise."
        ),
    )
    use_nlp = method.startswith("NLP")
    if use_nlp:
        st.caption(f"Classified by: **{active_backend_label}**")
    else:
        st.caption("Classified by: **Claude Sonnet 4.5** (OpenRouter, temperature=0)")

    st.divider()
    st.header("Filters")
    selected_diseases: list[str] = st.multiselect(
        "Disease area",
        options=DISEASE_AREA_NAMES,
        default=[],
        help=(
            "Select one or more SNIH disease areas to filter all tabs. "
            "Leave empty to see all areas."
        ),
    )
    show_only_health = st.checkbox(
        "Health-related experiments only",
        value=True,
        help=(
            "When enabled, hides experiments classified as not "
            "health-related (plant biology, materials science, fluid "
            "physics, etc.). Turn off to see the full dataset."
        ),
    )
    st.divider()
    st.caption("Pipeline status")
    active_count = len(classified_nlp_df if use_nlp else classified_ai_df)
    st.markdown(
        f"Classified experiments: **{active_count}**",
        help=(
            "Total number of ISS experiments that have been processed "
            "through the classification pipeline."
        ),
    )
    st.markdown(
        f"Clinical trials: **{len(trials_df)}**",
        help=(
            "Space-related clinical trials fetched from ClinicalTrials.gov "
            "using space + disease keyword combinations."
        ),
    )
    st.markdown(
        f"PubMed counts: **{len(pubs_df)}**",
        help=(
            "Number of disease areas with PubMed publication counts. "
            "These show how much published research exists for each "
            "SNIH area."
        ),
    )
    st.markdown(
        f"Therapies: **{len(therapies_df)}**",
        help=(
            "Approved drugs and medical devices that originated from or "
            "were significantly advanced by space research."
        ),
    )


# Bind the active classification dataset AFTER the sidebar has chosen.
classified_df: pd.DataFrame = classified_nlp_df if use_nlp else classified_ai_df


# Apply filters once for re-use across tabs
filtered_experiments = classified_df.copy()
if not filtered_experiments.empty:
    if show_only_health and "health_related" in filtered_experiments.columns:
        filtered_experiments = filtered_experiments[filtered_experiments["health_related"]]
    filtered_experiments = filter_by_diseases(filtered_experiments, selected_diseases)

filtered_trials = filter_by_diseases(trials_df, selected_diseases)


# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------
TAB_LABELS = [
    "Overview",
    "Experiment Explorer",
    "Translational Pipeline",
    "Clinical Trials",
    "Trial-Experiment Links",
    "Classification Comparison",
    "Approved Therapies",
    "Gap Analysis",
    "Disease Deep-Dive",
    "Sources & Methods",
    "📖 User Manual",
]
tabs = st.tabs(TAB_LABELS)


# --- Tab 1: Overview -------------------------------------------------------
with tabs[0]:
    st.subheader("Overview")
    if classified_df.empty:
        empty_state("No classified data yet.", "05_classify_experiments.py")
    else:
        total_exp = len(classified_df)
        health_yes = int(classified_df["health_related"].sum())
        total_trials = len(trials_df)

        m1, m2, m3, m4 = st.columns(4)
        m1.metric(
            "Total experiments",
            f"{total_exp:,}",
            help=(
                "All ISS experiments from NASA's Open Science Data "
                "Repository (OSDR). Each experiment is a unique research "
                "study conducted on the International Space Station."
            ),
        )
        m2.metric(
            "Health-related",
            f"{health_yes:,}",
            delta=f"{health_yes/total_exp:.0%}" if total_exp else None,
            help=(
                "Experiments where the classification method detected a "
                "disease-related term. The percentage shows health-related "
                "out of total. With NLP/MeSH this is ~11%; with AI Extended "
                "~52%. The difference is because NLP only counts literal "
                "disease mentions while AI infers from context."
            ),
        )
        m3.metric(
            "Clinical trials",
            f"{total_trials:,}",
            help=(
                "Total space-related clinical trials from ClinicalTrials.gov. "
                "These are medical studies on Earth that investigate "
                "conditions also studied in space research."
            ),
        )
        m4.metric(
            "PubMed (space biology)",
            f"{baseline_pubs:,}",
            help=(
                "Baseline count of PubMed articles matching 'space biology' "
                "— gives context for the scale of the field's published "
                "research."
            ),
        )

        # Tiered breakdown caption (spec 05 section 4.2)
        if tiered_summary:
            t1 = int(tiered_summary.get("tier_1_confirmed", 0))
            t2 = int(tiered_summary.get("tier_2_probable", 0))
            t3 = int(tiered_summary.get("tier_3_uncertain", 0))
            st.caption(
                f"**Tiered classification** (combines NLP + AI): "
                f"{t1:,} confirmed · {t2:,} probable · {t3:,} uncertain · "
                f"see the *Classification Comparison* tab for details."
            )

        st.divider()

        col_left, col_right = st.columns([3, 2])

        # Horizontal bar — experiments per disease area, descending
        with col_left:
            st.markdown("**Experiments per disease area**")
            st.caption(
                "Number of ISS experiments classified under each SNIH "
                "priority disease area. An experiment can appear in multiple "
                "areas if it covers more than one condition."
            )
            # Prefer the tiered totals (T1+T2) when available — that's the
            # spec 05 default. Tier 3 (uncertain) shown as faint annotation.
            if tiered_summary and "per_disease_area" in tiered_summary:
                area_rows = []
                for area in DISEASE_AREA_NAMES:
                    b = tiered_summary["per_disease_area"].get(area, {})
                    t1 = int(b.get("tier_1", 0))
                    t2 = int(b.get("tier_2", 0))
                    t3 = int(b.get("tier_3", 0))
                    area_rows.append(
                        {
                            "disease_area": area,
                            "Tier 1": t1,
                            "Tier 2": t2,
                            "Tier 3": t3,
                            "default_total": t1 + t2,
                            "hover": f"{t1} confirmed · {t2} probable · {t3} uncertain",
                        }
                    )
                counts_df = pd.DataFrame(area_rows).sort_values("default_total", ascending=True)
                stack_long = counts_df.melt(
                    id_vars=["disease_area", "hover"],
                    value_vars=["Tier 1", "Tier 2", "Tier 3"],
                    var_name="tier",
                    value_name="count",
                )
                fig_bar = px.bar(
                    stack_long,
                    x="count",
                    y="disease_area",
                    color="tier",
                    orientation="h",
                    color_discrete_map={
                        "Tier 1": "#16a34a",
                        "Tier 2": "#2563eb",
                        "Tier 3": "#cbd5e1",
                    },
                    custom_data=["hover"],
                )
                fig_bar.update_layout(
                    barmode="stack",
                    height=420,
                    xaxis_title="Experiments (multi-tag)",
                    yaxis_title="",
                    margin=dict(l=10, r=10, t=10, b=10),
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
                )
                fig_bar.update_traces(
                    hovertemplate="%{y}<br>%{customdata[0]}<extra></extra>",
                )
                st.plotly_chart(fig_bar, width="stretch")
                st.caption(
                    "Default counts = **Tier 1 + Tier 2** (NLP-confirmed plus "
                    "AI-confident). Tier 3 (uncertain) shown in grey for "
                    "context. Hover any bar for the full breakdown."
                )
            else:
                health_df = (
                    classified_df[classified_df["health_related"]]
                    if "health_related" in classified_df else classified_df
                )
                counts = disease_count_table(health_df).sort_values("count", ascending=True)
                fig_bar = px.bar(
                    counts,
                    x="count",
                    y="disease_area",
                    orientation="h",
                    text="count",
                    color="count",
                    color_continuous_scale="Blues",
                )
                fig_bar.update_layout(
                    height=420,
                    showlegend=False,
                    coloraxis_showscale=False,
                    xaxis_title="Experiments (multi-tag)",
                    yaxis_title="",
                    margin=dict(l=10, r=10, t=10, b=10),
                )
                fig_bar.update_traces(textposition="outside")
                st.plotly_chart(fig_bar, width="stretch")

        # Donut — health vs not health
        with col_right:
            st.markdown("**Health-related share**")
            st.caption(
                "Proportion of all 3,829 experiments that were classified "
                "as health-related vs. not. This ratio changes depending "
                "on which classification method is selected in the sidebar."
            )
            health_no = total_exp - health_yes
            fig_donut = go.Figure(
                go.Pie(
                    labels=["Health-related", "Not health-related"],
                    values=[health_yes, health_no],
                    hole=0.55,
                    marker=dict(colors=["#2563eb", "#cbd5e1"]),
                    textinfo="label+percent",
                )
            )
            fig_donut.update_layout(
                height=420,
                showlegend=False,
                margin=dict(l=10, r=10, t=10, b=10),
            )
            st.plotly_chart(fig_donut, width="stretch")

        # Top non-health categories
        non_health = classified_df[~classified_df["health_related"]]
        if not non_health.empty and "non_health_category" in non_health.columns:
            cat_counts = (
                non_health["non_health_category"]
                .replace({"": "unknown"})
                .value_counts()
                .head(10)
                .rename_axis("category")
                .reset_index(name="count")
            )
            st.markdown(f"**Top non-health categories** ({len(non_health):,} experiments)")
            st.caption(
                "Most common categories among experiments that were NOT "
                "classified as health-related. These are legitimate space "
                "research areas (plant biology, materials science) that "
                "don't map to SNIH disease areas."
            )
            fig_cat = px.bar(
                cat_counts,
                x="count",
                y="category",
                orientation="h",
                text="count",
                color="count",
                color_continuous_scale="Oranges",
            )
            fig_cat.update_layout(
                height=260,
                showlegend=False,
                coloraxis_showscale=False,
                xaxis_title="Experiments",
                yaxis_title="",
                margin=dict(l=10, r=10, t=10, b=10),
            )
            fig_cat.update_traces(textposition="outside")
            st.plotly_chart(fig_cat, width="stretch")


# --- Tab 2: Experiment Explorer -------------------------------------------
with tabs[1]:
    st.subheader("Experiment Explorer")
    if classified_df.empty:
        empty_state("No classified data yet.", "05_classify_experiments.py")
    else:
        search = st.text_input(
            "Search title or disease area",
            placeholder="bone, eye, OS-118, Alwood…",
            help=(
                "Free-text search across experiment titles, disease area "
                "tags, and OS IDs. Case-insensitive. Combine with the "
                "sidebar filters to narrow further."
            ),
        )

        view = filtered_experiments.copy()
        if search:
            mask = (
                view["title"].fillna("").str.contains(search, case=False, regex=False)
                | view["disease_areas"].fillna("").str.contains(search, case=False, regex=False)
                | view["osID"].fillna("").str.contains(search, case=False, regex=False)
            )
            view = view[mask]

        st.caption(
            f"Showing **{len(view):,}** of {len(classified_df):,} experiments. "
            "Click any column header to sort."
        )

        display_cols = [
            "osID",
            "title",
            "disease_areas",
            "primary_disease_area",
            "relevance_type",
            "health_related",
            "classification_source",
        ]
        present_cols = [c for c in display_cols if c in view.columns]
        st.dataframe(
            view[present_cols],
            width="stretch",
            height=560,
            hide_index=True,
            column_config={
                "osID": st.column_config.TextColumn(
                    "OS ID",
                    width="small",
                    help=(
                        "NASA's unique identifier for each experiment in "
                        "the Open Science Data Repository. Format: OS-XXX."
                    ),
                ),
                "title": st.column_config.TextColumn(
                    "Title",
                    width="large",
                    help=(
                        "The official title of the ISS experiment as "
                        "registered in OSDR."
                    ),
                ),
                "disease_areas": st.column_config.TextColumn(
                    "Disease areas",
                    width="medium",
                    help=(
                        "The SNIH disease area(s) this experiment maps to. "
                        "Semicolon-separated if multiple. Based on MeSH "
                        "disease codes found in the experiment text."
                    ),
                ),
                "primary_disease_area": st.column_config.TextColumn(
                    "Primary",
                    width="medium",
                    help=(
                        "The single disease area with the strongest "
                        "evidence (most MeSH term matches). Used when only "
                        "one area can be shown."
                    ),
                ),
                "relevance_type": st.column_config.TextColumn(
                    "Relevance",
                    width="small",
                    help=(
                        "How the classification was made. 'deterministic' "
                        "= NLP found MeSH evidence; 'insufficient_text' "
                        "= the experiment had too little text to classify."
                    ),
                ),
                "health_related": st.column_config.CheckboxColumn(
                    "Health?",
                    width="small",
                    help=(
                        "Whether the classification method found this "
                        "experiment relevant to any SNIH disease area. "
                        "True = at least one disease area assigned."
                    ),
                ),
                "classification_source": st.column_config.TextColumn(
                    "Source",
                    width="small",
                    help=(
                        "Which method classified this experiment. "
                        "'scispacy' = NLP/MeSH method, 'ai' = Claude AI, "
                        "'keyword' = simple keyword matching."
                    ),
                ),
            },
        )

        st.download_button(
            "Download filtered CSV",
            data=view.to_csv(index=False).encode("utf-8"),
            file_name="experiments_filtered.csv",
            mime="text/csv",
        )


# --- Tab 3: Translational Pipeline ----------------------------------------
with tabs[2]:
    st.subheader("Translational Pipeline")
    st.info(
        "**The translational pipeline shows how ISS research connects to "
        "clinical application.** For each disease area: how many ISS "
        "experiments exist, how many clinical trials are running, and what "
        "the ratio is. A high trial-to-experiment ratio suggests active "
        "translation from bench to bedside."
    )
    st.caption(
        "Each metric is normalized to its share (%) of its own total so the "
        "three series are visually comparable on the same axis."
    )

    if classified_df.empty or trials_df.empty or pubs_per_area.empty:
        empty_state(
            "Need experiments, trials, and publications.",
            "01, 06, 07 (and 05)",
        )
    else:
        exp_counts = disease_count_table(
            classified_df[classified_df["health_related"]]
        ).set_index("disease_area")["count"]
        trial_counts = disease_count_table(trials_df).set_index("disease_area")["count"]
        pub_counts = (
            pubs_per_area.set_index("disease_area")["publication_count"].astype(float)
        )

        pipeline = pd.DataFrame({
            "Experiments": exp_counts,
            "Trials": trial_counts,
            "Publications": pub_counts,
        }).fillna(0).reindex(DISEASE_AREA_NAMES)

        # Normalise each column to a percentage of its total
        normalised = pipeline.div(pipeline.sum(axis=0)).mul(100).round(1)
        norm_long = (
            normalised.reset_index()
            .melt(id_vars="disease_area", var_name="metric", value_name="share_pct")
        )

        fig_pipe = px.bar(
            norm_long,
            x="share_pct",
            y="disease_area",
            color="metric",
            orientation="h",
            barmode="group",
            color_discrete_map={
                "Experiments": "#2563eb",
                "Trials": "#16a34a",
                "Publications": "#f59e0b",
            },
            labels={"share_pct": "Share within metric (%)", "disease_area": ""},
        )
        fig_pipe.update_layout(
            height=520,
            margin=dict(l=10, r=10, t=10, b=10),
            legend_title_text="",
        )
        st.plotly_chart(fig_pipe, width="stretch")

        st.markdown("**Translation ratios**")
        st.caption(
            "Trials per experiment for each disease area. **Higher** = more "
            "clinical translation happening. **Lower** = research exists "
            "but hasn't moved to clinical trials yet."
        )
        ratio_df = pipeline.copy()
        ratio_df["trial / experiment"] = (
            ratio_df["Trials"] / ratio_df["Experiments"].replace(0, pd.NA)
        ).round(2)
        ratio_df["publications / experiment"] = (
            ratio_df["Publications"] / ratio_df["Experiments"].replace(0, pd.NA)
        ).round(1)
        ratio_df = ratio_df.reset_index().rename(columns={"index": "disease_area"})
        ratio_df["disease_area"] = pipeline.index
        st.dataframe(
            ratio_df[
                ["disease_area", "Experiments", "Trials", "Publications",
                 "trial / experiment", "publications / experiment"]
            ],
            width="stretch",
            hide_index=True,
        )


# --- Tab 4: Clinical Trials -----------------------------------------------
with tabs[3]:
    st.subheader("Clinical Trials")
    if trials_df.empty:
        empty_state("No trials data yet.", "06_fetch_clinical_trials.py")
    else:
        view_trials = filtered_trials.copy()

        c1, c2 = st.columns(2)
        with c1:
            phase_options = sorted(
                {p.strip() for s in view_trials["phase"].dropna()
                 for p in str(s).split(",") if p.strip()}
            )
            phase_pick = st.multiselect(
                "Phase",
                options=phase_options,
                help=(
                    "Filter to specific clinical trial phases. Phase 1 = "
                    "safety, Phase 2 = efficacy, Phase 3 = large-scale, "
                    "Phase 4 = post-market. Many space-related trials "
                    "have no declared phase (observational / bed rest)."
                ),
            )
        with c2:
            status_options = sorted(view_trials["status"].dropna().unique())
            status_pick = st.multiselect(
                "Status",
                options=status_options,
                help=(
                    "Filter to specific trial statuses. RECRUITING = "
                    "actively enrolling participants. COMPLETED = trial "
                    "finished. WITHDRAWN / TERMINATED = cancelled."
                ),
            )

        if phase_pick:
            view_trials = view_trials[
                view_trials["phase"].fillna("").apply(
                    lambda s: any(p in s for p in phase_pick)
                )
            ]
        if status_pick:
            view_trials = view_trials[view_trials["status"].isin(status_pick)]

        m1, m2, m3 = st.columns(3)
        m1.metric(
            "Trials shown",
            f"{len(view_trials):,}",
            help=(
                "Number of clinical trials displayed after applying any "
                "active filters."
            ),
        )
        m2.metric(
            "Phases",
            view_trials["phase"].fillna("").replace("", pd.NA).dropna().nunique(),
            help=(
                "Number of distinct trial phases in the current view. "
                "Phase 1 = safety testing, Phase 2 = efficacy, Phase 3 = "
                "large-scale, Phase 4 = post-market."
            ),
        )
        m3.metric(
            "Statuses",
            view_trials["status"].nunique(),
            help=(
                "Number of distinct trial statuses. Common statuses: "
                "RECRUITING (actively enrolling), COMPLETED, "
                "ACTIVE_NOT_RECRUITING, WITHDRAWN, TERMINATED."
            ),
        )

        col_a, col_b = st.columns(2)
        with col_a:
            st.markdown("**By status**")
            st.caption(
                "Distribution of trial statuses. *Recruiting* means "
                "actively looking for participants. *Completed* means the "
                "trial finished. *Withdrawn* means it was cancelled before "
                "enrollment."
            )
            status_counts = (
                view_trials["status"].value_counts().rename_axis("status")
                .reset_index(name="count")
            )
            fig_status = px.bar(
                status_counts, x="count", y="status", orientation="h",
                text="count", color="count", color_continuous_scale="Greens",
            )
            fig_status.update_layout(
                height=320, showlegend=False, coloraxis_showscale=False,
                xaxis_title="", yaxis_title="",
                margin=dict(l=10, r=10, t=10, b=10),
            )
            fig_status.update_traces(textposition="outside")
            st.plotly_chart(fig_status, width="stretch")

        with col_b:
            st.markdown("**By phase**")
            st.caption(
                "Trial phases indicate how far along the clinical testing "
                "process a treatment is. Phase 3 trials are the most "
                "advanced (closest to approval)."
            )
            phase_long = (
                view_trials["phase"].fillna("(unspecified)").replace("", "(unspecified)")
                .str.split(", ").explode().str.strip()
            )
            phase_counts = (
                phase_long.value_counts().rename_axis("phase").reset_index(name="count")
            )
            fig_phase = px.bar(
                phase_counts, x="count", y="phase", orientation="h",
                text="count", color="count", color_continuous_scale="Purples",
            )
            fig_phase.update_layout(
                height=320, showlegend=False, coloraxis_showscale=False,
                xaxis_title="", yaxis_title="",
                margin=dict(l=10, r=10, t=10, b=10),
            )
            fig_phase.update_traces(textposition="outside")
            st.plotly_chart(fig_phase, width="stretch")
            st.caption(
                "Note: 66% of trials show no declared phase. These are "
                "typically observational or bed rest studies exempt from "
                "FDA phase classification, not missing data."
            )

        st.markdown("**Trials**")
        st.dataframe(
            view_trials,
            width="stretch",
            height=520,
            hide_index=True,
            column_config={
                "url": st.column_config.LinkColumn("ClinicalTrials.gov"),
            },
        )


# --- Tab 5: Trial-Experiment Links (spec 04) -------------------------------
with tabs[4]:
    st.subheader("Trial-Experiment Links")
    if links_df.empty:
        empty_state(
            "No trial-experiment linkage yet.",
            "12_link_trials_experiments.py",
        )
    else:
        total_links = int(link_summary.get("total_links", len(links_df)))
        trials_linked = int(link_summary.get("trials_with_links", 0))
        exp_linked = int(link_summary.get("experiments_with_links", 0))
        total_trials_n = int(link_summary.get("total_trials", len(trials_df)))
        by_strength = link_summary.get("links_by_strength", {})

        m1, m2, m3, m4 = st.columns(4)
        m1.metric(
            "Total links",
            f"{total_links:,}",
            help=(
                "Number of connections found between clinical trials and "
                "ISS experiments. A link means both study the same medical "
                "condition (share MeSH disease codes)."
            ),
        )
        m2.metric(
            "Trials linked",
            f"{trials_linked:,}",
            delta=f"{(trials_linked/total_trials_n*100):.0f}%" if total_trials_n else None,
            help=(
                "How many of the 534 clinical trials have at least one "
                "matching ISS experiment. ~21% coverage — the rest study "
                "conditions with no ISS counterpart."
            ),
        )
        m3.metric(
            "Experiments linked",
            f"{exp_linked:,}",
            help=(
                "How many ISS experiments have at least one matching "
                "clinical trial."
            ),
        )
        m4.metric(
            "Strong links",
            f"{int(by_strength.get('strong', 0)):,}",
            help=(
                "Links where the trial and experiment share the exact same "
                "MeSH disease code AND have high text similarity. These "
                "are the most confident connections."
            ),
        )

        st.caption(
            "Deterministic linkage via SciSpacy MeSH extraction on trials + "
            "MeSH / disease-area / TF-IDF cosine overlap against the NLP-"
            "classified experiments. See Sources & Methods for thresholds."
        )

        # Filters for the table
        fcol1, fcol2, fcol3 = st.columns([2, 2, 3])
        with fcol1:
            strength_pick = st.multiselect(
                "Link strength",
                options=["strong", "moderate", "weak"],
                default=["strong", "moderate"],
                help=(
                    "Filter by confidence level. **Strong** = shared MeSH "
                    "codes + high text similarity. **Moderate** = shared "
                    "MeSH codes with moderate similarity. **Weak** = "
                    "shared disease area with low text overlap."
                ),
            )
        with fcol2:
            linked_area_pick = st.multiselect(
                "Disease area",
                options=DISEASE_AREA_NAMES,
                default=[],
                help=(
                    "Show only links involving experiments or trials in "
                    "these disease areas."
                ),
            )
        with fcol3:
            link_search = st.text_input(
                "Search trial / experiment title",
                placeholder="pain, thrombosis, NCT...",
                help=(
                    "Free-text search across trial title, experiment "
                    "title, NCT ID, or OS ID. Case-insensitive."
                ),
            )

        view_links = links_df.copy()
        if strength_pick:
            view_links = view_links[view_links["link_strength"].isin(strength_pick)]
        if linked_area_pick:
            pat = "|".join(pd.io.common.re.escape(a) for a in linked_area_pick)  # type: ignore
            view_links = view_links[
                view_links["shared_areas"].fillna("").str.contains(pat, regex=True)
            ]
        if link_search:
            s = link_search.strip()
            mask = (
                view_links["trial_title"].fillna("").str.contains(s, case=False, regex=False)
                | view_links["experiment_title"].fillna("").str.contains(s, case=False, regex=False)
                | view_links["nct_id"].fillna("").str.contains(s, case=False, regex=False)
                | view_links["osID"].fillna("").str.contains(s, case=False, regex=False)
            )
            view_links = view_links[mask]

        st.caption(f"Showing **{len(view_links):,}** of {len(links_df):,} links.")

        # Attach clickable URLs
        trial_url_map = dict(zip(trials_df["nct_id"].astype(str), trials_df.get("url", "")))
        exp_url_map = dict(
            zip(classified_df["osID"].astype(str), classified_df.get("source_url", ""))
            if "source_url" in classified_df.columns
            else []
        )
        display_links = view_links.copy()
        display_links["trial_url"] = display_links["nct_id"].map(trial_url_map).fillna("")
        display_links["experiment_url"] = display_links["osID"].map(exp_url_map).fillna("")

        st.dataframe(
            display_links[
                [
                    "link_strength",
                    "final_score",
                    "nct_id",
                    "trial_title",
                    "trial_url",
                    "osID",
                    "experiment_title",
                    "experiment_url",
                    "shared_areas",
                    "shared_mesh_ids",
                    "mesh_score",
                    "area_score",
                    "cosine_score",
                ]
            ],
            width="stretch",
            height=520,
            hide_index=True,
            column_config={
                "link_strength": st.column_config.TextColumn(
                    "Strength",
                    width="small",
                    help=(
                        "Confidence of the connection: **Strong** (high "
                        "MeSH + text overlap), **Moderate** (good MeSH "
                        "overlap), **Weak** (area match only)."
                    ),
                ),
                "final_score": st.column_config.NumberColumn(
                    "Score",
                    format="%.2f",
                    width="small",
                    help=(
                        "Combined linkage score (0-1) from MeSH overlap "
                        "(50%), disease area match (20%), and text "
                        "similarity (30%). Higher = stronger connection."
                    ),
                ),
                "nct_id": st.column_config.TextColumn(
                    "NCT ID",
                    width="small",
                    help=(
                        "ClinicalTrials.gov unique identifier. Click the "
                        "trial link to open the full record on "
                        "ClinicalTrials.gov."
                    ),
                ),
                "trial_title": st.column_config.TextColumn(
                    "Trial",
                    width="large",
                    help="Title of the clinical trial as registered on ClinicalTrials.gov.",
                ),
                "trial_url": st.column_config.LinkColumn(
                    "Trial link",
                    display_text="open",
                    help="Open the trial's full record on ClinicalTrials.gov.",
                ),
                "osID": st.column_config.TextColumn(
                    "OS ID",
                    width="small",
                    help=(
                        "NASA OSDR experiment identifier. Links to the "
                        "experiment record on osdr.nasa.gov."
                    ),
                ),
                "experiment_title": st.column_config.TextColumn(
                    "Experiment",
                    width="large",
                    help="Title of the ISS experiment as registered in OSDR.",
                ),
                "experiment_url": st.column_config.LinkColumn(
                    "Experiment link",
                    display_text="open",
                    help="Open the experiment's record on osdr.nasa.gov.",
                ),
                "shared_areas": st.column_config.TextColumn(
                    "Shared areas",
                    width="medium",
                    help=(
                        "SNIH disease areas that both the trial and "
                        "experiment belong to."
                    ),
                ),
                "shared_mesh_ids": st.column_config.TextColumn(
                    "Shared MeSH",
                    width="small",
                    help=(
                        "The specific MeSH codes that both the trial and "
                        "experiment share. These are the medical "
                        "conditions that connect them."
                    ),
                ),
                "mesh_score": st.column_config.NumberColumn(
                    "MeSH",
                    format="%.2f",
                    width="small",
                    help=(
                        "How many medical terms (MeSH codes) the trial "
                        "and experiment have in common, relative to the "
                        "total terms. 1.0 = perfect overlap."
                    ),
                ),
                "area_score": st.column_config.NumberColumn(
                    "Area",
                    format="%.2f",
                    width="small",
                    help=(
                        "Disease-area overlap score: how many of the "
                        "trial's SNIH areas are also assigned to the "
                        "experiment. 1.0 = all areas match."
                    ),
                ),
                "cosine_score": st.column_config.NumberColumn(
                    "Text",
                    format="%.2f",
                    width="small",
                    help=(
                        "Text similarity between trial and experiment "
                        "descriptions. Based on TF-IDF, a standard text "
                        "comparison method. 0.15+ is meaningful for "
                        "scientific text."
                    ),
                ),
            },
        )

        st.download_button(
            "Download filtered links CSV",
            data=view_links.to_csv(index=False).encode("utf-8"),
            file_name="trial_experiment_links_filtered.csv",
            mime="text/csv",
        )


# --- Tab 6: Classification Comparison (spec 05) ---------------------------
with tabs[5]:
    st.subheader("Classification Comparison")
    if tiered_df.empty or not tiered_summary:
        empty_state(
            "No tiered classification yet.",
            "13_build_tiered_classification.py",
        )
    else:
        # ---- Section A: Tier Overview ----
        st.markdown("### Tier overview")
        total_n = int(tiered_summary.get("total_experiments", len(tiered_df)))
        t1 = int(tiered_summary.get("tier_1_confirmed", 0))
        t2 = int(tiered_summary.get("tier_2_probable", 0))
        t3 = int(tiered_summary.get("tier_3_uncertain", 0))
        t0 = int(tiered_summary.get("tier_0_not_health", 0))
        coverage = float(tiered_summary.get("coverage_percent", 0.0))

        c1, c2, c3, c4 = st.columns(4)
        c1.metric(
            "Tier 1 — Confirmed",
            f"{t1:,}",
            delta=f"{t1/total_n*100:.1f}% of total",
            help=(
                "Experiments where BOTH the NLP method (MeSH-based) AND "
                "the AI method agree the experiment is health-related "
                "AND they agree on at least one disease area. **Highest "
                "confidence** — two independent methods confirmed the "
                "classification."
            ),
        )
        c2.metric(
            "Tier 2 — Probable",
            f"{t2:,}",
            delta=f"{t2/total_n*100:.1f}% of total",
            help=(
                "Experiments where the NLP method found no disease terms "
                "BUT the AI classified it as health-related with high "
                "confidence (≥70%). The AI inferred disease relevance "
                "from context (e.g., 'osteoblast differentiation' implies "
                "bone disease). Plausible but not evidence-backed by "
                "medical dictionary codes."
            ),
        )
        c3.metric(
            "Tier 3 — Uncertain",
            f"{t3:,}",
            delta=f"{t3/total_n*100:.1f}% of total",
            help=(
                "Experiments where the NLP method found no disease terms "
                "AND the AI classified it with low confidence (<70%). "
                "These need expert review to determine if they're truly "
                "health-related."
            ),
        )
        c4.metric(
            "Tier 0 — Not health",
            f"{t0:,}",
            delta=f"{t0/total_n*100:.1f}% of total",
            help=(
                "Experiments that neither method classified as "
                "health-related. These are likely basic science (plant "
                "biology, fluid physics, materials science) without "
                "direct disease relevance."
            ),
        )

        st.caption(
            f"**Tiered coverage:** {t1+t2+t3:,} of {total_n:,} experiments are "
            f"health-related across tiers 1-3 ({coverage:.1f}%). Tier 1 "
            f"experiments are backed by both NLP-detected MeSH evidence and "
            f"AI agreement. Tier 2 are AI-confident but lack a literal disease "
            f"term in the text. Tier 3 are AI-tagged but with low confidence — "
            f"treat with care."
        )

        # Stacked horizontal bar
        tier_dist = pd.DataFrame(
            {
                "tier": ["Tier 1 — Confirmed", "Tier 2 — Probable",
                         "Tier 3 — Uncertain", "Tier 0 — Not health"],
                "count": [t1, t2, t3, t0],
                "color": ["#16a34a", "#2563eb", "#f59e0b", "#cbd5e1"],
            }
        )
        fig_tier = px.bar(
            tier_dist,
            x="count",
            y=["Tiered classification"] * 4,
            color="tier",
            orientation="h",
            color_discrete_map={
                "Tier 1 — Confirmed": "#16a34a",
                "Tier 2 — Probable": "#2563eb",
                "Tier 3 — Uncertain": "#f59e0b",
                "Tier 0 — Not health": "#cbd5e1",
            },
            text="count",
            labels={"y": "", "count": "Experiments"},
        )
        fig_tier.update_layout(
            barmode="stack",
            height=170,
            margin=dict(l=10, r=10, t=10, b=10),
            yaxis=dict(showticklabels=False),
            legend=dict(orientation="h", yanchor="bottom", y=-0.6, x=0),
        )
        st.plotly_chart(fig_tier, width="stretch")
        st.caption(
            "Stacked bar showing how the 3,829 experiments break down by "
            "tier. Green = both methods agree (Tier 1). Blue = AI confident "
            "alone (Tier 2). Amber = AI low confidence (Tier 3). Grey = "
            "neither method tagged it (Tier 0)."
        )

        st.divider()

        # ---- Section B: Per-Disease-Area Breakdown ----
        st.markdown("### Per disease area")
        st.caption(
            "For each SNIH disease area, how many experiments fall into "
            "each tier. Useful for spotting where the two methods agree "
            "(big Tier 1 bars) vs. where AI is doing most of the work."
        )
        per_area = tiered_summary.get("per_disease_area", {})
        area_rows = []
        for area in DISEASE_AREA_NAMES:
            b = per_area.get(area, {})
            area_rows.append(
                {
                    "Disease area": area,
                    "Tier 1": int(b.get("tier_1", 0)),
                    "Tier 2": int(b.get("tier_2", 0)),
                    "Tier 3": int(b.get("tier_3", 0)),
                    "Total": int(b.get("total", 0)),
                }
            )
        per_area_df = pd.DataFrame(area_rows)

        col_tbl, col_chart = st.columns([1, 1])
        with col_tbl:
            st.dataframe(
                per_area_df,
                width="stretch",
                hide_index=True,
                height=400,
            )
        with col_chart:
            stack_long = per_area_df.melt(
                id_vars="Disease area",
                value_vars=["Tier 1", "Tier 2", "Tier 3"],
                var_name="tier",
                value_name="count",
            )
            fig_stack = px.bar(
                stack_long,
                x="count",
                y="Disease area",
                color="tier",
                orientation="h",
                color_discrete_map={
                    "Tier 1": "#16a34a",
                    "Tier 2": "#2563eb",
                    "Tier 3": "#f59e0b",
                },
                labels={"count": "Experiments", "Disease area": ""},
            )
            fig_stack.update_layout(
                barmode="stack",
                height=400,
                margin=dict(l=10, r=10, t=10, b=10),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
            )
            st.plotly_chart(fig_stack, width="stretch")

        st.divider()

        # ---- Section C: Method Comparison ----
        st.markdown("### Method comparison (NLP vs AI)")
        st.caption(
            "Side-by-side counts of how each method classifies experiments "
            "into the 10 SNIH disease areas. NLP/MeSH (green) tags fewer "
            "experiments but with traceable medical evidence; AI Extended "
            "(purple) is broader but inferred from context."
        )

        nlp_counts = disease_count_table(
            classified_nlp_df[classified_nlp_df["health_related"]]
        ).set_index("disease_area")["count"]
        ai_counts = disease_count_table(
            classified_ai_df[classified_ai_df["health_related"]]
        ).set_index("disease_area")["count"]

        method_df = pd.DataFrame(
            {
                "Disease area": DISEASE_AREA_NAMES,
                "NLP / MeSH": [int(nlp_counts.get(a, 0)) for a in DISEASE_AREA_NAMES],
                "AI Extended": [int(ai_counts.get(a, 0)) for a in DISEASE_AREA_NAMES],
            }
        )
        method_long = method_df.melt(
            id_vars="Disease area",
            var_name="method",
            value_name="count",
        )
        fig_method = px.bar(
            method_long,
            x="count",
            y="Disease area",
            color="method",
            orientation="h",
            barmode="group",
            color_discrete_map={
                "NLP / MeSH": "#16a34a",
                "AI Extended": "#7c3aed",
            },
            labels={"count": "Experiments", "Disease area": ""},
        )
        fig_method.update_layout(
            height=440,
            margin=dict(l=10, r=10, t=10, b=10),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
        )
        st.plotly_chart(fig_method, width="stretch")

        # Agreement metrics from the comparison CSV
        comparison_df = data_loader.load_classification_comparison()
        if not comparison_df.empty:
            n_cmp = len(comparison_df)
            agree_health = int(comparison_df["agree_health"].astype(str).str.lower().eq("true").sum())
            agree_exact = int(comparison_df["agree_areas"].astype(str).str.lower().eq("true").sum())
            agree_overlap = int(comparison_df["any_overlap"].astype(str).str.lower().eq("true").sum())
            disagree = int(n_cmp - agree_health)

            am1, am2, am3, am4 = st.columns(4)
            am1.metric(
                "Agree on health/not",
                f"{agree_health/n_cmp*100:.1f}%",
                delta=f"{agree_health:,} / {n_cmp:,}",
                help=(
                    "Percentage of experiments where NLP and AI give the "
                    "same yes/no answer on whether the experiment is "
                    "health-related."
                ),
            )
            am2.metric(
                "Exact disease-area match",
                f"{agree_exact/n_cmp*100:.1f}%",
                delta=f"{agree_exact:,}",
                help=(
                    "Percentage where NLP and AI assign exactly the same "
                    "set of disease areas."
                ),
            )
            am3.metric(
                "≥1 area overlap",
                f"{agree_overlap/n_cmp*100:.1f}%",
                delta=f"{agree_overlap:,}",
                help=(
                    "Percentage where NLP and AI share at least one "
                    "disease area, even if they don't match completely."
                ),
            )
            am4.metric(
                "Complete disagreement",
                f"{disagree/n_cmp*100:.1f}%",
                delta=f"{disagree:,}",
                delta_color="inverse",
                help=(
                    "Percentage where the two methods have zero overlap "
                    "— completely different conclusions."
                ),
            )

            # Scatter — area count NLP vs area count AI per experiment
            scatter_src = comparison_df.copy()
            scatter_src["nlp_n"] = scatter_src["nlp_disease_areas"].fillna("").apply(
                lambda s: 0 if not s else len([a for a in s.split("; ") if a.strip()])
            )
            scatter_src["ai_n"] = scatter_src["ai_disease_areas"].fillna("").apply(
                lambda s: 0 if not s else len([a for a in s.split("; ") if a.strip()])
            )
            agg = scatter_src.groupby(["nlp_n", "ai_n"]).size().reset_index(name="count")
            fig_scatter = px.scatter(
                agg,
                x="nlp_n",
                y="ai_n",
                size="count",
                color="count",
                color_continuous_scale="Blues",
                labels={
                    "nlp_n": "NLP disease areas (per experiment)",
                    "ai_n": "AI disease areas (per experiment)",
                    "count": "Experiments",
                },
            )
            fig_scatter.update_layout(
                height=380,
                margin=dict(l=10, r=10, t=10, b=10),
            )
            st.plotly_chart(fig_scatter, width="stretch")
            st.caption(
                "Bubble size = experiments with that combination. Points on "
                "the diagonal = methods agree on how many areas; off-diagonal "
                "= one method tagged more areas than the other."
            )

        st.divider()

        # ---- Section D: Experiment Explorer ----
        st.markdown("### Experiment explorer")
        st.caption(
            "Filterable table of all 3,829 experiments with tier "
            "assignment, AI confidence score, and the MeSH evidence trail "
            "(when available). Use this to drill into any single "
            "classification."
        )
        ex_col1, ex_col2, ex_col3 = st.columns([2, 2, 3])
        with ex_col1:
            tier_pick = st.multiselect(
                "Tier",
                options=["Tier 1 — Confirmed", "Tier 2 — Probable",
                         "Tier 3 — Uncertain", "Tier 0 — Not health"],
                default=["Tier 1 — Confirmed", "Tier 2 — Probable"],
                help=(
                    "Filter by confidence tier. Default shows Tier 1 + "
                    "Tier 2 — the experiments worth treating as "
                    "health-related for analysis."
                ),
            )
        with ex_col2:
            tier_area_pick = st.multiselect(
                "Disease area",
                options=DISEASE_AREA_NAMES,
                default=[],
                key="tier_area_pick",
                help=(
                    "Show only experiments tagged with one of these SNIH "
                    "disease areas."
                ),
            )
        with ex_col3:
            tier_search = st.text_input(
                "Search title or osID",
                placeholder="bone, OS-118, ...",
                key="tier_search",
                help="Free-text search on experiment title or OS ID.",
            )

        tier_label_to_int = {
            "Tier 1 — Confirmed": 1,
            "Tier 2 — Probable": 2,
            "Tier 3 — Uncertain": 3,
            "Tier 0 — Not health": 0,
        }
        tier_ints = {tier_label_to_int[t] for t in tier_pick} if tier_pick else set()

        view_tier = tiered_df.copy()
        if tier_ints:
            view_tier = view_tier[view_tier["tier"].isin(tier_ints)]
        if tier_area_pick:
            pat = "|".join(pd.io.common.re.escape(a) for a in tier_area_pick)  # type: ignore
            view_tier = view_tier[
                view_tier["disease_areas"].fillna("").str.contains(pat, regex=True)
            ]
        if tier_search:
            s = tier_search.strip()
            mask = (
                view_tier["title"].fillna("").str.contains(s, case=False, regex=False)
                | view_tier["osID"].fillna("").str.contains(s, case=False, regex=False)
            )
            view_tier = view_tier[mask]

        st.caption(f"Showing **{len(view_tier):,}** of {len(tiered_df):,} experiments.")
        st.dataframe(
            view_tier[
                [
                    "osID",
                    "title",
                    "tier",
                    "tier_label",
                    "disease_areas",
                    "primary_disease_area",
                    "ai_confidence",
                    "nlp_classified",
                    "ai_classified",
                    "nlp_mesh_evidence",
                    "classification_source",
                ]
            ],
            width="stretch",
            height=480,
            hide_index=True,
            column_config={
                "osID": st.column_config.TextColumn(
                    "OS ID",
                    width="small",
                    help="NASA OSDR experiment identifier (format OS-XXX).",
                ),
                "title": st.column_config.TextColumn(
                    "Title",
                    width="large",
                    help="Official title of the experiment from OSDR.",
                ),
                "tier": st.column_config.NumberColumn(
                    "Tier",
                    width="small",
                    help=(
                        "0 = not health, 1 = NLP+AI agree, 2 = AI confident, "
                        "3 = AI low confidence."
                    ),
                ),
                "tier_label": st.column_config.TextColumn(
                    "Tier label",
                    width="medium",
                    help="Human-readable name for the tier.",
                ),
                "disease_areas": st.column_config.TextColumn(
                    "Disease areas",
                    width="medium",
                    help=(
                        "SNIH disease areas assigned. For Tier 1, taken "
                        "from NLP (more precise). For Tier 2/3, from AI."
                    ),
                ),
                "primary_disease_area": st.column_config.TextColumn(
                    "Primary",
                    width="medium",
                    help="Single disease area with the strongest evidence.",
                ),
                "ai_confidence": st.column_config.NumberColumn(
                    "AI conf",
                    format="%.2f",
                    width="small",
                    help=(
                        "AI's max confidence score for any disease area "
                        "(0-1). The Tier 2 / Tier 3 split happens at 0.7."
                    ),
                ),
                "nlp_classified": st.column_config.CheckboxColumn(
                    "NLP?",
                    width="small",
                    help=(
                        "Did the NLP method find a literal disease term "
                        "in the experiment text?"
                    ),
                ),
                "ai_classified": st.column_config.CheckboxColumn(
                    "AI?",
                    width="small",
                    help="Did the AI tag this experiment as health-related?",
                ),
                "nlp_mesh_evidence": st.column_config.TextColumn(
                    "MeSH evidence",
                    width="medium",
                    help=(
                        "Pipe-separated MeSH Descriptor IDs (D-numbers) "
                        "that NLP found. Empty for Tier 2/3 (NLP didn't "
                        "fire). These are the audit trail."
                    ),
                ),
                "classification_source": st.column_config.TextColumn(
                    "Source",
                    width="small",
                    help=(
                        "How the row was classified: nlp+ai (Tier 1), "
                        "ai_high (Tier 2), ai_low (Tier 3), or none (Tier 0)."
                    ),
                ),
            },
        )
        st.download_button(
            "Download tiered CSV",
            data=view_tier.to_csv(index=False).encode("utf-8"),
            file_name="tiered_classification_filtered.csv",
            mime="text/csv",
        )

        st.divider()

        # ---- Section E: Backend Status ----
        st.markdown("### Backend status")
        st.info(
            "The dashboard supports three classification backends. Only "
            "one (SciSpacy) is currently active. When PubTator or "
            "MetaMapLite are activated, their results will appear here "
            "for cross-method comparison."
        )
        st.markdown(
            "| Backend | Status | Notes |\n"
            "|---|---|---|\n"
            f"| **SciSpacy** (`en_ner_bc5cdr_md` + MeSH linker) | "
            f"{'**Active**' if active_nlp_backend == 'scispacy' else 'Available'} | "
            f"Default. No account required. Local NER. |\n"
            "| **PubTator Central API** | Available (not yet run) | "
            "NLM REST API. Currently the ad-hoc text-annotate endpoint is "
            "unreachable; will activate when reinstated. |\n"
            "| **NLM MetaMapLite** (UMLS 2024AA) | Available | "
            "Highest accuracy of the three. Requires a free UMLS account "
            "to download ~2 GB of inverted-index data. |\n"
            "| **Claude Sonnet 4.5** (OpenRouter) | Available — comparison only | "
            "The legacy AI classification. Used to populate Tier 2/3. "
            "Toggle via the sidebar to use it as the active classification. |"
        )
        st.caption(
            "When additional backends are activated their results will appear "
            "here for comparison. Switching the default backend is a one-line "
            "config change in `config/classification_config.json`."
        )


# --- Tab 7: Approved Therapies & Devices ----------------------------------
with tabs[6]:
    st.subheader("Approved Therapies & Devices")
    if therapies_df.empty:
        empty_state("No therapies data yet.", "08_research_therapies.py")
    else:
        st.info(
            "These are drugs and medical devices that either originated "
            "from space research or were significantly advanced by "
            "experiments conducted on the ISS. **This is the end of the "
            "translational pipeline** — from space experiment to "
            "approved treatment."
        )
        st.dataframe(
            therapies_df,
            width="stretch",
            hide_index=True,
            column_config={
                "name": st.column_config.TextColumn(
                    "Name",
                    width="medium",
                    help="Name of the approved drug or medical device.",
                ),
                "type": st.column_config.TextColumn(
                    "Type",
                    width="small",
                    help="Drug (pharmaceutical) or Device (medical equipment).",
                ),
                "disease_area": st.column_config.TextColumn(
                    "Disease area",
                    width="medium",
                    help="The SNIH disease area this therapy addresses.",
                ),
                "approval_year": st.column_config.NumberColumn(
                    "Approved",
                    format="%d",
                    width="small",
                    help="Year the therapy was approved by a regulatory body.",
                ),
                "approving_body": st.column_config.TextColumn(
                    "Regulator",
                    width="small",
                    help="Approving regulatory body (e.g. FDA, EMA).",
                ),
                "iss_direct": st.column_config.TextColumn(
                    "ISS direct?",
                    width="small",
                    help=(
                        "Yes = the therapy depended directly on an ISS "
                        "experiment. No = it benefited from NASA-developed "
                        "technology adapted for terrestrial use."
                    ),
                ),
                "evidence_chain": st.column_config.TextColumn(
                    "Evidence chain",
                    width="large",
                    help=(
                        "Brief narrative of how space research contributed "
                        "to this therapy's development."
                    ),
                ),
                "sources": st.column_config.LinkColumn(
                    "Sources",
                    help="Public source URLs (semicolon-separated).",
                ),
            },
        )


# --- Tab 8: Gap Analysis --------------------------------------------------
with tabs[7]:
    st.subheader("Gap Analysis")
    st.info(
        "**The gap analysis identifies where ISS research investment "
        "doesn't match SNIH priority needs.** Disease areas with many "
        "experiments but few trials have low translation. Areas with few "
        "experiments but high Saudi disease burden represent research "
        "opportunities."
    )
    if classified_df.empty or trials_df.empty or pubs_per_area.empty:
        empty_state(
            "Need experiments, trials, and publications.",
            "01, 06, 07 (and 05)",
        )
    else:
        exp_counts = disease_count_table(
            classified_df[classified_df["health_related"]]
        ).set_index("disease_area")["count"]
        trial_counts = disease_count_table(trials_df).set_index("disease_area")["count"]
        pub_counts = (
            pubs_per_area.set_index("disease_area")["publication_count"].astype(float)
        )

        gap = pd.DataFrame({
            "Experiments": exp_counts,
            "Trials": trial_counts,
            "Publications": pub_counts,
        }).fillna(0).reindex(DISEASE_AREA_NAMES)

        # Heatmap normalised per metric (so each column shows relative intensity)
        normalised = gap.div(gap.max(axis=0)).fillna(0)
        fig_heat = go.Figure(
            go.Heatmap(
                z=normalised.values,
                x=normalised.columns,
                y=normalised.index,
                colorscale="Blues",
                colorbar=dict(title="Relative<br>intensity"),
                hovertemplate="%{y} · %{x}<br>relative: %{z:.0%}<extra></extra>",
            )
        )
        fig_heat.update_layout(
            height=440,
            margin=dict(l=10, r=10, t=10, b=10),
            yaxis=dict(autorange="reversed"),
        )
        st.markdown("**Research intensity heatmap** (normalised per column)")
        st.caption(
            "Shows how research effort (experiments, trials, publications) "
            "is distributed across disease areas. **Darker cells = more "
            "activity.** Normalised per column so you can compare across "
            "different metrics."
        )
        st.plotly_chart(fig_heat, width="stretch")

        # Radar — normalise once across all metrics for shape comparison
        radar_norm = gap.div(gap.max(axis=0)).fillna(0)
        fig_radar = go.Figure()
        palette = px.colors.qualitative.Set3
        for i, area in enumerate(DISEASE_AREA_NAMES):
            fig_radar.add_trace(
                go.Scatterpolar(
                    r=radar_norm.loc[area].tolist() + [radar_norm.loc[area].iloc[0]],
                    theta=list(radar_norm.columns) + [radar_norm.columns[0]],
                    name=area,
                    line=dict(color=palette[i % len(palette)]),
                    opacity=0.7,
                )
            )
        fig_radar.update_layout(
            height=560,
            polar=dict(radialaxis=dict(visible=True, range=[0, 1])),
            margin=dict(l=20, r=20, t=20, b=20),
            legend=dict(orientation="v", yanchor="top", y=1, xanchor="left", x=1.05),
        )
        st.markdown("**Disease area comparison** (each axis normalised to its max)")
        st.caption(
            "Each axis shows a different metric (experiments, trials, "
            "publications) normalised to its maximum. **Wider shapes** = "
            "more balanced coverage. **Narrow spikes** = uneven research "
            "distribution."
        )
        st.plotly_chart(fig_radar, width="stretch")

        # Text summary
        st.markdown("**Highlights**")
        ranked_exp = gap["Experiments"].sort_values(ascending=False)
        ranked_trials = gap["Trials"].sort_values(ascending=False)
        # Translation ratio: trials per experiment
        translation = (
            gap["Trials"] / gap["Experiments"].replace(0, pd.NA)
        ).dropna().sort_values()

        most_researched = ranked_exp.head(3)
        least_researched = ranked_exp.tail(3)
        worst_translation = translation.head(3)

        c1, c2, c3 = st.columns(3)
        with c1:
            st.markdown("**Most-researched**")
            st.caption(
                "Disease areas with the most ISS experiments. These are "
                "well-covered by space research."
            )
            for area, n in most_researched.items():
                st.write(f"- {area} — {int(n)} experiments")
        with c2:
            st.markdown("**Least-researched**")
            st.caption(
                "Disease areas with the fewest ISS experiments. These may "
                "represent gaps or opportunities for new space research."
            )
            for area, n in least_researched.items():
                st.write(f"- {area} — {int(n)} experiments")
        with c3:
            st.markdown("**Weakest translation**")
            st.caption(
                "Disease areas where the ratio of clinical trials to "
                "experiments is lowest. Research exists but isn't "
                "translating to clinical testing."
            )
            for area, ratio in worst_translation.items():
                exp = int(gap.loc[area, "Experiments"])
                trials = int(gap.loc[area, "Trials"])
                st.write(f"- {area} — {trials} trials / {exp} exp ({ratio:.2f})")


# --- Tab 9: Disease Deep-Dive ---------------------------------------------
with tabs[8]:
    st.subheader("Disease Deep-Dive")
    pick = st.selectbox(
        "Select a disease area",
        DISEASE_AREA_NAMES,
        help=(
            "Pick one of the 10 SNIH priority disease areas to see a "
            "detailed breakdown of experiments, trials, and links for "
            "that specific area."
        ),
    )
    st.caption(
        "Per-disease narrative summaries land here once script 09 generates "
        "the gap analysis JSON."
    )
    if not classified_df.empty:
        match = classified_df[
            classified_df["disease_areas"].fillna("").str.contains(pick, case=False)
        ]

        # Tiered breakdown for this area (spec 05 section 4.2)
        area_tier = (
            tiered_summary.get("per_disease_area", {}).get(pick, {})
            if tiered_summary else {}
        )
        t1_n = int(area_tier.get("tier_1", 0))
        t2_n = int(area_tier.get("tier_2", 0))
        t3_n = int(area_tier.get("tier_3", 0))

        # Per-area linkage counts (spec 04 section 7.2)
        area_links = (
            links_df[links_df["shared_areas"].fillna("").str.contains(pick, regex=False)]
            if not links_df.empty else pd.DataFrame()
        )
        linked_trials_count = int(area_links["nct_id"].nunique()) if not area_links.empty else 0
        linked_exp_count = int(area_links["osID"].nunique()) if not area_links.empty else 0

        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric(
            "Tier 1 confirmed",
            f"{t1_n:,}",
            help=(
                "Experiments in this disease area confirmed by both NLP "
                "and AI methods."
            ),
        )
        m2.metric(
            "Tier 2 probable",
            f"{t2_n:,}",
            help=(
                "Experiments in this disease area identified by AI only "
                "(high confidence ≥ 0.7)."
            ),
        )
        m3.metric(
            "Tier 3 uncertain",
            f"{t3_n:,}",
            help=(
                "Experiments in this disease area identified by AI only "
                "(low confidence < 0.7)."
            ),
        )
        m4.metric(
            "Linked trials",
            f"{linked_trials_count:,}",
            help=(
                "Clinical trials linked to experiments in this disease "
                "area via shared MeSH codes."
            ),
        )
        m5.metric(
            "Linked experiments",
            f"{linked_exp_count:,}",
            help=(
                "Experiments in this disease area that have at least "
                "one linked clinical trial."
            ),
        )
        if tiered_summary:
            st.caption(
                f"**{pick}**: {t1_n + t2_n:,} experiments by default "
                f"(Tier 1 + Tier 2). {t3_n:,} additional uncertain. "
                f"See *Classification Comparison* for the full tier explainer."
            )

        st.dataframe(
            match[["osID", "title", "primary_disease_area", "relevance_type"]].head(50),
            width="stretch",
            hide_index=True,
        )

        # Top 5 strongest links for this area (spec 04 section 7.2)
        if not area_links.empty:
            st.markdown("**Top 5 strongest trial ↔ experiment links**")
            top_area_links = area_links.head(5)
            st.dataframe(
                top_area_links[
                    [
                        "link_strength",
                        "final_score",
                        "nct_id",
                        "trial_title",
                        "osID",
                        "experiment_title",
                        "shared_mesh_ids",
                    ]
                ],
                width="stretch",
                hide_index=True,
                column_config={
                    "link_strength": st.column_config.TextColumn(
                        "Strength",
                        width="small",
                        help=(
                            "Strong = high MeSH + text overlap. Moderate = "
                            "good MeSH overlap. Weak = area match only."
                        ),
                    ),
                    "final_score": st.column_config.NumberColumn(
                        "Score",
                        format="%.2f",
                        width="small",
                        help=(
                            "Combined score (0-1) from MeSH 50%, area 20%, "
                            "text 30%."
                        ),
                    ),
                    "nct_id": st.column_config.TextColumn(
                        "NCT ID",
                        width="small",
                        help="ClinicalTrials.gov identifier.",
                    ),
                    "trial_title": st.column_config.TextColumn(
                        "Trial",
                        width="large",
                        help="Title of the clinical trial.",
                    ),
                    "osID": st.column_config.TextColumn(
                        "OS ID",
                        width="small",
                        help="NASA OSDR experiment identifier.",
                    ),
                    "experiment_title": st.column_config.TextColumn(
                        "Experiment",
                        width="large",
                        help="Title of the ISS experiment.",
                    ),
                    "shared_mesh_ids": st.column_config.TextColumn(
                        "Shared MeSH",
                        help=(
                            "MeSH disease codes shared by both. These are "
                            "the medical conditions that connect them."
                        ),
                    ),
                },
            )


# --- Tab 10: Sources & Methods --------------------------------------------
with tabs[9]:
    st.subheader("Sources & Methods")

    st.markdown("### How to read this dashboard")
    st.markdown(
        "This dashboard maps **3,829 International Space Station (ISS) "
        "experiments** to **10 Saudi National Institutes of Health (SNIH) "
        "priority disease areas**."
    )
    st.markdown("**How to use:**")
    st.markdown(
        "1. Start with the **Overview** tab to see the big picture.\n"
        "2. Use the sidebar to switch between **NLP/MeSH** (precise) and "
        "**AI Extended** (broad) classification methods.\n"
        "3. Filter by disease area to focus on specific health priorities.\n"
        "4. Use the **Classification Comparison** tab to understand "
        "confidence levels (Tier 1/2/3).\n"
        "5. Check **Trial-Experiment Links** to see which space research "
        "connects to clinical trials.\n"
        "6. Use **Gap Analysis** to identify research opportunities.\n"
        "7. Deep-dive into any disease area for detailed breakdowns."
    )
    st.markdown("**Classification methods:**")
    st.markdown(
        "- **NLP/MeSH (Default):** Uses biomedical named-entity "
        "recognition (SciSpacy) to find disease terms in experiment text, "
        "then maps them to SNIH areas via MeSH medical dictionary codes. "
        "Deterministic — same input always gives the same output. "
        "Classifies ~11% of experiments. Every classification has a "
        "traceable MeSH code as evidence.\n"
        "- **AI Extended:** Uses Claude (an AI language model) to read "
        "experiment descriptions and infer disease relevance. Classifies "
        "~52% of experiments. Catches implied relevance (e.g., 'bone "
        "remodeling' → musculoskeletal) but is non-deterministic and not "
        "citable in scientific publications.\n"
        "- **Tiered View:** Combines both methods. **Tier 1 (Confirmed)** "
        "= both agree. **Tier 2 (Probable)** = AI only, high confidence. "
        "**Tier 3 (Uncertain)** = AI only, low confidence."
    )
    st.markdown("**Trial linkage:**")
    st.markdown(
        "Trials are linked to experiments when they share the same "
        "medical condition (MeSH code). The link score combines: MeSH "
        "code overlap (50%), disease area match (20%), and text "
        "similarity (30%). Links are labeled **Strong**, **Moderate**, "
        "or **Weak** based on this score."
    )

    st.divider()

    st.markdown("### Data sources")
    osdr_count = int(classified_df["osID"].astype(str).str.startswith("OS-").sum()) \
        if not classified_df.empty else 0
    ssre_count = int(classified_df["osID"].astype(str).str.startswith("SSRE-").sum()) \
        if not classified_df.empty else 0
    st.markdown(
        f"**Experiment catalog** ({len(classified_df):,} total): "
        f"{osdr_count:,} from NASA OSDR (omics-focused datasets, "
        f"aim-level) + {ssre_count:,} from NASA Space Station Research "
        f"Explorer (SSRE — full ISS investigation catalog across NASA, "
        f"ESA, JAXA, ROSCOSMOS, and CSA)."
    )
    st.markdown(
        "| Source | URL | Used for |\n"
        "|---|---|---|\n"
        "| NASA OSDR | https://osdr.nasa.gov | Omics datasets (aim-level) |\n"
        "| NASA SSRE — All Experiments Report | https://www.nasa.gov/mission/station/research-explorer/ | Full ISS investigation catalog (all 5 partner agencies) |\n"
        "| NASA SSRE — All Publications Report | https://www.nasa.gov/mission/station/research-explorer/ | Publication titles linked to each SSRE investigation |\n"
        "| ClinicalTrials.gov | https://clinicaltrials.gov/api/v2/studies | Trials filtered by space keywords |\n"
        "| PubMed E-utilities | https://eutils.ncbi.nlm.nih.gov/entrez/eutils/ | Per-disease publication counts |\n"
        "| NLM MeSH (Medical Subject Headings) | https://www.nlm.nih.gov/mesh/ | Medical vocabulary used for the classification crosswalk |"
    )
    st.caption("All data sources are publicly available and free.")

    st.divider()
    st.markdown("**Classification methodology**")
    st.markdown(
        "Experiments are classified against SNIH disease areas using "
        "biomedical named-entity recognition with MeSH concept mapping. "
        "Disease entities are extracted from experiment text, linked to "
        "MeSH Descriptor IDs, and mapped to SNIH disease areas via MeSH "
        "tree codes (C-branch, plus F03 for mental health) using a frozen "
        "crosswalk. This method is fully deterministic and reproducible "
        "(same inputs always produce the same outputs) and leaves an "
        "audit trail of the exact MeSH descriptors that drove each "
        "classification (see the `mesh_evidence` column and "
        "`data/processed/nlp_classification_details.json`)."
    )
    st.markdown(f"**Current backend:** {active_backend_label}")
    st.caption(
        "An alternative AI-based classification (Claude Sonnet 4.5 via "
        "OpenRouter, temperature=0.0) is available for comparison via the "
        "sidebar *Classification method* toggle. Agreement between the two "
        "methods is reported in "
        "`data/processed/classification_comparison.csv`."
    )

    st.markdown("**Trial ↔ experiment linkage methodology**")
    st.markdown(
        "Clinical trials are linked to ISS experiments deterministically "
        "(no AI, no randomness) using three independent signals combined "
        "into a single score:"
    )
    st.markdown(
        "- **MeSH descriptor overlap** — SciSpacy runs on the trial's "
        "title + conditions to extract MeSH Descriptor IDs, which are "
        "compared to each experiment's `mesh_evidence` column from the "
        "NLP classification. `mesh_score = |intersection| / min(|trial|, |exp|)`.\n"
        "- **SNIH disease-area overlap** — `area_score = |intersection| / |trial areas|`. "
        "Also used as a pre-filter to keep the candidate space small.\n"
        "- **TF-IDF cosine similarity** — unigram+bigram over trial text "
        "(title+conditions+interventions) vs experiment text "
        "(title+objectives+approach+results), English stopwords, min_df=2."
    )
    st.markdown(
        "`final_score = 0.5·mesh + 0.2·area + 0.3·cosine`. A pair is linked "
        "only if `final_score ≥ 0.3` **and** (`mesh_score ≥ 0.5` or "
        "`cosine_score ≥ 0.15`). Strength labels: `strong ≥ 0.6`, "
        "`moderate ≥ 0.4`, `weak ≥ 0.3`."
    )
    if link_summary:
        trials_linked_n = int(link_summary.get("trials_with_links", 0))
        total_trials_n = int(link_summary.get("total_trials", 0))
        coverage_pct = (trials_linked_n / total_trials_n * 100) if total_trials_n else 0.0
        st.caption(
            f"**Coverage finding:** {trials_linked_n:,} of {total_trials_n:,} "
            f"trials ({coverage_pct:.1f}%) have at least one experiment link. "
            f"The remaining trials are about conditions with no direct "
            f"counterpart in the ISS experiment catalog (e.g. specific "
            f"clinical cohorts, rare diseases, or trauma-setting studies). "
            f"This is the honest ceiling of deterministic matching on this "
            f"dataset — loosening thresholds would trade precision for "
            f"coverage. See `data/processed/trial_experiment_links.csv` and "
            f"`data/processed/trial_linkage_summary.json`."
        )


# --- Tab 11: User Manual --------------------------------------------------
with tabs[10]:
    st.subheader("📖 User Manual")
    st.caption(
        "A plain-English guide to everything in this dashboard. If you "
        "have a question, look here first."
    )

    # ---- Getting Started ----
    st.markdown("## Getting started")
    st.markdown(
        "**What this dashboard shows.** Every experiment ever run on the "
        "International Space Station (ISS) — 3,829 in total — sorted "
        "into the 10 disease areas that matter most for Saudi Arabia "
        "(the SNIH priorities). Alongside that, every clinical trial on "
        "Earth that touches the same conditions, and every approved "
        "drug or device that came from space research."
    )
    st.markdown(
        "**Why it exists.** To answer one question: *Which space "
        "research is actually relevant to the diseases that matter to "
        "us, and how much of it has reached patients?*"
    )
    st.markdown(
        "**How to use it.**"
    )
    st.markdown(
        "1. **Look at the Overview** — that's the big picture in one "
        "page.\n"
        "2. **Use the sidebar** — pick a classification method, filter "
        "to a disease area you care about, hide non-health experiments "
        "if you want a clean view.\n"
        "3. **Read the tooltips** — every number, label, and chart on "
        "the dashboard has a `?` icon. Hover it for a plain-English "
        "explanation.\n"
        "4. **Drill down** — when something looks interesting, the "
        "Disease Deep-Dive tab shows everything for one disease area, "
        "and Trial-Experiment Links shows the bench-to-bedside "
        "connections."
    )

    st.divider()

    # ---- Tab-by-Tab Guide ----
    st.markdown("## Tab-by-tab guide")
    st.markdown(
        "**1. Overview.** The dashboard's home page. Top-line numbers "
        "(experiments, trials, publications), a bar chart of "
        "experiments per disease area, the health-vs-not-health share, "
        "and the most common non-health categories. Start here."
    )
    st.markdown(
        "**2. Experiment Explorer.** A searchable table of all 3,829 "
        "experiments. Use this when you want to find a specific "
        "experiment by name or look at every experiment in a disease "
        "area. The classification source column tells you which "
        "method made the call."
    )
    st.markdown(
        "**3. Translational Pipeline.** Side-by-side view of "
        "experiments → publications → clinical trials per disease "
        "area, plus a translation-ratio table. Use this to see "
        "where research is actually moving toward patients vs. "
        "where it's stuck at the lab bench."
    )
    st.markdown(
        "**4. Clinical Trials.** All 534 space-related trials from "
        "ClinicalTrials.gov, with phase and status filters. Click "
        "the URL column to open any trial's full record."
    )
    st.markdown(
        "**5. Trial-Experiment Links.** Connections between specific "
        "trials and specific experiments — based on shared MeSH "
        "disease codes. Strong links are the most confident "
        "(same medical condition + similar text). Use this to find "
        "the bench-to-bedside threads."
    )
    st.markdown(
        "**6. Classification Comparison.** Shows how the two "
        "classification methods agree and disagree. The four tier "
        "cards (Confirmed / Probable / Uncertain / Not health) are "
        "the most important thing — they tell you how confident to "
        "be in any given experiment's tag."
    )
    st.markdown(
        "**7. Approved Therapies.** Drugs and devices that came out "
        "of space research and got approved for Earth use. Small "
        "list, but the most concrete proof that ISS research can "
        "reach patients."
    )
    st.markdown(
        "**8. Gap Analysis.** Heatmap, radar chart, and three "
        "highlight cards (most-researched, least-researched, "
        "weakest translation). Use this to spot research gaps and "
        "opportunities."
    )
    st.markdown(
        "**9. Disease Deep-Dive.** Pick one disease area and see "
        "everything: tier counts, linked trials, linked experiments, "
        "the experiments themselves, and the strongest trial-"
        "experiment links for that area."
    )
    st.markdown(
        "**10. Sources & Methods.** Where the data comes from, how "
        "it's classified, how trials are linked, and the data-"
        "source URLs. Read this if you want to cite the dashboard "
        "or understand the methodology."
    )

    st.divider()

    # ---- Glossary ----
    st.markdown("## Glossary")
    st.markdown(
        "Plain-English definitions for every term you'll see on the "
        "dashboard:"
    )
    glossary = [
        ("**SNIH**",
         "Saudi National Institute of Health. Sets the country's 10 "
         "priority disease areas. The whole dashboard is organised around "
         "these areas."),
        ("**MeSH**",
         "Medical Subject Headings. The U.S. National Library of "
         "Medicine's official medical vocabulary — every disease has a "
         "unique MeSH code (e.g. D010024 = Osteoporosis). It's how this "
         "dashboard knows two pieces of text are about the same condition."),
        ("**MeSH Descriptor ID**",
         "A code starting with `D` followed by digits, e.g. `D010024`. "
         "Each one points to one medical concept in the MeSH vocabulary."),
        ("**Tree code (MeSH)**",
         "A hierarchical address like `C05.116.198.579` that tells you "
         "where a MeSH concept sits in the medical taxonomy. The first "
         "letter identifies the branch (C = diseases). We use these to "
         "map MeSH codes to SNIH areas."),
        ("**Crosswalk**",
         "A frozen lookup table that says 'this MeSH branch belongs to "
         "this SNIH disease area'. Lives at "
         "`scripts/mesh_snih_crosswalk.json`."),
        ("**NER (Named-Entity Recognition)**",
         "A technique that scans text and pulls out specific things — "
         "in our case, disease names. SciSpacy is the NER tool we use."),
        ("**NLP (Natural Language Processing)**",
         "The general field of teaching computers to read text. NER is "
         "one type of NLP task."),
        ("**SciSpacy**",
         "An open-source biomedical NLP library by Allen AI. The "
         "primary classifier here uses its `en_ner_bc5cdr_md` model — "
         "trained on biomedical literature to find disease and "
         "chemical mentions."),
        ("**PubTator**",
         "An NLM service that annotates biomedical text with disease, "
         "chemical, gene, and species mentions. Available as a backend "
         "but not currently active."),
        ("**MetaMapLite**",
         "Another NLM tool for mapping text to medical concepts. "
         "Highest accuracy of the three NLP options. Requires a free "
         "UMLS account, so it's available but not active."),
        ("**Deterministic**",
         "Same input always gives the same output. The NLP method is "
         "deterministic; the AI method is not."),
        ("**OSDR**",
         "NASA's Open Science Data Repository — `osdr.nasa.gov`. The "
         "source for all 3,829 ISS experiments in this dashboard."),
        ("**NCT ID**",
         "ClinicalTrials.gov's unique identifier for each trial, "
         "format `NCTxxxxxxxx`. Click the trial URL on the Trials tab "
         "to open the full record."),
        ("**TF-IDF**",
         "*Term Frequency × Inverse Document Frequency.* A standard "
         "way to measure how similar two pieces of text are by counting "
         "shared meaningful words (and downweighting common words). "
         "Used to score the text similarity between trials and "
         "experiments."),
        ("**Cosine similarity**",
         "A number from 0 to 1 that says how similar two text vectors "
         "are. 1.0 = identical, 0 = no overlap. For scientific text, "
         "0.15+ is meaningful."),
        ("**Health-related**",
         "An experiment that the classification method judged to be "
         "relevant to at least one SNIH disease area."),
        ("**Disease area**",
         "One of the 10 SNIH priority areas: Cardiovascular, Kidney, "
         "Cancer, Neurological, Eye, Rare inherited disorders, "
         "Women's health, Endocrine and metabolic, Musculoskeletal, "
         "Mental health."),
        ("**Classification source**",
         "Which method tagged a given experiment. `scispacy` = NLP, "
         "`ai` = Claude, `keyword` = simple keyword matching."),
        ("**Tier 1 — Confirmed**",
         "Both NLP and AI agree the experiment is health-related "
         "**and** they agree on at least one disease area. Highest "
         "confidence."),
        ("**Tier 2 — Probable**",
         "AI says health-related with high confidence (≥ 0.7), but "
         "NLP found no literal disease term. Plausible but not "
         "MeSH-backed."),
        ("**Tier 3 — Uncertain**",
         "AI says health-related with low confidence (< 0.7), and NLP "
         "didn't fire. Treat with care — needs expert review."),
        ("**Tier 0 — Not health**",
         "Neither method tagged it as health-related. Mostly basic "
         "science (plant biology, materials, fluid physics)."),
        ("**Link strength**",
         "How confident the trial↔experiment connection is. **Strong** "
         "= shared MeSH code + high text similarity. **Moderate** = "
         "shared MeSH with moderate similarity. **Weak** = shared "
         "disease area only."),
        ("**Translational pipeline**",
         "The path from a basic-science experiment, through "
         "publications, to a clinical trial, to an approved treatment. "
         "Each step is harder to reach. The dashboard tracks how many "
         "experiments make it to each step."),
        ("**F1 score**",
         "A common accuracy measure for classifiers, combining "
         "precision and recall into one number from 0 to 1. The "
         "SciSpacy `en_ner_bc5cdr_md` model has an F1 of 0.84 on the "
         "BC5CDR disease-chemical benchmark."),
    ]
    for term, defn in glossary:
        st.markdown(f"- {term} — {defn}")

    st.divider()

    # ---- FAQ ----
    st.markdown("## Frequently asked questions")

    with st.expander("Why are only ~11% of experiments classified as health-related?"):
        st.markdown(
            "Because the NLP method only fires when it finds a literal "
            "disease term in the experiment text. A study about "
            "'mechanical loading on bone tissue' is clearly "
            "musculoskeletal to a human reader — but if the title "
            "doesn't say 'osteoporosis' or 'fracture', NLP stays silent. "
            "This is intentional: it keeps the method precise and "
            "citable. The AI Extended view will show a much higher "
            "percentage (~52%) because it can infer from context."
        )

    with st.expander("Why do NLP and AI disagree so much?"):
        st.markdown(
            "Because they ask different questions. NLP asks: *Did the "
            "researcher write down a disease name?* AI asks: *Does this "
            "study sound disease-relevant?* Both are valid; they just "
            "have different precision/coverage trade-offs. The "
            "Classification Comparison tab shows you exactly where "
            "they disagree, by experiment."
        )

    with st.expander("What does 'Tier 2 Probable' mean?"):
        st.markdown(
            "It means the AI is fairly sure (≥ 70%) that the experiment "
            "is health-related, but the NLP method found no MeSH "
            "disease code in the text. So the AI inferred relevance "
            "from context — for example, recognising that 'osteoblast "
            "differentiation' relates to bone disease even though no "
            "disease was explicitly named. Plausible, but not "
            "evidence-backed by the medical dictionary."
        )

    with st.expander("Why do some trials have no linked experiments?"):
        st.markdown(
            "Because many trials we fetched are about conditions that "
            "ISS hasn't studied — for example, very specific clinical "
            "cohorts, rare diseases, or trauma-setting studies. "
            "Roughly 21% of trials have at least one experiment link. "
            "The other 79% are legitimately disconnected from the ISS "
            "experiment catalog. This is a coverage ceiling, not a bug."
        )

    with st.expander("Can I trust the AI classification?"):
        st.markdown(
            "**For exploration:** yes. Use AI Extended in the sidebar "
            "to see broader patterns and catch experiments NLP missed.\n\n"
            "**For publication or formal reporting:** use NLP/MeSH "
            "(Tier 1 only). Every Tier 1 classification has a "
            "traceable MeSH code and is reproducible. Tier 2 and 3 "
            "are AI-only and shouldn't be cited as confirmed evidence."
        )

    with st.expander("How often is the data updated?"):
        st.markdown(
            "The data here is a snapshot. To refresh it, re-run the "
            "pipeline scripts in `scripts/` (`01_fetch_nasa_osdr.py` "
            "→ `13_build_tiered_classification.py`). Each script is "
            "safe to re-run and will pick up new data from the source "
            "APIs."
        )

    with st.expander("What does a 'strong' link mean?"):
        st.markdown(
            "A strong link means the trial and the experiment share "
            "the **exact same MeSH disease code** (e.g. both about "
            "'Osteoporosis' D010024) AND their descriptions have high "
            "text similarity. These are the most confident "
            "bench-to-bedside connections in the dataset."
        )
