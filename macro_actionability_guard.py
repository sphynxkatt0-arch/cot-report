#!/usr/bin/env python3
"""Apply a final macro data-quality guard to directional decisions."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from build_directional_cot_system import OUT_DIR, VALIDATION_OUT, render_html, write_csv
from macro_direction_adapter import MINIMUM_RELIABLE_AVAILABILITY
from price_execution_adapter import read_validation

ROOT = Path(__file__).resolve().parent
DECISION_JSON = OUT_DIR / "cot_direction_latest.json"
DECISION_CSV = OUT_DIR / "cot_direction_latest.csv"
MACRO_CONTEXT_JSON = OUT_DIR / "macro_direction_context.json"
HTML_OUT = ROOT / "directional_cot_report.html"


def load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def apply_macro_actionability_guard(
    decisions: list[dict[str, Any]],
    macro_context: dict[str, Any],
) -> list[dict[str, Any]]:
    availability = float(macro_context.get("availability_ratio") or 0.0)
    reliable = bool(
        macro_context.get("reliable_for_action")
        if "reliable_for_action" in macro_context
        else availability >= MINIMUM_RELIABLE_AVAILABILITY
    )
    suppressed_override = bool(macro_context.get("hard_override_suppressed_by_freshness"))
    output: list[dict[str, Any]] = []
    for raw in decisions:
        row = dict(raw)
        row["macro_reliable_for_action"] = reliable
        row["macro_hard_override_suppressed_by_freshness"] = suppressed_override
        release_status = str(row.get("release_status") or "current")
        if release_status in {"delayed", "awaiting_release"}:
            output.append(row)
            continue
        if not reliable:
            row["pre_macro_quality_action"] = row.get("final_action")
            row["final_action"] = "Wait — Macro Data Incomplete"
            row["exposure_multiplier"] = 0.0
            row["macro_override"] = False
            reasons = list(row.get("reasons") or [])
            reasons.append(
                f"Trade blocked: fresh macro coverage {availability * 100:.0f}% is below "
                f"{MINIMUM_RELIABLE_AVAILABILITY * 100:.0f}%"
            )
            if suppressed_override:
                reasons.append("Severe macro alerts were not allowed to trigger a hard override because their source coverage was insufficient")
            row["reasons"] = reasons
        output.append(row)
    return output


def main() -> None:
    decisions = load_json(DECISION_JSON, [])
    macro_context = load_json(MACRO_CONTEXT_JSON, {})
    if not isinstance(decisions, list) or not decisions:
        raise ValueError(f"Missing or empty {DECISION_JSON}")
    if not isinstance(macro_context, dict):
        macro_context = {}
    guarded = apply_macro_actionability_guard(decisions, macro_context)
    DECISION_JSON.write_text(json.dumps(guarded, indent=2) + "\n", encoding="utf-8")
    write_csv(DECISION_CSV, guarded)
    HTML_OUT.write_text(render_html(guarded, read_validation()), encoding="utf-8")
    for row in guarded:
        print(f"{row['market_label']}: {row['final_action']} | macro reliable {row['macro_reliable_for_action']}")


if __name__ == "__main__":
    main()
