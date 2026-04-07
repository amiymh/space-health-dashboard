# Claude Code Prompt — Spec 03 Implementation

Paste this into Claude Code:

---

Read `specs/03_deterministic_classification.md` and implement it end to end. Start with the **SciSpacy backend** (default — no accounts needed). Do not deviate from the spec — ask me before making any changes.

## Rules
1. Follow the spec exactly. If you think something should be different, ASK ME first. Do not make unilateral decisions.
2. Do not skip steps. Do not stub anything out. Every script must be fully working.
3. If something fails, fix it and try again. Do not stop until classification is complete.
4. Talk to me like I am not technical. No jargon. Short sentences. Tell me what you're doing and why.

## Step-by-step execution

### Step 1: Install SciSpacy + NER model
```bash
pip install scispacy
pip install https://s3-us-west-2.amazonaws.com/ai2-s2-scispacy/releases/v0.5.4/en_ner_bc5cdr_md-0.5.4.tar.gz
```
If the version URL doesn't work, check https://allenai.github.io/scispacy/ for the latest release URL.
Verify the install works before moving on:
```python
import spacy; nlp = spacy.load("en_ner_bc5cdr_md"); print("OK")
```

### Step 2: Build the MeSH tree code lookup
- Download `tree-numbers.tsv` from https://github.com/dhimmel/mesh/tree/master/data
- If the file is outdated or unavailable, query the MeSH SPARQL API at https://id.nlm.nih.gov/mesh/sparql as described in the spec (section 2.4, option 2)
- Parse it into `scripts/mesh_tree_lookup.json` — a dict mapping MeSH Descriptor IDs to lists of tree codes
- Save the crosswalk JSON from section 5.1 of the spec as `scripts/mesh_snih_crosswalk.json`
- Create `config/classification_config.json` from section 6 of the spec

### Step 3: Implement `scripts/10_classify_nlp.py`
Follow section 7 of the spec exactly. The script must:
- Read the config to determine which backend to use
- Support all three backends (scispacy, pubtator, metamaplite) — but only scispacy needs to work right now
- For scispacy: load the model, add the MeSH entity linker, process each experiment
- Map MeSH Descriptor IDs → tree codes → SNIH disease areas using the crosswalk

**Test it on 10 experiments first.** Show me the output. Ask me if it looks right before running the full 3,829.

### Step 4: Run full classification
Run script 10 on all 3,829 experiments. Output to `data/processed/classified_experiments_nlp.csv`. Show me:
- Total experiments classified
- Count per disease area
- How many marked "Not health-related"
- How many marked "insufficient_text"

### Step 5: Implement and run `scripts/11_compare_classifications.py`
Follow section 8 of the spec. Compare AI vs NLP. Show me the agreement stats.

### Step 6: Update the dashboard
Follow section 9 of the spec:
- Default to NLP classification
- Add sidebar toggle for AI comparison
- Show backend badge
- Update Sources & Methods tab text

### Step 7: Verify
- Run `streamlit run app.py` and confirm it works
- Confirm all Done Criteria from section 12 of the spec are met
- Show me the final checklist

## Important
- The existing `classified_experiments.csv` must NOT be modified or deleted
- Start with SciSpacy backend only. PubTator and MetaMapLite backends should be coded but can remain untested until we activate them.
- If SciSpacy doesn't work, try PubTator as fallback. Do NOT switch to AI classification.
- Commit after each major step (scripts, data, dashboard changes)
