# Claude Code Prompt — Spec 04 Implementation

Paste this into Claude Code:

---

Read `specs/04_trial_experiment_linkage.md` and implement it end to end. Do not deviate from the spec — ask me before making any changes.

## Rules
1. Follow the spec exactly. If you think something should be different, ASK ME first. Do not make unilateral decisions.
2. Do not skip steps. Do not stub anything out. Every script must be fully working.
3. If something fails, fix it and try again. Do not stop until the linkage is complete.
4. Talk to me like I am not technical. No jargon. Short sentences. Tell me what you're doing and why.

## Step-by-step execution

### Step 1: Verify prerequisites
- Confirm `data/processed/classified_experiments_nlp.csv` exists (from Spec 03)
- Confirm `data/processed/clinical_trials.csv` exists (534 trials)
- Confirm venv312 has SciSpacy installed
- Confirm scikit-learn is available

### Step 2: Implement `scripts/12_link_trials_experiments.py`
Follow the spec sections 2-6 exactly:
- Layer 1: Run SciSpacy on trial titles+conditions to get MeSH IDs, then compute MeSH overlap with experiments
- Layer 2: Disease area set overlap
- Layer 3: TF-IDF cosine similarity
- Combined scoring with the weights from section 5

Use venv312 for SciSpacy (same as script 10).

### Step 3: Test on 10 trials first
Run the script on the first 10 trials only. Show me:
- How many links were found
- Top 5 strongest links (trial title + experiment title + scores)
- Any trials with zero links

Ask me if the results look reasonable before running all 534.

### Step 4: Run full linkage
Run on all 534 trials. Show me:
- Total links found
- Links by strength (strong/moderate/weak)
- Trials with links vs without
- Experiments with links vs without
- Top 10 strongest links across the whole dataset

### Step 5: Update the dashboard
Follow section 7 of the spec:
- Add Trial-Experiment Links tab or section
- Show linked pairs with filtering
- Update disease area views with trial counts

### Step 6: Verify
- Confirm all Done Criteria from section 10 are met
- Show me the final checklist
- Commit everything

## Important
- Use venv312 for any SciSpacy operations (same as Spec 03)
- Do NOT re-classify experiments — use the existing classified_experiments_nlp.csv
- Do NOT re-fetch trials — use the existing clinical_trials.csv
- The linkage is deterministic — no AI, no randomness
- Commit after each major step
