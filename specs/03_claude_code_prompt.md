# Claude Code Prompt — Spec 03 Implementation

Paste this into Claude Code:

---

Read `specs/03_deterministic_classification.md` and implement it end to end. Do not deviate from the spec — ask me before making any changes.

## Rules
1. Follow the spec exactly. If you think something should be different, ASK ME first. Do not make unilateral decisions.
2. Do not skip steps. Do not stub anything out. Every script must be fully working.
3. If something fails, fix it and try again. Do not stop until classification is complete.
4. Talk to me like I am not technical. No jargon. Short sentences. Tell me what you're doing and why.

## Step-by-step execution

### Step 1: UMLS Account & Data Download
I need a free UMLS account to download the MetaMapLite index data. Walk me through it:
- Open https://uts.nlm.nih.gov/uts/signup-login in my browser
- Tell me exactly what to fill in each field (name, email, purpose = "biomedical text mining for research project")
- After I confirm the account, tell me exactly where to click to download the **MetaMapLite dataset (2024AA USAbase)**
- Direct download link to try first: https://metamap.nlm.nih.gov/MetaMapLite.html — look for "MetaMap Lite" downloads section
- Also download `mtrees2024.bin` from https://www.nlm.nih.gov/mesh/filelist.html
- Tell me where to put the files: `data/metamaplite/ivf/2024AA/USAbase/` and `data/metamaplite/mtrees2024.bin`
- Add `data/metamaplite/` to `.gitignore`
- Do NOT proceed until I confirm the files are in place.

### Step 2: Install dependencies
```bash
pip install nltk
pip install git+https://github.com/LHNCBC/pymetamaplite.git
python -c "import nltk; nltk.download('averaged_perceptron_tagger_eng')"
```
Verify the install works before moving on.

### Step 3: Implement `scripts/10_classify_metamaplite.py`
Follow section 4 of the spec exactly. The crosswalk JSON is in section 3.1. Save the crosswalk as `scripts/mesh_snih_crosswalk.json` first, then build the script.

Test it on 10 experiments first. Show me the output. Ask me if it looks right before running the full 3,829.

### Step 4: Run full classification
Run script 10 on all 3,829 experiments. Output to `data/processed/classified_experiments_mtl.csv`. Show me:
- Total experiments classified
- Count per disease area
- How many marked "Not health-related"
- How many marked "insufficient_text"

### Step 5: Implement and run `scripts/11_compare_classifications.py`
Follow section 5 of the spec. Compare AI vs MTL. Show me the agreement stats.

### Step 6: Update the dashboard
Follow section 6 of the spec:
- Default to MTL classification
- Add sidebar toggle for AI comparison
- Update Sources & Methods tab text

### Step 7: Verify
- Run `streamlit run app.py` and confirm it works
- Confirm all Done Criteria from section 9 of the spec are met
- Show me the final checklist

## Important
- The existing `classified_experiments.csv` must NOT be modified or deleted
- If pyMetaMapLite doesn't work or the index data is problematic, STOP and tell me. Do not switch to a different method without asking.
- Commit after each major step (scripts, data, dashboard changes)
