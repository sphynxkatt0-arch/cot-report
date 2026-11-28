#!/usr/bin/env python3
"""Use historical validation as an exposure cap, never a directional vote.

The Non-commercial structural sign remains authoritative. Historical evidence
may preserve, reduce, or block exposure when the release-time full model is weak,
unestimable, or contradictory at the relevant 4w/13w/26w horizons.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from build_directional_cot_system import HTML_OUT, OUT_DIR, render_html, write_csv
from price_execution_adapter import read_validation

ROOT = Path(__file__).resolve().parent
DECISION_JSON = OUT_DIR / "cot_direction_latest.json"
DECISION_CSV = OUT_DIR / "cot_direction_latest.csv"
SUMMARY_CSV = OUT_DIR / "directional_model_comparison_summary.csv"
TARGET_MODEL = "new_release_decision"
RELEVANT_HORIZONS = ("4w", "13w", "26w")
EXPOSURE_CAPS = {
    "Supported": 1.25,
    "Tentative": 0.75,
    "Not validated": 0.35,
    "Contradictory": 0.0,
}


def read_summary(path: Path = SUMMARY_CSV) -> list[dict[str, str]]:
    if not path.exists():
        raise FileNotFoundError(f"Missing {path}")
    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def aggregate_evidence(rows: list[dict[str, str]]) -> tuple[str, dict[str, str], str]:
    by_horizon = {
        str(row.get("horizon")): str(row.get("evidence_grade") or "Not estimable")
        for row in rows
        if row.get("horizon") in RELEVANT_HORIZONS
    }
    missing = [horizon for horizon in RELEVANT_HORIZONS if horizon not in by_horizon]
    if missing:
        return "Not validated", by_horizon, f"missing evidence horizons: {', '.join(missing)}"

    grades = list(by_horizon.values())
    if "Contradictory" in grades:
        horizons = [h for h, grade in by_horizon.items() if grade == "Contradictory"]
        return "Contradictory", by_horizon, f"contradictory historical evidence at {', '.join(horizons)}"

    tactical = by_horizon["4w"]
    structural = [by_horizon["13w"], by_horizon["26w"]]
    supported_count = grades.count("Supported")
    positive_count = sum(grade in {"Supported", "Tentative"} for grade in grades)
    if (
        tactical == "Supported" and any(grade == "Supported" for grade in structural)
    ) or supported_count >= 2:
        return "Supported", by_horizon, "historical release-time model is supported across tactical and/or structural horizons"
    if positive_count >= 1:
        return "Tentative", by_horizon, "some relevant horizons are positive but full cross-horizon support is incomplete"
    return "Not validated", by_horizon, "relevant horizons are weak, mixed, or not estimable"


def reduced_action(action: str) -> str:
    if action == "Strong Long":
        return "Long — Reduced Size"
    if action == "Strong Short":
        return "Short — Reduced Size"
    return action


def apply_evidence_guard(
    decisions: list[dict[str, Any]],
    summary_rows: list[dict[str, str]],
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for raw in decisions:
        row = dict(raw)
        market = str(row.get("market") or "")
        evidence_rows = [
            item
            for item in summary_rows
            if item.get("market") == market and item.get("model") == TARGET_MODEL
        ]
        state, by_horizon, reason = aggregate_evidence(evidence_rows)
        cap = EXPOSURE_CAPS[state]
        row["historical_evidence_state"] = state
        row["historical_evidence_by_horizon"] = by_horizon
        row["historical_evidence_reason"] = reason
        row["historical_evidence_exposure_cap"] = cap

        action = str(row.get("final_action") or "")
        release_status = str(row.get("release_status") or "current")
        if release_status in {"delayed", "awaiting_release", "catch_up_delayed"}:
            output.append(row)
            continue
        higher_priority_actions = {
            "Hedge / Risk Override",
            "Wait — Macro Data Incomplete",
            "Wait — Liquidity Plumbing Stress",
            "No COT Trade",
            "No Trade",
        }
        if action in higher_priority_actions or action.startswith("Wait for "):
            output.append(row)
            continue

        current_exposure = float(row.get("exposure_multiplier") or 0.0)
        row["pre_historical_evidence_action"] = action
        row["pre_historical_evidence_exposure"] = current_exposure
        row["exposure_multiplier"] = round(min(current_exposure, cap), 4)
        if state == "Contradictory":
            side = "Long" if float(row.get("adjusted_cot_score") or 0.0) > 0 else "Short"
            row["final_action"] = f"Wait for {side} — Historical Evidence Conflict"
        elif state in {"Tentative", "Not validated"}:
            row["final_action"] = reduced_action(action)
        reasons = list(row.get("reasons") or [])
        reasons.append(
            f"Historical validation {state}; exposure capped at {cap:.2f}x — {reason}"
        )
        row["reasons"] = reasons
        output.append(row)
    return output


def main() -> None:
    try:
        decisions = json.loads(DECISION_JSON.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Cannot read {DECISION_JSON}: {exc}") from exc
    if not isinstance(decisions, list) or not decisions:
        raise ValueError("Directional decision JSON is empty")
    guarded = apply_evidence_guard(decisions, read_summary())
    DECISION_JSON.write_text(json.dumps(guarded, indent=2) + "\n", encoding="utf-8")
    write_csv(DECISION_CSV, guarded)
    HTML_OUT.write_text(render_html(guarded, read_validation()), encoding="utf-8")
    for row in guarded:
        print(
            f"{row['market_label']}: {row['final_action']} | "
            f"historical evidence {row['historical_evidence_state']}"
        )


if __name__ == "__main__":
    main()
