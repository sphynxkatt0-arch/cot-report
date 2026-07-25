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
DIRECTIONAL_HTML = ROOT / "directional_cot_report.html"
DASHBOARD_HTML = ROOT / "interactive_cot_dashboard.html"
ALLOWED_RELEASE_STATES = {"current", "awaiting_release", "delayed"}
REQUIRED_DECISION_FIELDS = {
    "model_version",
    "market",
    "market_label",
    "report_date",
    "release_status",
    "expected_report_date",
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


def same_sign(left: Any, right: Any) -> bool:
    if left is None or right is None:
        return True
    a = float(left)
    b = float(right)
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
    if len(versions) != 1 or "cot-direction-v1.1" not in versions:
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
        exposure = float(row.get("exposure_multiplier") or 0.0)
        if exposure < 0 or exposure > 1.25:
            failures.append(f"{market}: exposure multiplier out of range {exposure}")
        confidence = float(row.get("confidence_score") or 0.0)
        if confidence < 0 or confidence > 1:
            failures.append(f"{market}: confidence out of range {confidence}")
        if status == "delayed":
            if row.get("new_signal_available") is not False:
                failures.append(f"{market}: delayed report marked as new signal")
            if "Delayed" not in str(row.get("final_action")):
                failures.append(f"{market}: delayed report does not preserve prior signal")
        if status == "awaiting_release" and row.get("new_signal_available") is not False:
            failures.append(f"{market}: awaiting report marked as new signal")
        if not bool(row.get("macro_reliable_for_action")):
            if status == "current" and str(row.get("final_action")) != "Wait — Macro Data Incomplete":
                failures.append(f"{market}: unreliable macro data did not block action")
            if status == "current" and exposure != 0.0:
                failures.append(f"{market}: unreliable macro data left non-zero exposure")


def validate_history(failures: list[str]) -> None:
    if not HISTORY_CSV.exists():
        failures.append(f"missing {HISTORY_CSV}")
        return
    with HISTORY_CSV.open("r", newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        failures.append("directional history is empty")
        return
    markets = {row.get("market") for row in rows}
    if markets != {"sp500", "nq"}:
        failures.append(f"history markets incomplete: {sorted(markets)}")
    for index, row in enumerate(rows):
        if row.get("release_date_source") != "scheduled_history":
            failures.append(f"history row {index}: non-deterministic release source")
            break
        release = row.get("scheduled_release_date") or ""
        signal = row.get("signal_price_date") or ""
        if signal and signal < release:
            failures.append(f"history row {index}: signal price predates release")
            break
        if not same_sign(row.get("structural_score") or None, row.get("adjusted_cot_score") or None):
            failures.append(f"history row {index}: tactical sign reversal")
            break


def validate_summary(failures: list[str]) -> None:
    if not VALIDATION_CSV.exists():
        failures.append(f"missing {VALIDATION_CSV}")
        return
    with VALIDATION_CSV.open("r", newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    combinations = {(row.get("market"), row.get("horizon")) for row in rows}
    expected = {(market, horizon) for market in ("sp500", "nq") for horizon in ("1w", "4w", "13w", "26w")}
    if combinations != expected:
        failures.append(f"validation summary combinations incomplete: {sorted(combinations)}")


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
    validate_macro(failures)
    validate_html(failures)
    if failures:
        raise RuntimeError("Directional output validation failed:\n- " + "\n- ".join(failures))
    print("Directional output validation passed.")


if __name__ == "__main__":
    main()
