#!/usr/bin/env python3
"""Canonical v1.1 output validation for governed decisions and weekly changes."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import validate_directional_outputs as engine

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "model_output"
ALIGNED = OUT / "directional_model_comparison_aligned.csv"
SUMMARY = OUT / "directional_model_comparison_summary.csv"
DECISIONS = OUT / "cot_direction_latest.json"
POSITION_CHANGES = OUT / "cot_position_changes_latest.csv"
REPORT = ROOT / "directional_cot_report.html"
DASHBOARD = ROOT / "interactive_cot_dashboard.html"

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
            "evidence_grade",
            "evidence_reason",
            "score_hac_estimable",
            "edge_hac_estimable",
            "subperiod_sign_agreement_pct",
            "drift_adjusted_accuracy_pct",
            "avg_adverse_move",
            "path_utility",
        ):
            if row.get(field) in {None, ""}:
                failures.append(f"{label}: missing {field}")

    try:
        decisions = json.loads(DECISIONS.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        failures.append(f"cannot read latest decisions: {exc}")
        decisions = []
    if not isinstance(decisions, list) or len(decisions) != 2:
        failures.append("latest decisions must contain exactly S&P 500 and Nasdaq-100")
    else:
        required = {
            "weekly_signal_change",
            "weekly_signal_material",
            "previous_report_date",
            "adjusted_cot_score_change",
            "position_changes",
            "historical_evidence_state",
            "historical_evidence_exposure_cap",
            "release_status",
        }
        for row in decisions:
            market = str(row.get("market") or "unknown")
            missing = sorted(required - set(row))
            if missing:
                failures.append(f"{market}: missing governed decision fields {missing}")
            changes = row.get("position_changes") or []
            keys = {str(item.get("key")) for item in changes if isinstance(item, dict)}
            expected_keys = {
                "legacy_noncommercial",
                "asset_manager",
                "leveraged_money",
                "other_reportables",
                "nonreportables",
            }
            if keys != expected_keys:
                failures.append(f"{market}: weekly participant changes incomplete: {sorted(keys)}")

    position_rows = read_rows(POSITION_CHANGES)
    combinations = {(row.get("market"), row.get("key")) for row in position_rows}
    expected_combinations = {
        (market, key)
        for market in ("sp500", "nq")
        for key in (
            "legacy_noncommercial",
            "asset_manager",
            "leveraged_money",
            "other_reportables",
            "nonreportables",
        )
    }
    if combinations != expected_combinations:
        failures.append(
            f"weekly position-change CSV incomplete: got {len(combinations)} of {len(expected_combinations)} rows"
        )

    if not REPORT.exists():
        failures.append("directional report is missing")
    else:
        source = REPORT.read_text(encoding="utf-8", errors="replace")
        if "New full release decision" not in source:
            failures.append("report is missing the full release-decision model label")
        if source.count("<!-- WEEKLY_POSITION_CHANGE_START -->") != 1:
            failures.append("standalone report weekly-change panel is missing or duplicated")
        if "What changed this week" not in source:
            failures.append("standalone report is missing weekly-change heading")

    if not DASHBOARD.exists():
        failures.append("interactive dashboard is missing")
    else:
        source = DASHBOARD.read_text(encoding="utf-8", errors="replace")
        if source.count('id="directionalDecisionQuality"') != 1:
            failures.append("dashboard evidence/weekly-change panel is missing or duplicated")
        for text in (
            "Historical validation",
            "Weekly signal",
            "Retail proxy (Nonreportables)",
        ):
            if text not in source:
                failures.append(f"dashboard quality panel missing {text}")

    if failures:
        raise RuntimeError("Directional v1.1 output validation failed:\n- " + "\n- ".join(failures))


def main() -> None:
    engine.main()
    validate_v11()
    print("Directional v1.1 output validation passed.")


if __name__ == "__main__":
    main()
