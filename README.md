# Space-Health Dashboard

Mapping ISS research to SNIH priority disease areas, and tracing the
translational pipeline from microgravity experiments to clinical trials and
approved therapies.

> Built for the Saudi National Institute of Health (SNIH) at KFCRIS.

## What it does

Over 4,000 research investigations have been conducted aboard the International
Space Station since 2000 by NASA, ESA, JAXA, and CSA. This project:

1. **Collects** experiment metadata from NASA OSDR, NASA Research Explorer,
   ESA EEA, JAXA, and CSA.
2. **Classifies** each experiment against the 10 SNIH disease areas using
   Claude (via OpenRouter).
3. **Traces** translational impact through PubMed publications,
   ClinicalTrials.gov entries, and approved FDA/EMA therapies.
4. **Surfaces gaps** — disease areas with insufficient ISS research given
   their burden on Saudi public health.
5. **Presents** everything in an interactive Streamlit dashboard.

## SNIH disease areas

1. Cardiovascular diseases
2. Kidney diseases
3. Cancer
4. Neurological diseases
5. Eye diseases
6. Rare inherited disorders
7. Women's health
8. Endocrine and metabolic diseases
9. Musculoskeletal diseases
10. Mental health

Full keyword expansions live in `scripts/config.py`.

## Data sources

| Source | URL |
|---|---|
| NASA OSDR | <https://osdr.nasa.gov> |
| NASA Space Station Research Explorer | <https://www.nasa.gov/mission/station/research-explorer/> |
| ESA Erasmus Experiment Archive | <https://eea.spaceflight.esa.int> |
| JAXA Space Experiment Database | <https://humans-in-space.jaxa.jp/en/bss/experiment/> |
| CSA Experiments | <https://www.asc-csa.gc.ca/eng/sciences/experiments/> |
| ClinicalTrials.gov | <https://clinicaltrials.gov/api/v2/studies> |
| PubMed E-utilities | <https://eutils.ncbi.nlm.nih.gov/entrez/eutils/> |

## Setup

```bash
git clone <repo-url>
cd space-health-dashboard
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then add your API keys
```

Phase 1 scripts (01, 06, 07) need no API keys — only Phase 2+ require
`OPENROUTER_API_KEY` and `SERPAPI_KEY`.

## Usage

```bash
# Collect data
python scripts/01_fetch_nasa_osdr.py
python scripts/06_fetch_clinical_trials.py
python scripts/07_fetch_publications.py

# Launch dashboard
streamlit run app.py
```

See `CLAUDE.md` for the full pipeline order and `SPACE_HEALTH_SPECS.md` for
the complete specification.

## Dashboard

(Screenshot: TODO once data is in.)

The dashboard ships with eight tabs: Overview, Experiment Explorer,
Translational Pipeline, Clinical Trials, Approved Therapies & Devices,
Gap Analysis, Disease Deep-Dive, and Sources & Methods.

## License

Internal SNIH / KFCRIS project. Data is sourced from publicly available APIs
and remains the property of the originating agencies.
