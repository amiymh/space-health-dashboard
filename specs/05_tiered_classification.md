# Spec 05 — Tiered Classification & Comparison Page

**Date:** 2026-04-07
**Goal:** Combine NLP and AI classifications into a single tiered view that maximizes coverage while preserving transparency. Add a dedicated comparison page to the dashboard.

**Why:** The NLP method (Spec 03) classified 432 experiments (11.3%) — precise but narrow. The AI method classified ~2,000 (52%) — broader but less reliable. Combining them into tiers gives users the full picture: what's confirmed, what's probable, and what's uncertain. This also lays the groundwork for comparing additional backends (PubTator, MetaMapLite) when they're activated.

---

## 1. Three-Tier Classification

### Tier 1 — Confirmed (NLP + AI agree)
- NLP classified the experiment as health-related AND
- AI classified the experiment as health-related AND
- They agree on at least one disease area
- **Confidence: High.** Two independent methods agree.

### Tier 2 — Probable (AI only, high confidence)
- NLP did NOT classify the experiment as health-related (no literal disease term found) BUT
- AI classified it as health-related WITH confidence >= 0.7
- **Confidence: Medium.** AI inferred disease relevance from context (e.g., "osteoblast differentiation" → musculoskeletal). Plausible but not evidence-backed by MeSH.

### Tier 3 — Uncertain (AI only, low confidence)
- NLP did NOT classify the experiment as health-related BUT
- AI classified it as health-related WITH confidence < 0.7
- **Confidence: Low.** AI guessed, and wasn't confident about it.

### Tier 0 — Not health-related
- Neither NLP nor AI classified the experiment as health-related
- OR NLP marked it as `insufficient_text`

---

## 2. Script: `scripts/13_build_tiered_classification.py`

### 2.1 Input
- `data/processed/classified_experiments_nlp.csv` (NLP results with `mesh_evidence`)
- `data/processed/classified_experiments.csv` (AI results with confidence scores)
- `data/processed/classification_comparison.csv` (existing comparison from script 11)

### 2.2 Processing
```
For each experiment (by osID):
  1. Get NLP result: health_related, disease_areas, mesh_evidence
  2. Get AI result: health_related, disease_areas, confidence
  3. Determine tier:
     - If NLP health_related AND AI health_related AND shared_areas > 0 → Tier 1 (Confirmed)
     - If NOT NLP health_related AND AI health_related AND AI confidence >= 0.7 → Tier 2 (Probable)
     - If NOT NLP health_related AND AI health_related AND AI confidence < 0.7 → Tier 3 (Uncertain)
     - Else → Tier 0 (Not health-related)
  4. For Tier 1: use NLP disease areas (more precise)
  5. For Tier 2/3: use AI disease areas
  6. Write result
```

### 2.3 Output: `data/processed/tiered_classification.csv`

| Column | Description |
|--------|-------------|
| `osID` | Experiment ID |
| `title` | Experiment title |
| `tier` | 1, 2, 3, or 0 |
| `tier_label` | "Confirmed", "Probable", "Uncertain", "Not health-related" |
| `health_related` | True for tiers 1-3, False for tier 0 |
| `disease_areas` | Semicolon-separated areas (NLP for tier 1, AI for tiers 2-3) |
| `primary_disease_area` | Single area |
| `nlp_classified` | True/False — did NLP find disease terms |
| `ai_classified` | True/False — did AI tag as health-related |
| `ai_confidence` | AI confidence score (0-1) |
| `nlp_mesh_evidence` | MeSH descriptor IDs from NLP (empty for tiers 2-3) |
| `classification_source` | "nlp+ai" for tier 1, "ai_high" for tier 2, "ai_low" for tier 3, "none" for tier 0 |

### 2.4 Summary: `data/processed/tiered_classification_summary.json`
```json
{
  "total_experiments": 3829,
  "tier_1_confirmed": 0,
  "tier_2_probable": 0,
  "tier_3_uncertain": 0,
  "tier_0_not_health": 0,
  "total_health_related_tiered": 0,
  "coverage_percent": 0.0,
  "per_disease_area": {
    "Cardiovascular diseases": {"tier_1": 0, "tier_2": 0, "tier_3": 0},
    ...
  }
}
```

---

## 3. AI Confidence Score

The existing `classified_experiments.csv` may or may not have a confidence column. Check for:
- `confidence` column
- `classification_confidence` column
- If neither exists, check `classification_details.json` for per-experiment confidence

If no confidence data is available at all:
- AI experiments classified by keyword → treat as confidence 0.6 (moderate)
- AI experiments classified by Claude → treat as confidence 0.75 (above threshold)
- This is a reasonable proxy since the keyword method is less reliable than the LLM

---

## 4. Dashboard: Comparison Page

### 4.1 New tab: "Classification Comparison"

**Section A: Tier Overview**
- Four large KPI cards at the top:
  - Tier 1 Confirmed: count + % of total
  - Tier 2 Probable: count + % of total
  - Tier 3 Uncertain: count + % of total
  - Not Health-Related: count + % of total
- Stacked horizontal bar showing the tier distribution

**Section B: Per-Disease-Area Breakdown**
- Table with columns: Disease Area | Tier 1 | Tier 2 | Tier 3 | Total
- Stacked bar chart per disease area showing tier composition
- This answers: "For cardiovascular diseases, how many experiments are confirmed vs probable vs uncertain?"

**Section C: Method Comparison**
- Side-by-side bar chart: NLP counts vs AI counts per disease area
- Scatter plot: NLP disease area assignment (x) vs AI disease area assignment (y) — shows where methods agree/disagree
- Agreement metrics: % exact match, % any overlap, % complete disagreement

**Section D: Experiment Explorer**
- Filterable table of all 3,829 experiments
- Filters: tier (1/2/3/0), disease area, classification source
- Columns: osID, title, tier, disease areas, AI confidence, MeSH evidence
- Click to expand: shows full NLP and AI details side by side
- Export to CSV button

**Section E: Backend Status**
- Show which backends are active vs available:
  - SciSpacy: Active (default)
  - PubTator: Available (not yet run)
  - MetaMapLite: Available (requires UMLS account)
- Note: "When additional backends are activated, their results will appear here for comparison"

### 4.2 Update existing tabs
- The main disease area views should use **tiered totals** (tier 1 + tier 2) as the default count, with a note explaining the tiers
- Add a small tier badge next to each count: e.g., "82 experiments (54 confirmed, 28 probable)"

---

## 5. Dependencies

- pandas (already installed)
- No new dependencies

---

## 6. Execution

```bash
# Uses main venv (no SciSpacy needed — just reads CSVs)
python scripts/13_build_tiered_classification.py
```

**Estimated time:** < 30 seconds (just merging two CSVs)
**API cost:** $0

---

## 7. Done Criteria

- [ ] `tiered_classification.csv` exists with 3,829 rows
- [ ] Every row has a `tier` value (0, 1, 2, or 3)
- [ ] `tiered_classification_summary.json` exists
- [ ] Dashboard has "Classification Comparison" tab
- [ ] KPI cards show tier counts
- [ ] Per-disease-area breakdown table and chart work
- [ ] Method comparison charts render
- [ ] Experiment explorer with filters works
- [ ] Existing disease area tabs show tiered counts
- [ ] No existing files modified

---

## 8. Expected Outcomes

Based on current data:
- NLP health-related: 432 experiments
- AI health-related: ~2,000 experiments
- Overlap (both agree): estimated 300-400 → Tier 1
- AI-only high confidence: estimated 800-1,000 → Tier 2
- AI-only low confidence: estimated 500-700 → Tier 3
- Neither: estimated 1,700-2,000 → Tier 0

This would give a total health-related coverage of ~40-50% across tiers 1-3, with clear transparency about confidence levels.
