#!/usr/bin/env python3
"""Evaluate governed analog robustness without optimizing analog count.

The study reruns the current governed state across a fixed grid of analog counts
for all supported markets, preserving the canonical expanding-percentile score,
Friday release anchoring, momentum-aware analog distance, and full-history data.

It reports both the existing overlapping analog statistics and a transparent
non-overlapping episode view. Independent episodes are selected greedily in
similarity order: an analog is retained only when its realized forward price
window does not overlap any already-retained analog window for that horizon.
This is an explicit episode count, not an invented effective-N formula.

Output:
  analysis/worldclass/research/analog-robustness.json
"""
from __future__ import annotations

import json
import math
import statistics
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import build_worldclass_backtest as backtest
import build_worldclass_research_artifacts as research

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "worldclass" / "research" / "analog-robustness.json"
COUNTS = (15, 20, 30, 40, 60, 80, 120)
MARKET_DATASETS = {
    "sp500": "tff",
    "nq": "tff",
    "vix": "tff",
    "rty": "tff",
    "dow": "tff",
    "gold": "disaggregated",
    "silver": "disaggregated",
}


def finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def build_full_inputs() -> tuple[dict[str, Any], dict[str, Any]]:
    base = research.build_research_base()
    cot_data = base.get("COT_DATA") or {}
    prices = base.get("PRICE_DATA") or {}
    full_metals = research.ensure_full_metals()
    cot_data.setdefault("disaggregated", {}).update(full_metals.get("markets") or {})
    prices.update(full_metals.get("prices") or {})
    return cot_data, prices


def build_state(
    market: str,
    dataset: str,
    payload: dict[str, Any],
    prices_payload: Any,
) -> dict[str, Any]:
    rows = [
        row
        for row in (payload.get("records") or [])
        if isinstance(row, dict) and backtest.parse_date(row.get("date"))
    ]
    rows.sort(key=lambda row: str(row.get("date")))
    categories = list((payload.get("categories") or {}).keys())
    prices = backtest.price_records(prices_payload)
    if len(rows) < backtest.MIN_LOOKBACK_WEEKS or len(prices) < 200 or not categories:
        raise RuntimeError(f"Insufficient full-history inputs for {market}/{dataset}")

    score_rows: list[dict[str, Any]] = []
    scores: list[float | None] = [None] * len(rows)
    for index in range(len(rows)):
        if index + 1 < backtest.MIN_LOOKBACK_WEEKS:
            continue
        score = backtest.score_at(rows, index, dataset, categories)
        scores[index] = score
        report_date = backtest.parse_date(rows[index].get("date"))
        if score is None or report_date is None:
            continue
        release_target = report_date + timedelta(days=3)
        signal_index = backtest.first_price_index_on_or_after(prices, release_target)
        if signal_index is None:
            continue
        prior_index = max(backtest.MIN_LOOKBACK_WEEKS - 1, index - 4)
        prior_score = scores[prior_index]
        score_delta_4w = score - prior_score if prior_score is not None and prior_index != index else 0.0
        horizons: dict[str, Any] = {}
        for label, steps in backtest.HORIZONS.items():
            result = backtest.horizon_result(prices, signal_index, steps)
            if result is not None:
                horizons[label] = {
                    **result,
                    "end_index": signal_index + int(steps),
                }
        score_rows.append(
            {
                "report_date": report_date.isoformat(),
                "signal_date": prices[signal_index]["date_str"],
                "signal_index": signal_index,
                "score": score,
                "score_delta_4w": score_delta_4w,
                "horizons": horizons,
            }
        )

    if not score_rows:
        raise RuntimeError(f"No historical score rows for {market}/{dataset}")

    current_index = len(rows) - 1
    current_score = backtest.score_at(rows, current_index, dataset, categories)
    if current_score is None:
        raise RuntimeError(f"No current governed score for {market}/{dataset}")
    prior_index = max(backtest.MIN_LOOKBACK_WEEKS - 1, current_index - 4)
    prior_score = (
        backtest.score_at(rows, prior_index, dataset, categories)
        if prior_index != current_index
        else current_score
    )
    current_delta = current_score - prior_score if prior_score is not None else 0.0
    current_report_date = backtest.parse_date(rows[current_index].get("date"))

    return {
        "rows": rows,
        "prices": prices,
        "score_rows": score_rows,
        "current_report_date": current_report_date.isoformat() if current_report_date else str(rows[current_index].get("date") or ""),
        "current_score": current_score,
        "current_delta": current_delta,
    }


def rank_analogs(state: dict[str, Any], horizon: str) -> tuple[list[tuple[float, dict[str, Any]]], float | None]:
    realized = [
        row
        for row in state["score_rows"]
        if horizon in row["horizons"] and row["report_date"] != state["current_report_date"]
    ]
    unconditional_values = [row["horizons"][horizon]["return_pct"] for row in realized]
    unconditional = statistics.mean(unconditional_values) if unconditional_values else None
    ranked: list[tuple[float, dict[str, Any]]] = []
    for row in realized:
        distance = abs(row["score"] - state["current_score"]) + backtest.ANALOG_MOMENTUM_WEIGHT * abs(
            row["score_delta_4w"] - state["current_delta"]
        )
        ranked.append((distance, row))
    ranked.sort(key=lambda item: (item[0], item[1]["report_date"]))
    return ranked, unconditional


def metrics(
    analogs: list[tuple[float, dict[str, Any]]],
    horizon: str,
    unconditional: float | None,
) -> dict[str, Any]:
    returns = [row["horizons"][horizon]["return_pct"] for _, row in analogs]
    drawdowns = [row["horizons"][horizon]["drawdown_pct"] for _, row in analogs]
    distances = [distance for distance, _ in analogs]
    weights = [1.0 / (1.0 + distance) for distance in distances]
    expected = backtest.weighted_mean(returns, weights)
    median = statistics.median(returns) if returns else None
    q25 = backtest.quantile(returns, 0.25)
    q75 = backtest.quantile(returns, 0.75)
    avg_distance = statistics.mean(distances) if distances else None
    return {
        "observations": len(returns),
        "expected_return_pct": round(expected, 4) if expected is not None else None,
        "median_return_pct": round(median, 4) if median is not None else None,
        "hit_rate_pct": round(sum(1 for value in returns if value > 0) / len(returns) * 100.0, 2) if returns else None,
        "edge_vs_unconditional_pct": round(expected - unconditional, 4) if expected is not None and unconditional is not None else None,
        "unconditional_return_pct": round(unconditional, 4) if unconditional is not None else None,
        "q25_return_pct": round(q25, 4) if q25 is not None else None,
        "q75_return_pct": round(q75, 4) if q75 is not None else None,
        "avg_drawdown_pct": round(statistics.mean(drawdowns), 4) if drawdowns else None,
        "worst_drawdown_pct": round(min(drawdowns), 4) if drawdowns else None,
        "avg_analog_distance": round(avg_distance, 3) if avg_distance is not None else None,
    }


def select_non_overlapping(
    analogs: list[tuple[float, dict[str, Any]]],
    horizon: str,
) -> list[tuple[float, dict[str, Any]]]:
    selected: list[tuple[float, dict[str, Any]]] = []
    occupied: list[tuple[int, int]] = []
    for distance, row in analogs:
        start_index = int(row["signal_index"])
        end_index = int(row["horizons"][horizon]["end_index"])
        if any(not (end_index < start or start_index > end) for start, end in occupied):
            continue
        selected.append((distance, row))
        occupied.append((start_index, end_index))
    return selected


def stability_summary(rows_by_count: dict[str, Any], metric_path: tuple[str, str]) -> dict[str, Any]:
    edges: list[float] = []
    for count in COUNTS:
        row = rows_by_count[str(count)]
        branch, key = metric_path
        value = finite(row[branch].get(key))
        if value is not None:
            edges.append(value)
    positive = sum(1 for value in edges if value > 0)
    tested = len(edges)
    positive_fraction = positive / tested if tested else 0.0
    median_edge = statistics.median(edges) if edges else None
    if tested >= 4 and positive_fraction >= 0.8 and median_edge is not None and median_edge > 0:
        classification = "ROBUST"
    elif tested >= 3 and positive_fraction >= 0.5 and median_edge is not None and median_edge > 0:
        classification = "MIXED"
    else:
        classification = "FRAGILE"
    return {
        "classification": classification,
        "classification_scope": "analog-count edge-sign stability only; not statistical significance or causal confidence",
        "positive_edge_counts": positive,
        "tested_counts": tested,
        "positive_edge_fraction": round(positive_fraction, 4),
        "median_edge_pct": round(median_edge, 4) if median_edge is not None else None,
    }


def build_market_result(
    market: str,
    dataset: str,
    payload: dict[str, Any],
    prices_payload: Any,
) -> dict[str, Any]:
    state = build_state(market, dataset, payload, prices_payload)
    horizons: dict[str, Any] = {}
    for horizon in backtest.HORIZONS:
        ranked, unconditional = rank_analogs(state, horizon)
        rows_by_count: dict[str, Any] = {}
        for count in COUNTS:
            raw = ranked[: min(count, len(ranked))]
            independent = select_non_overlapping(raw, horizon)
            raw_metrics = metrics(raw, horizon, unconditional)
            independent_metrics = metrics(independent, horizon, unconditional)
            rows_by_count[str(count)] = {
                "raw_overlapping": raw_metrics,
                "non_overlapping": {
                    **independent_metrics,
                    "independent_episode_count": len(independent),
                    "episode_report_dates": [row["report_date"] for _, row in independent],
                    "selection_rule": "greedy similarity-order selection; realized forward price windows may not overlap",
                },
            }
        horizons[horizon] = {
            "counts": rows_by_count,
            "raw_parameter_stability": stability_summary(rows_by_count, ("raw_overlapping", "edge_vs_unconditional_pct")),
            "non_overlapping_parameter_stability": stability_summary(rows_by_count, ("non_overlapping", "edge_vs_unconditional_pct")),
        }

    return {
        "market": market,
        "market_label": backtest.MARKET_LABELS.get(market, market),
        "dataset": dataset,
        "current": {
            "report_date": state["current_report_date"],
            "score": round(state["current_score"], 3),
            "score_delta_4w": round(state["current_delta"], 3),
        },
        "historical_signal_count": len(state["score_rows"]),
        "horizons": horizons,
    }


def main() -> None:
    cot_data, prices = build_full_inputs()
    result: dict[str, Any] = {
        "schema_version": 1,
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "study": "governed analog-count and overlapping-window robustness",
        "model_version": backtest.MODEL_VERSION,
        "model_spec_hash": backtest.MODEL_SPEC_HASH,
        "governed_analog_count": backtest.ANALOG_COUNT,
        "tested_analog_counts": list(COUNTS),
        "methodology": {
            "lookahead_safe_score": True,
            "release_anchor": "first available close on/after Tuesday report date + 3 calendar days",
            "analog_distance": f"abs(score-current) + {backtest.ANALOG_MOMENTUM_WEIGHT:g}*abs(4w score momentum-current)",
            "purpose": "robustness diagnosis only; tested N values are not optimized or promoted automatically",
            "overlap_correction": "non-overlapping realized forward price windows selected greedily in similarity order",
            "independent_episode_note": "reported episode counts are explicit non-overlapping selections, not an effective-N formula",
        },
        "markets": {},
    }

    for market, dataset in MARKET_DATASETS.items():
        payload = ((cot_data.get(dataset) or {}).get(market))
        if not isinstance(payload, dict):
            raise RuntimeError(f"Missing full-history {dataset} payload for {market}")
        price_payload = prices.get(market)
        if price_payload is None:
            raise RuntimeError(f"Missing full-history prices for {market}")
        result["markets"][market] = build_market_result(market, dataset, payload, price_payload)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")

    print("ANALOG_ROBUSTNESS_BEGIN")
    print(
        f"model={backtest.MODEL_VERSION} governed_N={backtest.ANALOG_COUNT} "
        f"tested={','.join(str(value) for value in COUNTS)}"
    )
    for market, market_result in result["markets"].items():
        current = market_result["current"]
        print(
            f"{market.upper()} {market_result['dataset']} report={current['report_date']} "
            f"score={current['score']:.3f} delta4w={current['score_delta_4w']:+.3f} "
            f"history={market_result['historical_signal_count']}"
        )
        for horizon, horizon_result in market_result["horizons"].items():
            raw_stability = horizon_result["raw_parameter_stability"]
            nonoverlap_stability = horizon_result["non_overlapping_parameter_stability"]
            governed = horizon_result["counts"][str(backtest.ANALOG_COUNT)]
            raw = governed["raw_overlapping"]
            independent = governed["non_overlapping"]
            print(
                f"  {horizon:>3} raw={raw_stability['classification']} "
                f"{raw_stability['positive_edge_counts']}/{raw_stability['tested_counts']} positive; "
                f"N40 edge={raw['edge_vs_unconditional_pct']:+.4f}% exp={raw['expected_return_pct']:+.4f}% | "
                f"episodes={independent['independent_episode_count']} "
                f"edge={independent['edge_vs_unconditional_pct']:+.4f}% "
                f"stability={nonoverlap_stability['classification']}"
            )
    print("ANALOG_ROBUSTNESS_END")
    print(f"Saved {OUT}")


if __name__ == "__main__":
    main()
