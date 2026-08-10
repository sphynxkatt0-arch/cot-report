#!/usr/bin/env python3
"""Full COT actor-event, cross-instrument, and cumulative-horizon research engine.

Research-only. The Tuesday COT snapshot becomes eligible only after Friday
(report date + 3 calendar days). All actor level/change percentiles are expanding
history transforms. Threshold discovery is pre-2022; 2022+ is untouched holdout.

Outputs:
  analysis/worldclass/research/cot-actor-event-research.json
"""
from __future__ import annotations

import itertools
import json
import math
import random
import statistics
from bisect import bisect_left
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import build_worldclass_backtest as backtest
import evaluate_analog_robustness as robustness

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "worldclass" / "research" / "cot-actor-event-research.json"

SUPPORTED_MARKETS = ("sp500", "nq", "vix", "rty", "dow", "gold", "silver")
FINANCIAL_MARKETS = ("sp500", "nq", "rty", "dow", "vix")
EQUITY_MARKETS = ("sp500", "nq", "rty", "dow")
METAL_MARKETS = ("gold", "silver")
DATASETS = ("tff", "legacy", "disaggregated")
ACTORS = {
    "tff": {
        "dealer": "Dealer / Intermediary",
        "asset_mgr": "Asset Manager / Institutional",
        "lev_money": "Leveraged Funds",
        "other_reportable": "Other Reportables",
        "non_reportable": "Non-Reportables",
    },
    "legacy": {
        "noncommercial": "Non-Commercial",
        "commercial": "Commercial",
        "total_reportable": "Total Reportable",
        "nonreportable": "Non-Reportable",
    },
    "disaggregated": {
        "producer_merchant": "Producer / Merchant / Processor / User",
        "swap_dealer": "Swap Dealer",
        "managed_money": "Managed Money",
        "other_reportable": "Other Reportables",
        "non_reportable": "Non-Reportables",
    },
}
THRESHOLDS = (60, 65, 70, 75, 80, 85, 90)
HOLDOUT_START = date(2022, 1, 1)
ERA_WINDOWS = {
    "2016_2019": (date(2016, 1, 1), date(2019, 12, 31)),
    "2020_2022": (date(2020, 1, 1), date(2022, 12, 31)),
    "2023_plus": (date(2023, 1, 1), None),
}
EXACT_WEEKDAYS = {
    "monday": 6,
    "tuesday": 7,
    "wednesday": 8,
    "thursday": 9,
    "friday": 10,
}
FORWARD_HORIZONS = {
    "1w": 5,
    "2w": 10,
    "3w": 15,
    "4w": 20,
    "6w": 30,
    "8w": 40,
    "13w": 65,
    "26w": 130,
    "39w": 195,
    "52w": 260,
}
PRIMARY_THRESHOLD_HORIZON = "1w"
COMBINATION_THRESHOLD = 75
MIN_DISCOVERY_N = 20
MIN_HOLDOUT_N = 10
MIN_COMBINATION_N = 8


def finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def parse_date(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value or "")[:10])
    except ValueError:
        return None


def percentile_rank(values: list[float], current: float) -> float | None:
    clean = sorted(v for v in values if math.isfinite(v))
    if not clean:
        return None
    left = bisect_left(clean, current)
    equal = sum(1 for v in clean if v == current)
    return (left + max(equal, 1) / 2.0) / len(clean) * 100.0


def q(values: list[float], p: float) -> float | None:
    if not values:
        return None
    return backtest.quantile(values, p)


def r4(value: float | None) -> float | None:
    return round(value, 4) if value is not None and math.isfinite(value) else None


def magnitude_bucket(percentile: float | None) -> str | None:
    if percentile is None:
        return None
    if percentile < 50:
        return "SMALL"
    if percentile < 75:
        return "MEDIUM"
    if percentile < 90:
        return "LARGE"
    return "EXTREME"


def position_bucket(percentile: float | None) -> str | None:
    if percentile is None:
        return None
    if percentile <= 10:
        return "EXTREME_SHORT"
    if percentile <= 25:
        return "SHORT"
    if percentile < 75:
        return "NEUTRAL"
    if percentile < 90:
        return "LONG"
    return "EXTREME_LONG"


def signal_direction(delta: float | None) -> str:
    if delta is None or abs(delta) <= 1e-12:
        return "FLAT"
    return "ADD" if delta > 0 else "CUT"


def action_type(delta_long: float | None, delta_short: float | None, delta_net: float) -> str:
    if delta_long is None or delta_short is None:
        return "NET_ADD" if delta_net > 0 else ("NET_CUT" if delta_net < 0 else "FLAT")
    if delta_long > 0 and delta_short < 0:
        return "LONG_ADD_SHORT_COVER"
    if delta_long < 0 and delta_short > 0:
        return "LONG_LIQUIDATE_SHORT_ADD"
    if delta_long > 0 and delta_short >= 0:
        return "BOTH_SIDES_ADD_LONG_DOMINANT" if delta_net > 0 else "BOTH_SIDES_ADD_SHORT_DOMINANT"
    if delta_long <= 0 and delta_short < 0:
        return "BOTH_SIDES_CUT_SHORT_DOMINANT" if delta_net > 0 else "BOTH_SIDES_CUT_LONG_DOMINANT"
    if delta_long > 0:
        return "LONG_ADD"
    if delta_long < 0:
        return "LONG_LIQUIDATE"
    if delta_short > 0:
        return "SHORT_ADD"
    if delta_short < 0:
        return "SHORT_COVER"
    return "FLAT"


def actor_side_value(row: dict[str, Any], actor: str, side: str) -> float | None:
    candidates = (
        f"{actor}_{side}",
        f"{actor}_{side}_all",
        f"{actor}_{side}_contracts",
    )
    for key in candidates:
        value = finite(row.get(key))
        if value is not None:
            return value
    return None


def actor_net_value(row: dict[str, Any], actor: str) -> float | None:
    value = finite(row.get(f"{actor}_net"))
    if value is not None:
        return value
    long_value = actor_side_value(row, actor, "long")
    short_value = actor_side_value(row, actor, "short")
    if long_value is not None and short_value is not None:
        return long_value - short_value
    return None


def exact_cumulative_path(
    report_date: date,
    prices: list[dict[str, Any]],
    price_index_by_date: dict[date, int],
    signal_index: int,
) -> dict[str, float]:
    """Friday signal close -> exact next-week weekday close; missing day breaks chain."""
    path: dict[str, float] = {}
    if signal_index < 0 or signal_index >= len(prices):
        return path
    start_price = finite(prices[signal_index].get("price"))
    if start_price in (None, 0):
        return path
    for weekday, offset in EXACT_WEEKDAYS.items():
        target = report_date + timedelta(days=offset)
        idx = price_index_by_date.get(target)
        if idx is None or idx <= signal_index:
            break
        end_price = finite(prices[idx].get("price"))
        if end_price is None:
            break
        path[weekday] = (end_price / start_price - 1.0) * 100.0
    return path


def forward_results(prices: list[dict[str, Any]], signal_index: int) -> dict[str, dict[str, Any]]:
    output: dict[str, dict[str, Any]] = {}
    for label, steps in FORWARD_HORIZONS.items():
        result = backtest.horizon_result(prices, signal_index, steps)
        if result is not None:
            output[label] = {
                "return_pct": finite(result.get("return_pct")),
                "drawdown_pct": finite(result.get("drawdown_pct")),
                "end_index": signal_index + int(steps),
            }
    return output


def build_market_actor_events(
    market: str,
    dataset: str,
    payload: dict[str, Any],
    prices_payload: Any,
) -> dict[str, list[dict[str, Any]]]:
    rows = [
        row for row in (payload.get("records") or [])
        if isinstance(row, dict) and parse_date(row.get("date"))
    ]
    rows.sort(key=lambda row: str(row.get("date")))
    prices = backtest.price_records(prices_payload)
    if len(rows) < backtest.MIN_LOOKBACK_WEEKS or len(prices) < 200:
        return {}

    price_index_by_date = {row["date"]: idx for idx, row in enumerate(prices)}
    actors = ACTORS[dataset]
    events: dict[str, list[dict[str, Any]]] = {actor: [] for actor in actors}
    histories: dict[str, dict[str, list[float]]] = {
        actor: {"level": [], "magnitude": []} for actor in actors
    }

    for i, row in enumerate(rows):
        if i == 0:
            continue
        report_date = parse_date(row.get("date"))
        prev = rows[i - 1]
        if report_date is None:
            continue
        release_target = report_date + timedelta(days=3)
        signal_index = backtest.first_price_index_on_or_after(prices, release_target)
        if signal_index is None:
            continue

        for actor, label in actors.items():
            level = finite(row.get(f"{actor}_net_oi_pct"))
            previous_level = finite(prev.get(f"{actor}_net_oi_pct"))
            if level is None or previous_level is None:
                continue
            delta = level - previous_level
            histories[actor]["level"].append(level)
            histories[actor]["magnitude"].append(abs(delta))
            if i + 1 < backtest.MIN_LOOKBACK_WEEKS:
                continue

            level_pct = percentile_rank(histories[actor]["level"], level)
            mag_pct = percentile_rank(histories[actor]["magnitude"], abs(delta))
            long_now = actor_side_value(row, actor, "long")
            long_prev = actor_side_value(prev, actor, "long")
            short_now = actor_side_value(row, actor, "short")
            short_prev = actor_side_value(prev, actor, "short")
            d_long = long_now - long_prev if long_now is not None and long_prev is not None else None
            d_short = short_now - short_prev if short_now is not None and short_prev is not None else None
            net_now = actor_net_value(row, actor)
            net_prev = actor_net_value(prev, actor)
            d_net_contracts = net_now - net_prev if net_now is not None and net_prev is not None else None

            multiweek = {}
            for weeks in (2, 4, 8, 13):
                if i >= weeks:
                    old = finite(rows[i - weeks].get(f"{actor}_net_oi_pct"))
                    multiweek[f"delta_{weeks}w_net_oi_pp"] = r4(level - old) if old is not None else None
                else:
                    multiweek[f"delta_{weeks}w_net_oi_pp"] = None

            event = {
                "market": market,
                "dataset": dataset,
                "actor": actor,
                "actor_label": label,
                "report_date": report_date.isoformat(),
                "release_date": release_target.isoformat(),
                "signal_date": str(prices[signal_index].get("date_str") or prices[signal_index].get("date")),
                "signal_index": signal_index,
                "net_oi_pct": r4(level),
                "position_percentile": r4(level_pct),
                "position_bucket": position_bucket(level_pct),
                "delta_1w_net_oi_pp": r4(delta),
                "delta_net_contracts": r4(d_net_contracts),
                "delta_long_contracts": r4(d_long),
                "delta_short_contracts": r4(d_short),
                "direction": signal_direction(delta),
                "action_type": action_type(d_long, d_short, delta),
                "magnitude_percentile": r4(mag_pct),
                "magnitude_bucket": magnitude_bucket(mag_pct),
                "weekday_cumulative": {
                    k: r4(v)
                    for k, v in exact_cumulative_path(report_date, prices, price_index_by_date, signal_index).items()
                },
                "forward": {
                    h: {
                        "return_pct": r4(v.get("return_pct")),
                        "drawdown_pct": r4(v.get("drawdown_pct")),
                        "end_index": v.get("end_index"),
                    }
                    for h, v in forward_results(prices, signal_index).items()
                },
                **multiweek,
            }
            events[actor].append(event)
    return events


def summarize_values(values: list[float], drawdowns: list[float] | None = None) -> dict[str, Any]:
    clean = [float(v) for v in values if v is not None and math.isfinite(float(v))]
    if not clean:
        return {"n": 0}
    row = {
        "n": len(clean),
        "mean_pct": r4(statistics.mean(clean)),
        "median_pct": r4(statistics.median(clean)),
        "positive_rate_pct": r4(sum(v > 0 for v in clean) / len(clean) * 100.0),
        "negative_rate_pct": r4(sum(v < 0 for v in clean) / len(clean) * 100.0),
        "q10_pct": r4(q(clean, 0.10)),
        "q25_pct": r4(q(clean, 0.25)),
        "q75_pct": r4(q(clean, 0.75)),
        "q90_pct": r4(q(clean, 0.90)),
        "stddev_pct": r4(statistics.pstdev(clean)) if len(clean) >= 2 else 0.0,
        "prob_gt_1_pct": r4(sum(v > 1 for v in clean) / len(clean) * 100.0),
        "prob_lt_m1_pct": r4(sum(v < -1 for v in clean) / len(clean) * 100.0),
        "prob_gt_2_pct": r4(sum(v > 2 for v in clean) / len(clean) * 100.0),
        "prob_lt_m2_pct": r4(sum(v < -2 for v in clean) / len(clean) * 100.0),
        "prob_gt_5_pct": r4(sum(v > 5 for v in clean) / len(clean) * 100.0),
        "prob_lt_m5_pct": r4(sum(v < -5 for v in clean) / len(clean) * 100.0),
    }
    dd = [float(v) for v in (drawdowns or []) if v is not None and math.isfinite(float(v))]
    if dd:
        row["avg_drawdown_pct"] = r4(statistics.mean(dd))
        row["worst_drawdown_pct"] = r4(min(dd))
    return row


def event_return(event: dict[str, Any], horizon: str) -> float | None:
    if horizon in EXACT_WEEKDAYS:
        return finite((event.get("weekday_cumulative") or {}).get(horizon))
    return finite(((event.get("forward") or {}).get(horizon) or {}).get("return_pct"))


def event_drawdown(event: dict[str, Any], horizon: str) -> float | None:
    if horizon in EXACT_WEEKDAYS:
        return None
    return finite(((event.get("forward") or {}).get(horizon) or {}).get("drawdown_pct"))


def baseline_for_events(events: list[dict[str, Any]], horizon: str, start: date | None = None, end: date | None = None) -> float | None:
    vals = []
    for event in events:
        d = parse_date(event["report_date"])
        if d is None or (start and d < start) or (end and d > end):
            continue
        value = event_return(event, horizon)
        if value is not None:
            vals.append(value)
    return statistics.mean(vals) if vals else None


def filter_segment(events: list[dict[str, Any]], start: date | None = None, end: date | None = None) -> list[dict[str, Any]]:
    out = []
    for event in events:
        d = parse_date(event["report_date"])
        if d is None:
            continue
        if start is not None and d < start:
            continue
        if end is not None and d > end:
            continue
        out.append(event)
    return out


def metrics_for_condition(
    condition: list[dict[str, Any]],
    universe: list[dict[str, Any]],
    horizon: str,
    segment_start: date | None = None,
    segment_end: date | None = None,
) -> dict[str, Any]:
    selected = filter_segment(condition, segment_start, segment_end)
    values = []
    dds = []
    for event in selected:
        value = event_return(event, horizon)
        if value is None:
            continue
        values.append(value)
        dd = event_drawdown(event, horizon)
        if dd is not None:
            dds.append(dd)
    summary = summarize_values(values, dds)
    base = baseline_for_events(universe, horizon, segment_start, segment_end)
    summary["unconditional_mean_pct"] = r4(base)
    summary["edge_vs_unconditional_pct"] = r4(
        statistics.mean(values) - base if values and base is not None else None
    )
    return summary


def all_horizon_metrics(
    condition: list[dict[str, Any]],
    universe: list[dict[str, Any]],
    segment_start: date | None = None,
    segment_end: date | None = None,
) -> dict[str, Any]:
    horizons = list(EXACT_WEEKDAYS) + list(FORWARD_HORIZONS)
    return {
        horizon: metrics_for_condition(condition, universe, horizon, segment_start, segment_end)
        for horizon in horizons
    }


def events_at_threshold(events: list[dict[str, Any]], direction: str, threshold: int) -> list[dict[str, Any]]:
    return [
        e for e in events
        if e.get("direction") == direction
        and finite(e.get("magnitude_percentile")) is not None
        and float(e["magnitude_percentile"]) >= threshold
    ]


def threshold_grid(events: list[dict[str, Any]], direction: str) -> dict[str, Any]:
    out = {}
    for threshold in THRESHOLDS:
        cond = events_at_threshold(events, direction, threshold)
        out[str(threshold)] = {
            "discovery_pre_2022": all_horizon_metrics(cond, events, None, HOLDOUT_START - timedelta(days=1)),
            "holdout_2022_plus": all_horizon_metrics(cond, events, HOLDOUT_START, None),
            "full_history": all_horizon_metrics(cond, events),
        }
    return out


def stable_discovery_threshold(grid: dict[str, Any]) -> int | None:
    """Lowest threshold with adequate N and a three-cutoff same-sign 1W neighborhood."""
    thresholds = list(THRESHOLDS)
    for i, threshold in enumerate(thresholds):
        if i + 2 >= len(thresholds):
            break
        neighborhood = thresholds[i:i + 3]
        rows = [grid[str(t)]["discovery_pre_2022"][PRIMARY_THRESHOLD_HORIZON] for t in neighborhood]
        if rows[0].get("n", 0) < MIN_DISCOVERY_N:
            continue
        valid = [row for row in rows if row.get("n", 0) >= 10 and row.get("edge_vs_unconditional_pct") is not None]
        if len(valid) < 3:
            continue
        signs = [1 if row["edge_vs_unconditional_pct"] > 0 else -1 if row["edge_vs_unconditional_pct"] < 0 else 0 for row in valid]
        if 0 in signs or len(set(signs)) != 1:
            continue
        if sum(abs(float(row["edge_vs_unconditional_pct"])) >= 0.10 for row in valid) < 2:
            continue
        return threshold
    return None


def holdout_verdict(grid: dict[str, Any], threshold: int | None) -> dict[str, Any]:
    if threshold is None:
        return {"classification": "NO_STABLE_DISCOVERY_THRESHOLD"}
    train = grid[str(threshold)]["discovery_pre_2022"][PRIMARY_THRESHOLD_HORIZON]
    hold = grid[str(threshold)]["holdout_2022_plus"][PRIMARY_THRESHOLD_HORIZON]
    train_edge = finite(train.get("edge_vs_unconditional_pct"))
    hold_edge = finite(hold.get("edge_vs_unconditional_pct"))
    same_sign = train_edge is not None and hold_edge is not None and train_edge * hold_edge > 0
    enough = int(hold.get("n") or 0) >= MIN_HOLDOUT_N
    magnitude = hold_edge is not None and abs(hold_edge) >= 0.10
    neighbor_signs = []
    for t in THRESHOLDS:
        if t < threshold or t > threshold + 10:
            continue
        row = grid[str(t)]["holdout_2022_plus"][PRIMARY_THRESHOLD_HORIZON]
        edge = finite(row.get("edge_vs_unconditional_pct"))
        if int(row.get("n") or 0) >= 5 and edge is not None:
            neighbor_signs.append(1 if edge > 0 else -1 if edge < 0 else 0)
    target_sign = 1 if (train_edge or 0) > 0 else -1
    neighbor_ok = sum(s == target_sign for s in neighbor_signs) >= min(2, len(neighbor_signs)) if neighbor_signs else False
    classification = "OOS_SUPPORTED" if same_sign and enough and magnitude and neighbor_ok else "FAILED_HOLDOUT"
    return {
        "classification": classification,
        "threshold": threshold,
        "discovery_edge_1w_pct": r4(train_edge),
        "holdout_edge_1w_pct": r4(hold_edge),
        "holdout_n_1w": hold.get("n", 0),
        "same_sign": same_sign,
        "neighbor_sign_consistency": neighbor_ok,
    }


def era_metrics(condition: list[dict[str, Any]], universe: list[dict[str, Any]]) -> dict[str, Any]:
    out = {}
    for era, (start, end) in ERA_WINDOWS.items():
        out[era] = {
            horizon: metrics_for_condition(condition, universe, horizon, start, end)
            for horizon in ("1w", "4w", "13w", "26w")
        }
    return out


def non_overlapping_metrics(
    condition: list[dict[str, Any]],
    universe: list[dict[str, Any]],
    horizon: str,
) -> dict[str, Any]:
    if horizon in EXACT_WEEKDAYS:
        return {"n": 0, "note": "independence selection only applied to trading-step horizons"}
    selected = []
    last_end = -1
    for event in sorted(condition, key=lambda e: (e.get("signal_index", -1), e["report_date"])):
        info = ((event.get("forward") or {}).get(horizon) or {})
        start = int(event.get("signal_index") or -1)
        end = info.get("end_index")
        value = finite(info.get("return_pct"))
        if start < 0 or end is None or value is None:
            continue
        end = int(end)
        if start <= last_end:
            continue
        selected.append(event)
        last_end = end
    row = metrics_for_condition(selected, universe, horizon)
    row["independent_episode_count"] = row.get("n", 0)
    return row


def bootstrap_edge_ci(
    condition: list[dict[str, Any]],
    universe: list[dict[str, Any]],
    horizon: str,
    iterations: int = 400,
) -> dict[str, Any]:
    cond_vals = [event_return(e, horizon) for e in condition]
    cond_vals = [float(v) for v in cond_vals if v is not None]
    base_vals = [event_return(e, horizon) for e in universe]
    base_vals = [float(v) for v in base_vals if v is not None]
    if len(cond_vals) < 10 or len(base_vals) < 30:
        return {"iterations": 0, "low_pct": None, "high_pct": None}
    rng = random.Random(20260810 + len(cond_vals) + len(base_vals))
    diffs = []
    for _ in range(iterations):
        c = [cond_vals[rng.randrange(len(cond_vals))] for _ in range(len(cond_vals))]
        b = [base_vals[rng.randrange(len(base_vals))] for _ in range(len(base_vals))]
        diffs.append(statistics.mean(c) - statistics.mean(b))
    diffs.sort()
    return {
        "iterations": iterations,
        "low_pct": r4(q(diffs, 0.025)),
        "high_pct": r4(q(diffs, 0.975)),
    }


def dose_response(events: list[dict[str, Any]], direction: str) -> dict[str, Any]:
    out = {}
    for bucket in ("SMALL", "MEDIUM", "LARGE", "EXTREME"):
        cond = [e for e in events if e.get("direction") == direction and e.get("magnitude_bucket") == bucket]
        out[bucket] = all_horizon_metrics(cond, events)
    return out


def position_interaction(events: list[dict[str, Any]], direction: str, threshold: int) -> dict[str, Any]:
    out = {}
    for bucket in ("EXTREME_SHORT", "SHORT", "NEUTRAL", "LONG", "EXTREME_LONG"):
        cond = [
            e for e in events_at_threshold(events, direction, threshold)
            if e.get("position_bucket") == bucket
        ]
        out[bucket] = {
            horizon: metrics_for_condition(cond, events, horizon)
            for horizon in ("1w", "2w", "4w", "13w", "26w")
        }
    return out


def individual_actor_study(events: list[dict[str, Any]]) -> dict[str, Any]:
    result = {}
    for direction in ("ADD", "CUT"):
        grid = threshold_grid(events, direction)
        selected = stable_discovery_threshold(grid)
        verdict = holdout_verdict(grid, selected)
        selected_events = events_at_threshold(events, direction, selected) if selected is not None else []
        result[direction] = {
            "threshold_grid": grid,
            "selected_threshold": selected,
            "holdout_validation": verdict,
            "dose_response_full_history": dose_response(events, direction),
            "position_level_interaction": position_interaction(events, direction, selected or 75),
            "era_stability_at_selected": era_metrics(selected_events, events) if selected is not None else {},
            "non_overlapping_at_selected": {
                h: non_overlapping_metrics(selected_events, events, h)
                for h in ("1w", "2w", "3w", "4w", "8w", "13w", "26w", "52w")
            } if selected is not None else {},
            "bootstrap_edge_ci_at_selected": {
                h: bootstrap_edge_ci(selected_events, events, h)
                for h in ("1w", "4w", "13w")
            } if selected is not None else {},
        }
    return result


def combination_metrics(
    rows: list[dict[str, Any]],
    target_universe: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "full_history": {
            h: metrics_for_condition(rows, target_universe, h)
            for h in ("monday", "tuesday", "wednesday", "thursday", "friday", "1w", "2w", "3w", "4w", "8w", "13w", "26w", "52w")
        },
        "holdout_2022_plus": {
            h: metrics_for_condition(rows, target_universe, h, HOLDOUT_START, None)
            for h in ("1w", "2w", "3w", "4w", "8w", "13w", "26w", "52w")
        },
    }


def event_index(all_events: dict[tuple[str, str, str], list[dict[str, Any]]]) -> dict[tuple[str, str, str, str], dict[str, Any]]:
    idx = {}
    for (dataset, market, actor), events in all_events.items():
        for event in events:
            idx[(dataset, market, actor, event["report_date"])] = event
    return idx


def same_actor_pairwise(all_events: dict[tuple[str, str, str], list[dict[str, Any]]]) -> dict[str, Any]:
    out = {}
    for dataset, actors in ACTORS.items():
        markets = [m for m in SUPPORTED_MARKETS if any((dataset, m, a) in all_events for a in actors)]
        for actor in actors:
            available = [m for m in markets if (dataset, m, actor) in all_events]
            for a, b in itertools.combinations(available, 2):
                a_events = all_events[(dataset, a, actor)]
                b_by_date = {e["report_date"]: e for e in all_events[(dataset, b, actor)]}
                configurations = defaultdict(list)
                for ea in a_events:
                    eb = b_by_date.get(ea["report_date"])
                    if not eb:
                        continue
                    if min(finite(ea.get("magnitude_percentile")) or 0, finite(eb.get("magnitude_percentile")) or 0) < COMBINATION_THRESHOLD:
                        continue
                    da, db = ea.get("direction"), eb.get("direction")
                    if da not in ("ADD", "CUT") or db not in ("ADD", "CUT"):
                        continue
                    configurations[f"{da}_{db}"].append((ea, eb))
                pair_key = f"{dataset}:{actor}:{a}:{b}"
                pair_result = {}
                for config, pairs in configurations.items():
                    a_rows = [x[0] for x in pairs]
                    b_rows = [x[1] for x in pairs]
                    pair_result[config] = {
                        "joint_n": len(pairs),
                        "target_" + a: combination_metrics(a_rows, a_events),
                        "target_" + b: combination_metrics(b_rows, all_events[(dataset, b, actor)]),
                    }
                if pair_result:
                    out[pair_key] = pair_result
    return out


def breadth_study(all_events: dict[tuple[str, str, str], list[dict[str, Any]]]) -> dict[str, Any]:
    out = {}
    for dataset in ("tff", "legacy"):
        for actor in ACTORS[dataset]:
            by_date: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
            for market in FINANCIAL_MARKETS:
                for event in all_events.get((dataset, market, actor), []):
                    by_date[event["report_date"]][market] = event
            if not by_date:
                continue
            actor_result = defaultdict(lambda: defaultdict(list))
            for report_date, market_events in by_date.items():
                oriented = {}
                for market, event in market_events.items():
                    delta = finite(event.get("delta_1w_net_oi_pp"))
                    mag = finite(event.get("magnitude_percentile"))
                    if delta is None or mag is None or mag < COMBINATION_THRESHOLD:
                        continue
                    raw_sign = 1 if delta > 0 else -1 if delta < 0 else 0
                    oriented[market] = -raw_sign if market == "vix" else raw_sign
                if len(oriented) < 2:
                    continue
                risk_on = sum(v > 0 for v in oriented.values())
                risk_off = sum(v < 0 for v in oriented.values())
                orientation = "RISK_ON" if risk_on > risk_off else "RISK_OFF" if risk_off > risk_on else "MIXED"
                aligned = max(risk_on, risk_off)
                bucket = f"{orientation}_{aligned}of{len(oriented)}"
                for target_market in EQUITY_MARKETS:
                    event = market_events.get(target_market)
                    if event:
                        actor_result[bucket][target_market].append(event)
            rendered = {}
            for bucket, target_map in actor_result.items():
                rendered[bucket] = {}
                for target, rows in target_map.items():
                    universe = all_events.get((dataset, target, actor), [])
                    rendered[bucket][target] = combination_metrics(rows, universe)
            if rendered:
                out[f"{dataset}:{actor}"] = rendered
    return out


def cross_actor_same_market(all_events: dict[tuple[str, str, str], list[dict[str, Any]]]) -> dict[str, Any]:
    out = {}
    for dataset, actors in ACTORS.items():
        for market in SUPPORTED_MARKETS:
            available = [a for a in actors if (dataset, market, a) in all_events]
            if len(available) < 2:
                continue
            for actor_a, actor_b in itertools.combinations(available, 2):
                a_events = all_events[(dataset, market, actor_a)]
                b_by_date = {e["report_date"]: e for e in all_events[(dataset, market, actor_b)]}
                configs = defaultdict(list)
                for ea in a_events:
                    eb = b_by_date.get(ea["report_date"])
                    if not eb:
                        continue
                    if min(finite(ea.get("magnitude_percentile")) or 0, finite(eb.get("magnitude_percentile")) or 0) < COMBINATION_THRESHOLD:
                        continue
                    da, db = ea.get("direction"), eb.get("direction")
                    if da in ("ADD", "CUT") and db in ("ADD", "CUT"):
                        configs[f"{da}_{db}"].append(ea)
                rendered = {}
                for config, rows in configs.items():
                    if len(rows) >= 1:
                        rendered[config] = combination_metrics(rows, a_events)
                if rendered:
                    out[f"{dataset}:{market}:{actor_a}:{actor_b}"] = rendered
    return out


def cross_taxonomy(all_events: dict[tuple[str, str, str], list[dict[str, Any]]]) -> dict[str, Any]:
    out = {}
    for market in FINANCIAL_MARKETS:
        tff_actors = [a for a in ACTORS["tff"] if ("tff", market, a) in all_events]
        leg_actors = [a for a in ACTORS["legacy"] if ("legacy", market, a) in all_events]
        for ta in tff_actors:
            t_events = all_events[("tff", market, ta)]
            for la in leg_actors:
                l_by_date = {e["report_date"]: e for e in all_events[("legacy", market, la)]}
                configs = defaultdict(list)
                for te in t_events:
                    le = l_by_date.get(te["report_date"])
                    if not le:
                        continue
                    if min(finite(te.get("magnitude_percentile")) or 0, finite(le.get("magnitude_percentile")) or 0) < COMBINATION_THRESHOLD:
                        continue
                    if te.get("direction") in ("ADD", "CUT") and le.get("direction") in ("ADD", "CUT"):
                        configs[f"{te['direction']}_{le['direction']}"].append(te)
                rendered = {
                    cfg: combination_metrics(rows, t_events)
                    for cfg, rows in configs.items()
                }
                if rendered:
                    out[f"{market}:tff_{ta}:legacy_{la}"] = rendered
    return out


def lead_market_study(all_events: dict[tuple[str, str, str], list[dict[str, Any]]]) -> dict[str, Any]:
    out = {}
    for dataset, actors in ACTORS.items():
        market_group = FINANCIAL_MARKETS if dataset in ("tff", "legacy") else METAL_MARKETS
        for actor in actors:
            sources = [m for m in market_group if (dataset, m, actor) in all_events]
            for source in sources:
                source_events = all_events[(dataset, source, actor)]
                for direction in ("ADD", "CUT"):
                    source_cond = events_at_threshold(source_events, direction, COMBINATION_THRESHOLD)
                    if not source_cond:
                        continue
                    source_dates = {e["report_date"] for e in source_cond}
                    for target in sources:
                        if target == source:
                            continue
                        target_events = all_events[(dataset, target, actor)]
                        rows = [e for e in target_events if e["report_date"] in source_dates]
                        key = f"{dataset}:{actor}:{source}_{direction}_P{COMBINATION_THRESHOLD}->{target}"
                        out[key] = combination_metrics(rows, target_events)
    return out


def cross_sectional_rank_study(all_events: dict[tuple[str, str, str], list[dict[str, Any]]]) -> dict[str, Any]:
    """Does cross-market actor shock rank line up with next-1W return rank?"""
    out = {}
    for actor in ACTORS["tff"]:
        by_date = defaultdict(dict)
        for market in EQUITY_MARKETS:
            for event in all_events.get(("tff", market, actor), []):
                by_date[event["report_date"]][market] = event
        weekly_corrs = []
        weeks = 0
        for _, events in by_date.items():
            rows = []
            for market, event in events.items():
                delta = finite(event.get("delta_1w_net_oi_pp"))
                ret = event_return(event, "1w")
                if delta is not None and ret is not None:
                    rows.append((market, delta, ret))
            if len(rows) < 3:
                continue
            weeks += 1
            ds = [r[1] for r in rows]
            rs = [r[2] for r in rows]
            md, mr = statistics.mean(ds), statistics.mean(rs)
            cov = sum((d-md)*(r-mr) for d, r in zip(ds, rs))
            den = math.sqrt(sum((d-md)**2 for d in ds) * sum((r-mr)**2 for r in rs))
            if den > 1e-12:
                weekly_corrs.append(cov / den)
        out[actor] = {
            "weeks_with_3plus_equity_markets": weeks,
            "weeks_with_defined_cross_sectional_correlation": len(weekly_corrs),
            "mean_weekly_cross_sectional_corr_delta_vs_1w_return": r4(statistics.mean(weekly_corrs)) if weekly_corrs else None,
            "median_weekly_cross_sectional_corr_delta_vs_1w_return": r4(statistics.median(weekly_corrs)) if weekly_corrs else None,
        }
    return out


def current_state(all_events: dict[tuple[str, str, str], list[dict[str, Any]]], individual: dict[str, Any]) -> dict[str, Any]:
    out = {}
    for key, events in all_events.items():
        if not events:
            continue
        dataset, market, actor = key
        latest = max(events, key=lambda e: e["report_date"])
        study_key = f"{dataset}:{market}:{actor}"
        actor_study = individual.get(study_key, {})
        out[study_key] = {
            "report_date_tuesday": latest["report_date"],
            "release_date_friday": latest["release_date"],
            "direction": latest.get("direction"),
            "action_type": latest.get("action_type"),
            "delta_1w_net_oi_pp": latest.get("delta_1w_net_oi_pp"),
            "magnitude_percentile": latest.get("magnitude_percentile"),
            "magnitude_bucket": latest.get("magnitude_bucket"),
            "position_percentile": latest.get("position_percentile"),
            "position_bucket": latest.get("position_bucket"),
            "research_thresholds": {
                d: {
                    "selected_threshold": actor_study.get(d, {}).get("selected_threshold"),
                    "holdout_classification": actor_study.get(d, {}).get("holdout_validation", {}).get("classification"),
                }
                for d in ("ADD", "CUT")
            },
        }
    return out


def compact_validated_summary(individual: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for key, actor_result in individual.items():
        for direction in ("ADD", "CUT"):
            result = actor_result.get(direction, {})
            verdict = result.get("holdout_validation", {})
            threshold = result.get("selected_threshold")
            if threshold is None:
                continue
            grid = result.get("threshold_grid", {})
            hold = (((grid.get(str(threshold)) or {}).get("holdout_2022_plus") or {}).get("1w") or {})
            rows.append({
                "signal": f"{key}:{direction}",
                "threshold": threshold,
                "classification": verdict.get("classification"),
                "holdout_n_1w": hold.get("n", 0),
                "holdout_edge_1w_pct": hold.get("edge_vs_unconditional_pct"),
                "holdout_mean_1w_pct": hold.get("mean_pct"),
            })
    rows.sort(key=lambda r: (
        0 if r["classification"] == "OOS_SUPPORTED" else 1,
        -(abs(float(r["holdout_edge_1w_pct"])) if r["holdout_edge_1w_pct"] is not None else 0),
    ))
    return rows


def main() -> None:
    cot_data, prices_payloads = robustness.build_full_inputs()
    all_events: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    coverage = {}
    discovered_pairs = []

    for dataset in DATASETS:
        dataset_payload = cot_data.get(dataset) or {}
        for market in SUPPORTED_MARKETS:
            payload = dataset_payload.get(market)
            prices_payload = prices_payloads.get(market)
            if not isinstance(payload, dict) or prices_payload is None:
                continue
            built = build_market_actor_events(market, dataset, payload, prices_payload)
            if not built:
                continue
            discovered_pairs.append(f"{dataset}:{market}")
            pair_cov = {"record_count": len(payload.get("records") or []), "actors": {}}
            for actor, events in built.items():
                if not events:
                    continue
                all_events[(dataset, market, actor)] = events
                pair_cov["actors"][actor] = {
                    "event_count": len(events),
                    "latest_report_date": events[-1]["report_date"],
                    "complete_exact_weekday_count": sum(len(e.get("weekday_cumulative") or {}) == 5 for e in events),
                    "forward_52w_count": sum("52w" in (e.get("forward") or {}) for e in events),
                }
            coverage[f"{dataset}:{market}"] = pair_cov

    individual = {}
    for (dataset, market, actor), events in all_events.items():
        individual[f"{dataset}:{market}:{actor}"] = individual_actor_study(events)

    pairwise = same_actor_pairwise(all_events)
    breadth = breadth_study(all_events)
    cross_actor = cross_actor_same_market(all_events)
    taxonomy = cross_taxonomy(all_events)
    lead = lead_market_study(all_events)
    cross_sectional = cross_sectional_rank_study(all_events)
    summary = compact_validated_summary(individual)

    hypothesis_counts = {
        "individual_actor_direction_threshold_candidates": len(all_events) * 2 * len(THRESHOLDS),
        "same_actor_cross_instrument_pair_keys": len(pairwise),
        "breadth_actor_keys": len(breadth),
        "cross_actor_same_market_pair_keys": len(cross_actor),
        "cross_taxonomy_pair_keys": len(taxonomy),
        "lead_market_signal_target_keys": len(lead),
    }

    output = {
        "schema_version": 1,
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "study": "full cross-actor cross-instrument COT event research",
        "information_contract": {
            "cot_snapshot": "Tuesday",
            "public_availability": "Friday = report date + 3 calendar days",
            "release_anchor": "first market close on/after Friday release target",
            "exact_weekday_rule": "exact next-week Monday-Friday; a missing exact weekday breaks the cumulative weekday path and is never relabeled",
            "lookahead_safe": True,
            "percentiles": "expanding-history only at each report",
        },
        "governance": {
            "threshold_grid": list(THRESHOLDS),
            "threshold_selection": "lowest pre-2022 threshold with a three-cutoff same-sign 1W neighborhood; never best-return optimization",
            "discovery_segment": "pre-2022",
            "holdout_segment": "2022+",
            "combination_threshold": COMBINATION_THRESHOLD,
            "combination_policy": "cross-market/cross-actor combinations require both component actor changes >= P75 magnitude; results remain research-only",
            "horizons": {**{d: "exact weekday cumulative from release anchor" for d in EXACT_WEEKDAYS}, **FORWARD_HORIZONS},
            "production_changes": False,
            "multiple_testing_registry": hypothesis_counts,
        },
        "markets": list(SUPPORTED_MARKETS),
        "dataset_actor_taxonomy": ACTORS,
        "coverage": coverage,
        "discovered_dataset_market_pairs": discovered_pairs,
        "individual_actor_thresholds": individual,
        "same_actor_cross_instrument": pairwise,
        "cross_instrument_breadth": breadth,
        "cross_actor_same_instrument": cross_actor,
        "cross_report_taxonomy": taxonomy,
        "lead_market_effects": lead,
        "cross_sectional_rank_test": cross_sectional,
        "current_state": current_state(all_events, individual),
        "validated_signal_summary": summary,
        "evidence_labels": {
            "OOS_SUPPORTED": "discovery threshold retains direction and minimum effect/sample in untouched 2022+ holdout; not causal proof",
            "FAILED_HOLDOUT": "stable discovery pattern did not satisfy the frozen holdout rule",
            "NO_STABLE_DISCOVERY_THRESHOLD": "no threshold family passed the predeclared discovery stability rule",
            "INSUFFICIENT": f"combination samples below {MIN_COMBINATION_N} are descriptive only",
        },
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print("FULL COT ACTOR EVENT RESEARCH BEGIN")
    print(f"dataset_market_pairs={len(discovered_pairs)} actor_market_series={len(all_events)}")
    print(f"threshold_hypotheses={hypothesis_counts['individual_actor_direction_threshold_candidates']}")
    print(
        "combination_keys "
        f"same_actor={len(pairwise)} breadth={len(breadth)} cross_actor={len(cross_actor)} "
        f"cross_taxonomy={len(taxonomy)} lead={len(lead)}"
    )
    print("TOP OOS / DISCOVERY SIGNALS BY ABS HOLDOUT 1W EDGE")
    for row in summary[:40]:
        print(
            f"{row['classification']:28s} {row['signal']:55s} "
            f"P{row['threshold']:02d} N={int(row['holdout_n_1w'] or 0):3d} "
            f"edge={float(row['holdout_edge_1w_pct'] or 0):+7.3f}% "
            f"mean={float(row['holdout_mean_1w_pct'] or 0):+7.3f}%"
        )
    print("FULL COT ACTOR EVENT RESEARCH END")
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
