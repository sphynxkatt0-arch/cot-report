#!/usr/bin/env python3
"""Apply final CFTC release-state actionability rules."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from build_directional_cot_system import OUT_DIR, HTML_OUT, render_html, write_csv
from price_execution_adapter import read_validation

ROOT = Path(__file__).resolve().parent
DECISION_JSON = OUT_DIR / "cot_direction_latest.json"
DECISION_CSV = OUT_DIR / "cot_direction_latest.csv"


def apply_release_guard(decisions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for raw in decisions:
        row = dict(raw)
        status = str(row.get("release_status") or "current")
        row["new_report_observed"] = bool(row.get("first_observed_utc"))
        if status == "catch_up_delayed":
            row["pre_release_quality_action"] = row.get("final_action")
            row["final_action"] = "Wait — CFTC Catch-Up Still Behind"
            row["exposure_multiplier"] = 0.0
            row["new_signal_available"] = False
            reasons = list(row.get("reasons") or [])
            reasons.append(
                f"Catch-up report observed, but expected CFTC report {row.get('expected_report_date')} "
                f"is still {row.get('expected_gap_weeks', 'n/a')} week(s) ahead"
            )
            reasons.append("Positioning changes are displayed for context; no new trade exposure is permitted")
            row["reasons"] = reasons
        elif status == "delayed":
            row["new_signal_available"] = False
            row["exposure_multiplier"] = 0.0
            if "Delayed" not in str(row.get("final_action")):
                row["final_action"] = "Hold Prior Signal — CFTC Report Delayed"
        elif status == "awaiting_release":
            row["new_signal_available"] = False
            row["exposure_multiplier"] = 0.0
            row["final_action"] = "Hold Prior Signal — Awaiting Friday Release"
        output.append(row)
    return output


def main() -> None:
    try:
        decisions = json.loads(DECISION_JSON.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Cannot read {DECISION_JSON}: {exc}") from exc
    if not isinstance(decisions, list) or not decisions:
        raise ValueError("Directional decision JSON is empty")
    guarded = apply_release_guard(decisions)
    DECISION_JSON.write_text(json.dumps(guarded, indent=2) + "\n", encoding="utf-8")
    write_csv(DECISION_CSV, guarded)
    HTML_OUT.write_text(render_html(guarded, read_validation()), encoding="utf-8")
    for row in guarded:
        print(f"{row['market_label']}: {row['final_action']} | release {row['release_status']}")


if __name__ == "__main__":
    main()
