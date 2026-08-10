#!/usr/bin/env python3
"""Temporary research diagnostic for NQ daily post-release analog edge.

Uses the governed NQ/TFF score, momentum-aware analog distance, Friday release
anchor, full-history canonical research data, and fixed governed analog count.
No production parameter is changed or optimized.
"""
from __future__ import annotations

import json
import statistics
from datetime import timedelta

import build_worldclass_backtest as backtest
import build_worldclass_research_artifacts as research

DAILY_STEPS = {
    "monday_1d": 1,
    "tuesday_2d": 2,
    "wednesday_3d": 3,
    "thursday_4d": 4,
    "friday_5d": 5,
}
COUNTS = (20, 30, 40, 60, 80, 120)


def build_state():
    base = research.build_research_base()
    payload = base["COT_DATA"]["tff"]["nq"]
    prices = backtest.price_records(base["PRICE_DATA"]["nq"])
    rows = [r for r in payload["records"] if backtest.parse_date(r.get("date"))]
    rows.sort(key=lambda r: str(r.get("date")))
    categories = list(payload["categories"].keys())

    scores = [None] * len(rows)
    historical = []
    for i, row in enumerate(rows):
        if i + 1 < backtest.MIN_LOOKBACK_WEEKS:
            continue
        score = backtest.score_at(rows, i, "tff", categories)
        scores[i] = score
        report_date = backtest.parse_date(row.get("date"))
        if score is None or report_date is None:
            continue
        start_idx = backtest.first_price_index_on_or_after(prices, report_date + timedelta(days=3))
        if start_idx is None:
            continue
        prior_idx = max(backtest.MIN_LOOKBACK_WEEKS - 1, i - 4)
        prior = scores[prior_idx]
        delta = score - prior if prior is not None and prior_idx != i else 0.0
        returns = {}
        for label, steps in DAILY_STEPS.items():
            result = backtest.horizon_result(prices, start_idx, steps)
            if result is not None:
                returns[label] = result["return_pct"]
        historical.append({
            "report_date": report_date.isoformat(),
            "signal_date": prices[start_idx]["date_str"],
            "score": score,
            "delta": delta,
            "returns": returns,
        })

    current_i = len(rows) - 1
    current_score = backtest.score_at(rows, current_i, "tff", categories)
    prior_i = max(backtest.MIN_LOOKBACK_WEEKS - 1, current_i - 4)
    prior_score = backtest.score_at(rows, prior_i, "tff", categories)
    current_delta = current_score - prior_score
    current_report = backtest.parse_date(rows[current_i]["date"])
    return historical, current_score, current_delta, current_report


def metrics(analogs, label, unconditional):
    values = [r["returns"][label] for _, r in analogs]
    distances = [d for d, _ in analogs]
    weights = [1.0 / (1.0 + d) for d in distances]
    expected = backtest.weighted_mean(values, weights)
    return {
        "n": len(values),
        "expected_return_pct": round(expected, 4),
        "median_return_pct": round(statistics.median(values), 4),
        "hit_rate_pct": round(sum(v > 0 for v in values) / len(values) * 100, 2),
        "unconditional_return_pct": round(unconditional, 4),
        "edge_vs_unconditional_pct": round(expected - unconditional, 4),
        "q25_return_pct": round(backtest.quantile(values, 0.25), 4),
        "q75_return_pct": round(backtest.quantile(values, 0.75), 4),
        "avg_distance": round(statistics.mean(distances), 3),
    }


def main():
    historical, current_score, current_delta, current_report = build_state()
    out = {
        "current_report_date": current_report.isoformat(),
        "release_target_date": (current_report + timedelta(days=3)).isoformat(),
        "current_score": round(current_score, 3),
        "current_score_delta_4w": round(current_delta, 3),
        "governed_analog_count": backtest.ANALOG_COUNT,
        "model_version": backtest.MODEL_VERSION,
        "model_spec_hash": backtest.MODEL_SPEC_HASH,
        "daily": {},
    }

    for label in DAILY_STEPS:
        realized = [r for r in historical if label in r["returns"] and r["report_date"] != current_report.isoformat()]
        unconditional_values = [r["returns"][label] for r in realized]
        unconditional = statistics.mean(unconditional_values)
        ranked = []
        for row in realized:
            distance = abs(row["score"] - current_score) + backtest.ANALOG_MOMENTUM_WEIGHT * abs(row["delta"] - current_delta)
            ranked.append((distance, row))
        ranked.sort(key=lambda item: (item[0], item[1]["report_date"]))
        rows = {}
        for count in COUNTS:
            rows[str(count)] = metrics(ranked[:count], label, unconditional)
        out["daily"][label] = rows

    print("NQ_DAILY_RELEASE_PATH_BEGIN")
    print(json.dumps(out, indent=2, sort_keys=True))
    print("NQ_DAILY_RELEASE_PATH_END")
    print("DAY | N40 exp | hit | edge | baseline | N20 edge | N30 edge | N60 edge | N80 edge | N120 edge")
    for label in DAILY_STEPS:
        rows = out["daily"][label]
        r40 = rows["40"]
        print(
            f"{label:14s} | {r40['expected_return_pct']:+.4f}% | {r40['hit_rate_pct']:5.2f}% | "
            f"{r40['edge_vs_unconditional_pct']:+.4f}% | {r40['unconditional_return_pct']:+.4f}% | "
            f"{rows['20']['edge_vs_unconditional_pct']:+.4f}% | {rows['30']['edge_vs_unconditional_pct']:+.4f}% | "
            f"{rows['60']['edge_vs_unconditional_pct']:+.4f}% | {rows['80']['edge_vs_unconditional_pct']:+.4f}% | "
            f"{rows['120']['edge_vs_unconditional_pct']:+.4f}%"
        )


if __name__ == "__main__":
    main()
