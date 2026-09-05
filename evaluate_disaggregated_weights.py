#!/usr/bin/env python3
"""Evaluate Disaggregated COT actor weights for Gold and Silver.

This is a research-only study. It must consume the persistent full-history
Gold/Silver research payload, which contains complete normalized COT history and
daily prices. The compact browser runtime is intentionally invalid for this
study because governed horizon steps are expressed in trading days.

The study uses the same lookahead-safe expanding percentile transform and Friday
release anchoring as the production COT backtest, then compares a Managed-Money-
only baseline with secondary-actor variants. It never mutates production model
weights.

Output:
  analysis/worldclass/metal-weight-study.json
"""
from __future__ import annotations

import json
import math
import statistics
from bisect import bisect_left
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import model_spec as model_cfg

ROOT = Path(__file__).resolve().parent
RESEARCH_SOURCE = "worldclass/research/metals-full.json"
METALS = ROOT / RESEARCH_SOURCE
OUT = ROOT / "worldclass" / "metal-weight-study.json"
MODEL_SPEC = model_cfg.load_model_spec()
MODEL_SPEC_HASH = model_cfg.model_spec_hash(MODEL_SPEC)
MODEL_VERSION = str(MODEL_SPEC["model_version"])
MIN_LOOKBACK_WEEKS = int(MODEL_SPEC["lookback"]["minimum_weeks"])
HORIZONS = model_cfg.horizons(MODEL_SPEC)
HOLDOUT_START = date(2022, 1, 1)
TRAIN_END = HOLDOUT_START - timedelta(days=1)
MIN_FULL_HISTORY_COT_ROWS = 500
MIN_DAILY_TO_WEEKLY_RATIO = 3.0

ZERO = {
    "producer_merchant": 0.0,
    "swap_dealer": 0.0,
    "managed_money": 0.0,
    "other_reportable": 0.0,
    "non_reportable": 0.0,
}

VARIANTS: dict[str, dict[str, float]] = {
    "managed_money_only": {**ZERO, "managed_money": 1.0},
    "mm_plus_producer": {**ZERO, "managed_money": 1.0, "producer_merchant": -0.75},
    "mm_plus_swap": {**ZERO, "managed_money": 1.0, "swap_dealer": -0.35},
    "mm_plus_other": {**ZERO, "managed_money": 1.0, "other_reportable": -0.75},
    "mm_plus_nonreportable": {**ZERO, "managed_money": 1.0, "non_reportable": -0.75},
    "v1_1_blend": {
        "producer_merchant": -0.75,
        "swap_dealer": -0.35,
        "managed_money": 1.25,
        "other_reportable": -0.75,
        "non_reportable": -0.75,
    },
}

SECONDARY_VARIANTS = {
    "producer_merchant": "mm_plus_producer",
    "swap_dealer": "mm_plus_swap",
    "other_reportable": "mm_plus_other",
    "non_reportable": "mm_plus_nonreportable",
}


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
    clean = sorted(value for value in values if math.isfinite(value))
    if not clean:
        return None
    less = bisect_left(clean, current)
    equal = sum(1 for value in clean if value == current)
    return (less + max(equal, 1) / 2.0) / len(clean) * 100.0


def score_at(rows: list[dict[str, Any]], index: int, weights: dict[str, float]) -> float | None:
    numerator = 0.0
    denominator = 0.0
    for key, weight_value in weights.items():
        weight = float(weight_value)
        if weight == 0:
            continue
        field = f"{key}_net_oi_pct"
        current = finite(rows[index].get(field))
        if current is None:
            continue
        history = [finite(row.get(field)) for row in rows[: index + 1]]
        clean = [value for value in history if value is not None]
        rank = percentile_rank(clean, current)
        if rank is None:
            continue
        centered = (rank - 50.0) / 50.0
        numerator += weight * centered
        denominator += abs(weight)
    if denominator == 0:
        return None
    return max(0.0, min(100.0, 50.0 + 50.0 * numerator / denominator))


def price_records(payload: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for row in payload.get("records") or []:
        d = parse_date(row.get("date")) if isinstance(row, dict) else None
        p = finite(row.get("price")) if isinstance(row, dict) else None
        if d is not None and p is not None:
            out.append({"date": d, "price": p})
    out.sort(key=lambda row: row["date"])
    return out


def first_price_index_on_or_after(prices: list[dict[str, Any]], target: date) -> int | None:
    dates = [row["date"] for row in prices]
    index = bisect_left(dates, target)
    return index if index < len(prices) else None


def pearson(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 3 or len(xs) != len(ys):
        return None
    mx = statistics.mean(xs)
    my = statistics.mean(ys)
    dx = [x - mx for x in xs]
    dy = [y - my for y in ys]
    denom = math.sqrt(sum(v * v for v in dx) * sum(v * v for v in dy))
    if denom == 0:
        return None
    return sum(a * b for a, b in zip(dx, dy)) / denom


def period_bounds(items: list[tuple[date, float, float]]) -> tuple[str | None, str | None]:
    if not items:
        return None, None
    return items[0][0].isoformat(), items[-1][0].isoformat()


def horizon_metrics(
    signals: list[dict[str, Any]],
    horizon: str,
    segment_start: date | None = None,
    segment_end: date | None = None,
) -> dict[str, Any]:
    usable: list[tuple[date, float, float]] = []
    for signal in signals:
        report_date = signal["report_date"]
        if segment_start is not None and report_date < segment_start:
            continue
        if segment_end is not None and report_date > segment_end:
            continue
        value = signal["returns"].get(horizon)
        if value is not None:
            usable.append((report_date, signal["score"], value))
    usable.sort(key=lambda item: item[0])
    period_start, period_end = period_bounds(usable)
    if len(usable) < 10:
        return {
            "n": len(usable),
            "period_start": period_start,
            "period_end": period_end,
            "pearson_r": None,
            "extreme_spread_pct": None,
        }
    scored_returns = [(score, value) for _, score, value in usable]
    scores = [item[0] for item in scored_returns]
    returns = [item[1] for item in scored_returns]
    ranked = sorted(scored_returns, key=lambda item: item[0])
    bucket = max(1, len(ranked) // 5)
    bottom = [ret for _, ret in ranked[:bucket]]
    top = [ret for _, ret in ranked[-bucket:]]
    spread = statistics.mean(top) - statistics.mean(bottom)
    corr = pearson(scores, returns)
    return {
        "n": len(usable),
        "period_start": period_start,
        "period_end": period_end,
        "pearson_r": round(corr, 6) if corr is not None else None,
        "extreme_spread_pct": round(spread, 6),
        "top_quintile_return_pct": round(statistics.mean(top), 6),
        "bottom_quintile_return_pct": round(statistics.mean(bottom), 6),
        "unconditional_return_pct": round(statistics.mean(returns), 6),
    }


def build_signals(rows: list[dict[str, Any]], price_payload: dict[str, Any], weights: dict[str, float]) -> list[dict[str, Any]]:
    rows = [row for row in rows if isinstance(row, dict) and parse_date(row.get("date"))]
    rows.sort(key=lambda row: str(row.get("date")))
    prices = price_records(price_payload)
    signals: list[dict[str, Any]] = []
    for index in range(len(rows)):
        if index + 1 < MIN_LOOKBACK_WEEKS:
            continue
        report_date = parse_date(rows[index].get("date"))
        score = score_at(rows, index, weights)
        if report_date is None or score is None:
            continue
        start_index = first_price_index_on_or_after(prices, report_date + timedelta(days=3))
        if start_index is None:
            continue
        start_price = prices[start_index]["price"]
        returns: dict[str, float | None] = {}
        for horizon, steps in HORIZONS.items():
            end_index = start_index + int(steps)
            if end_index >= len(prices) or start_price == 0:
                returns[horizon] = None
            else:
                returns[horizon] = (prices[end_index]["price"] / start_price - 1.0) * 100.0
        signals.append({"report_date": report_date, "score": score, "returns": returns})
    return signals


def market_source_period(payload: dict[str, Any], market: str) -> dict[str, Any]:
    market_payload = payload["markets"][market]
    cot_rows = [row for row in market_payload.get("records") or [] if isinstance(row, dict) and parse_date(row.get("date"))]
    prices = price_records(payload["prices"][market])
    cot_dates = sorted(parse_date(row.get("date")) for row in cot_rows if parse_date(row.get("date")) is not None)
    return {
        "cot_rows": len(cot_rows),
        "cot_start": cot_dates[0].isoformat() if cot_dates else None,
        "cot_end": cot_dates[-1].isoformat() if cot_dates else None,
        "daily_price_rows": len(prices),
        "price_start": prices[0]["date"].isoformat() if prices else None,
        "price_end": prices[-1]["date"].isoformat() if prices else None,
    }


def validate_research_payload(payload: dict[str, Any]) -> dict[str, Any]:
    contract = payload.get("research_contract")
    if not isinstance(contract, dict):
        raise RuntimeError(f"{RESEARCH_SOURCE}: missing research_contract")
    if contract.get("full_history") is not True:
        raise RuntimeError(f"{RESEARCH_SOURCE}: research_contract.full_history must be true")
    if contract.get("daily_price_history") is not True:
        raise RuntimeError(f"{RESEARCH_SOURCE}: research_contract.daily_price_history must be true")
    if contract.get("browser_loaded") is True:
        raise RuntimeError(f"{RESEARCH_SOURCE}: browser-loaded runtime payload is forbidden for actor research")

    markets = payload.get("markets") or {}
    prices = payload.get("prices") or {}
    for market in ("gold", "silver"):
        cot_rows = ((markets.get(market) or {}).get("records") or [])
        price_rows = ((prices.get(market) or {}).get("records") or [])
        if len(cot_rows) < MIN_FULL_HISTORY_COT_ROWS:
            raise RuntimeError(
                f"{RESEARCH_SOURCE}: {market} has only {len(cot_rows)} COT rows; "
                f"need >= {MIN_FULL_HISTORY_COT_ROWS}"
            )
        if len(price_rows) < int(len(cot_rows) * MIN_DAILY_TO_WEEKLY_RATIO):
            raise RuntimeError(
                f"{RESEARCH_SOURCE}: {market} price history is too sparse for daily horizons "
                f"({len(price_rows)} price rows vs {len(cot_rows)} COT rows)"
            )
    return contract


def better(candidate: float | None, baseline: float | None) -> bool:
    if candidate is None or baseline is None:
        return False
    return candidate > baseline


def main() -> None:
    if not METALS.exists():
        raise FileNotFoundError(
            f"Missing persistent full-history research source {METALS}; "
            "run build_worldclass_metals.py first. Compact worldclass/metals.json is not a valid fallback."
        )
    payload = json.loads(METALS.read_text(encoding="utf-8"))
    research_contract = validate_research_payload(payload)

    result: dict[str, Any] = {
        "schema_version": 2,
        "study": "disaggregated metal actor incremental predictive value",
        "production_model_at_study_start": MODEL_VERSION,
        "model_spec_hash": MODEL_SPEC_HASH,
        "holdout_start": HOLDOUT_START.isoformat(),
        "research_provenance": {
            "research_source": RESEARCH_SOURCE,
            "full_history": True,
            "daily_price_history": True,
            "browser_loaded": False,
            "source_contract": research_contract,
        },
        "methodology": {
            "score_transform": "expanding percentile of actor net/open-interest percentage",
            "release_anchor": "first available close on/after report date + 3 calendar days",
            "horizon_steps": HORIZONS,
            "horizon_step_frequency": "daily trading observations",
            "extremes": "top score quintile return minus bottom score quintile return",
            "eligibility_rule": "secondary actor must improve both Pearson r and extreme spread vs Managed Money only for Gold and Silver at both 4w and 13w on the 2022+ holdout",
            "lookahead_safe": True,
            "parameter_governance": "research output cannot mutate production actor weights",
        },
        "variants": VARIANTS,
        "markets": {},
        "secondary_actor_verdicts": {},
    }

    for market in ("gold", "silver"):
        rows = payload["markets"][market]["records"]
        prices = payload["prices"][market]
        market_result: dict[str, Any] = {
            "source_period": market_source_period(payload, market),
            "variant_results": {},
        }
        for variant, weights in VARIANTS.items():
            signals = build_signals(rows, prices, weights)
            market_result["variant_results"][variant] = {
                "signal_count": len(signals),
                "full_history": {h: horizon_metrics(signals, h) for h in HORIZONS},
                "train_pre_2022": {h: horizon_metrics(signals, h, segment_end=TRAIN_END) for h in HORIZONS},
                "holdout_2022_plus": {h: horizon_metrics(signals, h, segment_start=HOLDOUT_START) for h in HORIZONS},
            }
        result["markets"][market] = market_result

    baseline_name = "managed_money_only"
    decision_horizons = ("4w", "13w")
    for actor, variant in SECONDARY_VARIANTS.items():
        checks = []
        details = []
        for market in ("gold", "silver"):
            base = result["markets"][market]["variant_results"][baseline_name]["holdout_2022_plus"]
            cand = result["markets"][market]["variant_results"][variant]["holdout_2022_plus"]
            for horizon in decision_horizons:
                corr_ok = better(cand[horizon]["pearson_r"], base[horizon]["pearson_r"])
                spread_ok = better(cand[horizon]["extreme_spread_pct"], base[horizon]["extreme_spread_pct"])
                checks.extend((corr_ok, spread_ok))
                details.append(
                    {
                        "market": market,
                        "horizon": horizon,
                        "baseline_r": base[horizon]["pearson_r"],
                        "candidate_r": cand[horizon]["pearson_r"],
                        "baseline_spread_pct": base[horizon]["extreme_spread_pct"],
                        "candidate_spread_pct": cand[horizon]["extreme_spread_pct"],
                        "correlation_improved": corr_ok,
                        "spread_improved": spread_ok,
                    }
                )
        result["secondary_actor_verdicts"][actor] = {
            "candidate": variant,
            "eligible_for_directional_weight": all(checks),
            "passed_checks": sum(1 for value in checks if value),
            "total_checks": len(checks),
            "details": details,
        }

    OUT.write_text(json.dumps(result, indent=2, default=str) + "\n", encoding="utf-8")

    print("METAL_WEIGHT_STUDY_BEGIN")
    print(
        f"source={RESEARCH_SOURCE} full_history={research_contract.get('full_history')} "
        f"daily_price_history={research_contract.get('daily_price_history')} model={MODEL_VERSION}"
    )
    for market in ("gold", "silver"):
        source_period = result["markets"][market]["source_period"]
        print(
            f"{market.upper()} source COT={source_period['cot_start']}..{source_period['cot_end']} "
            f"({source_period['cot_rows']} rows) prices={source_period['price_start']}..{source_period['price_end']} "
            f"({source_period['daily_price_rows']} daily rows)"
        )
        for segment in ("full_history", "train_pre_2022", "holdout_2022_plus"):
            print(f"  {segment}")
            for variant in VARIANTS:
                metrics = result["markets"][market]["variant_results"][variant][segment]
                parts = []
                for horizon in ("4w", "13w", "26w"):
                    m = metrics[horizon]
                    r = m.get("pearson_r")
                    spread = m.get("extreme_spread_pct")
                    r_text = "n/a" if r is None else f"{r:+.4f}"
                    spread_text = "n/a" if spread is None else f"{spread:+.3f}%"
                    parts.append(f"{horizon} n={m['n']} r={r_text} spread={spread_text}")
                print(f"    {variant:22s} " + " | ".join(parts))
    print("SECONDARY ACTOR ELIGIBILITY")
    for actor, verdict in result["secondary_actor_verdicts"].items():
        print(
            f"  {actor:20s} eligible={verdict['eligible_for_directional_weight']} "
            f"checks={verdict['passed_checks']}/{verdict['total_checks']}"
        )
    print("METAL_WEIGHT_STUDY_END")
    print(f"Saved {OUT}")


if __name__ == "__main__":
    main()
