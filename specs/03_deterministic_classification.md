# Spec 03 — Deterministic Classification via pyMetaMapLite + MeSH Crosswalk

**Date:** 2026-04-07
**Goal:** Replace the AI classification (script 05) as the *primary* disease-area assignment method with a fully deterministic NLM pipeline. The existing AI classifications are preserved as a secondary comparison layer — not deleted.

**Why:** The current pipeline uses Claude (via OpenRouter) to classify 73% of experiments. That method is non-deterministic (different runs can produce different results), not citable in a scientific context, and expensive ($10+ per run). NLM's MetaMapLite is the standard biomedical named-entity recognition tool — deterministic, free, reproducible, and peer-review defensible.

---

## 1. Architecture

```
scripts/10_classify_metamaplite.py        ← NEW: main script
scripts/mesh_snih_crosswalk.json          ← NEW: frozen MeSH C-branch → SNIH mapping
data/processed/classified_experiments_mtl.csv  ← NEW: MTL classification output
data/processed/classification_comparison.csv   ← NEW: AI vs MTL agreement report
```

The existing `classified_experiments.csv` (AI-based) is **not touched**. It gets renamed in the dashboard to "AI Extended Classification" and becomes available via a toggle. The new `classified_experiments_mtl.csv` becomes the default.

---

## 2. Tool: pyMetaMapLite

### 2.1 What it is
- Python implementation of NLM's MetaMapLite named-entity recognizer
- Maintained by NLM's Lister Hill Center: https://github.com/LHNCBC/pymetamaplite
- Maps free text → UMLS concept IDs (CUIs) with semantic types
- Uses inverted indexes from the UMLS Metathesaurus — no API calls, no network, no keys
- **Fully deterministic:** same input text always produces the same CUIs

### 2.2 Installation
```bash
pip install nltk
pip install git+https://github.com/LHNCBC/pymetamaplite.git
python -c "import nltk; nltk.download('averaged_perceptron_tagger_eng')"
```

### 2.3 Index data
Download the UMLS Metathesaurus inverted index files from:
https://metamap.nlm.nih.gov/MetaMapLite.html

Use the **2024AA USAbase** dataset (or latest available). Extract to:
```
data/metamaplite/ivf/2024AA/USAbase/
```

This is a ~2GB download. It is gitignored. The spec must document the exact version used so anyone can reproduce.

### 2.4 UMLS License
A free UMLS Terminology Services (UTS) account is required to download the index files.
Register at: https://uts.nlm.nih.gov/uts/signup-login
This is free and standard for any biomedical NLP work.

---

## 3. MeSH C-Branch → SNIH Disease Area Crosswalk

The MeSH tree organizes diseases under the "C" branch. Each SNIH disease area maps to one or more MeSH C-branch subcategories. This crosswalk is the core of the deterministic classification.

### 3.1 Crosswalk table

```json
{
  "Cardiovascular diseases": {
    "mesh_branches": ["C14"],
    "mesh_name": "Cardiovascular Diseases",
    "semantic_types": ["dsyn", "patf"],
    "notes": "Includes heart diseases, vascular diseases, blood pressure disorders"
  },
  "Kidney diseases": {
    "mesh_branches": ["C12.777", "C13.351.968"],
    "mesh_name": "Urologic Diseases / Kidney Diseases",
    "semantic_types": ["dsyn"],
    "notes": "C12.777 = kidney diseases under urologic; C13.351.968 = kidney diseases under female urogenital. Also match CUIs with 'renal' or 'kidney' in preferred name."
  },
  "Cancer": {
    "mesh_branches": ["C04"],
    "mesh_name": "Neoplasms",
    "semantic_types": ["neop"],
    "notes": "All neoplasms. The semantic type 'neop' (Neoplastic Process) is a strong standalone signal."
  },
  "Neurological diseases": {
    "mesh_branches": ["C10"],
    "mesh_name": "Nervous System Diseases",
    "semantic_types": ["dsyn"],
    "notes": "Includes neurodegenerative, cerebrovascular, vestibular. Exclude C10.228.140.490 (headache as standalone)."
  },
  "Eye diseases": {
    "mesh_branches": ["C11"],
    "mesh_name": "Eye Diseases",
    "semantic_types": ["dsyn"],
    "notes": "Includes SANS (spaceflight-associated neuro-ocular syndrome), retinal, corneal, glaucoma."
  },
  "Rare inherited disorders": {
    "mesh_branches": ["C16"],
    "mesh_name": "Congenital, Hereditary, and Neonatal Diseases and Abnormalities",
    "semantic_types": ["cgab", "dsyn"],
    "notes": "C16 covers genetic/congenital. Also match CUIs whose preferred name contains 'hereditary', 'congenital', 'genetic disorder', 'inborn error'."
  },
  "Women's health": {
    "mesh_branches": ["C13"],
    "mesh_name": "Female Urogenital Diseases and Pregnancy Complications",
    "semantic_types": ["dsyn", "patf"],
    "notes": "C13 covers female reproductive, pregnancy, gynecological. Exclude kidney sub-branch (handled above)."
  },
  "Endocrine and metabolic diseases": {
    "mesh_branches": ["C18", "C19"],
    "mesh_name": "Nutritional and Metabolic Diseases + Endocrine System Diseases",
    "semantic_types": ["dsyn"],
    "notes": "C18 = metabolic (diabetes, lipid, obesity). C19 = endocrine (thyroid, adrenal, pituitary). Both map to this single SNIH area."
  },
  "Musculoskeletal diseases": {
    "mesh_branches": ["C05"],
    "mesh_name": "Musculoskeletal Diseases",
    "semantic_types": ["dsyn"],
    "notes": "Includes osteoporosis, sarcopenia, bone diseases, joint diseases, muscular atrophy."
  },
  "Mental health": {
    "mesh_branches": ["F03"],
    "mesh_name": "Mental Disorders",
    "semantic_types": ["mobd", "menp"],
    "notes": "F03 is on the F (Psychiatry and Psychology) branch, not C. 'mobd' = Mental or Behavioral Dysfunction. Also match CUIs for sleep disorders (C10.886 cross-listed to F03)."
  }
}
```

### 3.2 Crosswalk rules
1. pyMetaMapLite extracts UMLS CUIs from experiment text
2. For each CUI, look up its MeSH tree codes (available in MRSTY and MRCONSO tables)
3. If any tree code starts with a prefix in the crosswalk, assign that SNIH disease area
4. A CUI can match multiple SNIH areas (multi-label, same as current behavior)
5. CUIs with no C-branch or F03 match → experiment is "Not health-related"
6. Semantic type is used as a secondary signal: `neop` → Cancer, `mobd` → Mental health, `cgab` → Rare inherited disorders

### 3.3 Handling edge cases
- **Experiments with empty/very short titles and no description:** Mark as `insufficient_text`. Do NOT guess. This is more honest than the AI pipeline's speculative 0.3-confidence tags.
- **CUIs that map to multiple C-branches:** Assign all matching SNIH areas (multi-label).
- **Anatomy terms without disease context:** MetaMapLite may return anatomy CUIs (A-branch) like "heart" without a disease. These are NOT sufficient for classification. Only C-branch and F03 CUIs count. However, if an anatomy CUI co-occurs with a pathological process semantic type (`patf`, `dsyn`), that combination counts.
- **Space-specific terms:** "microgravity", "spaceflight", "bed rest" are not diseases. They should not trigger any SNIH area on their own. Only disease/disorder CUIs count.

---

## 4. Script: `scripts/10_classify_metamaplite.py`

### 4.1 Input
- `data/processed/osdr_experiments.csv` (the same 3,829 experiments)

### 4.2 Processing per experiment
```
For each row:
  1. Concatenate: title + objectives + approach + results + researchAreas + publication_titles
  2. Tokenize and POS-tag using NLTK
  3. Run pyMetaMapLite.get_entities() → list of UMLS CUIs with semantic types
  4. For each CUI:
     a. Look up MeSH tree codes
     b. Match against crosswalk prefixes
     c. Collect all matching SNIH disease areas
  5. If any SNIH area matched → health_related = True
  6. Primary disease area = area with the most CUI hits (tie-break: alphabetical)
  7. Write result row
```

### 4.3 Output columns (same schema as existing classified_experiments.csv)
- `osID` — preserved from input
- `health_related` — True/False
- `disease_areas` — semicolon-separated SNIH areas (e.g., "Cardiovascular diseases; Musculoskeletal diseases")
- `primary_disease_area` — single area with most CUI evidence
- `relevance_type` — always "deterministic" (no confidence guessing)
- `classification_source` — always "metamaplite"
- `non_health_category` — for non-health experiments: most common non-C semantic type category
- `cui_evidence` — pipe-separated list of CUIs that drove the classification (for auditability)
- All original columns from osdr_experiments.csv are preserved

### 4.4 Output files
- `data/processed/classified_experiments_mtl.csv` — the new primary classification
- `data/processed/mtl_classification_details.json` — per-experiment CUI evidence (for debugging/auditing)

### 4.5 Performance
- pyMetaMapLite runs locally, no network calls
- With caching enabled (`use_cache=True`), expect ~5-10 experiments/second
- 3,829 experiments → ~7-12 minutes total
- No API costs

### 4.6 Checkpointing
- Save progress every 100 experiments to `data/checkpoints/mtl_classify_checkpoint.json`
- Resume from checkpoint on re-run (same pattern as script 05)

---

## 5. Comparison Report: `scripts/11_compare_classifications.py`

After script 10 completes, run script 11 to generate an agreement report between the AI classification and the MTL classification.

### 5.1 Output: `data/processed/classification_comparison.csv`

Columns:
- `osID`
- `ai_disease_areas` — from classified_experiments.csv
- `mtl_disease_areas` — from classified_experiments_mtl.csv
- `ai_health_related` / `mtl_health_related`
- `agree_health` — True if both agree on health/not-health
- `agree_areas` — True if disease area sets match exactly
- `ai_only_areas` — areas the AI found but MTL did not
- `mtl_only_areas` — areas MTL found but AI did not

### 5.2 Summary statistics printed to console
- Total agreement on health/not-health: X%
- Total agreement on disease areas (exact match): X%
- Total agreement on disease areas (any overlap): X%
- Per-disease-area agreement rates
- Top 20 experiments where the two methods disagree (for manual review)

---

## 6. Dashboard Changes

### 6.1 Default to MTL classification
- `data_loader.py` loads `classified_experiments_mtl.csv` as the primary dataset
- All tabs, metrics, and charts use MTL numbers by default

### 6.2 Comparison toggle
- Add a toggle in the sidebar: "Classification method: NLM MetaMapLite (default) | AI Extended"
- When toggled to AI, reload from `classified_experiments.csv`
- This enables direct visual comparison of the two methods

### 6.3 Sources & Methods tab update
- Replace the classification methodology text with:
  ```
  Classification methodology: Experiments were classified against SNIH 
  disease areas using NLM's MetaMapLite named-entity recognizer with 
  the UMLS 2024AA Metathesaurus. Extracted UMLS concepts were mapped 
  to SNIH disease areas via MeSH disease tree codes (C-branch) using 
  a frozen crosswalk. This method is fully deterministic and reproducible.
  
  An alternative AI-based classification (Claude Sonnet 4.5 via OpenRouter, 
  temperature=0.0) is available for comparison via the sidebar toggle.
  ```

---

## 7. Dependencies

### 7.1 New Python packages
```
nltk>=3.8.0
```

Plus pymetamaplite installed from GitHub (not on PyPI):
```
pip install git+https://github.com/LHNCBC/pymetamaplite.git
```

### 7.2 Data files (not in pip, must be downloaded separately)
- UMLS Metathesaurus inverted index files (2024AA USAbase)
- Download from https://metamap.nlm.nih.gov/MetaMapLite.html
- Requires free UMLS account
- Extract to `data/metamaplite/ivf/2024AA/USAbase/`
- Add `data/metamaplite/` to `.gitignore`

### 7.3 MeSH tree code lookup
The CUI → MeSH tree code mapping is available in the UMLS MRCONSO and MRHIER tables, which are part of the MetaMapLite index data. If the index doesn't include tree codes directly, we need a supplementary file:
- Download `mtrees2024.bin` from https://www.nlm.nih.gov/mesh/filelist.html
- This is a plain text file: `Descriptor Name;Tree Code` per line
- Parse it to build the CUI → tree code → SNIH area lookup
- Place at `data/metamaplite/mtrees2024.bin`

---

## 8. Execution Order

```bash
# 1. Install dependencies
pip install nltk
pip install git+https://github.com/LHNCBC/pymetamaplite.git
python -c "import nltk; nltk.download('averaged_perceptron_tagger_eng')"

# 2. Download and extract UMLS index data (manual step, requires UMLS account)
#    Place in data/metamaplite/ivf/2024AA/USAbase/

# 3. Download MeSH tree file
#    Place mtrees2024.bin in data/metamaplite/

# 4. Run classification
python scripts/10_classify_metamaplite.py

# 5. Run comparison
python scripts/11_compare_classifications.py

# 6. Verify dashboard
streamlit run app.py
```

**Estimated total time:** ~15 minutes of script execution (after manual data download)
**API cost:** $0
**Reproducibility:** 100% — same inputs always produce the same outputs

---

## 9. Done Criteria

- [ ] `classified_experiments_mtl.csv` exists with 3,829 rows
- [ ] Every row has `classification_source = "metamaplite"`
- [ ] All 10 SNIH disease areas have non-zero experiment counts
- [ ] `classification_comparison.csv` exists with agreement statistics
- [ ] Dashboard defaults to MTL classification
- [ ] AI classification accessible via sidebar toggle
- [ ] Sources & Methods tab updated with new methodology description
- [ ] No existing files modified (classified_experiments.csv untouched)
- [ ] `data/metamaplite/` added to .gitignore
- [ ] UMLS version and crosswalk documented in README

---

## 10. What This Does NOT Do

- Does NOT delete or modify the existing AI classification
- Does NOT require re-running scripts 01-09
- Does NOT change the clinical trials, publications, or approved therapies data
- Does NOT require OpenRouter API key or SerpAPI key
- Does NOT change the experiment count (still 3,829)

---

## 11. Citable Methodology

After this spec is implemented, the classification can be cited as:

> "ISS experiments were classified against SNIH priority disease areas using 
> NLM MetaMapLite (v3.6.2) with UMLS Metathesaurus 2024AA. Extracted biomedical 
> concepts (UMLS CUIs) were mapped to disease areas via MeSH tree codes using 
> a frozen crosswalk from MeSH C-branch subcategories to the 10 SNIH priority 
> disease areas. Classification is fully deterministic and reproducible."

This is standard methodology that any biomedical journal reviewer would recognize.
