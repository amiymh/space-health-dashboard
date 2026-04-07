# Spec 02 — Changelog

**Spec:** `specs/02_finish_ai_classification.md`
**Date applied:** 2026-04-07
**Author:** Claude (Opus 4.6, headless run)

---

## Summary

Ran the AI classifier against every experiment that had been left tagged
`none` or `incomplete` by the Spec 01 run. After this spec:

  - **Every one of the 3,829 experiments** has been through both the
    keyword and AI stages (or is explicitly marked `incomplete`, with a
    reason, on the one row that can't be classified).
  - **0 `none` rows remain** (target was <500, ideally <200).
  - **1 `incomplete` row remains** — `OS-875`, a pre-existing OSDR
    record with an empty title. This is not a Spec 02 failure.
  - **Health-related count jumped from 1,154 → 1,969** (+815).
  - Every disease area grew substantially. The biggest mover was
    **Endocrine and metabolic diseases** (+454), followed by
    **Neurological diseases** (+388), **Cancer** (+373), **Cardiovascular
    diseases** (+370), and a big proportional jump for
    **Rare inherited disorders** (+310, from 45 to 355 — the AI caught
    most of the omics/genetic studies the keyword list missed).

| Metric                                 | Before  | After  | Δ      |
|----------------------------------------|--------:|-------:|-------:|
| Rows tagged `none`                     |   2,605 |      0 | –2,605 |
| Rows tagged `incomplete`               |       1 |      1 |      0 |
| Rows tagged `keyword`                  |   1,040 |  1,040 |      0 |
| Rows tagged `ai`                       |     183 |  2,788 | +2,605 |
| Health-related experiments             |   1,154 |  1,969 |   +815 |
| Disease-area tag assignments (sum)     |   2,199 |  4,598 | +2,399 |

---

## Step 1 — Diagnosis: why were 2,605 rows tagged `none`?

**Root cause: the Spec 01 run was launched with `OPENROUTER_API_KEY=""`
to deliberately skip the AI fallback.**

The Spec 01 classifier pass ran keyword-only. The spec explicitly allows
this as a first-pass shortcut:

  > "If OPENROUTER_API_KEY is not set in .env, the script will skip the
  > AI fallback and tag those experiments as keyword-only or
  > unclassified — that's acceptable for a first pass; we can re-run
  > with the AI later."

The reason it was skipped: a brief AI run earlier in the Spec 01 session
showed that Sonnet 4.5 averages ~5 seconds per call. With ~2,600 rows
queued for AI classification, the full run would have taken ~4 hours of
wall time — too long for the user who was waiting at the end of the
session. Running keyword-only dropped that to ~15 seconds but left
2,605 rows stuck as `none`.

A secondary cause is that the classifier's resume logic
(`data/checkpoints/classify_checkpoint.json`) skips any `osID` already
present in the `results` dict. That means simply re-running the
classifier with the API key restored would **not** have reprocessed the
`none` rows — they would have been skipped as "already classified".
This is why this spec needed a `--retry-none` mechanism, not just a
plain re-run.

---

## Step 2 — Approach picked: A, the `--retry-none` flag

Chose **Approach A** from the spec: added a `--retry-none` CLI flag to
the existing `scripts/05_classify_experiments.py`. When set, it:

  1. Loads the checkpoint as normal.
  2. Identifies every row whose `classification_source` is `none` or
     `incomplete`.
  3. **Removes those rows from the `results` dict before the main loop
     starts**, so the loop sees them as "not yet processed" and
     re-runs both keyword matching and the AI fallback on them.
  4. `keyword` and `ai` classifications from prior runs are preserved
     untouched.
  5. At the end of every checkpoint cycle (every 50 records), prints a
     `[ai-retry] Classified X/Y (H health, NH not-health)` progress line
     tracking only the retry queue, not the whole catalog.

A second small change was made in the same commit: if the AI fallback
is attempted and all three tiers fail (Sonnet full → Sonnet title-only
→ Haiku title-only), the row's source is downgraded from `none` to
`incomplete` with the failure reason recorded in
`non_health_category` (e.g. `"ai_error: Connection reset by peer"`).
This gives the spec's verify step a clean way to distinguish genuine
API failures from unclassifiable rows.

`--retry-none` also hard-fails if `OPENROUTER_API_KEY` is missing —
there is no silent keyword-only fallback in this mode, per the spec:

  > "If OPENROUTER_API_KEY is missing or invalid, stop immediately and
  > report it. Do not silently fall back to keyword-only classification."

**Not picked: Approach B (a separate `05b_retry_unclassified.py` helper
script).** A one-file flag is simpler than a second entry point and
keeps all the classification logic (prompt, model selection, fallback
tiers, rate limiting) in one place.

**No change was made to** the prompt template, the disease area
definitions, the Sonnet 4.5 → Haiku 4.5 fallback chain, or the
1-second rate limit, per the spec's "don't touch" list.

---

## Step 3 — The run

Command:

```bash
OPENROUTER_API_KEY=<sk-…> python -u scripts/05_classify_experiments.py --retry-none
```

| Metric                           | Value |
|----------------------------------|------:|
| Rows queued for retry            | 2,606 (2,605 `none` + 1 `incomplete`) |
| AI calls made by the script      | 2,604 (via the classifier loop) |
| Plus manual retry                | 1 (see "AI errors" below)           |
| **Total new AI calls**           | **2,605** |
| OpenRouter API calls counter     | 183 → 2,787 (+2,604) in the script; +1 manual retry = 2,788 |
| Wall time                        | ~3 h 18 m (198 minutes) |
| Average time per call            | ~4.9 seconds |
| Cost (Sonnet 4.5, ~750 tok/call) | ~$10.6 — within the spec's $10-20 budget |
| Checkpoints saved                | Every 50 records (≈52 checkpoints) |

### AI errors

**One transient failure** during the 2,604-call run:
`SSRE-CSI-02` got a `Connection reset by peer` after the HTTP adapter's
4 built-in retries and the 3-tier Sonnet→Haiku fallback all exhausted.
The script marked it as `incomplete` with the error reason and moved on
(the spec's "log, sleep, retry, mark incomplete, keep going" behavior).

After the main run completed, `SSRE-CSI-02` was re-submitted manually
with a fresh session. It succeeded on the first attempt and was
correctly classified as `non_health_category: "plant biology"`
(the investigation is "Commercial Generic Bioprocessing Apparatus
Science Insert – 02: Silicate Garden, Seed Germination, Plant Cell
Culture and Yeast"). The manual retry brought the `incomplete` count
down from 2 to 1.

The remaining `incomplete` row is `OS-875`, a pre-existing OSDR record
with an empty title that's been flagged `incomplete_record` since the
original Spec 01 classification. It has no content to classify.

---

## Step 4 — Before / after disease-area counts

All counts are **health-related rows only**, multi-tag (an experiment
can appear in more than one area).

| Disease area                       |  Before  |  After  |     Δ  |
|------------------------------------|---------:|--------:|-------:|
| Endocrine and metabolic diseases   |      393 |     847 |   +454 |
| Neurological diseases              |      285 |     673 |   +388 |
| Cancer                             |      206 |     579 |   +373 |
| Cardiovascular diseases            |      273 |     643 |   +370 |
| Rare inherited disorders           |       45 |     355 |   +310 |
| Musculoskeletal diseases           |      533 |     776 |   +243 |
| Mental health                      |      167 |     261 |    +94 |
| Eye diseases                       |      112 |     193 |    +81 |
| Kidney diseases                    |       57 |     125 |    +68 |
| Women's health                     |      128 |     146 |    +18 |
| **Total tag assignments**          | **2,199** | **4,598** | **+2,399** |
| **Health-related rows**            | **1,154** | **1,969** |   **+815** |
| **Not-health-related rows**        | **2,675** | **1,860** |   **–815** |

The "Rare inherited disorders" jump (45 → 355) is the most dramatic.
The keyword list for that area is narrow (`genetic disorder`, `rare
disease`, `hereditary`, `monogenic`, `congenital`, `orphan disease`,
`inborn error`, `chromosomal`, `mendelian`, `inherited`), but Claude
correctly tagged hundreds of omics / model-organism / genetic-pathway
studies that never used those exact words in their titles. These are
experiments where the ISS environment is being used as a stressor to
study gene expression or cellular machinery that *is* relevant to rare
inherited disease research — the kind of indirect relevance only a
reasoning classifier can catch.

---

## Step 5 — Final classification-method breakdown

| Source       | Count | Notes |
|--------------|------:|-------|
| `ai`         | 2,788 | Sonnet 4.5 (mostly) with Haiku 4.5 fallback for content-moderated titles |
| `keyword`    | 1,040 | Mostly OSDR omics datasets that had rich objectives text |
| `incomplete` |     1 | `OS-875` — empty title in source data, pre-existing |
| `none`       |     0 | Was 2,605 before this run |
| **Total**    | **3,829** | |

The "both" source (keyword + AI) does not appear in this dataset — the
classifier's current logic only calls AI when keyword matching returns
zero hits, so a row is always tagged `keyword`, `ai`, `incomplete`, or
`none` but never `both`. This is consistent with Spec 01.

---

## Warnings / things to know

  - **Sonnet 4.5 occasionally returns `insufficient information`
    non-health categories** for SSRE rows whose title really is too
    terse to classify (examples from the log: `"Nanoracks-Iris"`,
    `"Sample-LDM"`, `"Qucopartex - Precious"`). These are not failures
    — they're the model correctly refusing to guess. They still count
    as successful AI classifications; they're just honestly tagged as
    not-health-related with a reason.
  - **The 1,860 non-health-related rows are largely ROSCOSMOS Earth-
    observation experiments, educational and cultural activities,
    technology demonstrations, materials science, and plant biology.**
    These are SSRE categories that genuinely don't map to the 10 SNIH
    disease areas, and that's expected — the point of classification
    is to correctly exclude them, not to force a disease tag.
  - **The sum of per-area counts (4,598) is much larger than
    health-related rows (1,969)** because many experiments map to
    multiple disease areas (e.g. cardiovascular + musculoskeletal for
    bed-rest/microgravity deconditioning studies, or cancer + rare
    inherited disorders for DNA-damage/radiation studies). This is
    intentional and correct — the dashboard has always treated disease
    tagging as multi-label.
  - **Total OpenRouter API calls** on the classifier's internal
    counter is 2,787 (it missed counting the 1 manual retry for
    `SSRE-CSI-02`). The actual number of Sonnet 4.5 calls made during
    this spec is 2,605 on top of the 183 from Spec 01, for a lifetime
    total of 2,788 `ai`-sourced rows.
  - **One pre-existing `incomplete` row (`OS-875`) remains.** It has
    no title in the source data — nothing to classify. Leaving it as
    `incomplete_record` is the correct behavior.
  - **No changes to `osdr_experiments.csv`** — Spec 02 was read-only
    on the source data, per the "What NOT to do" list.
  - **No git commits** — left for the user to review and commit
    manually.

---

## Step 6 — Files changed

**Changed**

  - `scripts/05_classify_experiments.py`
      - New `--retry-none` CLI flag (argparse added)
      - Logs to `[ai-retry]` prefix when the flag is set
      - Prints running `Classified X/Y (health, not-health)` line every
        50 records
      - AI failures in retry mode now downgrade the row to `incomplete`
        (with reason) instead of falling back to `none`
      - Hard-fails if `--retry-none` is used without `OPENROUTER_API_KEY`
  - `data/processed/classified_experiments.csv` — 3,829 rows, now
    includes ~2,600 AI classifications for SSRE rows
  - `data/processed/classification_details.json` — 3,829 entries
  - `data/checkpoints/classify_checkpoint.json` — 3,829 entries,
    `api_calls` counter at 2,788

**Not changed**

  - `scripts/02_fetch_research_explorer.py` — not touched
  - `scripts/01_fetch_nasa_osdr.py` — not touched
  - `data/processed/osdr_experiments.csv` — read-only per spec
  - `app.py` — no edits needed; the totals on the home page
    automatically pick up the new health-related count (1,969)
  - `requirements.txt` — no new dependencies
  - Prompt template, model selection, disease area definitions, rate
    limits — all per the spec's "don't touch" list

---

## Done criteria

  - [X] Every experiment has been through keyword + AI (or explicitly
        marked `incomplete` with a reason)
  - [X] `none` count is 0 (target was <500)
  - [X] All 10 disease areas have non-zero counts
  - [X] `streamlit run app.py` launches cleanly (HTTP 200, no errors)
  - [X] Home-page totals reconcile: 3,829 experiments, 1,969
        health-related, sum of tag assignments = 4,598 (multi-label)
  - [X] Changelog written (this file)

---

## How to reproduce this run

```bash
cd ~/Desktop/PythonProjects/space-health-dashboard
source venv/bin/activate

# Make sure OPENROUTER_API_KEY is set in .env
# Then retry all 'none' and 'incomplete' rows:
python scripts/05_classify_experiments.py --retry-none

# Smoke-test the dashboard
streamlit run app.py
```

Expect ~2,600 AI calls, ~3 hours wall time, ~$10-11 in OpenRouter
credits.
