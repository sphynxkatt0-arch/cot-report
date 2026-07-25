#!/usr/bin/env python3
"""Rebuild canonical COT history using scheduled Friday release dates only.

Live first-observed release metadata belongs in the latest decision. Historical
rows remain deterministic and never inherit the local observation ledger.
Forward outcomes include terminal returns and the best/worst path reached before
each horizon so model comparison can account for adverse movement.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from build_directional_cot_system import (
    HISTORY_OUT,
    VALIDATION_OUT,
    build_validation_summary,
    common_report_dates,
    feature_snapshot,
    load_market_inputs,
    price_index_at_or_after,
    write_csv,
)
from cftc_release_tracker import scheduled_release_datetime
from cot_direction_model import (
    load_config,
    preserve_structural_sign,
    structural_score_from_percentile,
    tactical_modifier,
)

ROOT = Path(__file__).resolve().parent
HORIZONS = (("1w", 5), ("4w", 20), ("13w", 65), ("26w", 130))


def path_outcomes(
    prices: pd.DataFrame,
    base_index: int | None,
    trading_days: int,
) -> tuple[float | None, float | None, float | None]:
    if base_index is None:
        return None, None, None
    target_index = base_index + trading_days
    if target_index >= len(prices):
        return None, None, None
    base_price = float(prices.iloc[base_index]["price"])
    if base_price <= 0:
        return None, None, None
    path = pd.to_numeric(
        prices.iloc[base_index : target_index + 1]["price"],
        errors="coerce",
    ).dropna()
    if path.empty:
        return None, None, None
    path_returns = (path / base_price - 1.0) * 100.0
    terminal = float(path_returns.iloc[-1])
    worst = float(path_returns.min())
    best = float(path_returns.max())
    return terminal, worst, best


def build_deterministic_history_for_market(
    market: str,
    legacy: pd.DataFrame,
    tff: pd.DataFrame,
    prices: pd.DataFrame,
    config: dict[str, Any],
) -> list[dict[str, Any]]:
    minimum = int(config["minimum_history_weeks"])
    rows: list[dict[str, Any]] = []
    for report_ts in common_report_dates(legacy, tff):
        snapshot = feature_snapshot(legacy, tff, report_ts, minimum)
        structural = structural_score_from_percentile(snapshot["noncommercial_percentile"], config)
        tactical, _ = tactical_modifier(
            structural,
            snapshot["other_reportable_trend13_rank"],
            snapshot["nonreportable_trend13_rank"],
            snapshot["noncommercial_flow4_rank"],
            config,
        )
        adjusted = preserve_structural_sign(structural, tactical)
        release_date = pd.Timestamp(scheduled_release_datetime(report_ts.date()).date())
        base_index = price_index_at_or_after(prices, release_date)
        base_price = float(prices.iloc[base_index]["price"]) if base_index is not None else None
        row: dict[str, Any] = {
            "market": market,
            "model_version": str(config["model_version"]),
            "report_date": report_ts.date().isoformat(),
            "scheduled_release_date": release_date.date().isoformat(),
            "release_date_source": "scheduled_history",
            **snapshot,
            "structural_score": structural,
            "tactical_modifier": tactical,
            "adjusted_cot_score": adjusted,
            "signal_price_date": prices.iloc[base_index]["date"].date().isoformat() if base_index is not None else None,
            "signal_price": base_price,
        }
        for label, trading_days in HORIZONS:
            terminal, worst, best = path_outcomes(prices, base_index, trading_days)
            row[f"forward_return_{label}"] = terminal
            row[f"forward_worst_path_return_{label}"] = worst
            row[f"forward_best_path_return_{label}"] = best
        rows.append(row)
    return rows


def main() -> None:
    config = load_config(ROOT / "config" / "cot_direction_model_v1.json")
    history: list[dict[str, Any]] = []
    for market in ("sp500", "nq"):
        legacy, tff, prices = load_market_inputs(market)
        history.extend(build_deterministic_history_for_market(market, legacy, tff, prices, config))
    validation = build_validation_summary(history)
    write_csv(HISTORY_OUT, history)
    write_csv(VALIDATION_OUT, validation)
    print(f"Wrote deterministic history: {HISTORY_OUT}")
    print(f"Wrote validation summary: {VALIDATION_OUT}")


if __name__ == "__main__":
    main()
