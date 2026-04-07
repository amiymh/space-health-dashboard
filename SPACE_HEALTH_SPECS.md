# Space-Health Dashboard — Project Specification

**Date:** 2026-04-07
**Purpose:** Map all ISS experiments to SNIH disease areas, trace translational pipeline to clinical trials and approved therapies, identify research gaps, and present findings in an interactive dashboard.

---

## 1. Project Overview

### 1.1 Background
Over 4,000 research investigations have been conducted aboard the ISS since 2000 by NASA, ESA, JAXA, and CSA. These experiments span human health, biology, physical sciences, and technology. The Saudi National Institute of Health (SNIH) has identified 10 priority disease areas. This project maps ISS research to those disease areas, traces the translational pipeline from experiment to clinical application, and identifies gaps for future research.

### 1.2 SNIH Disease Areas (10 categories)
1. **Cardiovascular diseases** — heart, cardiac, vascular, hypertension, atherosclerosis, blood pressure, arrhythmia, endothelial, aortic, coronary, thrombosis, angiogenesis
2. **Kidney diseases** — renal, nephro, kidney, glomerular, tubular, dialysis, nephrolithiasis, kidney stone, urinary
3. **Cancer** — tumor, oncology, carcinoma, neoplasm, malignant, metastasis, leukemia, lymphoma, melanoma, proliferation, apoptosis
4. **Neurological diseases** — brain, neural, neurodegenerative, Alzheimer, Parkinson, dementia, motor neuron, neuropathy, seizure, epilepsy, stroke, cerebral
5. **Eye diseases** — ocular, retina, optic, vision, intraocular pressure, VIIP, papilledema, cataract, glaucoma, macular, corneal
6. **Rare inherited disorders** — genetic disorder, rare disease, hereditary, monogenic, congenital, orphan disease, inborn error, chromosomal
7. **Women's health** — reproductive, fertility, ovarian, uterine, pregnancy, menstrual, breast, cervical, estrogen, maternal, gynecological
8. **Endocrine and metabolic diseases** — diabetes, insulin, thyroid, metabolic syndrome, obesity, lipid, glucose, hormone, adrenal, pituitary, growth hormone, cortisol
9. **Musculoskeletal diseases** — bone, muscle, skeletal, osteoporosis, sarcopenia, atrophy, cartilage, joint, spine, fracture, bone density, bone loss, tendon, collagen
10. **Mental health** — psychological, cognitive, stress, anxiety, depression, sleep, circadian, isolation, behavioral, mood, fatigue, psychosocial, neurobehavioral

### 1.3 Keyword Expansion Rules
- Each disease area has primary keywords (above) and should also match on:
  - Tissue/organ names associated with the disease (e.g., "liver" → endocrine/metabolic)
  - Known space-health conditions (e.g., "SANS" → eye diseases, "spaceflight-associated neuro-ocular syndrome")
  - Experimental models (e.g., "hindlimb unloading" → musculoskeletal, "bed rest" → cardiovascular + musculoskeletal)
- An experiment can map to multiple disease areas
- Experiments with no disease relevance (e.g., materials science, plant growth without health context) are tagged "Not health-related"

---

## 2. Data Sources & APIs

### 2.1 NASA OSDR (Open Science Data Repository)
- **Experiments API:** `https://osdr.nasa.gov/geode-py/ws/api/experiments` → returns ~928 experiment URLs
- **Single experiment:** `https://osdr.nasa.gov/geode-py/ws/api/experiment/{OS-ID}` → full metadata
- **Search API:** `https://osdr.nasa.gov/osdr/data/search?term={keyword}&from=0&size=25&type=cgene`
- **V2 Datasets API:** `https://visualization.osdr.nasa.gov/biodata/api/v2/datasets/` → 628 omics datasets
- **Fields to extract:** osID, title, objectives, approach, results, sponsoringAgency, researchAreas, nasaPrograms, factors, publications, people (PI + institution), releaseDate
- **Rate limiting:** 0.5s between requests, save progress every 50 experiments

### 2.2 NASA Space Station Research Explorer
- **URL:** `https://www.nasa.gov/mission/station/research-explorer/`
- **API:** No public API — web scraping or SerpAPI required
- **Contains:** 4,000+ investigations including non-omics (physical science, technology demos, education)
- **Approach:** Use SerpAPI to search `site:nasa.gov/mission/station/research-explorer` for each disease keyword, or browser automation to extract the full catalog
- **Alternative:** NASA publishes annual ISS Benefits reports — these can be parsed for experiment catalogs

### 2.3 ESA Erasmus Experiment Archive
- **URL:** `https://eea.spaceflight.esa.int`
- **API:** Requires authentication (401 on public access)
- **Approach:** Browser automation to extract experiment list, or SerpAPI to search `site:eea.spaceflight.esa.int`
- **Fallback:** ESA publishes experiment lists in PDF reports and on their website

### 2.4 JAXA Space Experiment Database
- **URL:** `https://humans-in-space.jaxa.jp/en/bss/experiment/`
- **API:** No public API
- **Approach:** Browser automation or SerpAPI

### 2.5 CSA (Canadian Space Agency)
- **URL:** `https://www.asc-csa.gc.ca/eng/sciences/experiments/`
- **API:** No public API
- **Approach:** Browser automation or SerpAPI

### 2.6 ClinicalTrials.gov
- **API:** `https://clinicaltrials.gov/api/v2/studies?query.term={term}&pageSize=100`
- **Free, no auth required**
- **Search terms per disease area:** combine "microgravity OR space OR ISS OR spaceflight OR astronaut" with each disease keyword set
- **Fields to extract:** NCT ID, title, status, phase, conditions, interventions, sponsor, start date, URL

### 2.7 PubMed (for publication counts)
- **API:** `https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pubmed&term={query}&rettype=count`
- **Free, no auth required**
- **Use:** Count publications linking space research to each disease area

### 2.8 FDA (for approved therapies)
- **No single API** for this — requires curated research
- **Approach:** Use SerpAPI + OpenRouter/Claude to research known space-derived drugs and devices
- **Known examples to verify:** protein crystallization → drug design, bone loss research → osteoporosis drugs, salmonella vaccine development, water purification tech, LSAH health monitoring devices

---

## 3. Data Pipeline

### 3.1 Architecture
```
scripts/
├── 01_fetch_nasa_osdr.py         # Phase 1: Pull 928 OSDR experiments
├── 02_fetch_research_explorer.py  # Phase 1: Pull broader NASA catalog
├── 03_fetch_esa_jaxa_csa.py      # Phase 1: Pull other agencies
├── 04_deduplicate_merge.py       # Phase 1: Merge all sources, remove duplicates
├── 05_classify_experiments.py    # Phase 2: AI classification against 10 disease areas
├── 06_fetch_clinical_trials.py   # Phase 3: ClinicalTrials.gov search
├── 07_fetch_publications.py      # Phase 3: PubMed publication counts
├── 08_research_therapies.py      # Phase 3: Approved drugs/devices research
├── 09_generate_gap_analysis.py   # Phase 4: AI-generated gap analysis per disease area
└── config.py                     # Shared constants, disease areas, API keys
```

### 3.2 Phase 1: Data Collection
- Run scripts 01-04 sequentially
- Output: `data/processed/all_experiments.csv` — deduplicated master list
- Columns: experiment_id, title, description, agency, mission, year, organism, tissue, PI, institution, publications_count, source_url, raw_source

### 3.3 Phase 2: Classification
- Script 05 reads `all_experiments.csv`
- For each experiment, sends title + description to Claude (via OpenRouter)
- Prompt template:
  ```
  Classify this ISS experiment against these disease areas. Return a JSON object.
  
  Experiment: {title}
  Description: {description}
  
  Disease areas: [list of 10]
  
  For each relevant disease area, assign:
  - relevance: "direct" (explicitly studies this disease), "indirect" (results applicable to this disease), or "none"
  - confidence: 0.0-1.0
  - reasoning: one sentence explaining the connection
  
  If the experiment is not health-related, return {"health_related": false, "category": "..."}.
  ```
- Output: `data/processed/classified_experiments.csv` — adds disease area columns
- Batch size: 50 per run, with checkpoint saves
- Estimated cost: ~$5-15 via OpenRouter

### 3.4 Phase 3: Translational Mapping
- Script 06: Search ClinicalTrials.gov for space-related trials per disease area
- Script 07: Count PubMed publications per disease area × space research
- Script 08: Research approved therapies (SerpAPI + manual curation)
- Output: `clinical_trials.csv`, `publication_counts.csv`, `approved_therapies.csv`

### 3.5 Phase 4: Analysis
- Script 09: For each disease area, generate gap analysis using Claude
- Input: experiment counts, publication counts, clinical trial counts, known therapies
- Output: `gap_analysis.json` — per-disease summaries, recommendations

---

## 4. Dashboard Specification

### 4.1 Tech Stack
- Streamlit (same as RNA dashboard)
- Plotly for charts
- Pandas for data
- Deployed on Streamlit Community Cloud

### 4.2 Layout

**Sidebar:**
- Disease area filter (multiselect, all 10)
- Agency filter (NASA, ESA, JAXA, CSA, Other)
- Year range slider
- Organism filter (Human, Mouse, Rat, Cell line, Other)
- Download buttons (CSV export, full report)

**Tab 1: Overview**
- Total experiment count (big metric)
- Donut chart: experiments by disease area
- Bar chart: experiments by agency
- Timeline: experiments per year
- Treemap: disease area × agency breakdown

**Tab 2: Experiment Explorer**
- Searchable, sortable, filterable data table of all experiments
- Columns: ID, Title, Agency, Year, Disease Areas, Organism, PI, Relevance Score
- Click to expand: full description, publications, source link
- Download filtered results as CSV

**Tab 3: Translational Pipeline**
- Sankey diagram or funnel chart per disease area:
  ISS Experiments → Publications → Clinical Trials → Approved Therapies
- Side-by-side comparison of all 10 disease areas
- Highlight disease areas with strongest vs weakest translation

**Tab 4: Clinical Trials**
- Table of space-related clinical trials from ClinicalTrials.gov
- Filter by disease area, phase, status
- Link to ClinicalTrials.gov entry
- Summary metrics: total trials, by phase, by status

**Tab 5: Approved Therapies & Devices**
- Curated table of FDA-approved drugs/devices with space research origins
- Evidence chain: ISS Experiment → Discovery → Development → Approval
- Filter by disease area

**Tab 6: Gap Analysis**
- Heatmap: disease area × research intensity (experiment count, publication count, trial count)
- Per-disease summary cards: what's been done, what's missing, recommendations
- Radar chart comparing disease areas across dimensions (experiments, publications, trials, therapies)

**Tab 7: Disease Deep-Dive**
- Select one of the 10 SNIH disease areas
- Full narrative summary (AI-generated, with citations)
- Key experiments table
- Key publications
- Relevant clinical trials
- Approved therapies
- Future research recommendations

**Tab 8: Sources & Methods**
- Data sources with links
- Classification methodology
- Last updated timestamp
- API status indicators
- Download raw data

### 4.3 Design Principles
- Clean, professional — this may appear in a publication or policy document
- Publication-quality charts (300 DPI export where possible)
- Every number is traceable to its source
- Arabic RTL support not required (English-language scientific audience)
- Responsive for desktop (primary) and tablet (secondary)
- Color scheme: professional/neutral — blues, grays, accent colors per disease area

### 4.4 Export Features
- CSV export of filtered experiment table
- Full report download (Word .docx) with charts embedded
- Individual chart download (HTML interactive)
- Raw data download (all CSVs in a ZIP)

---

## 5. Project Structure

```
space-health-dashboard/
├── data/
│   ├── raw/                          # Raw API responses (JSON)
│   │   ├── osdr_experiments.json
│   │   ├── research_explorer.json
│   │   ├── esa_experiments.json
│   │   ├── jaxa_experiments.json
│   │   ├── csa_experiments.json
│   │   └── clinical_trials.json
│   ├── processed/                     # Cleaned CSVs for the dashboard
│   │   ├── all_experiments.csv
│   │   ├── classified_experiments.csv
│   │   ├── clinical_trials.csv
│   │   ├── publication_counts.csv
│   │   ├── approved_therapies.csv
│   │   └── gap_analysis.json
│   └── checkpoints/                   # Progress saves for long-running scripts
├── scripts/
│   ├── config.py
│   ├── 01_fetch_nasa_osdr.py
│   ├── 02_fetch_research_explorer.py
│   ├── 03_fetch_esa_jaxa_csa.py
│   ├── 04_deduplicate_merge.py
│   ├── 05_classify_experiments.py
│   ├── 06_fetch_clinical_trials.py
│   ├── 07_fetch_publications.py
│   ├── 08_research_therapies.py
│   └── 09_generate_gap_analysis.py
├── modules/                           # Dashboard helper modules
│   ├── data_loader.py
│   ├── charts.py
│   ├── filters.py
│   ├── report.py
│   └── export.py
├── app.py                             # Streamlit dashboard
├── requirements.txt
├── .env.example
├── .gitignore
├── CLAUDE.md                          # Project documentation for AI assistants
└── README.md
```

---

## 6. Requirements

### 6.1 Python Packages
```
streamlit>=1.32.0,<1.55.0
pandas>=2.0.0
numpy>=1.24.0
plotly>=5.18.0
requests>=2.31.0
python-dotenv>=1.0.0
openai>=1.0.0           # For OpenRouter API (compatible endpoint)
python-docx>=1.1.0      # Word report generation
openpyxl>=3.1.0          # Excel export
tqdm>=4.65.0             # Progress bars for scripts
```

### 6.2 API Keys (in .env)
```
OPENROUTER_API_KEY=     # For experiment classification (Claude via OpenRouter)
SERPAPI_KEY=            # For Research Explorer, ESA, JAXA, CSA data collection
```

### 6.3 Free APIs (no key needed)
- NASA OSDR
- ClinicalTrials.gov
- PubMed E-utilities

---

## 7. Execution Order

| Step | Script | Dependency | Estimated Time | Cost |
|------|--------|------------|----------------|------|
| 1 | 01_fetch_nasa_osdr.py | None | ~15 min (928 API calls) | Free |
| 2 | 02_fetch_research_explorer.py | SerpAPI key | ~30 min | SerpAPI credits |
| 3 | 03_fetch_esa_jaxa_csa.py | SerpAPI key | ~20 min | SerpAPI credits |
| 4 | 04_deduplicate_merge.py | Steps 1-3 complete | <1 min | Free |
| 5 | 05_classify_experiments.py | Step 4 + OpenRouter key | ~30 min | ~$5-15 |
| 6 | 06_fetch_clinical_trials.py | None (runs independently) | ~10 min | Free |
| 7 | 07_fetch_publications.py | None (runs independently) | ~5 min | Free |
| 8 | 08_research_therapies.py | SerpAPI + OpenRouter | ~20 min | ~$2-5 |
| 9 | 09_generate_gap_analysis.py | Steps 5-8 complete | ~10 min | ~$2-5 |
| 10 | Dashboard (app.py) | All data in data/processed/ | Build time | Free |

**Total estimated API cost: $10-25**
**Total estimated time: ~2.5 hours of script execution (largely unattended)**

---

## 8. Quality Controls

### 8.1 Classification Validation
- After AI classification (step 5), manually review a random sample of 50 experiments
- Check for: false positives (tagged with wrong disease), false negatives (missed relevance), correct multi-tagging
- If accuracy < 90%, refine keywords and re-classify

### 8.2 Data Integrity
- Every experiment must have: ID, title, at least one source URL
- Deduplication must preserve the richest metadata version
- Clinical trials must link to valid NCT IDs
- Approved therapies must have verifiable FDA/EMA references

### 8.3 Dashboard Verification
- Every number in the dashboard must trace to a row in the underlying CSV
- Charts must match table data (no aggregation errors)
- Filters must correctly intersect (disease + agency + year)
- Export files must contain the same data shown on screen
