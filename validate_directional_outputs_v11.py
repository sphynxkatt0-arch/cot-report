#!/usr/bin/env python3
"""Canonical v1.1 validation for five governed COT markets."""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import validate_directional_outputs as engine
from cot_market_registry import DIRECTIONAL_MARKETS, MARKETS

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "model_output"
ALIGNED = OUT / "directional_model_comparison_aligned.csv"
SUMMARY = OUT / "directional_model_comparison_summary.csv"
DECISIONS = OUT / "cot_direction_latest.json"
POSITION_CHANGES = OUT / "cot_position_changes_latest.csv"
MACRO_EXPANSION = OUT / "macro_liquidity_expansion.json"
MACRO_SOURCES = OUT / "macro_liquidity_source_status.csv"
REPORT = ROOT / "directional_cot_report.html"
DASHBOARD = ROOT / "interactive_cot_dashboard.html"

engine.COMPARISON_MODELS = {"old_tff", "old_legacy", "new_structural", "new_structural_tactical", "new_release_decision"}
# Estimability is graded explicitly below; do not require every statistic to be finite.
engine.NEW_MODELS = set()


def read_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def finite(value: Any) -> float | None:
    if value in {None, ""}:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number else None


def truthy(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes"}


def validate_release_evidence(row: dict[str, str], failures: list[str]) -> None:
    label = f"{row.get('market')} {row.get('horizon')} release decision"
    required = {"evidence_grade", "evidence_reason", "score_hac_estimable", "edge_hac_estimable", "stability_subperiods", "drift_adjusted_n", "directional_n"}
    missing = sorted(field for field in required if row.get(field) in {None, ""})
    if missing:
        failures.append(f"{label}: missing {missing}")
        return
    grade = str(row.get("evidence_grade"))
    allowed = {"Supported", "Tentative", "Weak/Mixed", "Contradictory", "Not estimable"}
    if grade not in allowed:
        failures.append(f"{label}: invalid evidence grade {grade}")
    score_estimable, edge_estimable = truthy(row.get("score_hac_estimable")), truthy(row.get("edge_hac_estimable"))
    if score_estimable and (finite(row.get("score_hac_p")) is None or finite(row.get("score_slope_pp_per_unit")) is None):
        failures.append(f"{label}: score HAC marked estimable without finite slope and p-value")
    if edge_estimable and (finite(row.get("edge_hac_p")) is None or finite(row.get("positive_minus_negative")) is None):
        failures.append(f"{label}: edge HAC marked estimable without finite edge and p-value")
    if grade == "Not estimable" and score_estimable and edge_estimable:
        failures.append(f"{label}: Not estimable conflicts with two estimable HAC tests")
    subperiods = int(finite(row.get("stability_subperiods")) or 0)
    if subperiods not in {0, 3}:
        failures.append(f"{label}: stability must contain zero or three subperiods, found {subperiods}")
    if subperiods == 3 and finite(row.get("subperiod_sign_agreement_pct")) is None:
        failures.append(f"{label}: three-subperiod stability is missing sign agreement")
    directional_n = int(finite(row.get("directional_n")) or 0)
    if directional_n >= 20:
        for field in ("avg_directional_return", "avg_adverse_move", "worst_adverse_move", "path_utility"):
            if finite(row.get(field)) is None:
                failures.append(f"{label}: directional sample is missing {field}")
    if grade in {"Supported", "Tentative"} and directional_n < 20:
        failures.append(f"{label}: positive evidence grade has directional sample {directional_n}<20")


def expected_participant_keys(market: str) -> set[str]:
    return {str(spec["key"]) for spec in MARKETS[market]["participant_specs"]}


def validate_v11() -> None:
    failures: list[str] = []
    aligned = read_rows(ALIGNED)
    if not aligned or "release_decision_score" not in aligned[0]:
        failures.append("aligned comparison is missing release_decision_score")

    summary = read_rows(SUMMARY)
    release_rows = [row for row in summary if row.get("model") == "new_release_decision"]
    expected_release_rows = len(DIRECTIONAL_MARKETS) * 4
    if len(release_rows) != expected_release_rows:
        failures.append(f"expected {expected_release_rows} release-decision summary rows, found {len(release_rows)}")
    for row in release_rows:
        validate_release_evidence(row, failures)

    try:
        decisions = json.loads(DECISIONS.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        failures.append(f"cannot read latest decisions: {exc}")
        decisions = []
    if not isinstance(decisions, list) or len(decisions) != len(DIRECTIONAL_MARKETS):
        failures.append(f"latest decisions must contain exactly {len(DIRECTIONAL_MARKETS)} governed markets")
    else:
        required = {
            "weekly_signal_change", "weekly_signal_material", "previous_report_date", "adjusted_cot_score_change",
            "position_changes", "historical_evidence_state", "historical_evidence_exposure_cap", "release_status",
        }
        for row in decisions:
            market = str(row.get("market") or "unknown")
            missing = sorted(required - set(row))
            if missing:
                failures.append(f"{market}: missing governed decision fields {missing}")
            changes = row.get("position_changes") or []
            keys = {str(item.get("key")) for item in changes if isinstance(item, dict)}
            if market in MARKETS and keys != expected_participant_keys(market):
                failures.append(f"{market}: weekly participant changes incomplete: {sorted(keys)}")

    position_rows = read_rows(POSITION_CHANGES)
    combinations = {(row.get("market"), row.get("key")) for row in position_rows}
    expected_combinations = {(market, key) for market in DIRECTIONAL_MARKETS for key in expected_participant_keys(market)}
    if combinations != expected_combinations:
        failures.append(f"weekly position-change CSV incomplete: got {len(combinations)} of {len(expected_combinations)} rows")

    try:
        macro = json.loads(MACRO_EXPANSION.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        failures.append(f"cannot read macro-liquidity expansion: {exc}")
        macro = {}
    if macro:
        if macro.get("schema_version") != 1:
            failures.append("macro-liquidity expansion schema_version must be 1")
        if "does not create or reverse COT direction" not in str(macro.get("role")):
            failures.append("macro-liquidity extension role must remain explicitly non-directional")
        required_pillars = {"macro_regime", "net_liquidity", "bank_reserves", "treasury_supply", "repo_admin_spread", "funding_microstructure", "dealer_absorption", "money_market_allocation"}
        pillars = set((macro.get("pillars") or {}).keys())
        if not required_pillars.issubset(pillars):
            failures.append(f"macro-liquidity pillars incomplete: {sorted(pillars)}")
        coverage = finite(macro.get("source_coverage_ratio"))
        if coverage is None or not 0 <= coverage <= 1:
            failures.append("macro-liquidity source coverage must be between 0 and 1")

    macro_source_rows = read_rows(MACRO_SOURCES)
    if len(macro_source_rows) != 10:
        failures.append(f"macro source status expected 10 rows, found {len(macro_source_rows)}")
    else:
        datasets = {row.get("dataset") for row in macro_source_rows}
        if datasets != {"repo", "nypd", "mmf"}:
            failures.append(f"macro source datasets incomplete: {sorted(datasets)}")
        for row in macro_source_rows:
            if row.get("status") not in {"fresh", "stale", "unavailable"}:
                failures.append(f"invalid macro source status for {row.get('key')}: {row.get('status')}")

    if not REPORT.exists():
        failures.append("directional report is missing")
    else:
        source = REPORT.read_text(encoding="utf-8", errors="replace")
        for text in ("New full release decision", "What changed this week", "Macro liquidity control room", "Current State", "Russell 2000", "Dow Jones", "Gold"):
            if text not in source:
                failures.append(f"standalone report is missing {text}")
        if source.count("<!-- WEEKLY_POSITION_CHANGE_START -->") != 1:
            failures.append("standalone report weekly-change panel is missing or duplicated")
        if source.count("<!-- MACRO_LIQUIDITY_CONTROL_ROOM_START -->") != 1:
            failures.append("standalone report macro-liquidity control room is missing or duplicated")

    if not DASHBOARD.exists():
        failures.append("interactive dashboard is missing")
    else:
        source = DASHBOARD.read_text(encoding="utf-8", errors="replace")
        if source.count('id="directionalDecisionQuality"') != 1:
            failures.append("dashboard evidence/weekly-change panel is missing or duplicated")
        if source.count('id="macroLiquidityControlRoom"') != 1:
            failures.append("dashboard macro-liquidity control room is missing or duplicated")
        for text in ("Historical validation", "Weekly signal", "Funding microstructure", "Dealer absorption", "Official source health", "Russell 2000", "Dow Jones", "Gold"):
            if text not in source:
                failures.append(f"dashboard governed panels missing {text}")

    if failures:
        raise RuntimeError("Directional v1.1 output validation failed:\n- " + "\n- ".join(failures))


def main() -> None:
    engine.main()
    validate_v11()
    print("Directional v1.1 output validation passed for all five markets.")


if __name__ == "__main__":
    main()
