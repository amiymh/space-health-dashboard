"""
05_classify_experiments.py

Phase 2: classify every experiment in all_experiments.csv against the 10
SNIH disease areas using Claude (via OpenRouter).

For each experiment, the model returns:
  - For each relevant disease area: relevance ("direct" / "indirect" / "none"),
    confidence (0.0-1.0), and a one-sentence reasoning string.
  - Or {"health_related": false, "category": "..."} for non-health work.

Inputs:
  - data/processed/all_experiments.csv

Output:
  - data/processed/classified_experiments.csv (master + 10 disease columns)
  - data/checkpoints/classification_checkpoint.json (resume support)

Batch size: 50 per API run. Estimated cost: $5-15 across the catalog.

Status: STUB.

See SPACE_HEALTH_SPECS.md section 3.3.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import get_env, load_env  # noqa: E402

CLASSIFICATION_PROMPT = """\
Classify this ISS experiment against these disease areas. Return a JSON object.

Experiment: {title}
Description: {description}

Disease areas: {areas}

For each relevant disease area, assign:
- relevance: "direct" (explicitly studies this disease), "indirect" (results
  applicable to this disease), or "none"
- confidence: 0.0-1.0
- reasoning: one sentence explaining the connection

If the experiment is not health-related, return
{{"health_related": false, "category": "..."}}.
"""


def main() -> None:
    load_env()
    _ = get_env("OPENROUTER_API_KEY", required=False)
    # Will use scripts.config.DISEASE_AREAS and PROCESSED_DIR once implemented.

    # TODO: Load all_experiments.csv with pandas.
    # TODO: Resume from checkpoint if present.
    # TODO: For each batch of 50:
    #         build prompts, call OpenRouter with claude-opus-4-6 (or similar),
    #         parse JSON responses, append to results, checkpoint.
    # TODO: Write classified_experiments.csv with disease_area columns.

    print("Script not yet implemented. See SPACE_HEALTH_SPECS.md Section 3.3.")


if __name__ == "__main__":
    main()
