"""
Spec 03 — Deterministic disease-area classification for ISS experiments.

Input : data/processed/osdr_experiments.csv     (3,829 rows)
Output: data/processed/classified_experiments_nlp.csv
        data/processed/nlp_classification_details.json   (per-experiment evidence)

This script is BACKEND-AGNOSTIC. It supports three NER backends selected
via config/classification_config.json:

  - scispacy   (default, local, no account required)
  - pubtator   (HTTP to NLM PubTator3 annotate API; fallback; scaffolded)
  - metamaplite (local UMLS indexes; future; scaffolded, not tested)

Only the SciSpacy backend is fully active right now. The other two are
wired up but will raise NotImplementedError until a real endpoint / index
is available.

All three share the same post-processing:
  1. Detect disease entities in the experiment text.
  2. Resolve each to a MeSH Descriptor ID (D-number).
  3. Look up tree codes via scripts/mesh_tree_lookup.json.
  4. Match tree code prefixes against scripts/mesh_snih_crosswalk.json.
  5. Collect matching SNIH disease areas (multi-label).

Re-run safe — checkpoints every CHECKPOINT_EVERY experiments to
data/checkpoints/nlp_classify_checkpoint.json.

Usage:
    python scripts/10_classify_nlp.py               # full run
    python scripts/10_classify_nlp.py --limit 10    # test on first 10
    python scripts/10_classify_nlp.py --fresh       # ignore checkpoint
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
import warnings
from collections import Counter
from pathlib import Path
from typing import Any

warnings.filterwarnings("ignore", category=FutureWarning)

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import config  # noqa: E402

import pandas as pd  # noqa: E402
from tqdm import tqdm  # noqa: E402


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = config.PROJECT_ROOT
CONFIG_PATH = PROJECT_ROOT / "config" / "classification_config.json"
INPUT_CSV = config.PROCESSED_DIR / "osdr_experiments.csv"
OUTPUT_CSV = config.PROCESSED_DIR / "classified_experiments_nlp.csv"
DETAILS_JSON = config.PROCESSED_DIR / "nlp_classification_details.json"
CHECKPOINT_FILE = config.CHECKPOINT_DIR / "nlp_classify_checkpoint.json"

CHECKPOINT_EVERY = 100
MIN_TEXT_CHARS = 40   # below this, mark insufficient_text

# Output CSV columns (schema from spec section 7.3)
EXTRA_COLUMNS = [
    "health_related",
    "disease_areas",
    "primary_disease_area",
    "relevance_type",
    "classification_source",
    "non_health_category",
    "mesh_evidence",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def load_config() -> dict[str, Any]:
    return json.loads(CONFIG_PATH.read_text())


def load_json_file(rel_or_abs: str) -> Any:
    path = Path(rel_or_abs)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return json.loads(path.read_text())


def concat_experiment_text(row: dict[str, Any]) -> str:
    """Build the text blob the NER sees (spec 7.2 step 1)."""
    parts: list[str] = []
    for field in (
        "title",
        "objectives",
        "approach",
        "results",
        "researchAreas",
        "publication_titles",
    ):
        val = row.get(field)
        if val is None:
            continue
        s = str(val).strip()
        if s and s.lower() != "nan":
            parts.append(s)
    return " \n ".join(parts)


def tree_codes_to_snih_areas(
    tree_codes: list[str],
    crosswalk: dict[str, dict[str, Any]],
) -> list[str]:
    """A tree code matches a SNIH area if it starts with any crosswalk prefix."""
    areas: list[str] = []
    for area, entry in crosswalk.items():
        prefixes = entry.get("mesh_branches", [])
        for tc in tree_codes:
            if any(tc == p or tc.startswith(p + ".") for p in prefixes):
                if area not in areas:
                    areas.append(area)
                break
    return areas


# ---------------------------------------------------------------------------
# Backend: SciSpacy
# ---------------------------------------------------------------------------
class SciSpacyBackend:
    """
    SciSpacy en_ner_bc5cdr_md + MeSH entity linker.

    Note on IDs: scispacy's "mesh" linker returns UMLS CUIs (e.g. C0029456),
    not MeSH Descriptor IDs (D-numbers). We bridge CUI -> D-number via a
    name lookup built from dhimmel/mesh descriptor-terms.tsv. See
    build_mesh_tree_lookup.py.
    """

    name = "scispacy"

    def __init__(
        self,
        cfg: dict[str, Any],
        name_lookup: dict[str, str],
    ) -> None:
        import spacy
        import scispacy  # noqa: F401 — needed so EntityLinker pipe factory is registered
        from scispacy.linking import EntityLinker  # noqa: F401

        model_name = cfg["scispacy"]["model"]
        linker_name = cfg["scispacy"].get("linker", "mesh")
        self.min_score = float(cfg["scispacy"].get("min_entity_score", 0.7))
        self.name_lookup = name_lookup

        print(f"  loading {model_name}...")
        self.nlp = spacy.load(model_name)
        print(f"  attaching MeSH entity linker ({linker_name})...")
        self.nlp.add_pipe(
            "scispacy_linker",
            config={"resolve_abbreviations": True, "linker_name": linker_name},
        )
        self.linker = self.nlp.get_pipe("scispacy_linker")
        print("  ready")

    def extract_descriptors(self, text: str) -> tuple[list[str], list[dict[str, Any]]]:
        """
        Return (mesh_descriptor_ids, debug_entities).

        debug_entities is a list of dicts kept for the details JSON so the
        user can audit what fired.
        """
        if not text.strip():
            return [], []

        doc = self.nlp(text)
        descriptor_ids: list[str] = []
        debug: list[dict[str, Any]] = []

        for ent in doc.ents:
            if ent.label_ != "DISEASE":
                continue
            if not ent._.kb_ents:
                continue

            # Try each candidate CUI in score-descending order.
            matched_did: str | None = None
            matched_cui: str | None = None
            matched_score: float = 0.0
            matched_name: str | None = None

            for cui, score in ent._.kb_ents:
                if score < self.min_score:
                    break  # kb_ents is score-sorted
                concept = self.linker.kb.cui_to_entity.get(cui)
                if concept is None:
                    continue

                names_to_try: list[str] = []
                if concept.canonical_name:
                    names_to_try.append(concept.canonical_name)
                names_to_try.extend(concept.aliases or [])

                for nm in names_to_try:
                    did = self.name_lookup.get(nm.strip().lower())
                    if did:
                        matched_did = did
                        matched_cui = cui
                        matched_score = float(score)
                        matched_name = nm
                        break
                if matched_did:
                    break

            if matched_did:
                if matched_did not in descriptor_ids:
                    descriptor_ids.append(matched_did)
                debug.append(
                    {
                        "text": ent.text,
                        "label": ent.label_,
                        "cui": matched_cui,
                        "score": round(matched_score, 3),
                        "matched_name": matched_name,
                        "descriptor_id": matched_did,
                    }
                )
            else:
                debug.append(
                    {
                        "text": ent.text,
                        "label": ent.label_,
                        "cui": None,
                        "note": "no MeSH descriptor match above threshold",
                    }
                )

        return descriptor_ids, debug


class PubTatorBackend:
    """
    NLM PubTator3 annotate-text backend. SCAFFOLDED — not exercised.

    The documented endpoint at
    https://www.ncbi.nlm.nih.gov/research/pubtator3-api/annotate/
    currently returns HTTP 404 for ad-hoc text, so we raise
    NotImplementedError on construction. Implementation is intentionally
    left as a skeleton for when the endpoint is reinstated.
    """

    name = "pubtator"

    def __init__(self, cfg: dict[str, Any], name_lookup: dict[str, str]) -> None:
        self.api_url = cfg["pubtator"]["api_url"]
        self.throttle = 1.0 / float(cfg["pubtator"].get("requests_per_second", 3))
        self.name_lookup = name_lookup
        raise NotImplementedError(
            "PubTator annotate-text endpoint is unreachable. "
            "Re-enable this backend when the NLM PubTator3 API exposes "
            "ad-hoc text annotation again."
        )

    def extract_descriptors(self, text: str) -> tuple[list[str], list[dict[str, Any]]]:
        import requests

        if not text.strip():
            return [], []
        r = requests.post(
            self.api_url,
            data=text.encode("utf-8"),
            headers={"Content-Type": "text/plain", **config.REQUEST_HEADERS},
            timeout=60,
        )
        r.raise_for_status()
        time.sleep(self.throttle)
        # BioC JSON parsing would go here; each annotation has infons['identifier']
        # in the form "MESH:D010024" for diseases. Map them through the same
        # name_lookup as a fallback if only a name is present.
        raise NotImplementedError("BioC JSON parser for PubTator3 not implemented")


class MetaMapLiteBackend:
    """
    pyMetaMapLite backend. SCAFFOLDED — not exercised.

    Requires a free UMLS account and the 2024AA USAbase inverted-index
    data to be present at cfg['metamaplite']['ivf_dir']. Raises
    NotImplementedError on construction otherwise.
    """

    name = "metamaplite"

    def __init__(self, cfg: dict[str, Any], name_lookup: dict[str, str]) -> None:
        ivf_dir = PROJECT_ROOT / cfg["metamaplite"]["ivf_dir"]
        self.name_lookup = name_lookup
        if not ivf_dir.exists():
            raise NotImplementedError(
                f"MetaMapLite index directory not found at {ivf_dir}. "
                "Download the UMLS 2024AA USAbase dataset (free UMLS account "
                "required) and extract it there to activate this backend."
            )
        raise NotImplementedError("pyMetaMapLite wiring not implemented yet")

    def extract_descriptors(self, text: str) -> tuple[list[str], list[dict[str, Any]]]:  # noqa: D401
        raise NotImplementedError


def build_backend(cfg: dict[str, Any], name_lookup: dict[str, str]):
    backend_name = cfg.get("backend", "scispacy").lower()
    if backend_name == "scispacy":
        return SciSpacyBackend(cfg, name_lookup)
    if backend_name == "pubtator":
        return PubTatorBackend(cfg, name_lookup)
    if backend_name == "metamaplite":
        return MetaMapLiteBackend(cfg, name_lookup)
    raise ValueError(f"Unknown backend {backend_name!r}")


# ---------------------------------------------------------------------------
# Checkpoint
# ---------------------------------------------------------------------------
def load_checkpoint() -> dict[str, Any]:
    if not CHECKPOINT_FILE.exists():
        return {"processed_ids": [], "backend": None}
    try:
        return json.loads(CHECKPOINT_FILE.read_text())
    except Exception:
        return {"processed_ids": [], "backend": None}


def save_checkpoint(state: dict[str, Any]) -> None:
    config.save_json(CHECKPOINT_FILE, state)


# ---------------------------------------------------------------------------
# Row processing
# ---------------------------------------------------------------------------
def classify_row(
    row: dict[str, Any],
    backend: Any,
    tree_lookup: dict[str, list[str]],
    crosswalk: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Run one experiment through the backend and build the output row."""
    text = concat_experiment_text(row)

    # Insufficient-text guard (spec 5.3)
    if len(text) < MIN_TEXT_CHARS:
        return {
            **row,
            "health_related": False,
            "disease_areas": "",
            "primary_disease_area": "",
            "relevance_type": "insufficient_text",
            "classification_source": backend.name,
            "non_health_category": "",
            "mesh_evidence": "",
            "_debug": [{"note": "text too short for NER"}],
        }

    descriptor_ids, debug_entities = backend.extract_descriptors(text)

    # Count SNIH-area hits per descriptor for primary selection
    area_hit_counter: Counter[str] = Counter()
    evidence_descriptors: list[str] = []

    for did in descriptor_ids:
        tree_codes = tree_lookup.get(did, [])
        if not tree_codes:
            continue
        areas = tree_codes_to_snih_areas(tree_codes, crosswalk)
        if areas:
            evidence_descriptors.append(did)
            for a in areas:
                area_hit_counter[a] += 1

    if area_hit_counter:
        # Sort by (-count, name) for deterministic primary
        ordered_areas = sorted(
            area_hit_counter.items(), key=lambda kv: (-kv[1], kv[0])
        )
        disease_areas = [a for a, _ in ordered_areas]
        primary = disease_areas[0]
        return {
            **row,
            "health_related": True,
            "disease_areas": "; ".join(disease_areas),
            "primary_disease_area": primary,
            "relevance_type": "deterministic",
            "classification_source": backend.name,
            "non_health_category": "",
            "mesh_evidence": "|".join(evidence_descriptors),
            "_debug": debug_entities,
        }

    # No SNIH match
    return {
        **row,
        "health_related": False,
        "disease_areas": "",
        "primary_disease_area": "",
        "relevance_type": "deterministic",
        "classification_source": backend.name,
        "non_health_category": "",
        "mesh_evidence": "",
        "_debug": debug_entities,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Only process the first N experiments (for testing).",
    )
    parser.add_argument(
        "--fresh",
        action="store_true",
        help="Ignore any existing checkpoint and start over.",
    )
    args = parser.parse_args()

    cfg = load_config()
    backend_name = cfg.get("backend", "scispacy").lower()

    print(f"Backend: {backend_name}")
    print(f"Input  : {INPUT_CSV.relative_to(PROJECT_ROOT)}")

    df = pd.read_csv(INPUT_CSV)
    if args.limit:
        df = df.head(args.limit)
        print(f"LIMIT MODE — processing first {len(df)} experiments only")

    print(f"  loaded {len(df):,} experiments")
    print("Loading MeSH lookups...")
    tree_lookup: dict[str, list[str]] = load_json_file(cfg["mesh_tree_lookup"])
    name_lookup: dict[str, str] = load_json_file(cfg["mesh_name_to_descriptor"])
    crosswalk: dict[str, dict[str, Any]] = load_json_file(cfg["crosswalk"])
    print(
        f"  {len(tree_lookup):,} descriptors, "
        f"{len(name_lookup):,} term variants, "
        f"{len(crosswalk)} SNIH areas"
    )

    print("Initializing backend...")
    backend = build_backend(cfg, name_lookup)

    # Checkpoint logic: only used for full runs, not --limit/--fresh
    use_checkpoint = args.limit is None and not args.fresh
    state = load_checkpoint() if use_checkpoint else {"processed_ids": [], "backend": None}
    already_done: set[str] = set(state.get("processed_ids", [])) if state.get("backend") == backend.name else set()
    if already_done:
        print(f"  resuming from checkpoint: {len(already_done):,} already classified")
    else:
        state = {"processed_ids": [], "backend": backend.name, "rows": []}

    # Prior rows from checkpoint + details
    rows_out: list[dict[str, Any]] = state.get("rows", []) if already_done else []
    details: dict[str, Any] = {}
    if already_done and DETAILS_JSON.exists():
        try:
            details = json.loads(DETAILS_JSON.read_text())
        except Exception:
            details = {}

    remaining = df[~df["osID"].astype(str).isin(already_done)]
    print(f"  {len(remaining):,} experiments to process")

    pbar = tqdm(remaining.to_dict(orient="records"), total=len(remaining), unit="exp")
    for row in pbar:
        osid = str(row.get("osID") or "")
        # pandas NaN -> None
        clean_row = {k: (None if pd.isna(v) else v) for k, v in row.items()}
        try:
            result = classify_row(clean_row, backend, tree_lookup, crosswalk)
        except Exception as e:  # pragma: no cover — defensive
            pbar.write(f"error on {osid}: {type(e).__name__}: {e}")
            result = {
                **clean_row,
                "health_related": False,
                "disease_areas": "",
                "primary_disease_area": "",
                "relevance_type": "error",
                "classification_source": backend.name,
                "non_health_category": "",
                "mesh_evidence": "",
                "_debug": [{"error": f"{type(e).__name__}: {e}"}],
            }

        debug = result.pop("_debug", [])
        details[osid] = {
            "disease_areas": result["disease_areas"],
            "primary_disease_area": result["primary_disease_area"],
            "mesh_evidence": result["mesh_evidence"],
            "entities": debug,
        }
        rows_out.append(result)

        if use_checkpoint and (len(rows_out) % CHECKPOINT_EVERY == 0):
            save_checkpoint(
                {
                    "processed_ids": [str(r.get("osID")) for r in rows_out],
                    "backend": backend.name,
                    "rows": rows_out,
                }
            )

    # Final persist
    out_df = pd.DataFrame(rows_out)
    # Make sure all expected columns exist and are ordered: original first, extras last
    original_cols = [c for c in df.columns if c not in EXTRA_COLUMNS]
    ordered_cols = original_cols + [c for c in EXTRA_COLUMNS if c in out_df.columns]
    out_df = out_df.reindex(columns=ordered_cols)

    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    out_df.to_csv(OUTPUT_CSV, index=False, quoting=csv.QUOTE_MINIMAL)
    config.save_json(DETAILS_JSON, details)
    if use_checkpoint:
        save_checkpoint(
            {
                "processed_ids": [str(r.get("osID")) for r in rows_out],
                "backend": backend.name,
                "rows": rows_out,
            }
        )

    # Summary
    print()
    print("=" * 60)
    print(f"Wrote {OUTPUT_CSV.relative_to(PROJECT_ROOT)}  ({len(out_df):,} rows)")
    print(f"Wrote {DETAILS_JSON.relative_to(PROJECT_ROOT)}")
    print()

    hr = out_df["health_related"].sum()
    total = len(out_df)
    print(f"health_related TRUE : {hr:,} / {total:,}  ({hr/total:.1%})")
    print(f"health_related FALSE: {total - hr:,} / {total:,}")
    print()

    insuf = (out_df["relevance_type"] == "insufficient_text").sum()
    print(f"insufficient_text   : {insuf:,}")
    print()

    area_counter: Counter[str] = Counter()
    for s in out_df["disease_areas"].dropna():
        if isinstance(s, str) and s:
            for a in s.split("; "):
                a = a.strip()
                if a:
                    area_counter[a] += 1

    print("Per disease area (NLP):")
    for area in config.DISEASE_AREA_NAMES:
        print(f"  {area:40s} {area_counter.get(area, 0):5d}")


if __name__ == "__main__":
    main()
