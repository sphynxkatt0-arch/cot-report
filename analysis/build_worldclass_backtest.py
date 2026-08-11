#!/usr/bin/env python3
"""Build release-corrected walk-forward COT backtests and forward expectancy.

Historical scores use expanding-window percentiles. Outcomes are anchored to
CFTC public availability through the canonical release calendar; no study may
assume report_date + 3 calendar days is universally valid.
"""
from __future__ import annotations

import json
import math
import statistics
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import model_spec as model_cfg
from cftc_release_calendar import calendar_hash, release_record
from cot_research_core import finite, horizon_result as core_horizon_result, parse_date, percentile_rank, price_records, release_aligned_entry

ROOT = Path(__file__).resolve().parent
WORLDCLASS = ROOT / "worldclass"
BASE = WORLDCLASS / "base.json"
METALS = WORLDCLASS / "metals.json"
OUT = WORLDCLASS / "backtest.json"

MODEL_SPEC = model_cfg.load_model_spec()
MODEL_VERSION = str(MODEL_SPEC["model_version"])
MODEL_SPEC_HASH = model_cfg.model_spec_hash(MODEL_SPEC)
MIN_LOOKBACK_WEEKS = int(MODEL_SPEC["lookback"]["minimum_weeks"])
ANALOG_COUNT = int(MODEL_SPEC["analogs"]["count"])
ANALOG_DISPLAY_COUNT = int(MODEL_SPEC["analogs"]["display_count"])
ANALOG_MOMENTUM_WEIGHT = float(MODEL_SPEC["analogs"]["momentum_weight"])
HORIZONS = model_cfg.horizons(MODEL_SPEC)
SCORE_WEIGHTS = model_cfg.score_weights(MODEL_SPEC)

MARKET_LABELS = {
    "sp500": "S&P 500", "nq": "Nasdaq-100", "vix": "VIX Futures",
    "rty": "Russell 2000", "dow": "Dow Jones", "gold": "Gold", "silver": "Silver",
}


def score_at(rows: list[dict[str, Any]], index: int, dataset: str, categories: list[str]) -> float | None:
    weights = SCORE_WEIGHTS.get(dataset, {})
    numerator = 0.0
    denominator = 0.0
    for key in categories:
        weight = float(weights.get(key, 0.0))
        if weight == 0:
            continue
        field = f"{key}_net_oi_pct"
        current = finite(rows[index].get(field))
        if current is None:
            continue
        history = [finite(row.get(field)) for row in rows[: index + 1]]
        rank = percentile_rank([v for v in history if v is not None], current)
        if rank is None:
            continue
        centered = (rank - 50.0) / 50.0
        numerator += weight * centered
        denominator += abs(weight)
    if denominator == 0:
        return None
    return max(0.0, min(100.0, 50.0 + 50.0 * numerator / denominator))


def horizon_result(prices: list[dict[str, Any]], start_index: int, steps: int) -> dict[str, float] | None:
    result = core_horizon_result(prices, start_index, steps)
    if result is None:
        return None
    return {
        "return_pct": float(result["return_pct"]),
        "drawdown_pct": float(result["max_adverse_excursion_pct"]),
        "max_favorable_excursion_pct": float(result["max_favorable_excursion_pct"]),
        "exit_date": str(result["exit_date"]),
        "exit_price": float(result["exit_price"]),
    }


def quantile(values: list[float], q: float) -> float | None:
    clean = sorted(value for value in values if math.isfinite(value))
    if not clean:
        return None
    if len(clean) == 1:
        return clean[0]
    position = (len(clean) - 1) * q
    low = math.floor(position)
    high = math.ceil(position)
    if low == high:
        return clean[low]
    fraction = position - low
    return clean[low] * (1 - fraction) + clean[high] * fraction


def weighted_mean(values: list[float], weights: list[float]) -> float | None:
    if not values or not weights or len(values) != len(weights):
        return None
    total_weight = sum(weights)
    return None if total_weight <= 0 else sum(v * w for v, w in zip(values, weights)) / total_weight


def confidence_label(n: int, avg_distance: float | None, dispersion: float | None) -> str:
    if n < 15:
        return "Low"
    distance = avg_distance if avg_distance is not None else 99.0
    spread = dispersion if dispersion is not None else 99.0
    if n >= 35 and distance <= 7.5 and spread <= 12:
        return "High"
    if n >= 25 and distance <= 12 and spread <= 18:
        return "Medium"
    return "Low"


def independent_count(rows: list[dict[str, Any]], horizon_steps: int) -> int:
    selected = 0
    last_end = -1
    for row in sorted(rows, key=lambda r: int(r["signal_index"])):
        start = int(row["signal_index"])
        if start > last_end:
            selected += 1
            last_end = start + horizon_steps
    return selected


def build_dataset_backtest(market: str, dataset: str, payload: dict[str, Any], prices_payload: Any) -> dict[str, Any] | None:
    rows = [row for row in (payload.get("records") or []) if isinstance(row, dict) and parse_date(row.get("date"))]
    rows.sort(key=lambda row: str(row.get("date")))
    categories = list((payload.get("categories") or {}).keys())
    prices = price_records(prices_payload)
    if len(rows) < MIN_LOOKBACK_WEEKS or len(prices) < 200 or not categories:
        return None

    score_rows: list[dict[str, Any]] = []
    scores: list[float | None] = [None] * len(rows)
    for index in range(len(rows)):
        if index + 1 < MIN_LOOKBACK_WEEKS:
            continue
        score = score_at(rows, index, dataset, categories)
        scores[index] = score
        report_date = parse_date(rows[index].get("date"))
        if score is None or report_date is None:
            continue
        entry = release_aligned_entry(prices, report_date)
        if entry is None:
            continue
        signal_index = int(entry["index"])
        prior_index = max(MIN_LOOKBACK_WEEKS - 1, index - 4)
        prior_score = scores[prior_index]
        score_delta_4w = score - prior_score if prior_score is not None and prior_index != index else 0.0
        horizons: dict[str, Any] = {}
        for label, steps in HORIZONS.items():
            result = horizon_result(prices, signal_index, steps)
            if result is not None:
                horizons[label] = result
        score_rows.append({
            "report_date": report_date.isoformat(),
            "availability_at": entry["availability_at"],
            "availability_source": entry["availability_source"],
            "availability_confidence": entry["availability_confidence"],
            "release_calendar_version": entry["release_calendar_version"],
            "release_calendar_hash": entry["release_calendar_hash"],
            "release_target_date": release_record(report_date)["actual_release_date"],
            "signal_date": entry["entry_date"],
            "signal_price": entry["entry_price"],
            "signal_index": signal_index,
            "score": score,
            "score_delta_4w": score_delta_4w,
            "horizons": horizons,
        })

    if not score_rows:
        return None

    current_index = len(rows) - 1
    current_score = score_at(rows, current_index, dataset, categories)
    if current_score is None:
        return None
    prior_index = max(MIN_LOOKBACK_WEEKS - 1, current_index - 4)
    current_prior_score = score_at(rows, prior_index, dataset, categories) if prior_index != current_index else current_score
    current_delta = current_score - current_prior_score if current_prior_score is not None else 0.0
    current_report_date = parse_date(rows[current_index].get("date"))

    summaries: dict[str, Any] = {}
    for horizon, steps in HORIZONS.items():
        realized = [row for row in score_rows if horizon in row["horizons"] and row["report_date"] != rows[current_index].get("date")]
        unconditional_returns = [row["horizons"][horizon]["return_pct"] for row in realized]
        ranked: list[tuple[float, dict[str, Any]]] = []
        for row in realized:
            distance = abs(row["score"] - current_score) + ANALOG_MOMENTUM_WEIGHT * abs(row["score_delta_4w"] - current_delta)
            ranked.append((distance, row))
        ranked.sort(key=lambda item: (item[0], item[1]["report_date"]))
        analogs = ranked[: min(ANALOG_COUNT, len(ranked))]
        returns = [row["horizons"][horizon]["return_pct"] for _, row in analogs]
        drawdowns = [row["horizons"][horizon]["drawdown_pct"] for _, row in analogs]
        distances = [distance for distance, _ in analogs]
        weights = [1.0 / (1.0 + distance) for distance in distances]
        expected = weighted_mean(returns, weights)
        median = statistics.median(returns) if returns else None
        q25 = quantile(returns, 0.25)
        q75 = quantile(returns, 0.75)
        dispersion = statistics.pstdev(returns) if len(returns) >= 2 else None
        avg_distance = statistics.mean(distances) if distances else None
        unconditional = statistics.mean(unconditional_returns) if unconditional_returns else None
        summaries[horizon] = {
            "expected_return_pct": round(expected, 4) if expected is not None else None,
            "median_return_pct": round(median, 4) if median is not None else None,
            "hit_rate_pct": round(sum(1 for value in returns if value > 0) / len(returns) * 100.0, 2) if returns else None,
            "q25_return_pct": round(q25, 4) if q25 is not None else None,
            "q75_return_pct": round(q75, 4) if q75 is not None else None,
            "avg_drawdown_pct": round(statistics.mean(drawdowns), 4) if drawdowns else None,
            "worst_drawdown_pct": round(min(drawdowns), 4) if drawdowns else None,
            "unconditional_return_pct": round(unconditional, 4) if unconditional is not None else None,
            "edge_vs_unconditional_pct": round(expected - unconditional, 4) if expected is not None and unconditional is not None else None,
            "observations": len(returns),
            "independent_observations": independent_count([row for _, row in analogs], steps),
            "avg_analog_distance": round(avg_distance, 3) if avg_distance is not None else None,
            "confidence": confidence_label(len(returns), avg_distance, dispersion),
        }

    complete_analogs: list[tuple[float, dict[str, Any]]] = []
    for row in score_rows:
        if row["report_date"] == rows[current_index].get("date"):
            continue
        distance = abs(row["score"] - current_score) + ANALOG_MOMENTUM_WEIGHT * abs(row["score_delta_4w"] - current_delta)
        complete_analogs.append((distance, row))
    complete_analogs.sort(key=lambda item: (item[0], item[1]["report_date"]))
    analog_display = [{
        "report_date": row["report_date"], "availability_at": row["availability_at"],
        "signal_date": row["signal_date"], "score": round(row["score"], 2),
        "score_delta_4w": round(row["score_delta_4w"], 2), "distance": round(distance, 3),
        "returns": {h: round(result["return_pct"], 3) for h, result in row["horizons"].items()},
    } for distance, row in complete_analogs[:ANALOG_DISPLAY_COUNT]]

    current_release = release_record(current_report_date) if current_report_date else None
    return {
        "market": market,
        "market_label": MARKET_LABELS.get(market, market),
        "dataset": dataset,
        "dataset_label": payload.get("label") or dataset,
        "score_model": "Worldclass 0-100 expanding-percentile COT score",
        "model_version": MODEL_VERSION,
        "model_spec_hash": MODEL_SPEC_HASH,
        "methodology": {
            "minimum_lookback_weeks": MIN_LOOKBACK_WEEKS,
            "release_anchor": "First available daily close on/after canonical CFTC public availability",
            "release_calendar_aware": True,
            "release_calendar_hash": calendar_hash(),
            "analog_count": ANALOG_COUNT,
            "analog_distance": f"abs(score-current) + {ANALOG_MOMENTUM_WEIGHT:g}*abs(4w score momentum-current)",
            "lookahead_safe": True,
        },
        "current": {
            "report_date": current_report_date.isoformat() if current_report_date else str(rows[current_index].get("date") or ""),
            "release_target_date": current_release["actual_release_date"] if current_release else None,
            "availability_at": current_release["availability_at_utc"] if current_release else None,
            "availability_source": current_release["availability_source_type"] if current_release else None,
            "score": round(current_score, 3),
            "score_delta_4w": round(current_delta, 3),
        },
        "historical_signal_count": len(score_rows),
        "horizons": summaries,
        "closest_analogs": analog_display,
    }


def build() -> dict[str, Any]:
    if not BASE.exists():
        raise FileNotFoundError(f"Missing {BASE}; run build_worldclass_bundle.py first")
    base = json.loads(BASE.read_text(encoding="utf-8"))
    cot_data = base.get("COT_DATA") or {}
    prices = base.get("PRICE_DATA") or {}
    if METALS.exists():
        metals = json.loads(METALS.read_text(encoding="utf-8"))
        cot_data.setdefault("disaggregated", {}).update(metals.get("markets") or {})
        prices.update(metals.get("prices") or {})

    result: dict[str, Any] = {
        "schema_version": 3,
        "research_generation": "release-corrected-v2",
        "information_contract_version": "cftc-public-availability-v2",
        "release_calendar_hash": calendar_hash(),
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "model_version": MODEL_VERSION,
        "model_spec_hash": MODEL_SPEC_HASH,
        "markets": {},
    }
    for dataset, markets in cot_data.items():
        if dataset not in SCORE_WEIGHTS or not isinstance(markets, dict):
            continue
        for market, payload in markets.items():
            if not isinstance(payload, dict):
                continue
            built = build_dataset_backtest(market, dataset, payload, prices.get(market))
            if built is None:
                continue
            result["markets"].setdefault(market, {"label": MARKET_LABELS.get(market, market), "datasets": {}})
            result["markets"][market]["datasets"][dataset] = built
            print(f"Backtest {market}/{dataset}: {built['historical_signal_count']} release-corrected signals")
    if not result["markets"]:
        raise RuntimeError("No worldclass backtests could be built")
    return result


def main() -> None:
    WORLDCLASS.mkdir(parents=True, exist_ok=True)
    payload = build()
    temporary = OUT.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    temporary.replace(OUT)
    print(f"Saved {OUT} ({OUT.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
