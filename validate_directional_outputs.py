#!/usr/bin/env python3
"""Validate generated multi-market directional COT artifacts."""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from cot_market_registry import BASELINE_MARKETS, DIRECTIONAL_MARKETS

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "model_output"
LATEST_JSON = OUT / "cot_direction_latest.json"
HISTORY_CSV = OUT / "cot_direction_history.csv"
VALIDATION_CSV = OUT / "cot_direction_validation_summary.csv"
MACRO_JSON = OUT / "macro_direction_context.json"
COMPARISON_ALIGNED_CSV = OUT / "directional_model_comparison_aligned.csv"
COMPARISON_SUMMARY_CSV = OUT / "directional_model_comparison_summary.csv"
COMPARISON_AGREEMENT_CSV = OUT / "directional_model_agreement.csv"
DIRECTIONAL_HTML = ROOT / "directional_cot_report.html"
DASHBOARD_HTML = ROOT / "interactive_cot_dashboard.html"
ALLOWED_RELEASE_STATES = {"current", "awaiting_release", "delayed", "catch_up_delayed"}
COMPARISON_MODELS = {"old_tff", "old_legacy", "new_structural", "new_structural_tactical"}
NEW_MODELS = {"new_structural", "new_structural_tactical"}
HORIZONS = {"1w", "4w", "13w", "26w"}
REQUIRED_DECISION_FIELDS = {
    "model_version", "market", "market_label", "report_date", "release_status", "expected_report_date",
    "release_date_source", "structural_bias", "structural_score", "tactical_modifier", "adjusted_cot_score",
    "asset_manager_multiplier", "macro_availability_ratio", "macro_reliable_for_action", "execution_state",
    "exposure_multiplier", "confidence_score", "final_action", "new_signal_available", "secondary_report",
    "contract_selection_mode", "contract_selection_note", "conviction_group_label",
}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def finite_number(value: Any) -> float | None:
    if value in {None, ""}:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number else None


def same_sign(left: Any, right: Any) -> bool:
    a, b = finite_number(left), finite_number(right)
    if a is None or b is None or abs(a) < 1e-12 or abs(b) < 1e-12:
        return True
    return (a > 0) == (b > 0)


def validate_decisions(failures: list[str]) -> None:
    if not LATEST_JSON.exists():
        failures.append(f"missing {LATEST_JSON}")
        return
    rows = load_json(LATEST_JSON)
    expected_markets = set(DIRECTIONAL_MARKETS)
    if not isinstance(rows, list) or len(rows) != len(expected_markets):
        failures.append(f"latest decision JSON must contain {len(expected_markets)} governed market rows")
        return
    markets = {str(row.get("market")) for row in rows}
    if markets != expected_markets:
        failures.append(f"unexpected latest decision markets: {sorted(markets)}")
    versions = {str(row.get("model_version")) for row in rows}
    if versions not in ({"cot-direction-v1.1"}, {"cot-direction-v1.2"}):
        failures.append(f"unexpected model versions: {sorted(versions)}")
    for row in rows:
        market = str(row.get("market") or "unknown")
        missing = sorted(REQUIRED_DECISION_FIELDS - set(row))
        if missing:
            failures.append(f"{market}: missing fields {missing}")
        status = str(row.get("release_status"))
        if status not in ALLOWED_RELEASE_STATES:
            failures.append(f"{market}: invalid release status {status}")
        if not same_sign(row.get("structural_score"), row.get("adjusted_cot_score")):
            failures.append(f"{market}: tactical layer reversed structural sign")
        exposure = finite_number(row.get("exposure_multiplier")) or 0.0
        confidence = finite_number(row.get("confidence_score")) or 0.0
        if not 0 <= exposure <= 1.25:
            failures.append(f"{market}: exposure multiplier out of range {exposure}")
        if not 0 <= confidence <= 1:
            failures.append(f"{market}: confidence out of range {confidence}")
        if status in {"delayed", "awaiting_release", "catch_up_delayed"} and row.get("new_signal_available") is not False:
            failures.append(f"{market}: non-current report marked as a new signal")
        if status == "catch_up_delayed" and exposure != 0.0:
            failures.append(f"{market}: catch-up delayed report left non-zero exposure")
        if row.get("release_date_source") == "first_observed_delayed":
            target = str(row.get("effective_signal_target_date") or "")
            signal = str(row.get("signal_price_date") or "")
            if signal and target and signal < target:
                failures.append(f"{market}: delayed signal price predates effective observed target")
        if not bool(row.get("macro_reliable_for_action")) and status == "current":
            if str(row.get("final_action")) != "Wait — Macro Data Incomplete":
                failures.append(f"{market}: unreliable macro data did not block action")
            if exposure != 0.0:
                failures.append(f"{market}: unreliable macro data left non-zero exposure")


def validate_history(failures: list[str]) -> None:
    rows = read_csv(HISTORY_CSV)
    if not rows:
        failures.append(f"missing or empty {HISTORY_CSV}")
        return
    markets = {row.get("market") for row in rows}
    if markets != set(DIRECTIONAL_MARKETS):
        failures.append(f"history markets incomplete: {sorted(markets)}")
    required_path_columns = {f"forward_{kind}_path_return_{horizon}" for horizon in HORIZONS for kind in ("worst", "best")}
    missing_path_columns = sorted(required_path_columns - set(rows[0]))
    if missing_path_columns:
        failures.append(f"history missing path outcome columns {missing_path_columns}")
    for index, row in enumerate(rows):
        release, signal = row.get("scheduled_release_date") or "", row.get("signal_price_date") or ""
        if signal and signal < release:
            failures.append(f"history row {index}: signal price predates release")
            break
        if not same_sign(row.get("structural_score"), row.get("adjusted_cot_score")):
            failures.append(f"history row {index}: tactical sign reversal")
            break


def validate_summary(failures: list[str]) -> None:
    rows = read_csv(VALIDATION_CSV)
    combinations = {(row.get("market"), row.get("horizon")) for row in rows}
    expected = {(market, horizon) for market in DIRECTIONAL_MARKETS for horizon in HORIZONS}
    if combinations != expected:
        failures.append(f"validation summary combinations incomplete: got {len(combinations)} of {len(expected)}")


def validate_model_comparison(failures: list[str]) -> None:
    aligned = read_csv(COMPARISON_ALIGNED_CSV)
    if not aligned:
        failures.append(f"missing or empty {COMPARISON_ALIGNED_CSV}")
    else:
        markets = {row.get("market") for row in aligned}
        if markets != set(DIRECTIONAL_MARKETS):
            failures.append(f"comparison aligned markets incomplete: {sorted(markets)}")
        required = {
            "old_tff_score", "old_legacy_score", "structural_score", "adjusted_cot_score",
            *{f"forward_{kind}_path_return_{horizon}" for horizon in HORIZONS for kind in ("worst", "best")},
        }
        missing_columns = sorted(required - set(aligned[0]))
        if missing_columns:
            failures.append(f"comparison aligned file missing columns {missing_columns}")

    summary = read_csv(COMPARISON_SUMMARY_CSV)
    combinations = {(row.get("market"), row.get("horizon"), row.get("model")) for row in summary}
    expected = {(market, horizon, model) for market in DIRECTIONAL_MARKETS for horizon in HORIZONS for model in COMPARISON_MODELS}
    if combinations != expected:
        failures.append(f"model comparison summary incomplete: got {len(combinations)} of {len(expected)} combinations")
    required_fields = {
        "score_hac_p", "edge_hac_p", "drift_adjusted_accuracy_pct", "subperiod_sign_agreement_pct",
        "directional_n", "avg_directional_return", "avg_adverse_move", "worst_adverse_move", "path_utility",
    }
    for row in summary:
        market, model = str(row.get("market")), str(row.get("model"))
        label = f"{market} {row.get('horizon')} {model}"
        if row.get("status") != "exploratory_release_aligned_hac":
            failures.append(f"{label}: invalid comparison status")
            continue
        missing_fields = sorted(required_fields - set(row))
        if missing_fields:
            failures.append(f"{label}: missing comparison fields {missing_fields}")
            continue
        observations = finite_number(row.get("observations")) or 0
        baseline_unavailable = model in {"old_tff", "old_legacy"} and market not in BASELINE_MARKETS
        if not baseline_unavailable and observations < 20:
            failures.append(f"{label}: insufficient comparison observations {observations}")
        if model in NEW_MODELS and observations < 100:
            failures.append(f"{label}: new model has fewer than 100 observations")

    agreement = read_csv(COMPARISON_AGREEMENT_CSV)
    expected_pairs = len(COMPARISON_MODELS) * (len(COMPARISON_MODELS) - 1) // 2 * len(DIRECTIONAL_MARKETS)
    if len(agreement) != expected_pairs:
        failures.append(f"model agreement expected {expected_pairs} rows, found {len(agreement)}")


def validate_macro(failures: list[str]) -> None:
    if not MACRO_JSON.exists():
        failures.append(f"missing {MACRO_JSON}")
        return
    payload = load_json(MACRO_JSON)
    for key in ("availability_ratio", "reliable_for_action", "hard_override", "hard_override_suppressed_by_freshness", "stale_factors", "missing_factors"):
        if key not in payload:
            failures.append(f"macro context missing {key}")


def validate_html(failures: list[str]) -> None:
    if not DIRECTIONAL_HTML.exists():
        failures.append(f"missing {DIRECTIONAL_HTML}")
    else:
        source = DIRECTIONAL_HTML.read_text(encoding="utf-8", errors="replace")
        if "Directional COT Report" not in source:
            failures.append("standalone directional report title missing")
        for label in ("Russell 2000", "Dow Jones", "Gold"):
            if label not in source:
                failures.append(f"standalone directional report missing {label}")
        if "Exploratory model validation" not in source:
            failures.append("standalone validation section missing")
        if source.count("<!-- MODEL_COMPARISON_START -->") != 1 or 'id="modelComparisonPanel"' not in source:
            failures.append("model comparison report injection missing or duplicated")
    if not DASHBOARD_HTML.exists():
        failures.append(f"missing {DASHBOARD_HTML}")
    else:
        source = DASHBOARD_HTML.read_text(encoding="utf-8", errors="replace")
        if source.count("<!-- DIRECTIONAL_DECISION_START -->") != 1 or 'id="directionalDecisionSummary"' not in source:
            failures.append("dashboard directional injection is missing or duplicated")


def main() -> None:
    failures: list[str] = []
    validate_decisions(failures)
    validate_history(failures)
    validate_summary(failures)
    validate_model_comparison(failures)
    validate_macro(failures)
    validate_html(failures)
    if failures:
        raise RuntimeError("Directional output validation failed:\n- " + "\n- ".join(failures))
    print("Directional output validation passed for all governed markets.")


if __name__ == "__main__":
    main()
