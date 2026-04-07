"""
Shared configuration for the Space-Health Dashboard pipeline.

Defines:
- The 10 SNIH disease areas with primary keywords + expansions
- API endpoints for OSDR, ClinicalTrials.gov, PubMed, etc.
- Path constants for raw/processed/checkpoint directories
- Helper functions for loading .env variables and saving JSON
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
CHECKPOINT_DIR = DATA_DIR / "checkpoints"

for _d in (RAW_DIR, PROCESSED_DIR, CHECKPOINT_DIR):
    _d.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# SNIH Disease Areas (Section 1.2 of SPACE_HEALTH_SPECS.md)
# ---------------------------------------------------------------------------
DISEASE_AREAS: dict[str, dict[str, list[str]]] = {
    "Cardiovascular diseases": {
        "primary": [
            "heart", "cardiac", "vascular", "hypertension", "atherosclerosis",
            "blood pressure", "arrhythmia", "endothelial", "aortic", "coronary",
            "thrombosis", "angiogenesis",
        ],
        "expansions": [
            "cardiovascular", "myocardium", "myocardial", "ventricle",
            "bed rest", "orthostatic intolerance",
        ],
    },
    "Kidney diseases": {
        "primary": [
            "renal", "nephro", "kidney", "glomerular", "tubular", "dialysis",
            "nephrolithiasis", "kidney stone", "urinary",
        ],
        "expansions": ["urolithiasis", "ureter", "calcium oxalate"],
    },
    "Cancer": {
        "primary": [
            "tumor", "oncology", "carcinoma", "neoplasm", "malignant",
            "metastasis", "leukemia", "lymphoma", "melanoma", "proliferation",
            "apoptosis",
        ],
        "expansions": ["radiation-induced", "carcinogenesis", "DNA damage", "tumour"],
    },
    "Neurological diseases": {
        "primary": [
            "brain", "neural", "neurodegenerative", "Alzheimer", "Parkinson",
            "dementia", "motor neuron", "neuropathy", "seizure", "epilepsy",
            "stroke", "cerebral",
        ],
        "expansions": [
            "neuron", "neurological", "central nervous system", "CNS",
            "vestibular", "cognitive decline",
        ],
    },
    "Eye diseases": {
        "primary": [
            "ocular", "retina", "optic", "vision", "intraocular pressure",
            "VIIP", "papilledema", "cataract", "glaucoma", "macular", "corneal",
        ],
        "expansions": [
            "SANS", "spaceflight-associated neuro-ocular syndrome", "eye",
            "visual impairment",
        ],
    },
    "Rare inherited disorders": {
        "primary": [
            "genetic disorder", "rare disease", "hereditary", "monogenic",
            "congenital", "orphan disease", "inborn error", "chromosomal",
        ],
        "expansions": ["mendelian", "genetic mutation", "inherited"],
    },
    "Women's health": {
        "primary": [
            "reproductive", "fertility", "ovarian", "uterine", "pregnancy",
            "menstrual", "breast", "cervical", "estrogen", "maternal",
            "gynecological",
        ],
        "expansions": ["female", "ovary", "menstruation"],
    },
    "Endocrine and metabolic diseases": {
        "primary": [
            "diabetes", "insulin", "thyroid", "metabolic syndrome", "obesity",
            "lipid", "glucose", "hormone", "adrenal", "pituitary",
            "growth hormone", "cortisol",
        ],
        "expansions": [
            "metabolism", "metabolic", "liver", "hepatic", "fatty acid",
            "cholesterol",
        ],
    },
    "Musculoskeletal diseases": {
        "primary": [
            "bone", "muscle", "skeletal", "osteoporosis", "sarcopenia",
            "atrophy", "cartilage", "joint", "spine", "fracture",
            "bone density", "bone loss", "tendon", "collagen",
        ],
        "expansions": [
            "musculoskeletal", "hindlimb unloading", "disuse", "osteoblast",
            "osteoclast", "myogenic",
        ],
    },
    "Mental health": {
        "primary": [
            "psychological", "cognitive", "stress", "anxiety", "depression",
            "sleep", "circadian", "isolation", "behavioral", "mood",
            "fatigue", "psychosocial", "neurobehavioral",
        ],
        "expansions": ["confinement", "wellbeing", "mental"],
    },
}

DISEASE_AREA_NAMES: list[str] = list(DISEASE_AREAS.keys())


def all_keywords(area: str) -> list[str]:
    """Return primary + expansion keywords for a disease area."""
    entry = DISEASE_AREAS[area]
    return entry["primary"] + entry.get("expansions", [])


# ---------------------------------------------------------------------------
# API Endpoints (Section 2)
# ---------------------------------------------------------------------------

# NASA OSDR
OSDR_EXPERIMENTS_API = "https://osdr.nasa.gov/geode-py/ws/api/experiments"
OSDR_EXPERIMENT_API = "https://osdr.nasa.gov/geode-py/ws/api/experiment/{osid}"
OSDR_SEARCH_API = "https://osdr.nasa.gov/osdr/data/search"
OSDR_V2_DATASETS = "https://visualization.osdr.nasa.gov/biodata/api/v2/datasets/"

# NASA Research Explorer
NASA_RESEARCH_EXPLORER_URL = "https://www.nasa.gov/mission/station/research-explorer/"

# ESA / JAXA / CSA
ESA_EEA_URL = "https://eea.spaceflight.esa.int"
JAXA_EXPERIMENTS_URL = "https://humans-in-space.jaxa.jp/en/bss/experiment/"
CSA_EXPERIMENTS_URL = "https://www.asc-csa.gc.ca/eng/sciences/experiments/"

# ClinicalTrials.gov
CLINICAL_TRIALS_API = "https://clinicaltrials.gov/api/v2/studies"

# PubMed
PUBMED_ESEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"

# Space keywords used to filter trials/publications down to space-relevant work
SPACE_KEYWORDS = [
    "microgravity",
    "spaceflight",
    "space station",
    "ISS",
    "astronaut",
    "simulated weightlessness",
    "bed rest study",
]


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------
OSDR_REQUEST_DELAY_SEC = 0.5
CLINICAL_TRIALS_DELAY_SEC = 0.3
PUBMED_DELAY_SEC = 0.4
OSDR_CHECKPOINT_EVERY = 50

# Standard request headers — identify the project to remote APIs
REQUEST_HEADERS = {
    "User-Agent": "space-health-dashboard/0.1 (KFCRIS research; contact: amiymh@gmail.com)",
    "Accept": "application/json",
}


# ---------------------------------------------------------------------------
# .env loader
# ---------------------------------------------------------------------------
def load_env(env_path: Path | None = None) -> None:
    """
    Load key=value pairs from a .env file into os.environ.

    Uses python-dotenv if available, falls back to a tiny manual parser
    so the scripts work even before requirements are installed.
    """
    path = env_path or (PROJECT_ROOT / ".env")
    try:
        from dotenv import load_dotenv  # type: ignore

        load_dotenv(path)
        return
    except Exception:
        pass

    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def get_env(key: str, default: str | None = None, *, required: bool = False) -> str | None:
    """Read an environment variable, optionally raising if missing."""
    value = os.environ.get(key, default)
    if required and not value:
        raise RuntimeError(
            f"Environment variable {key} is required but not set. "
            f"Add it to {PROJECT_ROOT / '.env'}"
        )
    return value


# ---------------------------------------------------------------------------
# JSON helpers
# ---------------------------------------------------------------------------
def save_json(path: Path, data: Any) -> None:
    """Atomically write JSON to disk (write to .tmp then rename)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str))
    tmp.replace(path)


def load_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        return default
