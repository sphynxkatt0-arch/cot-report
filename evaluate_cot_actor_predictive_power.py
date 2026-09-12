#!/usr/bin/env python3
"""Lookahead-safe predictive-power diagnostics for the full COT actor event universe.

This layer does not replace the percentile/event backtests. It asks whether continuous
COT actor variables carry forecast information about subsequent returns.

For each available actor x market x horizon we report:
- Pearson correlation and Spearman/rank IC in discovery, holdout and full history;
- overlap-reduced holdout correlations using non-overlapping forward episodes;
- a univariate linear forecast fit on pre-2022 only and evaluated unchanged in 2022+;
- true OOS R^2 versus the frozen pre-2022 mean-return forecast;
- RMSE improvement and directional-hit lift versus that same baseline;
- discovery-frozen lower/upper decile return spread in the 2022+ holdout;
- era correlation stability.

The Tuesday COT snapshot remains unavailable until Friday publication/release anchoring,
and all percentiles used here are the expanding-history values produced by the actor
research engine.
"""
from __future__ import annotations

import json
import math
import statistics
from datetime import date
from pathlib import Path
from typing import Any

import build_cot_actor_event_research as actor_research

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "worldclass" / "research" / "cot-actor-predictive-power.json"
SUMMARY_OUT = ROOT / "worldclass" / "research" / "cot-actor-predictive-power-summary.json"

PREDICTORS = {
    "delta_1w_net_oi_pp": "signed weekly change in actor net position as percentage-points of open interest",
    "signed_change_percentile": "expanding historical magnitude percentile with the sign of the weekly change",
    "position_percentile": "expanding historical percentile of the actor's net/OI position level",
}
HORIZONS = tuple(actor_research.EXACT_WEEKDAYS) + tuple(actor_research.FORWARD_HORIZONS)
HOLDOUT_START = actor_research.HOLDOUT_START
ERA_WINDOWS = actor_research.ERA_WINDOWS


def finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def r6(value: float | None) -> float | None:
    return round(value, 6) if value is not None and math.isfinite(value) else None


def parse_date(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value or "")[:10])
    except ValueError:
        return None


def predictor_value(event: dict[str, Any], predictor: str) -> float | None:
    if predictor == "signed_change_percentile":
        magnitude = finite(event.get("magnitude_percentile"))
        delta = finite(event.get("delta_1w_net_oi_pp"))
        if magnitude is None or delta is None:
            return None
        if abs(delta) <= 1e-12:
            return 0.0
        return magnitude if delta > 0 else -magnitude
    return finite(event.get(predictor))


def horizon_value(event: dict[str, Any], horizon: str) -> float | None:
    if horizon in actor_research.EXACT_WEEKDAYS:
        return finite((event.get("weekday_cumulative") or {}).get(horizon))
    return finite(((event.get("forward") or {}).get(horizon) or {}).get("return_pct"))


def aligned(events: list[dict[str, Any]], predictor: str, horizon: str) -> list[tuple[dict[str, Any], float, float]]:
    rows = []
    for event in events:
        x = predictor_value(event, predictor)
        y = horizon_value(event, horizon)
        if x is None or y is None:
            continue
        rows.append((event, x, y))
    return rows


def pearson(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) != len(ys) or len(xs) < 3:
        return None
    mx = statistics.mean(xs)
    my = statistics.mean(ys)
    dx = [x - mx for x in xs]
    dy = [y - my for y in ys]
    vx = sum(v * v for v in dx)
    vy = sum(v * v for v in dy)
    if vx <= 0 or vy <= 0:
        return None
    return sum(a * b for a, b in zip(dx, dy)) / math.sqrt(vx * vy)


def rankdata(values: list[float]) -> list[float]:
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i + 1
        while j < len(order) and values[order[j]] == values[order[i]]:
            j += 1
        average_rank = (i + 1 + j) / 2.0
        for k in range(i, j):
            ranks[order[k]] = average_rank
        i = j
    return ranks


def spearman(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 3:
        return None
    return pearson(rankdata(xs), rankdata(ys))


def fisher_ci(r: float | None, n: int) -> list[float] | None:
    if r is None or n <= 3 or abs(r) >= 1:
        return None
    z = math.atanh(r)
    se = 1.0 / math.sqrt(n - 3)
    lo = math.tanh(z - 1.96 * se)
    hi = math.tanh(z + 1.96 * se)
    return [r6(lo), r6(hi)]


def correlation_block(rows: list[tuple[dict[str, Any], float, float]]) -> dict[str, Any]:
    xs = [x for _, x, _ in rows]
    ys = [y for _, _, y in rows]
    pr = pearson(xs, ys)
    sr = spearman(xs, ys)
    return {
        "n": len(rows),
        "pearson_r": r6(pr),
        "pearson_fisher95": fisher_ci(pr, len(rows)),
        "spearman_rho": r6(sr),
        "spearman_fisher95_approx": fisher_ci(sr, len(rows)),
    }


def linear_fit(rows: list[tuple[dict[str, Any], float, float]]) -> tuple[float, float] | None:
    if len(rows) < 3:
        return None
    xs = [x for _, x, _ in rows]
    ys = [y for _, _, y in rows]
    mx = statistics.mean(xs)
    my = statistics.mean(ys)
    denom = sum((x - mx) ** 2 for x in xs)
    if denom <= 0:
        return None
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / denom
    intercept = my - slope * mx
    return intercept, slope


def oos_forecast(discovery: list[tuple[dict[str, Any], float, float]], holdout: list[tuple[dict[str, Any], float, float]]) -> dict[str, Any]:
    fit = linear_fit(discovery)
    if fit is None or not holdout:
        return {"n": len(holdout)}
    intercept, slope = fit
    train_mean = statistics.mean(y for _, _, y in discovery)
    actual = [y for _, _, y in holdout]
    predicted = [intercept + slope * x for _, x, _ in holdout]
    baseline = [train_mean] * len(actual)
    sse_model = sum((y - p) ** 2 for y, p in zip(actual, predicted))
    sse_base = sum((y - b) ** 2 for y, b in zip(actual, baseline))
    rmse_model = math.sqrt(sse_model / len(actual))
    rmse_base = math.sqrt(sse_base / len(actual))
    oos_r2 = 1.0 - sse_model / sse_base if sse_base > 0 else None
    rmse_improvement = (rmse_base - rmse_model) / rmse_base * 100.0 if rmse_base > 0 else None
    model_hits = sum((p > 0) == (y > 0) for p, y in zip(predicted, actual)) / len(actual) * 100.0
    base_hits = sum((b > 0) == (y > 0) for b, y in zip(baseline, actual)) / len(actual) * 100.0
    return {
        "n": len(actual),
        "train_n": len(discovery),
        "intercept": r6(intercept),
        "slope": r6(slope),
        "train_mean_return_pct": r6(train_mean),
        "oos_r2": r6(oos_r2),
        "model_rmse_pct": r6(rmse_model),
        "baseline_rmse_pct": r6(rmse_base),
        "rmse_improvement_pct": r6(rmse_improvement),
        "model_direction_accuracy_pct": r6(model_hits),
        "baseline_direction_accuracy_pct": r6(base_hits),
        "direction_lift_pp": r6(model_hits - base_hits),
    }


def quantile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    pos = (len(ordered) - 1) * p
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return ordered[lo]
    weight = pos - lo
    return ordered[lo] * (1 - weight) + ordered[hi] * weight


def holdout_tail_spread(discovery: list[tuple[dict[str, Any], float, float]], holdout: list[tuple[dict[str, Any], float, float]]) -> dict[str, Any]:
    if len(discovery) < 20 or not holdout:
        return {}
    train_x = [x for _, x, _ in discovery]
    q10 = quantile(train_x, 0.10)
    q90 = quantile(train_x, 0.90)
    if q10 is None or q90 is None:
        return {}
    lower = [y for _, x, y in holdout if x <= q10]
    upper = [y for _, x, y in holdout if x >= q90]
    lower_mean = statistics.mean(lower) if lower else None
    upper_mean = statistics.mean(upper) if upper else None
    return {
        "discovery_q10_cut": r6(q10),
        "discovery_q90_cut": r6(q90),
        "holdout_lower_n": len(lower),
        "holdout_upper_n": len(upper),
        "holdout_lower_mean_pct": r6(lower_mean),
        "holdout_upper_mean_pct": r6(upper_mean),
        "holdout_p90_minus_p10_spread_pp": r6(upper_mean - lower_mean) if lower_mean is not None and upper_mean is not None else None,
    }


def non_overlapping(rows: list[tuple[dict[str, Any], float, float]], horizon: str) -> list[tuple[dict[str, Any], float, float]]:
    chosen = []
    last_end = -1
    end_horizon = horizon if horizon in actor_research.FORWARD_HORIZONS else "1w"
    for event, x, y in sorted(rows, key=lambda row: int(row[0].get("signal_index") or -1)):
        signal_index = int(event.get("signal_index") or -1)
        end_index = int((((event.get("forward") or {}).get(end_horizon) or {}).get("end_index") or signal_index))
        if signal_index <= last_end:
            continue
        chosen.append((event, x, y))
        last_end = max(end_index, signal_index)
    return chosen


def era_blocks(rows: list[tuple[dict[str, Any], float, float]]) -> dict[str, Any]:
    out = {}
    for label, (start, end) in ERA_WINDOWS.items():
        subset = []
        for row in rows:
            d = parse_date(row[0].get("report_date"))
            if d is None or d < start or (end is not None and d > end):
                continue
            subset.append(row)
        out[label] = correlation_block(subset)
    return out


def predictive_metric(events: list[dict[str, Any]], predictor: str, horizon: str) -> dict[str, Any]:
    rows = aligned(events, predictor, horizon)
    discovery = [row for row in rows if (parse_date(row[0].get("report_date")) or date.max) < HOLDOUT_START]
    holdout = [row for row in rows if (parse_date(row[0].get("report_date")) or date.min) >= HOLDOUT_START]
    independent_holdout = non_overlapping(holdout, horizon)
    return {
        "full_history": correlation_block(rows),
        "discovery_pre_2022": correlation_block(discovery),
        "holdout_2022_plus": correlation_block(holdout),
        "holdout_non_overlapping": correlation_block(independent_holdout),
        "oos_forecast": oos_forecast(discovery, holdout),
        "holdout_tail_spread": holdout_tail_spread(discovery, holdout),
        "era_stability": era_blocks(rows),
    }


def classification(metric: dict[str, Any]) -> str:
    oos = metric.get("oos_forecast") or {}
    discovery = metric.get("discovery_pre_2022") or {}
    holdout = metric.get("holdout_2022_plus") or {}
    r2 = finite(oos.get("oos_r2"))
    rmse = finite(oos.get("rmse_improvement_pct"))
    d_rho = finite(discovery.get("spearman_rho"))
    h_rho = finite(holdout.get("spearman_rho"))
    n = int(holdout.get("n") or 0)
    if r2 is not None and r2 > 0 and rmse is not None and rmse > 0 and n >= 30 and d_rho is not None and h_rho is not None and abs(h_rho) >= 0.10 and d_rho * h_rho > 0:
        return "OOS_PREDICTIVE"
    if r2 is not None and r2 > 0 and rmse is not None and rmse > 0:
        return "POSITIVE_OOS_R2_BUT_WEAK_CORRELATION"
    return "NO_OOS_PREDICTIVE_GAIN"


def compact_row(key: str, predictor: str, horizon: str, metric: dict[str, Any]) -> dict[str, Any]:
    holdout = metric["holdout_2022_plus"]
    independent = metric["holdout_non_overlapping"]
    oos = metric["oos_forecast"]
    tails = metric["holdout_tail_spread"]
    return {
        "series": key,
        "predictor": predictor,
        "horizon": horizon,
        "classification": classification(metric),
        "holdout_n": holdout.get("n"),
        "holdout_pearson_r": holdout.get("pearson_r"),
        "holdout_spearman_rho": holdout.get("spearman_rho"),
        "independent_n": independent.get("n"),
        "independent_spearman_rho": independent.get("spearman_rho"),
        "oos_r2": oos.get("oos_r2"),
        "rmse_improvement_pct": oos.get("rmse_improvement_pct"),
        "direction_lift_pp": oos.get("direction_lift_pp"),
        "holdout_p90_minus_p10_spread_pp": tails.get("holdout_p90_minus_p10_spread_pp"),
    }


def main() -> None:
    cot_data, prices_payloads = actor_research.robustness.build_full_inputs()
    all_events: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for dataset in actor_research.DATASETS:
        dataset_payload = cot_data.get(dataset) or {}
        for market in actor_research.SUPPORTED_MARKETS:
            payload = dataset_payload.get(market)
            prices_payload = prices_payloads.get(market)
            if not isinstance(payload, dict) or prices_payload is None:
                continue
            built = actor_research.build_market_actor_events(market, dataset, payload, prices_payload)
            for actor, events in built.items():
                if events:
                    all_events[(dataset, market, actor)] = events

    study: dict[str, Any] = {}
    ranking = []
    for (dataset, market, actor), events in all_events.items():
        key = f"{dataset}:{market}:{actor}"
        block = {}
        for predictor in PREDICTORS:
            horizons = {}
            for horizon in HORIZONS:
                metric = predictive_metric(events, predictor, horizon)
                horizons[horizon] = metric
                ranking.append(compact_row(key, predictor, horizon, metric))
            block[predictor] = horizons
        study[key] = block

    ranking.sort(
        key=lambda row: (
            0 if row["classification"] == "OOS_PREDICTIVE" else (1 if row["classification"] == "POSITIVE_OOS_R2_BUT_WEAK_CORRELATION" else 2),
            -(finite(row.get("oos_r2")) or -999.0),
            -abs(finite(row.get("holdout_spearman_rho")) or 0.0),
        )
    )

    output = {
        "schema_version": 1,
        "study": "COT actor continuous predictive power and correlations",
        "information_contract": {
            "cot_snapshot": "Tuesday",
            "public_availability": "Friday = report date + 3 calendar days",
            "release_anchor": "first market close on/after Friday release target",
            "lookahead_safe": True,
            "percentiles": "expanding-history only at each report",
        },
        "forecast_contract": {
            "discovery": "pre-2022",
            "holdout": "2022+ untouched",
            "oos_model": "univariate OLS intercept/slope fit on discovery only; coefficients frozen in holdout",
            "oos_baseline": "constant discovery-period mean return for the same series/horizon",
            "tail_cutoffs": "discovery-period predictor q10/q90 frozen before holdout",
            "overlap_control": "greedy non-overlapping forward episodes; exact weekdays use the 1W end index",
        },
        "predictors": PREDICTORS,
        "horizons": list(HORIZONS),
        "series_count": len(all_events),
        "metric_count": len(ranking),
        "series": study,
        "ranking": ranking,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    summary = {
        "schema_version": 1,
        "study": output["study"],
        "information_contract": output["information_contract"],
        "forecast_contract": output["forecast_contract"],
        "predictors": PREDICTORS,
        "horizons": list(HORIZONS),
        "series_count": len(all_events),
        "metric_count": len(ranking),
        "oos_predictive_count": sum(row["classification"] == "OOS_PREDICTIVE" for row in ranking),
        "positive_oos_r2_weak_count": sum(row["classification"] == "POSITIVE_OOS_R2_BUT_WEAK_CORRELATION" for row in ranking),
        "top_metrics": ranking[:250],
        "top_1w": [row for row in ranking if row["horizon"] == "1w"][:100],
        "top_4w": [row for row in ranking if row["horizon"] == "4w"][:100],
        "top_13w": [row for row in ranking if row["horizon"] == "13w"][:100],
        "top_26w": [row for row in ranking if row["horizon"] == "26w"][:100],
    }
    SUMMARY_OUT.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print("COT ACTOR PREDICTIVE POWER BEGIN")
    print(f"series_count={len(all_events)} metric_count={len(ranking)}")
    print(f"oos_predictive={summary['oos_predictive_count']} positive_oos_r2_weak={summary['positive_oos_r2_weak_count']}")
    print("TOP 1W PREDICTIVE METRICS")
    for row in summary["top_1w"][:30]:
        print(
            f"{row['classification']:38s} {row['series']:40s} {row['predictor']:26s} "
            f"N={int(row.get('holdout_n') or 0):3d} r={float(row.get('holdout_pearson_r') or 0):+7.3f} "
            f"rho={float(row.get('holdout_spearman_rho') or 0):+7.3f} R2={float(row.get('oos_r2') or 0):+8.4f} "
            f"RMSEimp={float(row.get('rmse_improvement_pct') or 0):+7.2f}% lift={float(row.get('direction_lift_pp') or 0):+7.2f}pp "
            f"P90-P10={float(row.get('holdout_p90_minus_p10_spread_pp') or 0):+7.3f}pp"
        )
    print("COT ACTOR PREDICTIVE POWER END")
    print(f"Wrote {OUT}")
    print(f"Wrote {SUMMARY_OUT}")


if __name__ == "__main__":
    main()
