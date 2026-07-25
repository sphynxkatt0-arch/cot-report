#!/usr/bin/env python3
"""Apply final CFTC release-state actionability rules.

The release tracker is authoritative at the final action stage. This prevents a
new tracker field or a multi-week catch-up state from being dropped by an
earlier build step.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from build_directional_cot_system import HTML_OUT, OUT_DIR, render_html, write_csv
from cftc_release_tracker import resolve_release_state
from price_execution_adapter import read_validation

ROOT = Path(__file__).resolve().parent
DECISION_JSON = OUT_DIR / "cot_direction_latest.json"
DECISION_CSV = OUT_DIR / "cot_direction_latest.csv"
ReleaseResolver = Callable[[str], dict[str, Any]]


def hydrate_release_state(
    row: dict[str, Any],
    resolver: ReleaseResolver,
) -> dict[str, Any]:
    report_date = str(row.get("report_date") or "")
    if not report_date:
        raise ValueError("Directional decision is missing report_date")
    state = resolver(report_date)
    if not isinstance(state, dict):
        raise TypeError("Release-state resolver must return a dictionary")
    hydrated = dict(row)
    for key in (
        "release_status",
        "expected_report_date",
        "expected_gap_weeks",
        "release_date_source",
        "effective_release_date",
        "scheduled_release_utc",
        "scheduled_release_stockholm",
        "first_observed_utc",
        "first_observed_delay_minutes",
        "is_delayed",
        "is_catch_up_delayed",
        "is_awaiting_release",
    ):
        if key in state:
            hydrated[key] = state[key]
    hydrated["new_report_observed"] = bool(hydrated.get("first_observed_utc"))
    return hydrated


def apply_release_guard(
    decisions: list[dict[str, Any]],
    resolver: ReleaseResolver = resolve_release_state,
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for raw in decisions:
        row = hydrate_release_state(dict(raw), resolver)
        status = str(row.get("release_status") or "current")
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
            reasons.append(
                "Positioning changes are displayed for context; no new trade exposure is permitted"
            )
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
        elif status == "current":
            row["new_signal_available"] = True
        else:
            raise ValueError(f"Unsupported CFTC release status: {status}")
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
