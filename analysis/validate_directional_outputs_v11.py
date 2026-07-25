#!/usr/bin/env python3
"""Canonical v1.1 output validation for the five-model comparison."""

from __future__ import annotations

import csv
from pathlib import Path

import validate_directional_outputs as engine

ROOT = Path(__file__).resolve().parent
ALIGNED = ROOT / "model_output" / "directional_model_comparison_aligned.csv"
SUMMARY = ROOT / "model_output" / "directional_model_comparison_summary.csv"
REPORT = ROOT / "directional_cot_report.html"

engine.COMPARISON_MODELS = {
    "old_tff",
    "old_legacy",
    "new_structural",
    "new_structural_tactical",
    "new_release_decision",
}
engine.NEW_MODELS = {
    "new_structural",
    "new_structural_tactical",
    "new_release_decision",
}


def read_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def validate_v11() -> None:
    failures: list[str] = []
    aligned = read_rows(ALIGNED)
    if not aligned or "release_decision_score" not in aligned[0]:
        failures.append("aligned comparison is missing release_decision_score")
    summary = read_rows(SUMMARY)
    release_rows = [row for row in summary if row.get("model") == "new_release_decision"]
    if len(release_rows) != 8:
        failures.append(f"expected 8 release-decision summary rows, found {len(release_rows)}")
    for row in release_rows:
        label = f"{row.get('market')} {row.get('horizon')} release decision"
        for field in (
            "score_hac_p",
            "edge_hac_p",
            "subperiod_sign_agreement_pct",
            "drift_adjusted_accuracy_pct",
            "avg_adverse_move",
            "path_utility",
        ):
            if engine.finite_number(row.get(field)) is None:
                failures.append(f"{label}: missing {field}")
    if not REPORT.exists():
        failures.append("directional report is missing")
    else:
        source = REPORT.read_text(encoding="utf-8", errors="replace")
        if "New full release decision" not in source:
            failures.append("report is missing the full release-decision model label")
    if failures:
        raise RuntimeError("Directional v1.1 output validation failed:\n- " + "\n- ".join(failures))


def main() -> None:
    engine.main()
    validate_v11()
    print("Directional v1.1 output validation passed.")


if __name__ == "__main__":
    main()
