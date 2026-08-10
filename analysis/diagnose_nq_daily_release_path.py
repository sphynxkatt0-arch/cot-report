#!/usr/bin/env python3
"""Temporary multi-market daily post-release analog diagnostic; no production changes.

Every historical COT observation is dated Tuesday but only becomes usable after
its Friday public release. The signal anchor is therefore the first available
market close on/after Tuesday report date + 3 calendar days. Daily steps are
trading sessions after that release close, not calendar days, so holidays do
not introduce lookahead.
"""
from __future__ import annotations

import json
import statistics
from datetime import timedelta

import build_worldclass_backtest as backtest
import evaluate_analog_robustness as robustness

DAILY_STEPS = {
    "session_1": 1,
    "session_2": 2,
    "session_3": 3,
    "session_4": 4,
    "session_5": 5,
}
CURRENT_WEEK_LABELS = {
    "session_1": "Monday",
    "session_2": "Tuesday",
    "session_3": "Wednesday",
    "session_4": "Thursday",
    "session_5": "Friday",
}
COUNTS = (20, 30, 40, 60, 80, 120)
MARKET_DATASETS = {
    "sp500": "tff",
    "nq": "tff",
    "vix": "tff",
    "rty": "tff",
    "dow": "tff",
    "gold": "disaggregated",
    "silver": "disaggregated",
}


def build_state(market, dataset, payload, prices_payload):
    prices = backtest.price_records(prices_payload)
    rows = [r for r in payload.get("records", []) if backtest.parse_date(r.get("date"))]
    rows.sort(key=lambda r: str(r.get("date")))
    categories = list((payload.get("categories") or {}).keys())
    if len(rows) < backtest.MIN_LOOKBACK_WEEKS or len(prices) < 200 or not categories:
        raise RuntimeError(f"Insufficient full-history inputs for {market}/{dataset}")

    scores = [None] * len(rows)
    historical = []
    for i, row in enumerate(rows):
        if i + 1 < backtest.MIN_LOOKBACK_WEEKS:
            continue
        score = backtest.score_at(rows, i, dataset, categories)
        scores[i] = score
        report_date = backtest.parse_date(row.get("date"))
        if score is None or report_date is None:
            continue

        release_target = report_date + timedelta(days=3)
        start_idx = backtest.first_price_index_on_or_after(prices, release_target)
        if start_idx is None:
            continue

        prior_idx = max(backtest.MIN_LOOKBACK_WEEKS - 1, i - 4)
        prior = scores[prior_idx]
        delta = score - prior if prior is not None and prior_idx != i else 0.0
        cumulative = {}
        sessions = {}
        for label, steps in DAILY_STEPS.items():
            result = backtest.horizon_result(prices, start_idx, steps)
            if result is None:
                continue
            cumulative[label] = result["return_pct"]
            end_idx = start_idx + steps
            if end_idx >= len(prices):
                continue
            previous = prices[end_idx - 1]["price"]
            current = prices[end_idx]["price"]
            if previous not in (None, 0) and current is not None:
                sessions[label] = (current / previous - 1.0) * 100.0

        historical.append({
            "report_date": report_date.isoformat(),
            "release_target_date": release_target.isoformat(),
            "signal_date": prices[start_idx]["date_str"],
            "score": score,
            "delta": delta,
            "cumulative": cumulative,
            "sessions": sessions,
        })

    current_i = len(rows) - 1
    current_score = backtest.score_at(rows, current_i, dataset, categories)
    prior_i = max(backtest.MIN_LOOKBACK_WEEKS - 1, current_i - 4)
    prior_score = backtest.score_at(rows, prior_i, dataset, categories)
    current_delta = current_score - prior_score if current_score is not None and prior_score is not None else 0.0
    current_report = backtest.parse_date(rows[current_i]["date"])
    if current_score is None or current_report is None:
        raise RuntimeError(f"Missing current state for {market}/{dataset}")
    return historical, current_score, current_delta, current_report


def metrics(analogs, label, field, unconditional):
    values = [r[field][label] for _, r in analogs]
    distances = [d for d, _ in analogs]
    weights = [1.0 / (1.0 + d) for d in distances]
    expected = backtest.weighted_mean(values, weights)
    return {
        "n": len(values),
        "expected_return_pct": round(expected, 4) if expected is not None else None,
        "median_return_pct": round(statistics.median(values), 4) if values else None,
        "hit_rate_pct": round(sum(v > 0 for v in values) / len(values) * 100, 2) if values else None,
        "unconditional_return_pct": round(unconditional, 4),
        "edge_vs_unconditional_pct": round(expected - unconditional, 4) if expected is not None else None,
        "q25_return_pct": round(backtest.quantile(values, 0.25), 4) if values else None,
        "q75_return_pct": round(backtest.quantile(values, 0.75), 4) if values else None,
        "avg_analog_distance": round(statistics.mean(distances), 3) if distances else None,
    }


def summarize_field(historical, current_score, current_delta, current_report, field):
    output = {}
    for label in DAILY_STEPS:
        realized = [r for r in historical if label in r[field] and r["report_date"] != current_report.isoformat()]
        unconditional = statistics.mean(r[field][label] for r in realized)
        ranked = []
        for row in realized:
            distance = abs(row["score"] - current_score) + backtest.ANALOG_MOMENTUM_WEIGHT * abs(row["delta"] - current_delta)
            ranked.append((distance, row))
        ranked.sort(key=lambda item: (item[0], item[1]["report_date"]))
        rows = {
            str(count): metrics(ranked[: min(count, len(ranked))], label, field, unconditional)
            for count in COUNTS
        }
        edges = [rows[str(count)]["edge_vs_unconditional_pct"] for count in COUNTS]
        positive = sum(1 for value in edges if value is not None and value > 0)
        negative = sum(1 for value in edges if value is not None and value < 0)
        if positive >= 5:
            stability = "POSITIVE"
        elif negative >= 5:
            stability = "NEGATIVE"
        else:
            stability = "MIXED"
        output[label] = {
            "counts": rows,
            "edge_sign_stability": stability,
            "positive_edge_counts": positive,
            "negative_edge_counts": negative,
            "tested_counts": len(COUNTS),
        }
    return output


def market_result(market, dataset, payload, prices_payload):
    historical, current_score, current_delta, current_report = build_state(market, dataset, payload, prices_payload)
    return {
        "market": market,
        "dataset": dataset,
        "current_report_date_tuesday_snapshot": current_report.isoformat(),
        "public_release_target_friday": (current_report + timedelta(days=3)).isoformat(),
        "current_score": round(current_score, 3),
        "current_score_delta_4w": round(current_delta, 3),
        "historical_states": len(historical),
        "cumulative_from_friday_release_close": summarize_field(
            historical, current_score, current_delta, current_report, "cumulative"
        ),
        "individual_post_release_sessions": summarize_field(
            historical, current_score, current_delta, current_report, "sessions"
        ),
    }


def print_table(title, results, field):
    print(title)
    print("MARKET | DAY | N40 exp | hit | edge | baseline | sign stability")
    for market in MARKET_DATASETS:
        market_rows = results[market][field]
        for label in DAILY_STEPS:
            bucket = market_rows[label]
            r40 = bucket["counts"]["40"]
            day = CURRENT_WEEK_LABELS[label]
            print(
                f"{market.upper():6s} | {day:9s} | {r40['expected_return_pct']:+.4f}% | "
                f"{r40['hit_rate_pct']:5.2f}% | {r40['edge_vs_unconditional_pct']:+.4f}% | "
                f"{r40['unconditional_return_pct']:+.4f}% | {bucket['edge_sign_stability']} "
                f"({bucket['positive_edge_counts']}/{bucket['tested_counts']} positive)"
            )


def main():
    cot_data, prices = robustness.build_full_inputs()
    results = {}
    for market, dataset in MARKET_DATASETS.items():
        payload = ((cot_data.get(dataset) or {}).get(market))
        if not isinstance(payload, dict):
            raise RuntimeError(f"Missing {dataset} payload for {market}")
        price_payload = prices.get(market)
        if price_payload is None:
            raise RuntimeError(f"Missing price payload for {market}")
        results[market] = market_result(market, dataset, payload, price_payload)

    out = {
        "study": "multi-market daily COT post-release analog diagnostic",
        "information_timing": {
            "cot_position_snapshot": "Tuesday",
            "public_release": "Friday",
            "lookahead_safe_anchor": "first market close on/after Tuesday report date + 3 calendar days",
            "daily_step_definition": "successive available trading sessions after the Friday release close",
        },
        "governed_analog_count": backtest.ANALOG_COUNT,
        "tested_analog_counts": list(COUNTS),
        "model_version": backtest.MODEL_VERSION,
        "model_spec_hash": backtest.MODEL_SPEC_HASH,
        "markets": results,
    }

    print("MULTI_MARKET_DAILY_RELEASE_PATH_BEGIN")
    print(json.dumps(out, indent=2, sort_keys=True))
    print("MULTI_MARKET_DAILY_RELEASE_PATH_END")
    print_table("CUMULATIVE FROM FRIDAY RELEASE CLOSE", results, "cumulative_from_friday_release_close")
    print_table("INDIVIDUAL POST-RELEASE SESSIONS", results, "individual_post_release_sessions")


if __name__ == "__main__":
    main()
