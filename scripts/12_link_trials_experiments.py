"""
Spec 04 — Link clinical trials to ISS experiments.

Three-layer deterministic linkage (no AI, no randomness):

  Layer 1  MeSH descriptor overlap between trial (NER on title+conditions)
           and experiment (mesh_evidence column from Spec 03).

  Layer 2  SNIH disease-area set overlap (also used as a pre-filter to
           shrink the candidate-pair space).

  Layer 3  TF-IDF cosine similarity between trial text
           (title+conditions+interventions) and experiment text
           (title+objectives+approach+results).

Combined:
  final_score = 0.5*mesh + 0.2*area + 0.3*cosine
  accept if (final_score >= 0.3) AND (mesh_score >= 0.5 OR cosine_score >= 0.15)

Strength labels:
  strong   >= 0.6
  moderate >= 0.4
  weak     >= 0.3

Inputs:
  data/processed/clinical_trials.csv               (534 trials)
  data/processed/classified_experiments_nlp.csv    (3,829 experiments)
  scripts/mesh_snih_crosswalk.json
  scripts/mesh_tree_lookup.json
  scripts/mesh_name_to_descriptor.json
  config/classification_config.json                (for the SciSpacy backend)

Outputs:
  data/processed/trial_experiment_links.csv
  data/processed/trial_linkage_summary.json
  data/checkpoints/trial_mesh_cache.json           (NER results cached so
                                                    re-runs are cheap)

Usage:
  ./venv312/bin/python scripts/12_link_trials_experiments.py
  ./venv312/bin/python scripts/12_link_trials_experiments.py --limit 10   # test
  ./venv312/bin/python scripts/12_link_trials_experiments.py --refresh-mesh  # re-run NER
"""

from __future__ import annotations

import argparse
import json
import sys
import warnings
from collections import defaultdict
from pathlib import Path
from typing import Any

warnings.filterwarnings("ignore", category=FutureWarning)

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import config  # noqa: E402

import pandas as pd  # noqa: E402
from sklearn.feature_extraction.text import TfidfVectorizer  # noqa: E402
from sklearn.metrics.pairwise import cosine_similarity  # noqa: E402
from tqdm import tqdm  # noqa: E402


# ---------------------------------------------------------------------------
# Paths + thresholds
# ---------------------------------------------------------------------------
PROJECT_ROOT = config.PROJECT_ROOT
TRIALS_CSV = config.PROCESSED_DIR / "clinical_trials.csv"
EXPERIMENTS_CSV = config.PROCESSED_DIR / "classified_experiments_nlp.csv"
CLASS_CONFIG = PROJECT_ROOT / "config" / "classification_config.json"

OUT_LINKS_CSV = config.PROCESSED_DIR / "trial_experiment_links.csv"
OUT_SUMMARY_JSON = config.PROCESSED_DIR / "trial_linkage_summary.json"
MESH_CACHE = config.CHECKPOINT_DIR / "trial_mesh_cache.json"

# Thresholds from spec sections 2.2, 3.2, 4.2, 5
MESH_THRESHOLD = 0.5
COSINE_THRESHOLD = 0.15
FINAL_THRESHOLD = 0.3
STRONG_THRESHOLD = 0.6
MODERATE_THRESHOLD = 0.4

# Combination weights from spec section 5
W_MESH = 0.5
W_AREA = 0.2
W_COSINE = 0.3


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def parse_set(val: object, sep: str = "; ") -> set[str]:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return set()
    s = str(val).strip()
    if not s or s.lower() == "nan":
        return set()
    return {part.strip() for part in s.split(sep) if part.strip()}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text())


# ---------------------------------------------------------------------------
# SciSpacy backend (trimmed down copy of script 10's SciSpacyBackend —
# kept inline so this script is self-contained per the spec's design)
# ---------------------------------------------------------------------------
class TrialNER:
    """Extract MeSH Descriptor IDs from a trial's title + conditions."""

    def __init__(self, cfg: dict[str, Any], name_lookup: dict[str, str]) -> None:
        import spacy
        import scispacy  # noqa: F401 — registers pipe factory
        from scispacy.linking import EntityLinker  # noqa: F401

        sci = cfg["scispacy"]
        self.min_score = float(sci.get("min_entity_score", 0.7))
        self.name_lookup = name_lookup

        print(f"  loading {sci['model']} ...")
        self.nlp = spacy.load(sci["model"])
        print(f"  attaching MeSH entity linker ({sci.get('linker', 'mesh')}) ...")
        self.nlp.add_pipe(
            "scispacy_linker",
            config={"resolve_abbreviations": True, "linker_name": sci.get("linker", "mesh")},
        )
        self.linker = self.nlp.get_pipe("scispacy_linker")
        print("  ready")

    def extract(self, text: str) -> list[str]:
        """Return a de-duplicated list of MeSH Descriptor IDs."""
        if not text or not text.strip():
            return []
        doc = self.nlp(text)
        out: list[str] = []
        for ent in doc.ents:
            if ent.label_ != "DISEASE" or not ent._.kb_ents:
                continue
            for cui, score in ent._.kb_ents:
                if score < self.min_score:
                    break
                concept = self.linker.kb.cui_to_entity.get(cui)
                if concept is None:
                    continue
                names = [concept.canonical_name] if concept.canonical_name else []
                names.extend(concept.aliases or [])
                matched = None
                for nm in names:
                    did = self.name_lookup.get(nm.strip().lower())
                    if did:
                        matched = did
                        break
                if matched:
                    if matched not in out:
                        out.append(matched)
                    break
        return out


# ---------------------------------------------------------------------------
# Trial MeSH extraction (with cache)
# ---------------------------------------------------------------------------
def extract_trial_mesh(
    trials: pd.DataFrame,
    ner: TrialNER,
    refresh: bool,
) -> dict[str, list[str]]:
    cache: dict[str, list[str]] = {}
    if MESH_CACHE.exists() and not refresh:
        try:
            cache = load_json(MESH_CACHE)
            print(f"  loaded cache: {len(cache):,} trials already done")
        except Exception:
            cache = {}

    missing = [
        (str(r["nct_id"]), r)
        for _, r in trials.iterrows()
        if str(r["nct_id"]) not in cache
    ]
    if not missing:
        return cache

    print(f"  running NER on {len(missing):,} trials ...")
    for nct_id, r in tqdm(missing, unit="trial"):
        title = str(r.get("title") or "")
        cond = str(r.get("conditions") or "")
        text = (title + " . " + cond).strip()
        cache[nct_id] = ner.extract(text)

    config.save_json(MESH_CACHE, cache)
    return cache


# ---------------------------------------------------------------------------
# Core linkage
# ---------------------------------------------------------------------------
def build_trial_text(row: dict[str, Any]) -> str:
    parts = []
    for field in ("title", "conditions", "interventions"):
        v = row.get(field)
        if v is None:
            continue
        s = str(v).strip()
        if s and s.lower() != "nan":
            parts.append(s)
    return " . ".join(parts)


def build_experiment_text(row: dict[str, Any]) -> str:
    parts = []
    for field in ("title", "objectives", "approach", "results"):
        v = row.get(field)
        if v is None:
            continue
        s = str(v).strip()
        if s and s.lower() != "nan":
            parts.append(s)
    return " . ".join(parts)


def strength_label(score: float) -> str:
    if score >= STRONG_THRESHOLD:
        return "strong"
    if score >= MODERATE_THRESHOLD:
        return "moderate"
    return "weak"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Only process the first N trials (for testing).",
    )
    parser.add_argument(
        "--refresh-mesh",
        action="store_true",
        help="Ignore the trial MeSH cache and re-run NER on every trial.",
    )
    args = parser.parse_args()

    print("Loading inputs ...")
    trials = pd.read_csv(TRIALS_CSV)
    experiments = pd.read_csv(EXPERIMENTS_CSV)
    cfg = load_json(CLASS_CONFIG)
    name_lookup = load_json(PROJECT_ROOT / cfg["mesh_name_to_descriptor"])
    print(
        f"  {len(trials):,} trials, "
        f"{len(experiments):,} experiments, "
        f"{len(name_lookup):,} MeSH name variants"
    )

    # Normalise experiment health flag + filter down
    experiments["health_related_bool"] = (
        experiments["health_related"]
        .astype(str)
        .str.lower()
        .map({"true": True, "false": False})
        .fillna(False)
    )
    health_exp = experiments[experiments["health_related_bool"]].copy().reset_index(drop=True)
    print(f"  {len(health_exp):,} health-related experiments (Layer 1 candidates)")

    # Optional limit for test runs
    if args.limit:
        trials = trials.head(args.limit).copy()
        print(f"  LIMIT MODE — processing first {len(trials)} trials only")

    # Build experiment MeSH sets from mesh_evidence column
    exp_mesh_sets: dict[str, set[str]] = {}
    exp_area_sets: dict[str, set[str]] = {}
    exp_text_by_id: dict[str, str] = {}
    for _, r in health_exp.iterrows():
        osid = str(r["osID"])
        exp_mesh_sets[osid] = parse_set(r.get("mesh_evidence"), sep="|")
        exp_area_sets[osid] = parse_set(r.get("disease_areas"), sep="; ")
        exp_text_by_id[osid] = build_experiment_text(r.to_dict())

    # Trial-side NER
    print("Initializing SciSpacy backend ...")
    ner = TrialNER(cfg, name_lookup)

    print("Extracting MeSH from trials ...")
    trial_mesh_cache = extract_trial_mesh(trials, ner, refresh=args.refresh_mesh)
    trial_mesh_sets: dict[str, set[str]] = {
        str(r["nct_id"]): set(trial_mesh_cache.get(str(r["nct_id"]), []))
        for _, r in trials.iterrows()
    }
    trial_area_sets: dict[str, set[str]] = {
        str(r["nct_id"]): parse_set(r.get("disease_areas"), sep="; ")
        for _, r in trials.iterrows()
    }
    trial_text_by_id: dict[str, str] = {
        str(r["nct_id"]): build_trial_text(r.to_dict()) for _, r in trials.iterrows()
    }

    # Layer 2 pre-filter: candidate experiments share >=1 disease area
    print("Pre-filtering by disease-area overlap ...")
    candidates: list[tuple[str, str]] = []
    area_to_exp: dict[str, list[str]] = defaultdict(list)
    for osid, areas in exp_area_sets.items():
        for a in areas:
            area_to_exp[a].append(osid)

    for nct_id, t_areas in trial_area_sets.items():
        seen: set[str] = set()
        for a in t_areas:
            for osid in area_to_exp.get(a, []):
                if osid not in seen:
                    seen.add(osid)
                    candidates.append((nct_id, osid))
    print(f"  {len(candidates):,} candidate (trial, experiment) pairs after pre-filter")

    if not candidates:
        print("No candidates after pre-filter — nothing to link.")
        _write_empty_outputs(trials, experiments, health_exp)
        return

    # TF-IDF on the full corpus we actually need
    print("Building TF-IDF matrix ...")
    trial_ids = list(trials["nct_id"].astype(str))
    exp_ids = list(health_exp["osID"].astype(str))
    corpus = [trial_text_by_id[t] for t in trial_ids] + [exp_text_by_id[e] for e in exp_ids]
    # Biomedical text: min_df=2 to drop hapax, stop_words english
    vectorizer = TfidfVectorizer(
        lowercase=True,
        stop_words="english",
        ngram_range=(1, 2),
        min_df=2,
        max_df=0.9,
    )
    matrix = vectorizer.fit_transform(corpus)
    trial_matrix = matrix[: len(trial_ids)]
    exp_matrix = matrix[len(trial_ids):]
    print(
        f"  vocab={len(vectorizer.vocabulary_):,}  "
        f"trials={trial_matrix.shape}  experiments={exp_matrix.shape}"
    )

    # Full cosine matrix for the health subset — only 534x432 floats, trivial
    print("Computing cosine similarity matrix ...")
    cosine_mat = cosine_similarity(trial_matrix, exp_matrix)
    trial_row_index = {tid: i for i, tid in enumerate(trial_ids)}
    exp_col_index = {eid: j for j, eid in enumerate(exp_ids)}

    # Score every candidate pair
    print("Scoring candidate pairs ...")
    scored_rows: list[dict[str, Any]] = []
    trial_by_nct = {str(r["nct_id"]): r for _, r in trials.iterrows()}
    exp_by_osid = {str(r["osID"]): r for _, r in health_exp.iterrows()}

    for nct_id, osid in tqdm(candidates, unit="pair"):
        t_mesh = trial_mesh_sets.get(nct_id, set())
        e_mesh = exp_mesh_sets.get(osid, set())
        shared_mesh = sorted(t_mesh & e_mesh)

        denom_mesh = min(len(t_mesh), len(e_mesh))
        mesh_score = len(shared_mesh) / denom_mesh if denom_mesh > 0 else 0.0

        t_areas = trial_area_sets.get(nct_id, set())
        e_areas = exp_area_sets.get(osid, set())
        shared_areas = sorted(t_areas & e_areas)
        area_score = len(shared_areas) / len(t_areas) if t_areas else 0.0

        i = trial_row_index.get(nct_id)
        j = exp_col_index.get(osid)
        cosine_score = float(cosine_mat[i, j]) if (i is not None and j is not None) else 0.0

        final_score = W_MESH * mesh_score + W_AREA * area_score + W_COSINE * cosine_score

        # Spec section 5 acceptance rule
        accept = (
            final_score >= FINAL_THRESHOLD
            and (mesh_score >= MESH_THRESHOLD or cosine_score >= COSINE_THRESHOLD)
        )
        if not accept:
            continue

        scored_rows.append(
            {
                "nct_id": nct_id,
                "osID": osid,
                "trial_title": str(trial_by_nct[nct_id].get("title") or ""),
                "experiment_title": str(exp_by_osid[osid].get("title") or ""),
                "link_strength": strength_label(final_score),
                "final_score": round(final_score, 4),
                "mesh_score": round(mesh_score, 4),
                "area_score": round(area_score, 4),
                "cosine_score": round(cosine_score, 4),
                "shared_mesh_ids": "|".join(shared_mesh),
                "shared_areas": "; ".join(shared_areas),
            }
        )

    links_df = pd.DataFrame(scored_rows)
    if not links_df.empty:
        links_df = links_df.sort_values(
            ["final_score", "nct_id", "osID"], ascending=[False, True, True]
        ).reset_index(drop=True)

    # Write outputs
    OUT_LINKS_CSV.parent.mkdir(parents=True, exist_ok=True)
    links_df.to_csv(OUT_LINKS_CSV, index=False)
    print(f"\nWrote {OUT_LINKS_CSV.relative_to(PROJECT_ROOT)}  ({len(links_df):,} rows)")

    # Summary JSON
    summary = _build_summary(
        trials=trials,
        experiments=experiments,
        health_experiments=health_exp,
        links=links_df,
    )
    config.save_json(OUT_SUMMARY_JSON, summary)
    print(f"Wrote {OUT_SUMMARY_JSON.relative_to(PROJECT_ROOT)}")

    _print_report(links_df, summary)


def _build_summary(
    *,
    trials: pd.DataFrame,
    experiments: pd.DataFrame,
    health_experiments: pd.DataFrame,
    links: pd.DataFrame,
) -> dict[str, Any]:
    total_trials = int(len(trials))
    total_experiments = int(len(experiments))
    trials_with_links = int(links["nct_id"].nunique()) if not links.empty else 0
    experiments_with_links = int(links["osID"].nunique()) if not links.empty else 0
    by_strength = (
        links["link_strength"].value_counts().to_dict() if not links.empty else {}
    )
    for k in ("strong", "moderate", "weak"):
        by_strength.setdefault(k, 0)

    coverage_by_area: dict[str, dict[str, int]] = {}
    if not links.empty:
        for area in config.DISEASE_AREA_NAMES:
            mask = links["shared_areas"].fillna("").str.contains(area, regex=False)
            sub = links[mask]
            coverage_by_area[area] = {
                "links": int(len(sub)),
                "trials": int(sub["nct_id"].nunique()),
                "experiments": int(sub["osID"].nunique()),
            }
    else:
        for area in config.DISEASE_AREA_NAMES:
            coverage_by_area[area] = {"links": 0, "trials": 0, "experiments": 0}

    return {
        "total_trials": total_trials,
        "trials_with_links": trials_with_links,
        "total_experiments": total_experiments,
        "health_related_experiments": int(len(health_experiments)),
        "experiments_with_links": experiments_with_links,
        "total_links": int(len(links)),
        "links_by_strength": {k: int(v) for k, v in by_strength.items()},
        "links_per_trial_avg": round(
            float(len(links)) / total_trials if total_trials else 0.0, 3
        ),
        "links_per_experiment_avg": round(
            float(len(links)) / int(len(health_experiments))
            if len(health_experiments)
            else 0.0,
            3,
        ),
        "coverage_by_area": coverage_by_area,
    }


def _write_empty_outputs(
    trials: pd.DataFrame,
    experiments: pd.DataFrame,
    health_experiments: pd.DataFrame,
) -> None:
    empty_cols = [
        "nct_id",
        "osID",
        "trial_title",
        "experiment_title",
        "link_strength",
        "final_score",
        "mesh_score",
        "area_score",
        "cosine_score",
        "shared_mesh_ids",
        "shared_areas",
    ]
    pd.DataFrame(columns=empty_cols).to_csv(OUT_LINKS_CSV, index=False)
    summary = _build_summary(
        trials=trials,
        experiments=experiments,
        health_experiments=health_experiments,
        links=pd.DataFrame(columns=empty_cols),
    )
    config.save_json(OUT_SUMMARY_JSON, summary)


def _print_report(links: pd.DataFrame, summary: dict[str, Any]) -> None:
    print()
    print("=" * 70)
    print("Linkage summary")
    print("=" * 70)
    print(f"Total trials                : {summary['total_trials']:,}")
    print(f"Trials with >=1 link        : {summary['trials_with_links']:,}  "
          f"({summary['trials_with_links']/summary['total_trials']:.1%})")
    print(f"Health-related experiments  : {summary['health_related_experiments']:,}")
    print(f"Experiments with >=1 link   : {summary['experiments_with_links']:,}")
    print(f"Total links                 : {summary['total_links']:,}")
    print()
    bs = summary["links_by_strength"]
    print(f"Strong links    (>= {STRONG_THRESHOLD})   : {bs.get('strong', 0):,}")
    print(f"Moderate links  (>= {MODERATE_THRESHOLD})   : {bs.get('moderate', 0):,}")
    print(f"Weak links      (>= {FINAL_THRESHOLD})   : {bs.get('weak', 0):,}")
    print()

    print("Per disease area:")
    print(f"  {'Area':40s} {'links':>7s} {'trials':>7s} {'exp':>7s}")
    for area, stats in summary["coverage_by_area"].items():
        print(
            f"  {area:40s} {stats['links']:7d} {stats['trials']:7d} {stats['experiments']:7d}"
        )

    if not links.empty:
        print()
        print("Top 10 strongest links:")
        for _, r in links.head(10).iterrows():
            print(
                f"  [{r['link_strength']:8s}] f={r['final_score']:.2f} "
                f"m={r['mesh_score']:.2f} a={r['area_score']:.2f} c={r['cosine_score']:.2f}  "
                f"{r['nct_id']} <-> {r['osID']}"
            )
            print(f"    trial : {str(r['trial_title'])[:80]}")
            print(f"    exp   : {str(r['experiment_title'])[:80]}")
            if r["shared_mesh_ids"]:
                print(f"    mesh  : {r['shared_mesh_ids']}")
            if r["shared_areas"]:
                print(f"    areas : {r['shared_areas']}")

        zero_link_trials = summary["total_trials"] - summary["trials_with_links"]
        print()
        print(f"Trials with zero links      : {zero_link_trials:,}")


if __name__ == "__main__":
    main()
