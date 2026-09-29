#!/usr/bin/env python3
"""Canonical v1.1 five-model comparison.

Extends the shared comparison engine with the historical release-time decision
model while reusing the same HAC, stability, drift, path, and agreement logic.
"""

from __future__ import annotations

import compare_directional_models as engine

MODEL_COLUMNS = {
    "old_tff": "old_tff_score",
    "old_legacy": "old_legacy_score",
    "new_structural": "structural_score",
    "new_structural_tactical": "adjusted_cot_score",
    "new_release_decision": "release_decision_score",
}
NEW_MODELS = {
    "new_structural",
    "new_structural_tactical",
    "new_release_decision",
}

# Patch the shared engine's runtime configuration before re-exporting functions.
engine.MODEL_COLUMNS = MODEL_COLUMNS
engine.NEW_MODELS = NEW_MODELS

agreement_rows = engine.agreement_rows
hac_slope_stats = engine.hac_slope_stats
load_aligned = engine.load_aligned
model_summary_rows = engine.model_summary_rows
threshold_for_model = engine.threshold_for_model


def main() -> None:
    engine.main()


if __name__ == "__main__":
    main()
