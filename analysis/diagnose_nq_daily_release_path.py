#!/usr/bin/env python3
"""Strict walk-forward test of previous-week COT -> exact next-week weekday returns.

The COT snapshot is dated Tuesday and is assumed public on Friday (report date +
3 calendar days). Forecasts are locked at that Friday close. The five targets
are the exact calendar Monday, Tuesday, Wednesday, Thursday and Friday of the
following week. Each target is a single-session close-to-close return, never a
cumulative D+n return.

For every historical target release, analogs and weekday baselines are built
ONLY from earlier COT releases. Future analogs are forbidden. The governed
model uses N=40 once 40 prior realized states exist; an adaptive N<=40 audit is
also retained so the earliest forecastable reports are exercised rather than
silently discarded.
"""
from __future__ import annotations

import json
import math
import statistics
from datetime import timedelta
from pathlib import Path

import build_worldclass_backtest as backtest
import evaluate_analog_robustness as robustness

WEEKDAYS = {
    "monday": 6,     # Tuesday COT snapshot + 6 calendar days
    "tuesday": 7,
    "wednesday": 8,
    "thursday": 9,
    "friday": 10,
}
MARKET_DATASETS = {
    "sp500": "tff",
    "nq": "tff",
    "vix": "tff",
    "rty": "tff",
    "dow": "tff",
    "gold": "disaggregated",
    "silver": "disaggregated",
}
OUT = Path(__file__).resolve().with_name("daily_release_walkforward_results.json")


def sign(value):
    if value is None or not math.isfinite(value):
        return 0
    return 1 if value > 0 else (-1 if value < 0 else 0)


def direction(value):
    s = sign(value)
    return "BULLISH" if s > 0 else ("BEARISH" if s < 0 else "NEUTRAL")


def exact_session_return(prices, price_index_by_date, target_date):
    """Return exact target calendar weekday close vs previous trading close."""
    idx = price_index_by_date.get(target_date)
    if idx is None or idx <= 0:
        return None
    previous = prices[idx - 1]["price"]
    current = prices[idx]["price"]
    if previous in (None, 0) or current is None:
        return None
    return (current / previous - 1.0) * 100.0


def build_states(market, dataset, payload, prices_payload):
    prices = backtest.price_records(prices_payload)
    price_index_by_date = {row["date"]: idx for idx, row in enumerate(prices)}
    rows = [r for r in payload.get("records", []) if backtest.parse_date(r.get("date"))]
    rows.sort(key=lambda r: str(r.get("date")))
    categories = list((payload.get("categories") or {}).keys())
    if len(rows) < backtest.MIN_LOOKBACK_WEEKS or len(prices) < 200 or not categories:
        raise RuntimeError(f"Insufficient full-history inputs for {market}/{dataset}")

    scores = [None] * len(rows)
    states = []
    for i, row in enumerate(rows):
        if i + 1 < backtest.MIN_LOOKBACK_WEEKS:
            continue
        score = backtest.score_at(rows, i, dataset, categories)
        scores[i] = score
        report_date = backtest.parse_date(row.get("date"))
        if score is None or report_date is None:
            continue

        prior_i = max(backtest.MIN_LOOKBACK_WEEKS - 1, i - 4)
        prior_score = scores[prior_i]
        delta = score - prior_score if prior_score is not None and prior_i != i else 0.0
        release_date = report_date + timedelta(days=3)
        outcomes = {}
        outcome_dates = {}
        for weekday, offset in WEEKDAYS.items():
            target_date = report_date + timedelta(days=offset)
            realized = exact_session_return(prices, price_index_by_date, target_date)
            if realized is not None:
                outcomes[weekday] = realized
                outcome_dates[weekday] = target_date.isoformat()

        states.append({
            "report_date": report_date.isoformat(),
            "release_date": release_date.isoformat(),
            "score": score,
            "delta_4w": delta,
            "outcomes": outcomes,
            "outcome_dates": outcome_dates,
        })
    return states


def weighted_forecast(target, prior_rows, weekday, count):
    eligible = [row for row in prior_rows if weekday in row["outcomes"]]
    if not eligible:
        return None
    ranked = []
    for row in eligible:
        distance = abs(row["score"] - target["score"]) + backtest.ANALOG_MOMENTUM_WEIGHT * abs(
            row["delta_4w"] - target["delta_4w"]
        )
        ranked.append((distance, row))
    ranked.sort(key=lambda item: (item[0], item[1]["report_date"]))
    n = min(count, len(ranked))
    selected = ranked[:n]
    values = [row["outcomes"][weekday] for _, row in selected]
    distances = [distance for distance, _ in selected]
    weights = [1.0 / (1.0 + distance) for distance in distances]
    expected = backtest.weighted_mean(values, weights)
    baseline = statistics.mean(row["outcomes"][weekday] for row in eligible)
    if expected is None:
        return None
    return {
        "n": n,
        "prior_weekday_observations": len(eligible),
        "expected_return_pct": expected,
        "baseline_return_pct": baseline,
        "edge_vs_baseline_pct": expected - baseline,
        "analog_positive_rate_pct": sum(v > 0 for v in values) / len(values) * 100.0,
        "analog_median_return_pct": statistics.median(values),
        "analog_q25_return_pct": backtest.quantile(values, 0.25),
        "analog_q75_return_pct": backtest.quantile(values, 0.75),
        "avg_analog_distance": statistics.mean(distances),
    }


def aggregate(records):
    if not records:
        return {"observations": 0}
    model_hits = [r["model_direction_hit"] for r in records]
    baseline_hits = [r["baseline_direction_hit"] for r in records]
    expected = [r["expected_return_pct"] for r in records]
    actual = [r["actual_return_pct"] for r in records]
    baseline = [r["baseline_return_pct"] for r in records]
    abs_error = [abs(e - a) for e, a in zip(expected, actual)]
    squared_error = [(e - a) ** 2 for e, a in zip(expected, actual)]
    model_rate = sum(model_hits) / len(model_hits) * 100.0
    baseline_rate = sum(baseline_hits) / len(baseline_hits) * 100.0
    return {
        "observations": len(records),
        "model_direction_hit_rate_pct": round(model_rate, 2),
        "expanding_weekday_baseline_hit_rate_pct": round(baseline_rate, 2),
        "direction_hit_lift_vs_baseline_pp": round(model_rate - baseline_rate, 2),
        "mean_forecast_return_pct": round(statistics.mean(expected), 4),
        "mean_realized_return_pct": round(statistics.mean(actual), 4),
        "mean_expanding_weekday_baseline_pct": round(statistics.mean(baseline), 4),
        "mean_forecast_edge_vs_baseline_pct": round(
            statistics.mean(r["edge_vs_baseline_pct"] for r in records), 4
        ),
        "mae_pct": round(statistics.mean(abs_error), 4),
        "rmse_pct": round(math.sqrt(statistics.mean(squared_error)), 4),
        "bullish_forecast_share_pct": round(
            sum(r["forecast_direction"] == "BULLISH" for r in records) / len(records) * 100.0, 2
        ),
        "bearish_forecast_share_pct": round(
            sum(r["forecast_direction"] == "BEARISH" for r in records) / len(records) * 100.0, 2
        ),
    }


def walk_forward_market(market, dataset, payload, prices_payload):
    states = build_states(market, dataset, payload, prices_payload)
    per_weekday = {weekday: [] for weekday in WEEKDAYS}
    report_audit = []

    for idx, target in enumerate(states):
        prior = states[:idx]
        report_predictions = {}
        for weekday in WEEKDAYS:
            if weekday not in target["outcomes"]:
                continue
            forecast = weighted_forecast(target, prior, weekday, backtest.ANALOG_COUNT)
            if forecast is None:
                continue
            actual = target["outcomes"][weekday]
            forecast_direction = direction(forecast["expected_return_pct"])
            baseline_direction = direction(forecast["baseline_return_pct"])
            row = {
                "report_date": target["report_date"],
                "release_date": target["release_date"],
                "target_date": target["outcome_dates"][weekday],
                "weekday": weekday,
                "n": forecast["n"],
                "prior_weekday_observations": forecast["prior_weekday_observations"],
                "expected_return_pct": round(forecast["expected_return_pct"], 6),
                "baseline_return_pct": round(forecast["baseline_return_pct"], 6),
                "edge_vs_baseline_pct": round(forecast["edge_vs_baseline_pct"], 6),
                "actual_return_pct": round(actual, 6),
                "forecast_direction": forecast_direction,
                "baseline_direction": baseline_direction,
                "model_direction_hit": sign(forecast["expected_return_pct"]) == sign(actual) and sign(actual) != 0,
                "baseline_direction_hit": sign(forecast["baseline_return_pct"]) == sign(actual) and sign(actual) != 0,
            }
            per_weekday[weekday].append(row)
            report_predictions[weekday] = row
        if report_predictions:
            report_audit.append({
                "report_date": target["report_date"],
                "release_date": target["release_date"],
                "predictions": report_predictions,
            })

    latest = states[-1]
    prior = [row for row in states[:-1] if row["report_date"] < latest["report_date"]]
    current = {}
    for weekday in WEEKDAYS:
        forecast = weighted_forecast(latest, prior, weekday, backtest.ANALOG_COUNT)
        if forecast is None:
            continue
        target_date = backtest.parse_date(latest["report_date"]) + timedelta(days=WEEKDAYS[weekday])
        current[weekday] = {
            "target_date": target_date.isoformat(),
            "n": forecast["n"],
            "expected_return_pct": round(forecast["expected_return_pct"], 4),
            "forecast_direction": direction(forecast["expected_return_pct"]),
            "expanding_weekday_baseline_pct": round(forecast["baseline_return_pct"], 4),
            "cot_edge_vs_baseline_pct": round(forecast["edge_vs_baseline_pct"], 4),
            "analog_positive_rate_pct": round(forecast["analog_positive_rate_pct"], 2),
            "analog_median_return_pct": round(forecast["analog_median_return_pct"], 4),
            "q25_return_pct": round(forecast["analog_q25_return_pct"], 4),
            "q75_return_pct": round(forecast["analog_q75_return_pct"], 4),
            "avg_analog_distance": round(forecast["avg_analog_distance"], 3),
        }

    adaptive_summary = {weekday: aggregate(rows) for weekday, rows in per_weekday.items()}
    governed_summary = {
        weekday: aggregate([row for row in rows if row["n"] == backtest.ANALOG_COUNT])
        for weekday, rows in per_weekday.items()
    }
    complete_reports = sum(
        1 for report in report_audit if len(report["predictions"]) == len(WEEKDAYS)
    )
    governed_complete_reports = sum(
        1
        for report in report_audit
        if len(report["predictions"]) == len(WEEKDAYS)
        and all(p["n"] == backtest.ANALOG_COUNT for p in report["predictions"].values())
    )
    return {
        "market": market,
        "dataset": dataset,
        "scored_cot_states": len(states),
        "walk_forward_reports_with_any_realized_weekday": len(report_audit),
        "walk_forward_reports_with_all_five_weekdays": complete_reports,
        "governed_n40_reports_with_all_five_weekdays": governed_complete_reports,
        "adaptive_n_le_40": adaptive_summary,
        "governed_n40": governed_summary,
        "current_report": {
            "snapshot_date_tuesday": latest["report_date"],
            "public_release_date_friday": latest["release_date"],
            "score": round(latest["score"], 3),
            "score_delta_4w": round(latest["delta_4w"], 3),
            "weekday_forecast": current,
        },
        "per_report_audit": report_audit,
    }


def print_market_summary(result):
    print(f"\n{result['market'].upper()} WALK-FORWARD")
    print(
        "states={states} reports_any={anyr} reports_all5={all5} governed_all5={gov}".format(
            states=result["scored_cot_states"],
            anyr=result["walk_forward_reports_with_any_realized_weekday"],
            all5=result["walk_forward_reports_with_all_five_weekdays"],
            gov=result["governed_n40_reports_with_all_five_weekdays"],
        )
    )
    print("DAY       | N40 obs | hit   | baseline hit | lift   | mean fcst | mean actual | MAE")
    for weekday in WEEKDAYS:
        row = result["governed_n40"][weekday]
        print(
            f"{weekday.title():10s}| {row.get('observations', 0):7d} | "
            f"{row.get('model_direction_hit_rate_pct', 0):5.2f}% | "
            f"{row.get('expanding_weekday_baseline_hit_rate_pct', 0):11.2f}% | "
            f"{row.get('direction_hit_lift_vs_baseline_pp', 0):+6.2f} | "
            f"{row.get('mean_forecast_return_pct', 0):+9.4f}% | "
            f"{row.get('mean_realized_return_pct', 0):+10.4f}% | "
            f"{row.get('mae_pct', 0):.4f}%"
        )
    current = result["current_report"]
    print(
        f"CURRENT COT snapshot={current['snapshot_date_tuesday']} release={current['public_release_date_friday']} "
        f"score={current['score']:.3f} delta4w={current['score_delta_4w']:+.3f}"
    )
    print("DAY       | DATE       | DIR     | expected | baseline | COT edge | analog +")
    for weekday in WEEKDAYS:
        row = current["weekday_forecast"].get(weekday)
        if not row:
            continue
        print(
            f"{weekday.title():10s}| {row['target_date']} | {row['forecast_direction']:7s} | "
            f"{row['expected_return_pct']:+8.4f}% | {row['expanding_weekday_baseline_pct']:+8.4f}% | "
            f"{row['cot_edge_vs_baseline_pct']:+8.4f}% | {row['analog_positive_rate_pct']:6.2f}%"
        )


def main():
    cot_data, prices = robustness.build_full_inputs()
    markets = {}
    for market, dataset in MARKET_DATASETS.items():
        payload = ((cot_data.get(dataset) or {}).get(market))
        price_payload = prices.get(market)
        if not isinstance(payload, dict) or price_payload is None:
            raise RuntimeError(f"Missing research inputs for {market}/{dataset}")
        markets[market] = walk_forward_market(market, dataset, payload, price_payload)

    output = {
        "study": "previous-week COT to exact next-week weekday walk-forward",
        "model_version": backtest.MODEL_VERSION,
        "model_spec_hash": backtest.MODEL_SPEC_HASH,
        "governed_analog_count": backtest.ANALOG_COUNT,
        "information_contract": {
            "cot_snapshot": "Tuesday",
            "public_release_assumption": "Friday = report date + 3 calendar days",
            "forecast_lock": "Friday release close",
            "targets": "exact calendar Monday-Friday of the following week",
            "return_definition": "each target weekday close vs immediately previous trading close",
            "lookahead_rule": "each target may use only earlier COT reports and their already-realized weekday outcomes",
            "holiday_rule": "missing exact calendar weekday observations are omitted; they are never relabeled to another weekday",
            "adaptive_audit": "N=min(40, available prior same-weekday observations) exercises early history",
            "governed_test": "primary score uses only forecasts with the full fixed N=40 prior analogs",
        },
        "markets": markets,
    }
    OUT.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote {OUT}")
    for market in MARKET_DATASETS:
        print_market_summary(markets[market])


if __name__ == "__main__":
    main()
