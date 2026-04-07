# Spec 04 — Trial-Experiment Linkage

**Date:** 2026-04-07
**Goal:** Link the 534 clinical trials in `clinical_trials.csv` to the 3,829 ISS experiments in `osdr_experiments.csv` so the dashboard can show which trials relate to which experiments and vice versa.

**Why:** The trials were fetched by keyword search (space terms + disease terms) but have no connection to specific ISS experiments. The cousin's requirement #3 is "clinical trials linked to experiments." Right now they're just two disconnected tables.

---

## 1. The Linkage Problem

There is no shared ID between trials and experiments. No NCT ID appears in OSDR, and no OSDR ID appears in ClinicalTrials.gov. The linkage must be inferred.

### 1.1 Available signals for matching

| Signal | Trials field | Experiments field | Strength |
|--------|-------------|-------------------|----------|
| Disease area overlap | `disease_areas` | `classified_experiments_nlp.csv → disease_areas` | Medium — same area doesn't mean related |
| MeSH evidence overlap | `conditions` (MeSH terms) | `classified_experiments_nlp.csv → mesh_evidence` | Strong — shared MeSH descriptors |
| Keyword/text similarity | `title`, `conditions`, `interventions` | `title`, `objectives`, `approach`, `results` | Medium — can catch thematic links |
| Shared PI / author | `lead_sponsor` (org, not person) | `principal_investigator`, `all_people` | Weak — trials list orgs, experiments list people |
| Publication bridge | ClinicalTrials.gov references → PubMed → experiment publications | `publication_titles` | Strong — but rare |

### 1.2 Approach: Three-layer deterministic linkage

We use three independent methods and combine them. Each produces a score. No AI, no LLM — everything is text matching and set operations.

---

## 2. Layer 1: MeSH Descriptor Overlap (Primary)

### 2.1 Logic
Both datasets now have MeSH descriptor IDs:
- Trials: `conditions` field contains MeSH-like disease names. Run SciSpacy on trial titles + conditions to extract MeSH descriptor IDs (same pipeline as Spec 03).
- Experiments: `mesh_evidence` column in `classified_experiments_nlp.csv` already has MeSH descriptor IDs.

For each trial-experiment pair:
```
mesh_overlap = trial_mesh_ids ∩ experiment_mesh_ids
mesh_score = |mesh_overlap| / min(|trial_mesh_ids|, |experiment_mesh_ids|)
```

### 2.2 Threshold
- `mesh_score >= 0.5` → candidate link

### 2.3 Why this works
If a trial studies "Osteoporosis" (D010024) and an experiment detected "Osteoporosis" (D010024), they are studying the same condition. This is the strongest deterministic signal.

---

## 3. Layer 2: Disease Area Match (Secondary)

### 3.1 Logic
Both datasets have SNIH disease area assignments:
- Trials: `disease_areas` column (from keyword search at fetch time)
- Experiments: `disease_areas` from NLP classification

For each trial-experiment pair:
```
area_overlap = trial_areas ∩ experiment_areas
area_score = |area_overlap| / |trial_areas|
```

### 3.2 Threshold
- `area_score >= 1.0` (all trial areas match) → weak candidate link
- This layer is too broad on its own (many experiments share an area). It serves as a filter, not a standalone signal.

---

## 4. Layer 3: TF-IDF Text Similarity (Tiebreaker)

### 4.1 Logic
For candidate pairs from Layers 1 and 2, compute text similarity:

```python
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

# Corpus: all trial texts + all experiment texts
trial_text = f"{title} {conditions} {interventions}"
experiment_text = f"{title} {objectives} {approach} {results}"

# Fit TF-IDF on combined corpus, compute pairwise cosine similarity
```

### 4.2 Threshold
- `cosine_score >= 0.15` → supports the link (biomedical texts are sparse, so 0.15 is meaningful)

### 4.3 Why TF-IDF and not something fancier
- Deterministic: same input → same output
- No external dependencies (scikit-learn is already installed)
- No API calls, no models to download
- Fast: 534 × 3,829 = ~2M pairs, TF-IDF handles this in seconds

---

## 5. Combined Scoring

```
final_score = (0.5 × mesh_score) + (0.2 × area_score) + (0.3 × cosine_score)
```

A trial-experiment pair is linked if:
1. `final_score >= 0.3` AND
2. At least one of `mesh_score >= 0.5` OR `cosine_score >= 0.15`

This prevents pure area-match links (too loose) while allowing MeSH-only or text-only links when the signal is strong.

### 5.1 Link strength labels
- `final_score >= 0.6` → "strong"
- `final_score >= 0.4` → "moderate"
- `final_score >= 0.3` → "weak"

---

## 6. Script: `scripts/12_link_trials_experiments.py`

### 6.1 Input
- `data/processed/clinical_trials.csv` (534 trials)
- `data/processed/classified_experiments_nlp.csv` (3,829 experiments with MeSH evidence)
- `scripts/mesh_snih_crosswalk.json`
- `config/classification_config.json` (for SciSpacy backend settings)

### 6.2 Processing steps
1. Load both datasets
2. Run SciSpacy NER on trial `title + conditions` → extract MeSH descriptor IDs per trial (reuse the same pipeline from script 10, use venv312)
3. For each trial, compute mesh_score against every health-related experiment
4. Filter: only pairs where experiment is health-related
5. Compute area_score for remaining candidates
6. Build TF-IDF matrix for trials + experiments
7. Compute cosine_score for candidate pairs
8. Combine scores, apply thresholds
9. Write output

### 6.3 Optimization
- Don't compute all 534 × 3,829 pairs naively
- First filter: only compare trial to experiments that share at least one disease area (Layer 2 as pre-filter)
- This reduces the comparison space dramatically
- Then compute MeSH overlap and TF-IDF only for pre-filtered candidates

### 6.4 Output files

**`data/processed/trial_experiment_links.csv`**
| Column | Description |
|--------|-------------|
| `nct_id` | Trial NCT ID |
| `osID` | Experiment OS ID |
| `link_strength` | "strong" / "moderate" / "weak" |
| `final_score` | Combined score (0-1) |
| `mesh_score` | MeSH descriptor overlap score |
| `area_score` | Disease area overlap score |
| `cosine_score` | TF-IDF cosine similarity |
| `shared_mesh_ids` | Pipe-separated shared MeSH descriptor IDs |
| `shared_areas` | Semicolon-separated shared SNIH areas |

**`data/processed/trial_linkage_summary.json`**
```json
{
  "total_trials": 534,
  "trials_with_links": 0,
  "total_experiments": 3829,
  "experiments_with_links": 0,
  "total_links": 0,
  "links_by_strength": {"strong": 0, "moderate": 0, "weak": 0},
  "links_per_trial_avg": 0.0,
  "links_per_experiment_avg": 0.0,
  "coverage_by_area": {}
}
```

---

## 7. Dashboard Changes

### 7.1 Trial-Experiment view
Add a new tab or section: "Trial-Experiment Links"
- Table showing linked pairs with trial title, experiment title, link strength, shared areas
- Filter by disease area, link strength
- Click trial → opens ClinicalTrials.gov link
- Click experiment → opens OSDR link

### 7.2 Per-disease-area view
In each disease area section, show:
- Number of linked trials
- Number of linked experiments
- Top 5 strongest links

### 7.3 Trial detail panel
When user clicks a trial:
- Show trial metadata (title, status, phase, conditions, sponsor)
- Show linked experiments with scores
- Link to ClinicalTrials.gov page

---

## 8. Dependencies

- SciSpacy (already installed in venv312 from Spec 03)
- scikit-learn (already installed — used for TF-IDF)
- No new dependencies

---

## 9. Execution

```bash
# Uses venv312 (same as script 10)
./venv312/bin/python scripts/12_link_trials_experiments.py
```

**Estimated time:** 2-5 minutes (SciSpacy NER on 534 trials + TF-IDF on candidates)
**API cost:** $0
**Accounts required:** None

---

## 10. Done Criteria

- [ ] `trial_experiment_links.csv` exists
- [ ] `trial_linkage_summary.json` exists with coverage stats
- [ ] At least 50% of trials have at least one experiment link
- [ ] Link strength distribution is reported
- [ ] Dashboard shows Trial-Experiment Links tab/section
- [ ] Each disease area page shows linked trials count
- [ ] No existing files modified
- [ ] Script runs in venv312 using SciSpacy (same as script 10)

---

## 11. Expected Outcomes

With 534 trials and 432 health-related experiments (from Spec 03), expect:
- Not every trial will link — some trials are tangentially space-related
- Not every experiment will link — most experiments are basic science without clinical translation
- Strong links (MeSH overlap) will be the most meaningful
- The linkage gives the dashboard its "bench to bedside" narrative: this ISS experiment → these clinical trials are exploring the same conditions

---

## 12. What This Does NOT Do

- Does NOT use AI or LLMs for matching
- Does NOT modify clinical_trials.csv or classified_experiments_nlp.csv
- Does NOT re-fetch trials from ClinicalTrials.gov
- Does NOT create new disease area assignments
- Does NOT require any API keys or accounts
