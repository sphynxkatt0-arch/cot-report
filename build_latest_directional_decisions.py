#!/usr/bin/env python3
"""Build latest governed decisions for every configured COT market."""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from build_directional_cot_system import HTML_OUT, OUT_DIR, VALIDATION_OUT, build_latest_market_decision, load_market_inputs, render_html, write_csv
from cot_direction_model import load_config
from cot_market_registry import DIRECTIONAL_MARKETS
from macro_direction_adapter import load_macro_direction_context

ROOT = Path(__file__).resolve().parent


def read_validation() -> list[dict[str, Any]]:
    if not VALIDATION_OUT.exists():
        raise FileNotFoundError(f"Missing {VALIDATION_OUT}; run rebuild_directional_history.py before latest decisions")
    with VALIDATION_OUT.open("r", newline="", encoding="utf-8-sig") as handle:
        rows: list[dict[str, Any]] = []
        for raw in csv.DictReader(handle):
            row: dict[str, Any] = dict(raw)
            for key in (
                "observations", "pearson_r", "spearman_r", "bullish_n", "bullish_avg_return",
                "bearish_n", "bearish_avg_return", "neutral_n", "neutral_avg_return", "bullish_minus_bearish",
            ):
                if row.get(key) not in {None, ""}:
                    try:
                        row[key] = float(row[key])
                    except (TypeError, ValueError):
                        pass
            rows.append(row)
        return rows


def main() -> None:
    config = load_config(ROOT / "config" / "cot_direction_model_v1.json")
    macro_context = load_macro_direction_context().to_dict()
    decisions: list[dict[str, Any]] = []
    for market in DIRECTIONAL_MARKETS:
        legacy, secondary, prices = load_market_inputs(market)
        decisions.append(build_latest_market_decision(market, legacy, secondary, prices, macro_context, config))

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "cot_direction_latest.json").write_text(json.dumps(decisions, indent=2) + "\n", encoding="utf-8")
    (OUT_DIR / "macro_direction_context.json").write_text(json.dumps(macro_context, indent=2) + "\n", encoding="utf-8")
    write_csv(OUT_DIR / "cot_direction_latest.csv", decisions)
    HTML_OUT.write_text(render_html(decisions, read_validation()), encoding="utf-8")
    for decision in decisions:
        print(f"{decision['market_label']}: {decision['final_action']} | {decision['structural_bias']} | release {decision['release_status']} | exposure {decision['exposure_multiplier']:.2f}x")
    print(f"Wrote {HTML_OUT}")


if __name__ == "__main__":
    main()
