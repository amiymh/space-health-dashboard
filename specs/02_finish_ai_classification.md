# Spec 02 — Finish AI Classification on Unclassified SSRE Experiments

## Context

After Spec 01 ran, `data/processed/classified_experiments.csv` contains 3,829 experiments (904 OSDR + 2,925 SSRE). The classification pipeline (`scripts/05_classify_experiments.py`) ran end-to-end but **2,605 experiments are still tagged `none`** because the AI fallback step was skipped or rate-limited during the SSRE run. Current breakdown:

- `none`: 2,605 (need AI)
- `keyword`: 1,040
- `ai`: 183
- `incomplete`: 1

Health-related experiments today: 1,154 out of 3,829. The real number is almost certainly much higher — many of those 2,605 "none" rows are biology, human research, and life science investigations whose titles just didn't trip the keyword list.

The dashboard is being shown to leadership at the Saudi National Institute of Health. Showing a 3,829-experiment headline while only ~30% are mapped to disease areas undermines the whole point of the project. This spec finishes the job.

## Goal

Run the AI classifier against every experiment currently tagged `none` (or `incomplete`) so that all 3,829 experiments end up with either a disease-area assignment or a confident "not health-related" tag. After this spec runs, the disease-area totals on the dashboard should fully reconcile with the headline experiment count.

## Inputs you have access to

- `scripts/05_classify_experiments.py` — the existing classifier. Two-stage: keyword match first, then AI via OpenRouter. Has checkpoint resumption via `data/checkpoints/classify_checkpoint.json`.
- `data/processed/classified_experiments.csv` — current state (3,829 rows)
- `data/processed/classification_details.json` — per-experiment classification details
- `data/checkpoints/classify_checkpoint.json` — resume state
- `data/processed/osdr_experiments.csv` — source data (904 OSDR + 2,925 SSRE)
- `.env` — must contain `OPENROUTER_API_KEY`. If it doesn't, stop and tell the user before doing anything else.

## Step 1 — Diagnose why 2,605 SSRE rows are still `none`

Before re-running anything, figure out why those rows weren't AI-classified the first time. Likely causes:

1. **`OPENROUTER_API_KEY` was missing** during the Spec 01 run → script silently skipped AI fallback
2. **Rate limiting / timeout** → script gave up partway through
3. **Empty input fields** → SSRE rows with empty `objectives` and `publication_titles` got dropped before reaching the AI step
4. **Checkpoint state already says "done"** → script thinks it's finished and won't retry

Read `scripts/05_classify_experiments.py` carefully and identify which of these is happening. Look at:
- How the script decides whether to call the AI
- How `none` results are written to the checkpoint
- Whether `none` results are re-tried on subsequent runs or skipped

**Document your finding in 3–5 lines at the top of the changelog you'll write in Step 5.**

## Step 2 — Make the classifier re-process `none` rows

Modify `scripts/05_classify_experiments.py` so that on this run, rows currently tagged `none` or `incomplete` get re-classified through the AI fallback. Two acceptable approaches:

**Approach A (preferred): add a `--retry-none` flag**

Add a CLI flag `--retry-none` that, when set, causes the script to:
- Load existing classifications from the checkpoint as normal
- But treat any row with `classification_method == 'none'` or `'incomplete'` as if it had no checkpoint entry — i.e., re-run keyword + AI on it
- Preserve all existing `keyword` and `ai` classifications untouched

**Approach B: a one-shot helper script**

If modifying `05_classify_experiments.py` cleanly is hard, create `scripts/05b_retry_unclassified.py` that:
- Reads `classified_experiments.csv`
- Filters to rows where `classification_method` is `none` or `incomplete`
- Calls the same AI classification function from `05_classify_experiments.py` (import it; do not duplicate the prompt or model logic)
- Writes the updated rows back into `classified_experiments.csv` and `classification_details.json`

Either way, **do not duplicate the prompt template, model selection, or disease-area definitions** — import them from the existing module. The whole point is that this run uses the same logic that produced the existing 183 `ai` classifications, just applied to more rows.

## Step 3 — Run it

Run the AI classification on the 2,605 unclassified rows. Expectations:

- ~2,605 AI calls
- At the current rate limit (~1 call/sec) this should take 45–60 minutes
- Estimated cost: $10–$20 in OpenRouter credits depending on model. The existing script uses Claude Sonnet 4.5 with Haiku 4.5 fallback — keep that exact configuration. Do not switch models to save money.
- Log progress every 50 records: `[ai-retry] Classified X/2605 (Y health, Z not-health)`
- Save checkpoints frequently so a crash doesn't lose progress
- Handle API errors gracefully — log, sleep, retry up to 3 times, then mark as `incomplete` and move on. **Do not crash the whole run on a single API failure.**

If `OPENROUTER_API_KEY` is missing or invalid, **stop immediately** and report it. Do not silently fall back to keyword-only classification.

## Step 4 — Verify

After the run completes, verify all of the following:

- [ ] `classified_experiments.csv` still has exactly 3,829 rows (no rows added or lost)
- [ ] The number of rows tagged `none` has dropped substantially (target: < 500, ideally < 200)
- [ ] The number of `ai` classifications has increased by roughly the number that were `none` before
- [ ] All 10 disease-area columns still have non-zero counts
- [ ] `classification_details.json` has been updated with the new classifications
- [ ] No existing `keyword` or `ai` classifications were overwritten or lost (compare row counts before/after for each method)

Print a before/after table of disease-area counts.

## Step 5 — Write a changelog

Append (do not overwrite) to `specs/01_changelog.md`, OR create a new file `specs/02_changelog.md`. Either works. Include:

1. Your diagnosis from Step 1 (why the 2,605 rows were `none`)
2. The approach you picked in Step 2 (A or B) and why
3. Total AI calls made
4. Approximate API cost
5. Before/after disease-area counts (10 rows, two columns)
6. Final classification-method breakdown (`keyword` / `ai` / `none` / `incomplete`)
7. Any rows that ended up `incomplete` and why
8. Approximate runtime

## Done criteria

- [ ] Every experiment in `classified_experiments.csv` has been through both keyword and AI classification (or is explicitly marked `incomplete` with a reason)
- [ ] `none` count is < 500
- [ ] All 10 disease-area columns reflect the full 3,829-row dataset
- [ ] Dashboard launches via `streamlit run app.py` and the home page totals reconcile (sum of disease-area counts should be close to total health-related count)
- [ ] Changelog written

## What NOT to do

- Do NOT re-run keyword classification on rows that already have `keyword` or `ai` results — only touch the `none` and `incomplete` rows
- Do NOT change the AI prompt template, the disease area definitions, or the model selection. Use what's already in `05_classify_experiments.py`.
- Do NOT modify `osdr_experiments.csv` — this spec is read-only on the source data
- Do NOT delete `classification_details.json` — append/update only
- Do NOT commit anything to git
- Do NOT skip AI fallback if the key is missing — stop and report instead
- Do NOT batch AI calls in parallel — keep the existing sequential 1-call-per-second pacing to avoid OpenRouter rate limits

## When finished, report back

Print a self-contained summary the user can paste back:

1. Diagnosis of why 2,605 rows were unclassified
2. Approach used (A or B)
3. AI calls made / approximate cost / runtime
4. Before/after disease area counts
5. Final method breakdown
6. Any warnings
7. Confirmation the dashboard launches and totals reconcile
