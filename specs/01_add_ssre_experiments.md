# Spec 01 — Add NASA Space Station Research Explorer (SSRE) Experiments

## Context

The Space-Health Dashboard currently contains 904 experiments fetched from NASA's Open Science Data Repository (OSDR). OSDR is an omics-focused subset of ISS research and represents only ~25% of the experiments actually conducted on the International Space Station. The full NASA catalog — the **Space Station Research Explorer (SSRE)** — contains ~3,000+ experiments across all disciplines (biology, human research, physical science, technology, education).

The dashboard's audience is leadership at the Saudi National Institute of Health (SNIH). For that audience, showing 904 experiments when the real number is ~3,500 across NASA/ESA/JAXA/CSA undermines credibility. This spec addresses the largest of those gaps: adding the missing NASA experiments from SSRE.

A placeholder script already exists at `scripts/02_fetch_research_explorer.py`. It is a stub. **Replace its body with a working implementation per this spec.** Do not delete the file or rename it — other scripts and the spec doc reference its current path.

## Goal

Fetch all NASA Space Station Research Explorer investigations, normalize them to match the existing OSDR experiment schema, deduplicate against the existing OSDR data, run them through the existing classification pipeline, and refresh the dashboard so it reflects the combined dataset.

Done means: the dashboard loads, shows ~3,000+ experiments instead of 904, and every new experiment has a disease-area classification.

## Inputs you have access to

- The full project at the current working directory
- `scripts/01_fetch_nasa_osdr.py` — reference for how OSDR fetching is structured
- `scripts/02_fetch_research_explorer.py` — placeholder you will replace
- `scripts/05_classify_experiments.py` — classification pipeline that runs against `data/processed/osdr_experiments.csv`. Note this file name; see "Output schema" below.
- `data/processed/osdr_experiments.csv` — the existing 904-experiment file (schema reference)
- `data/processed/classification_details.json` — existing classifications (do not lose these)
- `.env` — may contain `OPENROUTER_API_KEY`, `SERPAPI_KEY`. Read but do not write.

## Step 1 — Investigate the best way to fetch SSRE data

Before writing any fetch code, **investigate which of these access methods is most reliable**, in this order of preference:

1. **Direct web endpoint.** Visit `https://www.nasa.gov/mission/station/research-explorer/` and inspect the page in your browser tools. The site is a frontend on top of some data source — check the network tab for JSON/XHR requests it makes when you filter or paginate. If you find a clean JSON endpoint, use it directly. This is by far the best option.
2. **NASA TechPort API.** NASA also publishes investigation data through TechPort (`https://techport.nasa.gov/api`). Check whether SSRE investigations are exposed there.
3. **Downloadable dataset.** Check `data.nasa.gov` and the NASA Open Data Portal for a published SSRE dataset (CSV, JSON, or similar).
4. **HTML scraping.** If none of the above work, fall back to scraping the SSRE web pages directly.
5. **SerpAPI search + scrape** (what the current stub assumes). Use this only if all of the above fail. It requires a paid SerpAPI key and is the least reliable option.

**Document your investigation in a comment block at the top of the new `02_fetch_research_explorer.py` so future maintainers know why you picked the method you did.** Two or three sentences is enough.

## Step 2 — Implement the fetcher

Write the fetcher in `scripts/02_fetch_research_explorer.py`. Match the style of `scripts/01_fetch_nasa_osdr.py`:

- Use the same `requests.Session` setup with retries
- Use the same `config.py` imports for paths, headers, and env loading
- Write a checkpoint file to `data/checkpoints/research_explorer_checkpoint.json` so the script is resumable
- Save raw JSON responses to `data/raw/research_explorer.json`
- Save the flattened, normalized CSV to `data/processed/research_explorer.csv`
- Log progress every 25 records: `[ssre] Fetched X/Y: <experiment_id>`
- Handle network errors gracefully — log and continue, don't crash

For each experiment, extract whatever the source provides for the following fields. If a field is unavailable from SSRE, leave it empty — do **not** make up data:

- experiment_id (NASA's internal ID for the investigation)
- title
- objectives / summary / description (whichever the source provides; collapse into one `objectives` field)
- approach / methodology (if available)
- results / findings (if available)
- principal_investigator
- pi_institution
- sponsoring_agency (likely "NASA" for all rows but capture the actual value)
- research_areas / discipline / category
- nasa_programs / mission
- publications_count (if available)
- publication_titles (if available, joined by `; `)
- release_date / start_date
- source_url (the canonical SSRE URL for the investigation)

## Step 3 — Output schema (CRITICAL)

The classification script (`05_classify_experiments.py`) reads from `data/processed/osdr_experiments.csv` and expects a specific column layout. To make the new SSRE experiments flow through the existing pipeline without rewriting downstream code, you have two options. **Pick option A unless you find a strong reason not to:**

**Option A — Merge SSRE into the OSDR CSV (preferred).**

Add a new step in `scripts/02_fetch_research_explorer.py` (or a small new helper script `scripts/02b_merge_ssre_into_osdr.py`) that:

1. Reads `data/processed/osdr_experiments.csv` and `data/processed/research_explorer.csv`
2. Normalizes the SSRE rows to match the OSDR column schema exactly. The OSDR columns are:
   ```
   osID, title, objectives, approach, results, sponsoringAgency,
   researchAreas, nasaPrograms, factors, publications_count,
   publication_titles, principal_investigator, pi_institution,
   all_people, releaseDate, source_url
   ```
3. Use a prefix like `SSRE-` for the `osID` of SSRE rows so they don't collide with OSDR's `OS-XXX` IDs
4. **Deduplicate.** OSDR experiments are sometimes also listed in SSRE. Match on `(title + principal_investigator)` lowercased and stripped — if a match is found, prefer the OSDR row (it has more structured fields). Log how many duplicates were dropped.
5. Write the combined file to `data/processed/osdr_experiments.csv`, **but first back up the original to `data/processed/osdr_experiments_backup_pre_ssre.csv`**. Do not lose the existing data.

**Option B — Keep SSRE as a separate file.**

Only do this if you find that the SSRE and OSDR schemas are fundamentally incompatible. In that case, you'll also need to update `scripts/05_classify_experiments.py` to read from both files, and update `modules/data_loader.py` to load both. This is more invasive — only do it if Option A genuinely won't work.

## Step 4 — Run classification on the new experiments

After the merge, run `python scripts/05_classify_experiments.py`. The classification script already supports checkpoint-based resumption — it will skip the existing 904 OSDR experiments (because their results are already in `data/checkpoints/classify_checkpoint.json`) and only classify the new SSRE rows.

**Important:** The classification script makes AI calls via OpenRouter for experiments that don't get a keyword match. With ~2,000 new experiments, expect 200–400 AI calls (~5–10 minutes at the current 1-second rate limit). If `OPENROUTER_API_KEY` is not set in `.env`, the script will skip the AI fallback and tag those experiments as keyword-only or unclassified — that's acceptable for a first pass; we can re-run with the AI later.

After classification completes, verify:
- `data/processed/classified_experiments.csv` exists and has roughly 3,000+ rows
- `data/processed/classification_details.json` has been updated
- The breakdown printed by the script shows non-zero counts for every disease area

## Step 5 — Refresh the dashboard

Run `streamlit run app.py` locally (or just confirm the data files load) and verify:
- The total experiment count on the home page is now ~3,000+
- Every disease area chart still renders without errors
- The Experiment Explorer page can filter and display SSRE rows
- The "data sources" section of the dashboard mentions both OSDR and SSRE

If the dashboard hard-codes "904 experiments from NASA OSDR" anywhere in the UI text, update it to reflect the new combined number and source list.

## Step 6 — Update the methods document

There is a methods document at `space-health-methods.docx` (or in the user's uploads folder). **Do not edit the docx directly.** Instead, write a short markdown file at `specs/01_changelog.md` that summarizes:

- The new total experiment count (e.g., "3,127 experiments: 904 from OSDR + 2,223 from SSRE, deduplicated")
- The investigation method you picked in Step 1 and why
- How many duplicates were dropped during the merge
- Classification breakdown (how many SSRE experiments fell into each disease area)
- Any errors or skipped records

The user (or I) will fold this changelog into the methods doc later.

## Done criteria

Before declaring this spec complete, verify ALL of the following:

- [ ] `scripts/02_fetch_research_explorer.py` is no longer a stub — it runs end-to-end and exits with code 0
- [ ] `data/raw/research_explorer.json` exists and is non-empty
- [ ] `data/processed/research_explorer.csv` exists with at least 1,000 rows
- [ ] `data/processed/osdr_experiments_backup_pre_ssre.csv` exists (the backup of the original)
- [ ] `data/processed/osdr_experiments.csv` now contains both OSDR and SSRE rows
- [ ] `data/processed/classified_experiments.csv` reflects the combined dataset
- [ ] `data/processed/classification_details.json` reflects the combined dataset
- [ ] `streamlit run app.py` launches without errors and the home page shows the new count
- [ ] `specs/01_changelog.md` exists and summarizes what changed
- [ ] No existing test or script is broken — run any existing tests if they exist

## What NOT to do

- Do **not** delete or rename `scripts/02_fetch_research_explorer.py` — replace its body
- Do **not** delete the existing `data/processed/osdr_experiments.csv` without backing it up first
- Do **not** modify `scripts/05_classify_experiments.py` unless Option B is unavoidable. Its current behavior is what we want.
- Do **not** modify `scripts/01_fetch_nasa_osdr.py` — leave OSDR fetching alone
- Do **not** invent or hallucinate experiment data. If a field is unavailable from the source, leave it empty.
- Do **not** rerun the existing 904 OSDR classifications. The checkpoint system will skip them — let it.
- Do **not** commit anything to git. The user will review and commit manually.
- Do **not** edit `space-health-methods.docx`. Write the changelog as markdown instead.
- Do **not** add new top-level dependencies to `requirements.txt` unless absolutely necessary. If you must add one (e.g., `beautifulsoup4` for HTML scraping), justify it in your PR-style summary at the end.

## When finished, report back

At the end of the run, print a concise summary that includes:

1. Which fetch method you chose in Step 1 and a one-line reason
2. Total SSRE experiments fetched
3. Duplicates dropped during the merge
4. New combined experiment total
5. New AI classification calls made (if any)
6. Per-disease-area counts (before vs. after)
7. Any warnings or skipped records the user should know about
8. Confirmation that the dashboard launched successfully

This summary is what the user will paste back into the chat with me, so make it readable and self-contained.
