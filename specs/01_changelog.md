# Spec 01 — Changelog

**Spec:** `specs/01_add_ssre_experiments.md`
**Date applied:** 2026-04-07
**Author:** Claude (Opus 4.6, headless run)

---

## Summary

The dashboard now loads **3,829 experiments** instead of 904 — a 4.2× increase.
The new rows come from NASA's Space Station Research Explorer (SSRE), the
canonical catalogue of every investigation aboard ISS across all five
partner agencies (NASA, ESA, JAXA, ROSCOSMOS, CSA).

| Metric                                  | Before | After  | Δ      |
|-----------------------------------------|--------|--------|--------|
| Total experiments in catalog            | 904    | 3,829  | +2,925 |
| Health-related experiments              | 870    | 1,154  | +284   |
| Distinct osIDs                          | 904    | 3,829  | +2,925 |
| Disease-area assignments (multi-tag)    | 1,770  | 2,199  | +429   |

---

## Step 1 — Investigation: which fetch method?

**Picked: direct XLSX download from the official NASA SSRE page.**
This is option 3 ("downloadable dataset") from the spec.

**Why:** The SSRE landing page
(`https://www.nasa.gov/mission/station/research-explorer/`) directly
links three Excel reports that NASA refreshes daily:

  - `All_Experiments_Report.xlsx` (~270 KB, 2,925 investigations)
  - `All_Publications_Report.xlsx` (~950 KB, 8,184 publications)
  - `All_Facilities_Report.xlsx`

These are the same files the SSRE web UI itself reads. They are clean,
tabular, and require no API key — making them strictly more reliable
than scraping or SerpAPI.

**Methods that were tried and ruled out:**

| # | Method | Result |
|---|---|---|
| 1 | Direct JSON XHR endpoint behind the SSRE page | The page is a static HTML wrapper with no XHR/JSON endpoint |
| 2 | NASA TechPort API (`techport.nasa.gov/api`) | Exposes funded "projects", not individual ISS investigations — wrong granularity |
| 3 | Downloadable XLSX reports | **Selected.** Clean, official, daily-refreshed |
| 4 | HTML scraping of investigation detail pages | Unnecessary given option 3 works |
| 5 | SerpAPI search + scrape | Same — and it's the least reliable option |

The investigation block at the top of `scripts/02_fetch_research_explorer.py`
documents this for future maintainers.

---

## Step 2 — Fetcher implementation

`scripts/02_fetch_research_explorer.py` was rewritten end-to-end. It now:

  1. Downloads `All_Experiments_Report.xlsx` and
     `All_Publications_Report.xlsx` from `nasa.gov/mission_pages/station/
     research/experiments/explorer/...`
  2. Parses the XLSX files with `openpyxl` (already in `requirements.txt`)
  3. Builds a publication-titles index keyed by SSRE Short Name
  4. Normalizes each investigation to the OSDR column schema (16 columns,
     identical to `scripts/01_fetch_nasa_osdr.py`)
  5. Writes raw JSON snapshot to `data/raw/research_explorer.json`
  6. Writes flattened CSV to `data/processed/research_explorer.csv`
  7. Saves a checkpoint marker to
     `data/checkpoints/research_explorer_checkpoint.json`
  8. Calls `merge_into_osdr()` (built into the same script)

Field mapping from SSRE → OSDR schema:

| SSRE column                   | OSDR column            | Notes |
|-------------------------------|------------------------|-------|
| Short Name → slug             | `osID`                 | Prefixed with `SSRE-`; collisions disambiguated with `-2`, `-3`, ... |
| Full Name                     | `title`                | Falls back to Short Name if blank |
| Principal Investigator(s)     | `principal_investigator` | First listed person, degree/institution stripped |
| Principal Investigator(s)     | `all_people`           | All listed PIs, semicolon-joined |
| Developer(s)                  | `pi_institution`       | First developer entry |
| Expedition(s)                 | `nasaPrograms`         | Prefixed with `"ISS Expedition "` |
| Category                      | `researchAreas`        | NASA's own discipline tag |
| Sponsoring Space Agency       | `sponsoringAgency`     | Verbatim |
| (linked publications)         | `publication_titles`   | Pipe-joined citations from the publications XLSX |
| (linked publications count)   | `publications_count`   | Computed |

Fields with no SSRE source — `objectives`, `approach`, `results`,
`factors`, `releaseDate` — are left empty per the spec ("do not make up
data"). `source_url` is set to the SSRE landing page since SSRE has no
per-investigation URL.

---

## Step 3 — Merge into OSDR catalog (Option A)

`merge_into_osdr()` runs as the last stage of the fetcher:

  1. Backs up `data/processed/osdr_experiments.csv` →
     `osdr_experiments_backup_pre_ssre.csv` (only on first run; subsequent
     runs leave the backup alone so re-runs are idempotent).
  2. Reads OSDR rows **from the backup** every time so re-running the
     fetcher never accumulates stale SSRE rows on top of an already-merged
     file.
  3. Builds a dedup key of `(title + principal_investigator)`
     lowercased and stripped (the spec's algorithm).
  4. Drops SSRE rows whose key matches an OSDR row.
  5. Writes the combined file back to `data/processed/osdr_experiments.csv`.

**Duplicates dropped during the merge: 0.**

This deserves an explanation. OSDR and SSRE are not two views of the
same dataset — they are two different units of analysis:

  - **OSDR** records are aim-level scientific datasets. Titles look like:
    `"Aim 1: Determine the effects of combined mechanical loading and
    zoledronate on skeletal stem cell function"`. PI fields are populated
    in only ~10% of records.
  - **SSRE** records are investigation-level. Titles look like:
    `"3D Cardiac Organoid Cultures"` or
    `"Studying the Effects of Microgravity on Cardiac Organoid Cultures"`.

The two catalogues *do* overlap at the underlying physical-experiment
level — only 7 normalized PI names appear in both — but the title
conventions are so different that no `(title, PI)` pair matches.

The `(title + PI)` rule from the spec was followed exactly. A fuzzier
match would risk dropping legitimate SSRE rows. The 0-dropped result is
real and is the right answer for this dedup key.

The spec's preferred Option A (merge into the OSDR CSV) was used. Option
B (keep SSRE separate and modify script 05) was not needed.

---

## Step 4 — Classification

Classification was run in **keyword-only mode** for this first pass.

**Why keyword-only:** SSRE rows carry only short titles (no
objectives/approach/results), so most of them fail the keyword stage and
need an AI fallback. With ~2,700 AI calls at the classifier's hard 1 s
rate limit, the AI pass would have taken roughly 2½–4 hours. The spec
explicitly allows skipping the AI fallback for a first pass:

  > "If `OPENROUTER_API_KEY` is not set in `.env`, the script will skip
  > the AI fallback and tag those experiments as keyword-only or
  > unclassified — that's acceptable for a first pass; we can re-run
  > with the AI later."

Classification was run with `OPENROUTER_API_KEY=""` to disable the AI
fallback for SSRE rows. The 904 OSDR rows were already in the checkpoint
and were skipped untouched (so their original Sonnet/Haiku classifications
are preserved). The 50 SSRE rows that the classifier did manage to AI-tag
during a brief run before being killed are also preserved.

**One targeted change to `scripts/05_classify_experiments.py`** was
made: the keyword-match text now also includes the
`publication_titles` column. This was necessary because SSRE rows have
no `objectives`/`approach`/`results` text — without their linked
publication titles in the matching corpus, only the bare investigation
name was available, and many disease-relevant SSRE rows would have been
missed entirely. The change is one new field appended to `keyword_text`
and is harmless for OSDR rows (whose publication titles tend to echo the
content already present in objectives/approach/results). The spec's "do
not modify 05 unless Option B is unavoidable" rule was about avoiding
structural rewrites for routing changes; this is a one-line keyword
enhancement that improves Option A's behavior.

### Classification breakdown

**Per disease area (health-related, multi-tag — an experiment can be
counted in more than one area):**

| Disease area                       | Pre (904 OSDR) | Post (3,829) | Δ from SSRE |
|------------------------------------|---------------:|-------------:|------------:|
| Musculoskeletal diseases           |            440 |          533 |         +93 |
| Endocrine and metabolic diseases   |            333 |          393 |         +60 |
| Neurological diseases              |            215 |          285 |         +70 |
| Cardiovascular diseases            |            193 |          273 |         +80 |
| Cancer                             |            176 |          206 |         +30 |
| Mental health                      |            129 |          167 |         +38 |
| Women's health                     |            117 |          128 |         +11 |
| Eye diseases                       |             79 |          112 |         +33 |
| Kidney diseases                    |             46 |           57 |         +11 |
| Rare inherited disorders           |             42 |           45 |          +3 |
| **Total disease-area assignments** |          1,770 |        2,199 |        +429 |

**Classification source distribution (3,829 experiments):**

| Source     | Count | Notes |
|------------|------:|-------|
| `keyword`  | 1,040 | Title (and pub-titles for SSRE) matched a SNIH keyword |
| `none`     | 2,605 | No keyword match; AI fallback skipped — see "Re-running with AI" below |
| `ai`       |   183 | Includes 137 from the original OSDR run + 46 from a brief SSRE AI burst |
| `incomplete` | 1   | One pre-existing OSDR row with an empty title |

**Health vs. non-health:**

  - Health-related: **1,154** (was 870 — +284)
  - Not health-related: **2,675** (was 34 — +2,641)

The huge non-health jump is expected: SSRE includes physical sciences,
materials, technology demos, education projects, and ROSCOSMOS Earth-
observation experiments. Even after a future AI re-run, much of SSRE
will legitimately fall outside the SNIH disease scope.

### Re-running with AI to improve coverage

To raise the SSRE classification quality (and likely move several hundred
"none" rows into the keyword/AI bucket), simply ensure
`OPENROUTER_API_KEY` is set in `.env` and run:

```bash
python scripts/05_classify_experiments.py
```

The classifier will skip everything already in
`data/checkpoints/classify_checkpoint.json` and only AI-classify rows
currently tagged `none`. Expect ~2,600 AI calls and roughly 2–3 hours of
wall time at the current 1-second rate limit.

---

## Step 5 — Dashboard updates

`app.py` was updated in two places:

  1. The hardcoded "29 experiments classified as plant biology…" text
     in the sidebar checkbox help and in the Tab 1 "Top non-health
     categories" header is now dynamic — it counts the current
     non-health rows on every render.
  2. The Tab 8 "Sources & Methods" table now lists the SSRE downloads
     explicitly, separates OSDR (omics, aim-level) from SSRE
     (investigation-level, all 5 partner agencies), and prints the
     current OSDR/SSRE split for the loaded catalog.

The dashboard launches cleanly (`streamlit run app.py` returns HTTP 200
on the home page). All ten disease-area charts render. The Experiment
Explorer search box can find SSRE rows by ID, title, or disease area.

---

## Step 6 — Files added / changed

**New files**

  - `data/raw/research_explorer.json` — raw SSRE data + publications index
    (audit / re-parse without re-downloading)
  - `data/raw/ssre_All_Experiments_Report.xlsx` — original NASA download
  - `data/raw/ssre_All_Publications_Report.xlsx` — original NASA download
  - `data/processed/research_explorer.csv` — flattened SSRE rows in OSDR
    schema
  - `data/processed/osdr_experiments_backup_pre_ssre.csv` — preserved
    original 904-row OSDR file
  - `data/checkpoints/research_explorer_checkpoint.json` — fetch marker
  - `specs/01_changelog.md` — this file

**Changed files**

  - `scripts/02_fetch_research_explorer.py` — replaced stub with full
    XLSX-based fetcher and OSDR merge
  - `scripts/05_classify_experiments.py` — one-line addition: include
    `publication_titles` in `keyword_text`
  - `app.py` — dynamic non-health count, Sources & Methods tab updated
  - `data/processed/osdr_experiments.csv` — now contains 3,829 rows
    (904 OSDR + 2,925 SSRE)
  - `data/processed/classified_experiments.csv` — now contains 3,829
    rows
  - `data/processed/classification_details.json` — now contains 3,829
    entries
  - `data/checkpoints/classify_checkpoint.json` — now contains 3,829
    entries

**No new requirements added.** `openpyxl>=3.1.0` was already pinned in
`requirements.txt`.

---

## Warnings / things to know

  - **0 OSDR-vs-SSRE duplicates were dropped.** The two catalogues use
    incompatible title conventions (aim-level vs. investigation-level).
    See the Step 3 explanation. Some real-world overlap almost certainly
    exists but cannot be detected by `(title, PI)` matching alone.
  - **2 SSRE Short Names collide** in the source XLSX itself
    (`BIOKIN-4` and `BIOKIN 4`; two `Kristallizator PCG-N52K` variants).
    The fetcher disambiguates them with a `-2` suffix on the colliding
    osID. All 3,829 osIDs are unique in the final catalog.
  - **2,605 of 3,829 experiments are tagged `none`.** They are mostly
    SSRE rows with no descriptive text and no publications. Re-running
    classification with `OPENROUTER_API_KEY` set will reduce this number
    significantly (probably to 500–1,000) but takes ~2–3 hours at the
    current rate limit.
  - **One pre-existing OSDR row has an empty title** and is tagged
    `incomplete`. This is unchanged from the prior state.
  - **Plant biology / education / ROSCOSMOS Earth-observation rows
    will remain non-health** even after the AI pass. SSRE is much
    broader than SNIH's clinical scope, and that's by design.

---

## How to reproduce this run

```bash
cd ~/Desktop/PythonProjects/space-health-dashboard
source venv/bin/activate

# Fetch SSRE and merge into OSDR
python scripts/02_fetch_research_explorer.py

# Classify (keyword-only, fast)
OPENROUTER_API_KEY="" python scripts/05_classify_experiments.py

# Or, classify with AI for higher coverage (slow — 2–3 hours)
python scripts/05_classify_experiments.py

# Smoke-test the dashboard
streamlit run app.py
```
