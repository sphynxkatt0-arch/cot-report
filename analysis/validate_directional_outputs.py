#!/usr/bin/env python3
"""Validate generated directional COT artifacts before declaring refresh success."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

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
ALLOWED_RELEASE_STATES = {"current", "awaiting_release", "delayed"}
COMPARISON_MODELS = {"old_tff", "old_legacy", "new_structural", "new_structural_tactical"}
NEW_MODELS = {"new_structural", "new_structural_tactical"}
HORIZONS = {"1w", "4w", "13w", "26w"}
REQUIRED_DECISION_FIELDS = {
    "model_version",
    "market",
    "market_label",
    "report_date",
    "release_status",
    "expected_report_date",
    "release_date_source",
    "structural_bias",
    "structural_score",
    "tactical_modifier",
    "adjusted_cot_score",
    "asset_manager_multiplier",
    "macro_availability_ratio",
    "macro_reliable_for_action",
    "execution_state",
    "exposure_multiplier",
    "confidence_score",
    "final_action",
    "new_signal_available",
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
    a = finite_number(left)
    b = finite_number(right)
    if a is None or b is None:
        return True
    if abs(a) < 1e-12 or abs(b) < 1e-12:
        return True
    return (a > 0) == (b > 0)


def validate_decisions(failures: list[str]) -> None:
    if not LATEST_JSON.exists():
        failures.append(f"missing {LATEST_JSON}")
        return
    rows = load_json(LATEST_JSON)
    if not isinstance(rows, list) or len(rows) != 2:
        failures.append("latest decision JSON must contain exactly S&P 500 and Nasdaq-100 rows")
        return
    markets = {str(row.get("market")) for row in rows}
    if markets != {"sp500", "nq"}:
        failures.append(f"unexpected latest decision markets: {sorted(markets)}")
    versions = {str(row.get("model_version")) for row in rows}
    if versions != {"cot-direction-v1.1"}:
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
        if exposure < 0 or exposure > 1.25:
            failures.append(f"{market}: exposure multiplier out of range {exposure}")
        confidence = finite_number(row.get("confidence_score")) or 0.0
        if confidence < 0 or confidence > 1:
            failures.append(f"{market}: confidence out of range {confidence}")
        if status == "delayed":
            if row.get("new_signal_available") is not False:
                failures.append(f"{market}: delayed report marked as new signal")
            action = str(row.get("final_action"))
            if "Delayed" not in action and "Delayed Release Price" not in action:
                failures.append(f"{market}: delayed report does not preserve/block signal correctly")
        if status == "awaiting_release" and row.get("new_signal_available") is not False:
            failures.append(f"{market}: awaiting report marked as new signal")
        if row.get("release_date_source") == "first_observed_delayed":
            target = str(row.get("effective_signal_target_date") or "")
            signal = str(row.get("signal_price_date") or "")
            if signal and target and signal < target:
                failures.append(f"{market}: delayed signal price predates effective observed target")
        if not bool(row.get("macro_reliable_for_action")):
            if status == "current" and str(row.get("final_action")) != "Wait — Macro Data Incomplete":
                failures.append(f"{market}: unreliable macro data did not block action")
            if status == "current" and exposure != 0.0:
                failures.append(f"{market}: unreliable macro data left non-zero exposure")


def validate_history(failures: list[str]) -> None:
    rows = read_csv(HISTORY_CSV)
    if not rows:
        failures.append(f"missing or empty {HISTORY_CSV}")
        return
    markets = {row.get("market") for row in rows}
    if markets != {"sp500", "nq"}:
        failures.append(f"history markets incomplete: {sorted(markets)}")
    required_path_columns = {
        f"forward_{kind}_path_return_{horizon}"
        for horizon in HORIZONS
        for kind in ("worst", "best")
    }
    missing_path = sorted(required_path_columns - set(rows[0]))
    if missing_path:
        failures.append(f"history missing path columns {missing_path}")
    for index, row in enumerate(rows):
        if row.get("release_date_source") != "scheduled_history":
            failures.append(f"history row {index}: non-deterministic release source")
            break
        release = row.get("scheduled_release_date") or ""
        signal = row.get("signal_price_date") or ""
        if signal and signal < release:
            failures.append(f"history row {index}: signal price predates release")
            break
        if not same_sign(row.get("structural_score"), row.get("adjusted_cot_score")):
            failures.append(f"history row {index}: tactical sign reversal")
            break


def validate_summary(failures: list[str]) -> None:
    rows = read_csv(VALIDATION_CSV)
    combinations = {(row.get("market"), row.get("horizon")) for row in rows}
    expected = {(market, horizon) for market in ("sp500", "nq") for horizon in HORIZONS}
    if combinations != expected:
        failures.append(f"validation summary combinations incomplete: {sorted(combinations)}")


def validate_model_comparison(failures: list[str]) -> None:
    aligned = read_csv(COMPARISON_ALIGNED_CSV)
    if not aligned:
        failures.append(f"missing or empty {COMPARISON_ALIGNED_CSV}")
    else:
        markets = {row.get("market") for row in aligned}
        if markets != {"sp500", "nq"}:
            failures.append(f"comparison aligned markets incomplete: {sorted(markets)}")
        required = {
            "old_tff_score",
            "old_legacy_score",
            "structural_score",
            "adjusted_cot_score",
            *{
                f"forward_{kind}_path_return_{horizon}"
                for horizon in HORIZONS
                for kind in ("worst", "best")
            },
        }
        missing_columns = sorted(required - set(aligned[0]))
        if missing_columns:
            failures.append(f"comparison aligned file missing columns {missing_columns}")

    summary = read_csv(COMPARISON_SUMMARY_CSV)
    combinations = {
        (row.get("market"), row.get("horizon"), row.get("model"))
        for row in summary
    }
    expected = {
        (market, horizon, model)
        for market in ("sp500", "nq")
        for horizon in HORIZONS
        for model in COMPARISON_MODELS
    }
    if combinations != expected:
        failures.append(
            f"model comparison summary incomplete: got {len(combinations)} of {len(expected)} combinations"
        )
    required_fields = {
        "score_hac_p",
        "edge_hac_p",
        "drift_adjusted_accuracy_pct",
        "subperiod_sign_agreement_pct",
        "directional_n",
        "avg_directional_return",
        "avg_adverse_move",
        "worst_adverse_move",
        "path_utility",
    }
    for row in summary:
        label = f"{row.get('market')} {row.get('horizon')} {row.get('model')}"
        if row.get("status") != "exploratory_release_aligned_hac":
            failures.append(f"{label}: invalid comparison status")
            continue
        missing_fields = sorted(required_fields - set(row))
        if missing_fields:
            failures.append(f"{label}: missing comparison fields {missing_fields}")
            continue
        observations = finite_number(row.get("observations")) or 0
        if observations < 20:
            failures.append(f"{label}: insufficient comparison observations {observations}")
        if row.get("model") in NEW_MODELS:
            if observations < 100:
                failures.append(f"{label}: new model has fewer than 100 observations")
            if finite_number(row.get("score_hac_p")) is None:
                failures.append(f"{label}: missing score HAC p-value")
            if finite_number(row.get("edge_hac_p")) is None:
                failures.append(f"{label}: missing edge HAC p-value")
            if (finite_number(row.get("subperiod_sign_agreement_pct")) is None
                    or (finite_number(row.get("stability_subperiods")) or 0) != 3):
                failures.append(f"{label}: incomplete chronological stability")
            if (finite_number(row.get("drift_adjusted_n")) or 0) < 20:
                failures.append(f"{label}: insufficient drift-adjusted sample")
            for field in ("avg_directional_return", "avg_adverse_move", "worst_adverse_move", "path_utility"):
                if finite_number(row.get(field)) is None:
                    failures.append(f"{label}: missing {field}")

    agreement = read_csv(COMPARISON_AGREEMENT_CSV)
    expected_pairs = len(COMPARISON_MODELS) * (len(COMPARISON_MODELS) - 1) // 2 * 2
    if len(agreement) != expected_pairs:
        failures.append(f"model agreement expected {expected_pairs} rows, found {len(agreement)}")


def validate_macro(failures: list[str]) -> None:
    if not MACRO_JSON.exists():
        failures.append(f"missing {MACRO_JSON}")
        return
    payload = load_json(MACRO_JSON)
    for key in (
        "availability_ratio",
        "reliable_for_action",
        "hard_override",
        "hard_override_suppressed_by_freshness",
        "stale_factors",
        "missing_factors",
    ):
        if key not in payload:
            failures.append(f"macro context missing {key}")


def validate_html(failures: list[str]) -> None:
    if not DIRECTIONAL_HTML.exists():
        failures.append(f"missing {DIRECTIONAL_HTML}")
    else:
        source = DIRECTIONAL_HTML.read_text(encoding="utf-8", errors="replace")
        if source.count("Directional COT Report") < 1:
            failures.append("standalone directional report title missing")
        if "Exploratory model validation" not in source:
            failures.append("standalone validation section missing")
        if source.count("<!-- MODEL_COMPARISON_START -->") != 1:
            failures.append("model comparison report injection missing or duplicated")
        if "id=\"modelComparisonPanel\"" not in source:
            failures.append("model comparison panel ID missing")
        for text in ("HAC p", "Path utility", "Drift-adjusted", "Directional agreement"):
            if text not in source:
                failures.append(f"model comparison report missing {text}")
    if not DASHBOARD_HTML.exists():
        failures.append(f"missing {DASHBOARD_HTML}")
    else:
        source = DASHBOARD_HTML.read_text(encoding="utf-8", errors="replace")
        if source.count("<!-- DIRECTIONAL_DECISION_START -->") != 1:
            failures.append("dashboard directional injection is missing or duplicated")
        if "id=\"directionalDecisionSummary\"" not in source:
            failures.append("dashboard directional summary ID missing")
        if "Selected-report research regime" not in source:
            failures.append("old dashboard regime is not labelled research-only")


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
    print("Directional output validation passed.")


if __name__ == "__main__":
    main()
