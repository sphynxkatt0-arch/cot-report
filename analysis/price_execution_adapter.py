#!/usr/bin/env python3
"""Refine COT execution using post-release move and price-trend agreement."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import pandas as pd

from build_directional_cot_report import MARKETS, read_prices
from build_directional_cot_system import OUT_DIR, VALIDATION_OUT, render_html, write_csv
from cot_direction_model import clamp, final_action, load_config

ROOT = Path(__file__).resolve().parent
DECISION_JSON = OUT_DIR / "cot_direction_latest.json"
DECISION_CSV = OUT_DIR / "cot_direction_latest.csv"
HTML_OUT = ROOT / "directional_cot_report.html"


def finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number else None


def trailing_return(prices: pd.DataFrame, periods: int) -> float | None:
    if len(prices) <= periods:
        return None
    latest = float(prices.iloc[-1]["price"])
    prior = float(prices.iloc[-1 - periods]["price"])
    if prior == 0:
        return None
    return (latest / prior - 1.0) * 100.0


def evaluate_execution(
    *,
    market: str,
    adjusted_cot_score: float | None,
    release_change_pct: float | None,
    trend_20d_pct: float | None,
    trend_65d_pct: float | None,
    config: dict[str, Any],
) -> dict[str, Any]:
    if adjusted_cot_score is None or abs(adjusted_cot_score) < 0.25:
        return {"state": "No structural signal", "multiplier": 0.0, "alignment": "neutral"}
    if release_change_pct is None or trend_20d_pct is None:
        return {"state": "Unavailable", "multiplier": 0.0, "alignment": "unavailable"}

    sign = 1.0 if adjusted_cot_score > 0 else -1.0
    signed_release = sign * release_change_pct
    signed_20d = sign * trend_20d_pct
    signed_65d = sign * trend_65d_pct if trend_65d_pct is not None else None
    cfg = config["execution"]
    invalidation = float(cfg["nq_invalidation_pct"] if market == "nq" else cfg["sp500_invalidation_pct"])
    waiting_band = float(cfg["waiting_band_pct"])

    if signed_release <= -invalidation or signed_20d <= -invalidation:
        state = "Invalidated"
        multiplier = float(cfg["invalidated_multiplier"])
        alignment = "opposed"
    elif signed_release > waiting_band and signed_20d >= 0:
        state = "Confirmed"
        multiplier = float(cfg["confirmed_multiplier"])
        alignment = "aligned"
    elif signed_release < -waiting_band or signed_20d < -waiting_band:
        state = "Contradicted"
        multiplier = float(cfg["contradicted_multiplier"])
        alignment = "opposed"
    else:
        state = "Waiting"
        multiplier = float(cfg["waiting_multiplier"])
        alignment = "mixed"

    return {
        "state": state,
        "multiplier": multiplier,
        "alignment": alignment,
        "signed_release_change_pct": round(signed_release, 3),
        "signed_trend_20d_pct": round(signed_20d, 3),
        "signed_trend_65d_pct": round(signed_65d, 3) if signed_65d is not None else None,
    }


def read_validation() -> list[dict[str, Any]]:
    if not VALIDATION_OUT.exists():
        return []
    with VALIDATION_OUT.open("r", newline="", encoding="utf-8-sig") as handle:
        rows = []
        for row in csv.DictReader(handle):
            converted = dict(row)
            for key in (
                "observations",
                "pearson_r",
                "spearman_r",
                "bullish_n",
                "bullish_avg_return",
                "bearish_n",
                "bearish_avg_return",
                "neutral_n",
                "neutral_avg_return",
                "bullish_minus_bearish",
            ):
                if key in converted and converted[key] not in {"", None}:
                    try:
                        converted[key] = float(converted[key])
                    except ValueError:
                        pass
            rows.append(converted)
        return rows


def refine_decisions(decisions: list[dict[str, Any]], config: dict[str, Any]) -> list[dict[str, Any]]:
    refined: list[dict[str, Any]] = []
    for decision in decisions:
        market = str(decision["market"])
        meta = MARKETS[market]
        prices = read_prices(meta["price_path"], meta["price_col"])
        trend_20d = trailing_return(prices, 20)
        trend_65d = trailing_return(prices, 65)
        release_change = finite(decision.get("price_change_since_release_pct"))
        execution = evaluate_execution(
            market=market,
            adjusted_cot_score=finite(decision.get("adjusted_cot_score")),
            release_change_pct=release_change,
            trend_20d_pct=trend_20d,
            trend_65d_pct=trend_65d,
            config=config,
        )

        release_status = str(decision.get("release_status") or "current")
        if release_status in {"delayed", "awaiting_release"}:
            refined.append(decision)
            continue

        decision = dict(decision)
        decision["execution_state"] = execution["state"]
        decision["execution_multiplier"] = execution["multiplier"]
        decision["price_alignment"] = execution["alignment"]
        decision["price_trend_20d_pct"] = round(trend_20d, 3) if trend_20d is not None else None
        decision["price_trend_65d_pct"] = round(trend_65d, 3) if trend_65d is not None else None
        adjusted = abs(float(decision.get("adjusted_cot_score") or 0.0))
        exposure = (
            adjusted
            * float(decision.get("asset_manager_multiplier") or 1.0)
            * float(decision.get("macro_multiplier") or 1.0)
            * float(execution["multiplier"])
        )
        decision["exposure_multiplier"] = round(clamp(exposure, 0.0, 1.25), 4)
        decision["final_action"] = final_action(
            finite(decision.get("adjusted_cot_score")),
            execution["state"],
            decision["exposure_multiplier"],
            float(decision.get("confidence_score") or 0.0),
            bool(decision.get("macro_override")),
            config,
        )
        reasons = [
            reason for reason in list(decision.get("reasons") or [])
            if not str(reason).startswith("Price execution ")
        ]
        reasons.append(
            f"Price execution {execution['state']}; 20d trend {trend_20d:+.2f}% and 65d trend {trend_65d:+.2f}%"
            if trend_20d is not None and trend_65d is not None
            else f"Price execution {execution['state']}; trend history incomplete"
        )
        decision["reasons"] = reasons
        refined.append(decision)
    return refined


def main() -> None:
    if not DECISION_JSON.exists():
        raise FileNotFoundError(f"Missing {DECISION_JSON}; run build_directional_cot_system.py first")
    config = load_config(ROOT / "config" / "cot_direction_model_v1.json")
    decisions = json.loads(DECISION_JSON.read_text(encoding="utf-8"))
    refined = refine_decisions(decisions, config)
    DECISION_JSON.write_text(json.dumps(refined, indent=2) + "\n", encoding="utf-8")
    write_csv(DECISION_CSV, refined)
    HTML_OUT.write_text(render_html(refined, read_validation()), encoding="utf-8")
    for row in refined:
        print(f"{row['market_label']}: {row['final_action']} | price {row.get('price_alignment', 'n/a')}")


if __name__ == "__main__":
    main()
