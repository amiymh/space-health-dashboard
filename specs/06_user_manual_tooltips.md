# Spec 06 — User Manual & Dashboard Tooltips

**Date:** 2026-04-07
**Goal:** Add comprehensive help tooltips to every element in the dashboard (every metric, label, title, number, chart, filter, and toggle) AND add a built-in user manual page. A non-technical user should be able to understand every single thing they see by hovering on the `?` icon.

**Why:** The dashboard is built for non-scientists and non-coders. Every number, label, and chart needs a plain-English explanation accessible on hover. No jargon without definition.

---

## 1. Implementation: Streamlit `help=` Parameter

Streamlit supports a `help=` parameter on most widgets and `st.metric()`. This renders a `?` icon that shows a tooltip on hover. Use this for every element.

For elements that don't support `help=` directly (like `st.markdown`, chart titles, table headers), use a pattern like:
```python
st.markdown("**Title** " + tooltip_icon("explanation text"))
```

Where `tooltip_icon` is a helper that renders an inline `?` using `st.caption` or similar. Alternatively, use `st.info()` blocks for section-level explanations.

---

## 2. Sidebar Tooltips

### Classification radio button
Already has `help=`. Verify it reads:
> "NLP/MeSH is the primary method — fully deterministic, uses biomedical named-entity recognition to find disease terms and maps them to SNIH areas via MeSH codes. AI Extended uses Claude (an AI model) which infers disease relevance from context. AI catches more experiments but is less precise."

### Disease area filter
Already has `help=`. Verify it reads:
> "Select one or more SNIH disease areas to filter all tabs. Leave empty to see all areas."

### Hide non-health toggle
Already has `help=`. Verify it reads:
> "When enabled, hides experiments classified as not health-related (plant biology, materials science, fluid physics, etc.). Turn off to see the full dataset."

### Sidebar stats
Add help text next to each count:
- **Classified experiments:** `help="Total number of ISS experiments that have been processed through the classification pipeline."`
- **Clinical trials:** `help="Space-related clinical trials fetched from ClinicalTrials.gov using space + disease keyword combinations."`
- **PubMed counts:** `help="Number of disease areas with PubMed publication counts. These show how much published research exists for each SNIH area."`
- **Therapies:** `help="Approved drugs and medical devices that originated from or were significantly advanced by space research."`

---

## 3. Tab 1: Overview

### Metrics row
- **Total experiments:** `help="All ISS experiments from NASA's Open Science Data Repository (OSDR). Each experiment is a unique research study conducted on the International Space Station."`
- **Health-related:** `help="Experiments where the classification method detected a disease-related term. The percentage shows health-related out of total. With NLP/MeSH this is ~11%; with AI Extended ~52%. The difference is because NLP only counts literal disease mentions while AI infers from context."`
- **Clinical trials:** `help="Total space-related clinical trials from ClinicalTrials.gov. These are medical studies on Earth that investigate conditions also studied in space research."`
- **PubMed (space biology):** `help="Baseline count of PubMed articles matching 'space biology' — gives context for the scale of the field's published research."`

### Charts
- **Experiments per disease area (bar chart):** Add subtitle: `"Number of ISS experiments classified under each SNIH priority disease area. An experiment can appear in multiple areas if it covers more than one condition."`
- **Health-related share (pie chart):** Add subtitle: `"Proportion of all 3,829 experiments that were classified as health-related vs. not. This ratio changes depending on which classification method is selected in the sidebar."`
- **Top non-health categories:** Add subtitle: `"Most common categories among experiments that were NOT classified as health-related. These are legitimate space research areas (plant biology, materials science) that don't map to SNIH disease areas."`

---

## 4. Tab 2: Experiment Explorer

### Table columns — each column header needs a tooltip:
- **osID:** `"NASA's unique identifier for each experiment in the Open Science Data Repository. Format: OS-XXX."`
- **title:** `"The official title of the ISS experiment as registered in OSDR."`
- **health_related:** `"Whether the classification method found this experiment relevant to any SNIH disease area. True = at least one disease area assigned."`
- **disease_areas:** `"The SNIH disease area(s) this experiment maps to. Semicolon-separated if multiple. Based on MeSH disease codes found in the experiment text."`
- **primary_disease_area:** `"The single disease area with the strongest evidence (most MeSH term matches). Used when only one area can be shown."`
- **classification_source:** `"Which method classified this experiment. 'scispacy' = NLP/MeSH method, 'claude' = AI method, 'keyword' = simple keyword matching."`
- **mesh_evidence:** `"The MeSH Descriptor IDs (medical dictionary codes) that were found in the experiment text. These are the evidence trail for why the experiment was classified under its disease area(s). Format: pipe-separated D-numbers like D010024|D003920."`

---

## 5. Tab 3: Translational Pipeline

Add section explanation at top:
> "The translational pipeline shows how ISS research connects to clinical application. For each disease area: how many ISS experiments exist, how many clinical trials are running, and what the ratio is. A high trial-to-experiment ratio suggests active translation from bench to bedside."

### Metrics and charts:
- **Translation ratios:** `help="Trials per experiment for each disease area. Higher = more clinical translation happening. Lower = research exists but hasn't moved to clinical trials yet."`

---

## 6. Tab 4: Clinical Trials

### Metrics row
- **Trials shown:** `help="Number of clinical trials displayed after applying any active filters."`
- **Phases:** `help="Number of distinct trial phases in the current view. Phase 1 = safety testing, Phase 2 = efficacy, Phase 3 = large-scale, Phase 4 = post-market."`
- **Statuses:** `help="Number of distinct trial statuses. Common statuses: RECRUITING (actively enrolling), COMPLETED, ACTIVE_NOT_RECRUITING, WITHDRAWN, TERMINATED."`

### Charts
- **By status (pie):** `"Distribution of trial statuses. 'Recruiting' means actively looking for participants. 'Completed' means the trial finished. 'Withdrawn' means it was cancelled before enrollment."`
- **By phase (bar):** `"Trial phases indicate how far along the clinical testing process a treatment is. Phase 3 trials are the most advanced (closest to approval)."`

---

## 7. Tab 5: Trial-Experiment Links

### Metrics row
- **Total links:** `help="Number of connections found between clinical trials and ISS experiments. A link means both study the same medical condition (share MeSH disease codes)."`
- **Trials linked:** `help="How many of the 534 clinical trials have at least one matching ISS experiment. 21.2% coverage — the rest study conditions with no ISS counterpart."`
- **Experiments linked:** `help="How many ISS experiments have at least one matching clinical trial."`
- **Strong links:** `help="Links where the trial and experiment share the exact same MeSH disease code AND have high text similarity. These are the most confident connections."`

### Filters
- **Link strength filter:** `help="Filter by confidence level. Strong = shared MeSH codes + high text similarity. Moderate = shared MeSH codes with moderate similarity. Weak = shared disease area with low text overlap."`
- **Disease area filter:** `help="Show only links involving experiments or trials in these disease areas."`

### Table columns
- **nct_id:** `"ClinicalTrials.gov unique identifier. Click the trial URL to see the full record on ClinicalTrials.gov."`
- **osID:** `"NASA OSDR experiment identifier. Links to the experiment record on osdr.nasa.gov."`
- **link_strength:** `"Confidence of the connection: Strong (high MeSH + text overlap), Moderate (good MeSH overlap), Weak (area match only)."`
- **final_score:** `"Combined linkage score (0-1) from MeSH overlap (50%), disease area match (20%), and text similarity (30%). Higher = stronger connection."`
- **mesh_score:** `"How many medical terms (MeSH codes) the trial and experiment have in common, relative to the total terms. 1.0 = perfect overlap."`
- **cosine_score:** `"Text similarity between trial and experiment descriptions. Based on TF-IDF, a standard text comparison method. 0.15+ is meaningful for scientific text."`
- **shared_mesh_ids:** `"The specific MeSH codes that both the trial and experiment share. These are the medical conditions that connect them."`
- **shared_areas:** `"SNIH disease areas that both the trial and experiment belong to."`

---

## 8. Tab 6: Classification Comparison

### Tier KPI cards
- **Tier 1 — Confirmed:** `help="Experiments where BOTH the NLP method (MeSH-based) AND the AI method agree the experiment is health-related AND they agree on at least one disease area. Highest confidence — two independent methods confirmed the classification."`
- **Tier 2 — Probable:** `help="Experiments where the NLP method found no disease terms BUT the AI classified it as health-related with high confidence (≥70%). The AI inferred disease relevance from context (e.g., 'osteoblast differentiation' implies bone disease). Plausible but not evidence-backed by medical dictionary codes."`
- **Tier 3 — Uncertain:** `help="Experiments where the NLP method found no disease terms AND the AI classified it with low confidence (<70%). These need expert review to determine if they're truly health-related."`
- **Tier 0 — Not health:** `help="Experiments that neither method classified as health-related. These are likely basic science (plant biology, fluid physics, materials science) without direct disease relevance."`

### Agreement metrics
- **Agree on health/not:** `help="Percentage of experiments where NLP and AI give the same yes/no answer on whether the experiment is health-related."`
- **Exact disease-area match:** `help="Percentage where NLP and AI assign exactly the same set of disease areas."`
- **≥1 area overlap:** `help="Percentage where NLP and AI share at least one disease area, even if they don't match completely."`
- **Complete disagreement:** `help="Percentage where the two methods have zero overlap — completely different conclusions."`

### Backend status
Add explanatory text:
> "The dashboard supports three classification backends. Only one (SciSpacy) is currently active. When PubTator or MetaMapLite are activated, their results will appear here for cross-method comparison."

---

## 9. Tab 7: Approved Therapies

Add section explanation:
> "These are drugs and medical devices that either originated from space research or were significantly advanced by experiments conducted on the ISS. This is the end of the translational pipeline — from space experiment to approved treatment."

### Table columns
- **name:** `"Name of the approved drug or medical device."`
- **type:** `"Whether this is a drug (pharmaceutical) or device (medical equipment)."`
- **disease_areas:** `"Which SNIH disease area(s) this therapy addresses."`
- **description:** `"Brief description of what the therapy does and how space research contributed to its development."`

---

## 10. Tab 8: Gap Analysis

Add section explanation:
> "The gap analysis identifies where ISS research investment doesn't match SNIH priority needs. Disease areas with many experiments but few trials have low translation. Areas with few experiments but high Saudi disease burden represent research opportunities."

### Charts
- **Research intensity heatmap:** `help="Shows how research effort (experiments, trials, publications) is distributed across disease areas. Darker cells = more activity. Normalized per column so you can compare across different metrics."`
- **Disease area comparison radar:** `help="Each axis shows a different metric (experiments, trials, publications) normalized to its maximum. Wider shapes = more balanced coverage. Narrow spikes = uneven research distribution."`

### Highlight cards
- **Most-researched:** `help="Disease areas with the most ISS experiments. These are well-covered by space research."`
- **Least-researched:** `help="Disease areas with the fewest ISS experiments. These may represent gaps or opportunities for new space research."`
- **Weakest translation:** `help="Disease areas where the ratio of clinical trials to experiments is lowest. Research exists but isn't translating to clinical testing."`

---

## 11. Tab 9: Disease Deep-Dive

### Disease area selector
`help="Pick one of the 10 SNIH priority disease areas to see a detailed breakdown of experiments, trials, and links for that specific area."`

### Metrics row
- **Tier 1 confirmed:** `help="Experiments in this disease area confirmed by both NLP and AI methods."`
- **Tier 2 probable:** `help="Experiments in this disease area identified by AI only (high confidence)."`
- **Tier 3 uncertain:** `help="Experiments in this disease area identified by AI only (low confidence)."`
- **Linked trials:** `help="Clinical trials linked to experiments in this disease area via shared MeSH codes."`
- **Linked experiments:** `help="Experiments in this disease area that have at least one linked clinical trial."`

### Top 5 strongest links table
Column tooltips same as Tab 5 link table.

---

## 12. Tab 10: Sources & Methods

This tab IS the manual. Expand it with:

### Section: How to Read This Dashboard
```
This dashboard maps 3,829 International Space Station (ISS) experiments 
to 10 Saudi National Institutes of Health (SNIH) priority disease areas.

HOW TO USE:
1. Start with the Overview tab to see the big picture
2. Use the sidebar to switch between NLP/MeSH (precise) and AI Extended (broad) classification methods
3. Filter by disease area to focus on specific health priorities
4. Use the Classification Comparison tab to understand confidence levels (Tier 1/2/3)
5. Check Trial-Experiment Links to see which space research connects to clinical trials
6. Use Gap Analysis to identify research opportunities
7. Deep-dive into any disease area for detailed breakdowns

CLASSIFICATION METHODS:
• NLP/MeSH (Default): Uses biomedical named-entity recognition (SciSpacy) 
  to find disease terms in experiment text, then maps them to SNIH areas via 
  MeSH medical dictionary codes. Deterministic — same input always gives 
  same output. Classifies ~11% of experiments. Every classification has a 
  traceable MeSH code as evidence.

• AI Extended: Uses Claude (an AI language model) to read experiment 
  descriptions and infer disease relevance. Classifies ~52% of experiments. 
  Catches implied relevance (e.g., "bone remodeling" → musculoskeletal) 
  but is non-deterministic and not citable in scientific publications.

• Tiered View: Combines both methods. Tier 1 (Confirmed) = both agree. 
  Tier 2 (Probable) = AI only, high confidence. Tier 3 (Uncertain) = AI only, 
  low confidence.

TRIAL LINKAGE:
Trials are linked to experiments when they share the same medical condition 
(MeSH code). The link score combines: MeSH code overlap (50%), disease area 
match (20%), and text similarity (30%). Links are labeled Strong, Moderate, 
or Weak based on this score.

DATA SOURCES:
• Experiments: NASA Open Science Data Repository (OSDR)
• Clinical Trials: ClinicalTrials.gov v2 API
• Medical vocabulary: NLM Medical Subject Headings (MeSH)
• Publications: PubMed
• All data is publicly available and free
```

---

## 13. User Manual Tab (New)

Add a new tab called "📖 User Manual" as the LAST tab (after Sources & Methods). This should contain:

### 13.1 Getting Started
Plain-English walkthrough of what the dashboard shows and why.

### 13.2 Tab-by-Tab Guide
For each of the 10 tabs, a 3-4 sentence description of what it shows, when to use it, and what to look for.

### 13.3 Glossary
Inline definitions of every term used in the dashboard:
- SNIH, MeSH, NER, OSDR, NLP, TF-IDF, MeSH Descriptor ID, Tree code, Crosswalk, Deterministic, F1 score, NCT ID, Tier 1/2/3, SciSpacy, PubTator, MetaMapLite, Cosine similarity, Health-related, Disease area, Classification source, Link strength, Translational pipeline

### 13.4 FAQ
- "Why are only 11% of experiments classified as health-related?" → Because NLP only tags literal disease terms.
- "Why do NLP and AI disagree so much?" → NLP looks for exact medical terms, AI infers from context.
- "What does 'Tier 2 Probable' mean?" → AI thinks it's health-related with high confidence, but no MeSH code was found.
- "Why do some trials have no linked experiments?" → Those trials study conditions that ISS hasn't researched.
- "Can I trust the AI classification?" → For exploration yes. For publication, use NLP/MeSH (Tier 1) only.
- "How often is the data updated?" → The data reflects a snapshot. Re-run the pipeline scripts to refresh.
- "What does a strong link mean?" → The trial and experiment share the same MeSH disease code and have similar descriptions.

---

## 14. Done Criteria

- [ ] Every `st.metric()` has a `help=` parameter
- [ ] Every sidebar widget has a `help=` parameter
- [ ] Every chart has a subtitle or caption explaining what it shows
- [ ] Every table column in the Experiment Explorer has a tooltip
- [ ] Every table column in the Trial-Experiment Links has a tooltip
- [ ] Classification Comparison tier cards have tooltips
- [ ] Agreement metrics have tooltips
- [ ] Sources & Methods tab has the "How to Read" section
- [ ] New "User Manual" tab exists with: Getting Started, Tab Guide, Glossary, FAQ
- [ ] A non-technical person can understand every element by reading the tooltip
- [ ] No existing functionality broken
