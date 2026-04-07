# Space-Health Dashboard — Project Notes for AI Assistants

This project maps ISS experiments to the 10 SNIH disease areas, traces the
translational pipeline (publications → clinical trials → approved therapies),
and presents the results in a Streamlit dashboard.

The complete specification lives in `SPACE_HEALTH_SPECS.md` at the project
root. **Read it before doing anything non-trivial.** Sections referenced
below correspond to that file.

---

## Architecture (Section 5)

```
space-health-dashboard/
├── data/raw/           # Raw API JSON responses (gitignored — regenerable)
├── data/processed/     # Cleaned CSVs that the dashboard reads
├── data/checkpoints/   # Resume state for long-running fetchers (gitignored)
├── scripts/            # config.py + 9 numbered pipeline scripts
├── modules/            # Dashboard helpers (data_loader, charts, filters, ...)
├── app.py              # Streamlit dashboard
└── SPACE_HEALTH_SPECS.md
```

`scripts/config.py` is the single source of truth for disease areas, API
endpoints, paths, and rate limits. Every script imports from there.

---

## Data flow

```
01_fetch_nasa_osdr.py ─┐
02_fetch_research_explorer.py ─┤
03_fetch_esa_jaxa_csa.py ─┘  → 04_deduplicate_merge.py → all_experiments.csv
                                                                │
                                                                ▼
                                            05_classify_experiments.py (OpenRouter/Claude)
                                                                │
                                                                ▼
                                                  classified_experiments.csv
                                                                │
06_fetch_clinical_trials.py  → clinical_trials.csv              │
07_fetch_publications.py     → publication_counts.csv           │
08_research_therapies.py     → approved_therapies.csv           │
                                                                ▼
                                  09_generate_gap_analysis.py → gap_analysis.json
                                                                │
                                                                ▼
                                                            app.py (Streamlit)
```

---

## How to run

```bash
cd ~/Desktop/PythonProjects/space-health-dashboard
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Phase 1 — data collection (free APIs first)
python scripts/01_fetch_nasa_osdr.py
python scripts/06_fetch_clinical_trials.py
python scripts/07_fetch_publications.py

# Phase 1 (continued, requires SERPAPI_KEY in .env)
python scripts/02_fetch_research_explorer.py
python scripts/03_fetch_esa_jaxa_csa.py
python scripts/04_deduplicate_merge.py

# Phase 2 — AI classification (requires OPENROUTER_API_KEY)
python scripts/05_classify_experiments.py

# Phase 3 — translational mapping
python scripts/08_research_therapies.py

# Phase 4 — gap analysis
python scripts/09_generate_gap_analysis.py

# Dashboard
streamlit run app.py
```

All numbered scripts are safe to re-run. Long-running fetchers checkpoint to
`data/checkpoints/` and resume from where they stopped.

---

## API dependencies

| Source | Auth | Used by |
|---|---|---|
| NASA OSDR (`osdr.nasa.gov`) | Free, no key | 01 |
| NASA Research Explorer | Web — via SerpAPI | 02 |
| ESA / JAXA / CSA | Web — via SerpAPI | 03 |
| ClinicalTrials.gov v2 API | Free, no key | 06 |
| PubMed E-utilities | Free, no key | 07 |
| OpenRouter (Claude) | `OPENROUTER_API_KEY` | 05, 08, 09 |
| SerpAPI | `SERPAPI_KEY` | 02, 03, 08 |

Phase 1 scripts 01, 06, and 07 work with no API keys at all.

---

## Quality controls (Section 8)

- After classification (script 05), spot-check ~50 experiments. If accuracy
  drops below 90%, refine keywords in `config.py` and re-run.
- Every experiment must carry an ID, a title, and at least one source URL.
- Every dashboard number must trace back to a row in a processed CSV.

---

## Conventions

- Imperative, dependency-light Python. No clever frameworks.
- Use `tqdm` for progress in long loops.
- Always write JSON via `config.save_json` (atomic write).
- Identify the project to remote APIs via `config.REQUEST_HEADERS`.
- Disease area names must match `config.DISEASE_AREA_NAMES` exactly — never
  hard-code them in individual scripts.
