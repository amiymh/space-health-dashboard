# Claude Code Prompt — Spec 05 Implementation

Paste this into Claude Code:

---

Read `specs/05_tiered_classification.md` and implement it end to end. Do not deviate from the spec — ask me before making any changes.

## Rules
1. Follow the spec exactly. If you think something should be different, ASK ME first. Do not make unilateral decisions.
2. Do not skip steps. Do not stub anything out. Every script must be fully working.
3. If something fails, fix it and try again. Do not stop until the comparison page is complete.
4. Talk to me like I am not technical. No jargon. Short sentences. Tell me what you're doing and why.

## Step-by-step execution

### Step 1: Check AI confidence data
- Look at `data/processed/classified_experiments.csv` — does it have a `confidence` or `classification_confidence` column?
- Check `data/processed/classification_details.json` for per-experiment confidence
- If no confidence data exists, use the proxy from spec section 3 (keyword=0.6, Claude=0.75)
- Tell me what you found before proceeding

### Step 2: Implement `scripts/13_build_tiered_classification.py`
Follow spec sections 2-3 exactly. Merge NLP and AI results into tiers:
- Tier 1: Both agree
- Tier 2: AI only, high confidence
- Tier 3: AI only, low confidence
- Tier 0: Neither

Show me the tier counts before proceeding.

### Step 3: Build the Comparison tab
Follow spec section 4 exactly:
- KPI cards for each tier
- Per-disease-area breakdown (table + stacked bar)
- Method comparison charts (side-by-side bars, agreement metrics)
- Experiment explorer with filters
- Backend status section

### Step 4: Update existing disease area tabs
Add tiered counts as described in spec section 4.2.

### Step 5: Verify
- Run `streamlit run app.py` and confirm the new tab works
- Confirm all Done Criteria from spec section 7
- Show me the final numbers
- Commit and push

## Important
- This script runs in the MAIN venv (not venv312) — it just reads CSVs, no SciSpacy needed
- Do NOT modify classified_experiments.csv or classified_experiments_nlp.csv
- The tiered view is ADDITIVE — it combines existing data, doesn't replace it
- Commit after each major step
