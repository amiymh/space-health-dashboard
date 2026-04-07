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
@st.cache_data(show_spinner=False)
def load_all() -> dict[str, pd.DataFrame]:
    classified = data_loader.load_classified_experiments()
    trials = data_loader.load_clinical_trials()
    pubs = data_loader.load_publication_counts()
    therapies = data_loader.load_approved_therapies()

    if not classified.empty:
        # CSV stores booleans as the strings "True"/"False"
        classified["health_related"] = (
            classified["health_related"]
            .astype(str)
            .str.lower()
            .map({"true": True, "false": False})
            .fillna(False)
        )
        classified["disease_areas"] = classified["disease_areas"].fillna("")
        classified["primary_disease_area"] = classified["primary_disease_area"].fillna("")
        classified["non_health_category"] = classified["non_health_category"].fillna("")

    return {
        "classified": classified,
        "trials": trials,
        "pubs": pubs,
        "therapies": therapies,
    }


data = load_all()
classified_df: pd.DataFrame = data["classified"]
trials_df: pd.DataFrame = data["trials"]
pubs_df: pd.DataFrame = data["pubs"]
therapies_df: pd.DataFrame = data["therapies"]


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
    st.header("Filters")
    selected_diseases: list[str] = st.multiselect(
        "Disease area",
        options=DISEASE_AREA_NAMES,
        default=[],
        help="Empty = show all. Filters experiments and trials wherever a "
             "disease tag is available.",
    )
    show_only_health = st.checkbox(
        "Health-related experiments only",
        value=True,
        help="Hide experiments classified as plant biology, materials, "
             "physical science, technology, or education.",
    )
    st.divider()
    st.caption("Pipeline status")
    st.write(f"Classified experiments: **{len(classified_df)}**")
    st.write(f"Clinical trials: **{len(trials_df)}**")
    st.write(f"PubMed counts: **{len(pubs_df)}**")
    st.write(f"Therapies: **{len(therapies_df)}**")


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
    "Approved Therapies",
    "Gap Analysis",
    "Disease Deep-Dive",
    "Sources & Methods",
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
        m1.metric("Total experiments", f"{total_exp:,}")
        m2.metric("Health-related", f"{health_yes:,}",
                  delta=f"{health_yes/total_exp:.0%}" if total_exp else None)
        m3.metric("Clinical trials", f"{total_trials:,}")
        m4.metric("PubMed (space biology)", f"{baseline_pubs:,}")

        st.divider()

        col_left, col_right = st.columns([3, 2])

        # Horizontal bar — experiments per disease area, descending
        with col_left:
            st.markdown("**Experiments per disease area**")
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
                "osID": st.column_config.TextColumn("OS ID", width="small"),
                "title": st.column_config.TextColumn("Title", width="large"),
                "disease_areas": st.column_config.TextColumn("Disease areas", width="medium"),
                "primary_disease_area": st.column_config.TextColumn("Primary", width="medium"),
                "relevance_type": st.column_config.TextColumn("Relevance", width="small"),
                "health_related": st.column_config.CheckboxColumn("Health?", width="small"),
                "classification_source": st.column_config.TextColumn("Source", width="small"),
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
    st.caption(
        "ISS Experiments → PubMed Publications → Clinical Trials. "
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
            phase_pick = st.multiselect("Phase", options=phase_options)
        with c2:
            status_options = sorted(view_trials["status"].dropna().unique())
            status_pick = st.multiselect("Status", options=status_options)

        if phase_pick:
            view_trials = view_trials[
                view_trials["phase"].fillna("").apply(
                    lambda s: any(p in s for p in phase_pick)
                )
            ]
        if status_pick:
            view_trials = view_trials[view_trials["status"].isin(status_pick)]

        m1, m2, m3 = st.columns(3)
        m1.metric("Trials shown", f"{len(view_trials):,}")
        m2.metric("Phases", view_trials["phase"].fillna("").replace("", pd.NA).dropna().nunique())
        m3.metric("Statuses", view_trials["status"].nunique())

        col_a, col_b = st.columns(2)
        with col_a:
            st.markdown("**By status**")
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


# --- Tab 5: Approved Therapies & Devices (stub) ---------------------------
with tabs[4]:
    st.subheader("Approved Therapies & Devices")
    if therapies_df.empty:
        empty_state("No therapies data yet.", "08_research_therapies.py")
    else:
        st.dataframe(therapies_df, width="stretch")


# --- Tab 6: Gap Analysis --------------------------------------------------
with tabs[5]:
    st.subheader("Gap Analysis")
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
            for area, n in most_researched.items():
                st.write(f"- {area} — {int(n)} experiments")
        with c2:
            st.markdown("**Least-researched**")
            for area, n in least_researched.items():
                st.write(f"- {area} — {int(n)} experiments")
        with c3:
            st.markdown("**Weakest translation**")
            st.caption("low trials-per-experiment ratio")
            for area, ratio in worst_translation.items():
                exp = int(gap.loc[area, "Experiments"])
                trials = int(gap.loc[area, "Trials"])
                st.write(f"- {area} — {trials} trials / {exp} exp ({ratio:.2f})")


# --- Tab 7: Disease Deep-Dive (stub) ---------------------------------------
with tabs[6]:
    st.subheader("Disease Deep-Dive")
    pick = st.selectbox("Select a disease area", DISEASE_AREA_NAMES)
    st.caption(
        "Per-disease narrative summaries land here once script 09 generates "
        "the gap analysis JSON."
    )
    if not classified_df.empty:
        match = classified_df[
            classified_df["disease_areas"].fillna("").str.contains(pick, case=False)
        ]
        st.write(f"{len(match)} experiments classified to **{pick}**")
        st.dataframe(
            match[["osID", "title", "primary_disease_area", "relevance_type"]].head(50),
            width="stretch",
            hide_index=True,
        )


# --- Tab 8: Sources & Methods (stub) --------------------------------------
with tabs[7]:
    st.subheader("Sources & Methods")
    osdr_count = int(classified_df["osID"].astype(str).str.startswith("OS-").sum()) \
        if not classified_df.empty else 0
    ssre_count = int(classified_df["osID"].astype(str).str.startswith("SSRE-").sum()) \
        if not classified_df.empty else 0
    st.markdown(
        f"""
        **Experiment catalog** ({len(classified_df):,} total):
        {osdr_count:,} from NASA OSDR (omics-focused datasets, aim-level)
        + {ssre_count:,} from NASA Space Station Research Explorer
        (SSRE — full ISS investigation catalog across NASA, ESA, JAXA,
        ROSCOSMOS, and CSA).

        | Source | URL | Used for |
        |---|---|---|
        | NASA OSDR | https://osdr.nasa.gov | Omics datasets (aim-level) |
        | NASA SSRE — All Experiments Report | https://www.nasa.gov/mission/station/research-explorer/ | Full ISS investigation catalog (all 5 partner agencies) |
        | NASA SSRE — All Publications Report | https://www.nasa.gov/mission/station/research-explorer/ | Publication titles linked to each SSRE investigation |
        | ClinicalTrials.gov | https://clinicaltrials.gov/api/v2/studies | Trials filtered by space keywords |
        | PubMed E-utilities | https://eutils.ncbi.nlm.nih.gov/entrez/eutils/ | Per-disease publication counts |
        """
    )
    st.caption(
        "Classification methodology: keyword matching against the SNIH "
        "disease keyword lists in scripts/config.py, with Claude (via "
        "OpenRouter) as a fallback for experiments where keywords found "
        "no match. See SPACE_HEALTH_SPECS.md section 3.3."
    )
