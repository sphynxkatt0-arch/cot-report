#!/usr/bin/env python3
"""Report how current NQ/TFF expectancy changes with analog sample size.

This is a research diagnostic only. It reuses the governed walk-forward score,
release anchoring, distance metric, and full-history canonical research source;
it does not alter production model parameters.
"""
from __future__ import annotations

import json

import build_worldclass_backtest as backtest
import build_worldclass_research_artifacts as research

COUNTS = (20, 30, 40, 60, 80, 120)
HORIZONS = ("1w", "2w", "4w", "13w", "26w")


def main() -> None:
    base = research.build_research_base()
    payload = base["COT_DATA"]["tff"]["nq"]
    prices = base["PRICE_DATA"]["nq"]
    original_count = backtest.ANALOG_COUNT
    results = {}
    try:
        for count in COUNTS:
            backtest.ANALOG_COUNT = count
            built = backtest.build_dataset_backtest("nq", "tff", payload, prices)
            if built is None:
                raise RuntimeError(f"NQ/TFF backtest unavailable for N={count}")
            results[str(count)] = {
                "current": built["current"],
                "historical_signal_count": built["historical_signal_count"],
                "horizons": {h: built["horizons"][h] for h in HORIZONS},
            }
    finally:
        backtest.ANALOG_COUNT = original_count

    print("NQ_ANALOG_SENSITIVITY_BEGIN")
    print(json.dumps(results, indent=2, sort_keys=True))
    print("NQ_ANALOG_SENSITIVITY_END")

    for horizon in HORIZONS:
        print(f"HORIZON {horizon}")
        print("N | exp | median | hit | edge | q25 | q75 | avgDD | worstDD | avgDist | conf")
        for count in COUNTS:
            row = results[str(count)]["horizons"][horizon]
            print(
                f"{count:>3} | {row['expected_return_pct']:+.4f}% | {row['median_return_pct']:+.4f}% | "
                f"{row['hit_rate_pct']:.2f}% | {row['edge_vs_unconditional_pct']:+.4f}% | "
                f"{row['q25_return_pct']:+.4f}% | {row['q75_return_pct']:+.4f}% | "
                f"{row['avg_drawdown_pct']:+.4f}% | {row['worst_drawdown_pct']:+.4f}% | "
                f"{row['avg_analog_distance']:.3f} | {row['confidence']}"
            )


if __name__ == "__main__":
    main()
