# Spec 03 — Deterministic Classification via NLP + MeSH Crosswalk

**Date:** 2026-04-07 (revised)
**Goal:** Replace the AI classification (script 05) as the *primary* disease-area assignment method with a fully deterministic NLP pipeline. The existing AI classifications are preserved as a secondary comparison layer — not deleted.

**Why:** The current pipeline uses Claude (via OpenRouter) to classify 73% of experiments. That method is non-deterministic (different runs can produce different results), not citable in a scientific context, and expensive ($10+ per run). NLP-based biomedical NER tools are the standard in the field — deterministic, free, reproducible, and peer-review defensible.

---

## 1. Architecture — Multi-Backend Design

The system supports **three NER backends**. Only one runs at a time, selected via config. This lets us start immediately with SciSpacy (no accounts needed), and upgrade to MetaMapLite later for higher accuracy.

```
scripts/10_classify_nlp.py                ← NEW: main script (backend-agnostic)
scripts/mesh_snih_crosswalk.json          ← NEW: frozen MeSH C-branch → SNIH mapping
scripts/mesh_tree_lookup.json             ← NEW: MeSH Descriptor ID → tree codes
config/classification_config.json         ← NEW: backend selection + paths
data/processed/classified_experiments_nlp.csv   ← NEW: NLP classification output
data/processed/classification_comparison.csv    ← NEW: AI vs NLP agreement report
```

The existing `classified_experiments.csv` (AI-based) is **not touched**. It gets renamed in the dashboard to "AI Extended Classification" and becomes available via a toggle. The new `classified_experiments_nlp.csv` becomes the default.

---

## 2. Backend A: SciSpacy + MeSH Entity Linker (DEFAULT — No Account Required)

### 2.1 What it is
- SciSpacy is a Python NLP library by Allen AI built on spaCy, with models trained on biomedical text
- The `en_ner_bc5cdr_md` model detects DISEASE and CHEMICAL entities (84% F1 score on BC5CDR corpus)
- The built-in MeSH entity linker maps detected entities to MeSH Descriptor IDs (e.g., D003920 = Diabetes Mellitus)
- **No accounts, no licenses, no downloads beyond pip install**
- Deterministic: same input always produces the same entities

### 2.2 Installation
```bash
pip install scispacy
pip install https://s3-us-west-2.amazonaws.com/ai2-s2-scispacy/releases/v0.5.4/en_ner_bc5cdr_md-0.5.4.tar.gz
```

### 2.3 How it works
```python
import spacy
import scispacy
from scispacy.linking import EntityLinker

nlp = spacy.load("en_ner_bc5cdr_md")
nlp.add_pipe("scispacy_linker", config={
    "resolve_abbreviations": True,
    "linker_name": "mesh"
})

doc = nlp("The study examined bone loss and osteoporosis in microgravity")
for ent in doc.ents:
    if ent.label_ == "DISEASE":
        for mesh_id, score in ent._.kb_ents:
            # mesh_id = MeSH Descriptor ID like "D010024" (Osteoporosis)
            # Look up tree codes for this descriptor
            # D010024 → C05.116.198.579 → starts with C05 → Musculoskeletal
            pass
```

### 2.4 MeSH Descriptor → Tree Code Lookup
SciSpacy returns MeSH Descriptor IDs (D-numbers). We need to map these to tree codes to use our crosswalk. Two options (script should try both, prefer option 1):

**Option 1: Pre-built lookup from dhimmel/mesh (CC0 licensed, no account)**
- Download `tree-numbers.tsv` from https://github.com/dhimmel/mesh (CC0 license)
- Format: `descriptor_id \t tree_number` (one row per tree number)
- Parse into a dict: `{"D010024": ["C05.116.198.579"], "D003920": ["C18.452.394.750", "C19.246"]}`
- Save as `scripts/mesh_tree_lookup.json`

**Option 2: MeSH RDF SPARQL API (free, no account, live query)**
- Endpoint: https://id.nlm.nih.gov/mesh/sparql
- Query all descriptor → tree number mappings in one request
- Cache result locally as `scripts/mesh_tree_lookup.json`

```sparql
SELECT ?descriptor ?treeNumber
WHERE {
  ?descriptor a meshv:TopicalDescriptor .
  ?descriptor meshv:treeNumber ?treeNumberNode .
  ?treeNumberNode rdfs:label ?treeNumber .
}
```

### 2.5 Limitations
- SciSpacy's NER is trained on PubMed abstracts — may miss space-specific disease terminology
- Entity linking uses approximate string matching (char-3grams), not exact lookup
- MeSH KB in SciSpacy has ~30K entities vs UMLS's ~3M concepts

---

## 3. Backend B: MeSH on Demand / PubTator API (No Account Required)

### 3.1 What it is
- PubTator Central is NLM's free API for biomedical concept annotation
- Send text → get back annotated disease/chemical/gene entities with MeSH IDs
- Uses NLM's own deep-learning NER models (same team that builds MetaMap)
- **No account, no downloads. Just HTTP requests.**
- Deterministic for the same model version

### 3.2 API Usage
```
POST https://www.ncbi.nlm.nih.gov/research/pubtator3-api/annotate/
Content-Type: text/plain

The study examined bone loss and osteoporosis in microgravity conditions
```

Returns annotated text with MeSH disease IDs → same tree code lookup as Backend A.

### 3.3 Limitations
- Requires internet for each request (3,829 requests)
- Rate limited — may need throttling (recommend 3 requests/second)
- NLM can update their models, slightly changing results over time
- Slower than local processing (~20-30 minutes for full dataset with throttling)

---

## 4. Backend C: pyMetaMapLite (Requires Free UMLS Account — FUTURE)

### 4.1 What it is
- Python implementation of NLM's MetaMapLite named-entity recognizer
- Maintained by NLM's Lister Hill Center: https://github.com/LHNCBC/pymetamaplite
- Maps free text → UMLS concept IDs (CUIs) with semantic types
- Uses inverted indexes from the UMLS Metathesaurus — no API calls, no network
- **Highest accuracy of the three backends**
- **Requires a free UMLS account to download ~2GB index data**

### 4.2 Installation
```bash
pip install nltk
pip install git+https://github.com/LHNCBC/pymetamaplite.git
python -c "import nltk; nltk.download('averaged_perceptron_tagger_eng')"
```

### 4.3 Index data
Download the UMLS Metathesaurus inverted index files from:
https://metamap.nlm.nih.gov/MetaMapLite.html

Use the **2024AA USAbase** dataset. Extract to:
```
data/metamaplite/ivf/2024AA/USAbase/
```

### 4.4 Activation
When index data is available, change `config/classification_config.json`:
```json
{
  "backend": "metamaplite",
  "metamaplite_ivf_dir": "data/metamaplite/ivf/2024AA/USAbase"
}
```

Re-run script 10. Dashboard will automatically use the new results. Previous SciSpacy results are archived.

---

## 5. MeSH C-Branch → SNIH Disease Area Crosswalk

This crosswalk is shared by all three backends. Each backend produces MeSH tree codes; this mapping converts them to SNIH disease areas.

### 5.1 Crosswalk table

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
    "notes": "C12.777 = kidney diseases under urologic; C13.351.968 = kidney diseases under female urogenital. Also match descriptors with 'renal' or 'kidney' in preferred name."
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
    "notes": "C16 covers genetic/congenital. Also match descriptors whose preferred name contains 'hereditary', 'congenital', 'genetic disorder', 'inborn error'."
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
    "notes": "F03 is on the F (Psychiatry and Psychology) branch, not C. 'mobd' = Mental or Behavioral Dysfunction. Also match descriptors for sleep disorders (C10.886 cross-listed to F03)."
  }
}
```

### 5.2 Crosswalk rules
1. Backend extracts disease entities from experiment text and returns MeSH Descriptor IDs
2. For each Descriptor ID, look up its MeSH tree codes (from mesh_tree_lookup.json)
3. If any tree code starts with a prefix in the crosswalk, assign that SNIH disease area
4. A descriptor can match multiple SNIH areas (multi-label, same as current behavior)
5. Descriptors with no C-branch or F03 match → experiment is "Not health-related"
6. For MetaMapLite backend only: semantic type is used as a secondary signal

### 5.3 Handling edge cases
- **Experiments with empty/very short titles and no description:** Mark as `insufficient_text`. Do NOT guess.
- **Descriptors that map to multiple C-branches:** Assign all matching SNIH areas (multi-label).
- **Anatomy terms without disease context:** Only DISEASE-labeled entities count for SciSpacy. For MetaMapLite, only C-branch and F03 CUIs count.
- **Space-specific terms:** "microgravity", "spaceflight", "bed rest" are not diseases. They should not trigger any SNIH area on their own.

---

## 6. Configuration File: `config/classification_config.json`

```json
{
  "backend": "scispacy",
  "scispacy": {
    "model": "en_ner_bc5cdr_md",
    "linker": "mesh",
    "min_entity_score": 0.7
  },
  "pubtator": {
    "api_url": "https://www.ncbi.nlm.nih.gov/research/pubtator3-api/annotate/",
    "requests_per_second": 3
  },
  "metamaplite": {
    "ivf_dir": "data/metamaplite/ivf/2024AA/USAbase",
    "use_cache": true
  },
  "mesh_tree_lookup": "scripts/mesh_tree_lookup.json",
  "crosswalk": "scripts/mesh_snih_crosswalk.json"
}
```

To switch backends, change `"backend"` to `"scispacy"`, `"pubtator"`, or `"metamaplite"`. Re-run script 10.

---

## 7. Script: `scripts/10_classify_nlp.py`

### 7.1 Input
- `data/processed/osdr_experiments.csv` (the same 3,829 experiments)

### 7.2 Processing per experiment
```
For each row:
  1. Concatenate: title + objectives + approach + results + researchAreas + publication_titles
  2. Run the selected NER backend on the concatenated text
  3. Collect disease entities with MeSH Descriptor IDs
  4. For each Descriptor ID:
     a. Look up MeSH tree codes from mesh_tree_lookup.json
     b. Match against crosswalk prefixes
     c. Collect all matching SNIH disease areas
  5. If any SNIH area matched → health_related = True
  6. Primary disease area = area with the most descriptor hits (tie-break: alphabetical)
  7. Write result row
```

### 7.3 Output columns (same schema as existing classified_experiments.csv)
- `osID` — preserved from input
- `health_related` — True/False
- `disease_areas` — semicolon-separated SNIH areas
- `primary_disease_area` — single area with most evidence
- `relevance_type` — always "deterministic"
- `classification_source` — "scispacy" / "pubtator" / "metamaplite"
- `non_health_category` — for non-health experiments
- `mesh_evidence` — pipe-separated list of MeSH Descriptor IDs that drove the classification (for auditability)
- All original columns from osdr_experiments.csv are preserved

### 7.4 Output files
- `data/processed/classified_experiments_nlp.csv` — the new primary classification
- `data/processed/nlp_classification_details.json` — per-experiment entity evidence (for debugging/auditing)

### 7.5 Performance estimates
| Backend | Speed | Internet | Account |
|---------|-------|----------|---------|
| SciSpacy | ~10-20 exp/sec | No | No |
| PubTator | ~3 exp/sec (throttled) | Yes | No |
| MetaMapLite | ~5-10 exp/sec | No | Yes (free) |

SciSpacy: ~3-6 minutes for 3,829 experiments
PubTator: ~20-30 minutes
MetaMapLite: ~7-12 minutes

### 7.6 Checkpointing
- Save progress every 100 experiments to `data/checkpoints/nlp_classify_checkpoint.json`
- Resume from checkpoint on re-run

---

## 8. Comparison Report: `scripts/11_compare_classifications.py`

After script 10 completes, run script 11 to generate an agreement report between the AI classification and the NLP classification.

### 8.1 Output: `data/processed/classification_comparison.csv`

Columns:
- `osID`
- `ai_disease_areas` — from classified_experiments.csv
- `nlp_disease_areas` — from classified_experiments_nlp.csv
- `ai_health_related` / `nlp_health_related`
- `agree_health` — True if both agree on health/not-health
- `agree_areas` — True if disease area sets match exactly
- `ai_only_areas` — areas the AI found but NLP did not
- `nlp_only_areas` — areas NLP found but AI did not

### 8.2 Summary statistics printed to console
- Total agreement on health/not-health: X%
- Total agreement on disease areas (exact match): X%
- Total agreement on disease areas (any overlap): X%
- Per-disease-area agreement rates
- Top 20 experiments where the two methods disagree (for manual review)

---

## 9. Dashboard Changes

### 9.1 Default to NLP classification
- `data_loader.py` loads `classified_experiments_nlp.csv` as the primary dataset
- All tabs, metrics, and charts use NLP numbers by default

### 9.2 Comparison toggle
- Add a toggle in the sidebar: "Classification method: NLP/MeSH (default) | AI Extended"
- When toggled to AI, reload from `classified_experiments.csv`

### 9.3 Backend badge
- Show which NLP backend was used in the sidebar: "Classified by: SciSpacy + MeSH" (or PubTator, or MetaMapLite)
- This updates automatically based on `classification_source` in the CSV

### 9.4 Sources & Methods tab update
Replace the classification methodology text with:
```
Classification methodology: Experiments were classified against SNIH
disease areas using biomedical named-entity recognition with MeSH
concept mapping. Disease entities were extracted from experiment text,
linked to MeSH Descriptor IDs, and mapped to SNIH disease areas via
MeSH tree codes (C-branch) using a frozen crosswalk. This method is
fully deterministic and reproducible.

Current backend: [SciSpacy en_ner_bc5cdr_md + MeSH Entity Linker |
PubTator Central API | NLM MetaMapLite with UMLS 2024AA]

An alternative AI-based classification (Claude Sonnet 4.5 via OpenRouter,
temperature=0.0) is available for comparison via the sidebar toggle.
```

---

## 10. Dependencies

### 10.1 For SciSpacy backend (default)
```
scispacy
en_ner_bc5cdr_md (installed from S3 URL)
spacy>=3.0
```

### 10.2 For PubTator backend
```
requests (already in most environments)
```

### 10.3 For MetaMapLite backend (future)
```
nltk>=3.8.0
pymetamaplite (from GitHub)
UMLS index data (requires free UMLS account)
```

### 10.4 Shared
```
MeSH tree lookup: scripts/mesh_tree_lookup.json (built from dhimmel/mesh or MeSH SPARQL API, no account)
Crosswalk: scripts/mesh_snih_crosswalk.json (defined in this spec)
```

---

## 11. Execution Order

```bash
# 1. Install SciSpacy (default backend)
pip install scispacy
pip install https://s3-us-west-2.amazonaws.com/ai2-s2-scispacy/releases/v0.5.4/en_ner_bc5cdr_md-0.5.4.tar.gz

# 2. Build MeSH tree lookup (download from dhimmel/mesh, no account needed)
python scripts/build_mesh_tree_lookup.py

# 3. Run classification
python scripts/10_classify_nlp.py

# 4. Run comparison
python scripts/11_compare_classifications.py

# 5. Verify dashboard
streamlit run app.py
```

**Estimated total time:** ~5 minutes of script execution
**API cost:** $0
**Accounts required:** None
**Reproducibility:** 100% — same inputs always produce the same outputs

---

## 12. Done Criteria

- [ ] `classified_experiments_nlp.csv` exists with 3,829 rows
- [ ] Every row has `classification_source` matching the active backend
- [ ] All 10 SNIH disease areas have non-zero experiment counts
- [ ] `classification_comparison.csv` exists with agreement statistics
- [ ] Dashboard defaults to NLP classification
- [ ] AI classification accessible via sidebar toggle
- [ ] Sources & Methods tab updated with new methodology description
- [ ] No existing files modified (classified_experiments.csv untouched)
- [ ] Config file allows backend switching
- [ ] `scripts/mesh_tree_lookup.json` and `scripts/mesh_snih_crosswalk.json` committed

---

## 13. What This Does NOT Do

- Does NOT delete or modify the existing AI classification
- Does NOT require re-running scripts 01-09
- Does NOT change the clinical trials, publications, or approved therapies data
- Does NOT require OpenRouter API key or SerpAPI key
- Does NOT change the experiment count (still 3,829)
- Does NOT require any account or license for the default backend

---

## 14. Future Upgrade Path

When the UMLS account is available:
1. Download MetaMapLite index data
2. Change config to `"backend": "metamaplite"`
3. Re-run script 10
4. Dashboard automatically updates — shows "Classified by: MetaMapLite"
5. Previous SciSpacy results archived in `data/archive/`

This is a one-line config change + one script re-run. No code changes needed.

---

## 15. Citable Methodology

After this spec is implemented, the classification can be cited as:

> "ISS experiments were classified against SNIH priority disease areas using
> biomedical named-entity recognition (SciSpacy en_ner_bc5cdr_md / NLM
> MetaMapLite). Extracted disease entities were linked to MeSH Descriptor
> IDs and mapped to SNIH disease areas via MeSH tree codes using a frozen
> crosswalk from MeSH C-branch subcategories to the 10 SNIH priority
> disease areas. Classification is fully deterministic and reproducible."

This is standard methodology that any biomedical journal reviewer would recognize.
