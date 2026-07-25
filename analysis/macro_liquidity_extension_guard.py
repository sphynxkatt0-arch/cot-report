#!/usr/bin/env python3
"""Block new exposure when multiple fresh liquidity-plumbing pillars are severely stressed."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from build_directional_cot_system import HTML_OUT, OUT_DIR, render_html, write_csv
from price_execution_adapter import read_validation

ROOT = Path(__file__).resolve().parent
DECISION_JSON = OUT_DIR / "cot_direction_latest.json"
DECISION_CSV = OUT_DIR / "cot_direction_latest.csv"
MACRO_JSON = OUT_DIR / "macro_liquidity_expansion.json"
CONFIG = ROOT / "config" / "macro_liquidity_guard_v1.json"


def finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number else None


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def evaluate_guard(macro: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    coverage = finite(macro.get("source_coverage_ratio")) or 0.0
    minimum_coverage = float(config["minimum_source_coverage"])
    threshold = float(config["severe_score_threshold"])
    eligible = list(config["eligible_pillars"])
    pillars = macro.get("pillars") or {}
    evaluations: list[dict[str, Any]] = []
    severe: list[str] = []
    for key in eligible:
        pillar = pillars.get(key) or {}
        score = finite(pillar.get("score"))
        state = str(pillar.get("state") or "Unavailable")
        available = score is not None and state.lower() != "unavailable"
        is_severe = bool(available and score <= threshold)
        if is_severe:
            severe.append(key)
        evaluations.append(
            {
                "pillar": key,
                "score": score,
                "state": state,
                "available": available,
                "severe": is_severe,
                "reasons": pillar.get("reasons") or [],
            }
        )
    available_count = sum(item["available"] for item in evaluations)
    required = int(config["minimum_severe_pillars"])
    reliable = coverage >= minimum_coverage and available_count >= required
    active = reliable and len(severe) >= required
    return {
        "model_version": config["model_version"],
        "reliable": reliable,
        "active": active,
        "source_coverage_ratio": coverage,
        "minimum_source_coverage": minimum_coverage,
        "severe_score_threshold": threshold,
        "minimum_severe_pillars": required,
        "severe_pillars": severe,
        "pillar_evaluations": evaluations,
    }


def apply_guard(
    decisions: list[dict[str, Any]],
    macro: dict[str, Any],
    config: dict[str, Any],
) -> list[dict[str, Any]]:
    evaluation = evaluate_guard(macro, config)
    output: list[dict[str, Any]] = []
    for raw in decisions:
        row = dict(raw)
        row["liquidity_plumbing_guard"] = evaluation
        row["liquidity_plumbing_guard_active"] = bool(evaluation["active"])
        row["liquidity_plumbing_guard_reliable"] = bool(evaluation["reliable"])
        if not evaluation["active"]:
            output.append(row)
            continue
        existing_action = str(row.get("final_action") or "")
        if existing_action in {"Hedge / Risk Override", "Wait — Macro Data Incomplete"}:
            output.append(row)
            continue
        row["pre_liquidity_plumbing_action"] = existing_action
        row["pre_liquidity_plumbing_exposure"] = float(row.get("exposure_multiplier") or 0.0)
        row["final_action"] = str(config["action"])
        row["exposure_multiplier"] = 0.0
        reasons = list(row.get("reasons") or [])
        reasons.append(
            "Liquidity plumbing guard active: severe fresh pillars "
            + ", ".join(evaluation["severe_pillars"])
        )
        reasons.append("The guard blocks exposure but preserves the structural COT direction")
        row["reasons"] = reasons
        output.append(row)
    return output


def main() -> None:
    decisions = load_json(DECISION_JSON)
    macro = load_json(MACRO_JSON)
    config = load_json(CONFIG)
    if not isinstance(decisions, list) or not decisions:
        raise ValueError("latest decision JSON is empty")
    if config.get("schema_version") != 1:
        raise ValueError("macro liquidity guard config must use schema_version 1")
    guarded = apply_guard(decisions, macro, config)
    DECISION_JSON.write_text(json.dumps(guarded, indent=2) + "\n", encoding="utf-8")
    write_csv(DECISION_CSV, guarded)
    HTML_OUT.write_text(render_html(guarded, read_validation()), encoding="utf-8")
    state = "active" if guarded[0].get("liquidity_plumbing_guard_active") else "inactive"
    print(f"Liquidity plumbing guard {state}")


if __name__ == "__main__":
    main()
