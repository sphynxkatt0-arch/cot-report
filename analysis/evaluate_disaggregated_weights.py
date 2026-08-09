#!/usr/bin/env python3
"""Evaluate Disaggregated COT actor weights for Gold and Silver.

The study is deliberately separate from the production model. It uses the same
lookahead-safe expanding percentile transform and Friday release anchoring as the
production COT backtest, then compares a Managed-Money-only baseline with each
secondary actor added one at a time plus the v1.1 production blend.

A secondary actor is eligible for directional weight only if it improves the
2022+ holdout versus Managed Money alone on BOTH Gold and Silver for BOTH the
4-week and 13-week horizons in:
  1. score/forward-return Pearson correlation, and
  2. top-quintile minus bottom-quintile forward-return spread.

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
METALS = ROOT / "worldclass" / "metals.json"
OUT = ROOT / "worldclass" / "metal-weight-study.json"
MODEL_SPEC = model_cfg.load_model_spec()
MIN_LOOKBACK_WEEKS = int(MODEL_SPEC["lookback"]["minimum_weeks"])
HORIZONS = model_cfg.horizons(MODEL_SPEC)
HOLDOUT_START = date(2022, 1, 1)

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


def horizon_metrics(signals: list[dict[str, Any]], horizon: str, segment_start: date | None) -> dict[str, Any]:
    usable = []
    for signal in signals:
        if segment_start is not None and signal["report_date"] < segment_start:
            continue
        value = signal["returns"].get(horizon)
        if value is not None:
            usable.append((signal["score"], value))
    if len(usable) < 10:
        return {"n": len(usable), "pearson_r": None, "extreme_spread_pct": None}
    scores = [item[0] for item in usable]
    returns = [item[1] for item in usable]
    ranked = sorted(usable, key=lambda item: item[0])
    bucket = max(1, len(ranked) // 5)
    bottom = [ret for _, ret in ranked[:bucket]]
    top = [ret for _, ret in ranked[-bucket:]]
    spread = statistics.mean(top) - statistics.mean(bottom)
    return {
        "n": len(usable),
        "pearson_r": round(pearson(scores, returns) or 0.0, 6),
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


def better(candidate: float | None, baseline: float | None) -> bool:
    if candidate is None or baseline is None:
        return False
    return candidate > baseline


def main() -> None:
    if not METALS.exists():
        raise FileNotFoundError(f"Missing {METALS}; run build_worldclass_metals.py first")
    payload = json.loads(METALS.read_text(encoding="utf-8"))
    result: dict[str, Any] = {
        "schema_version": 1,
        "study": "disaggregated metal actor incremental predictive value",
        "production_model_at_study_start": "1.1.0",
        "holdout_start": HOLDOUT_START.isoformat(),
        "methodology": {
            "score_transform": "expanding percentile of actor net/open-interest percentage",
            "release_anchor": "first available close on/after report date + 3 calendar days",
            "extremes": "top score quintile return minus bottom score quintile return",
            "eligibility_rule": "secondary actor must improve both Pearson r and extreme spread vs Managed Money only for Gold and Silver at both 4w and 13w on the 2022+ holdout",
            "lookahead_safe": True,
        },
        "variants": VARIANTS,
        "markets": {},
        "secondary_actor_verdicts": {},
    }

    for market in ("gold", "silver"):
        rows = payload["markets"][market]["records"]
        prices = payload["prices"][market]
        market_result: dict[str, Any] = {"variant_results": {}}
        for variant, weights in VARIANTS.items():
            signals = build_signals(rows, prices, weights)
            market_result["variant_results"][variant] = {
                "signal_count": len(signals),
                "full_history": {h: horizon_metrics(signals, h, None) for h in HORIZONS},
                "holdout_2022_plus": {h: horizon_metrics(signals, h, HOLDOUT_START) for h in HORIZONS},
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
                details.append({
                    "market": market,
                    "horizon": horizon,
                    "baseline_r": base[horizon]["pearson_r"],
                    "candidate_r": cand[horizon]["pearson_r"],
                    "baseline_spread_pct": base[horizon]["extreme_spread_pct"],
                    "candidate_spread_pct": cand[horizon]["extreme_spread_pct"],
                    "correlation_improved": corr_ok,
                    "spread_improved": spread_ok,
                })
        result["secondary_actor_verdicts"][actor] = {
            "candidate": variant,
            "eligible_for_directional_weight": all(checks),
            "passed_checks": sum(1 for value in checks if value),
            "total_checks": len(checks),
            "details": details,
        }

    OUT.write_text(json.dumps(result, indent=2, default=str) + "\n", encoding="utf-8")

    print("METAL_WEIGHT_STUDY_BEGIN")
    for market in ("gold", "silver"):
        print(f"{market.upper()} holdout 2022+")
        for variant in VARIANTS:
            metrics = result["markets"][market]["variant_results"][variant]["holdout_2022_plus"]
            m4 = metrics["4w"]
            m13 = metrics["13w"]
            print(
                f"  {variant:22s} 4w r={m4['pearson_r']:+.4f} spread={m4['extreme_spread_pct']:+.3f}% | "
                f"13w r={m13['pearson_r']:+.4f} spread={m13['extreme_spread_pct']:+.3f}%"
            )
    print("SECONDARY ACTOR ELIGIBILITY")
    for actor, verdict in result["secondary_actor_verdicts"].items():
        print(f"  {actor:20s} eligible={verdict['eligible_for_directional_weight']} checks={verdict['passed_checks']}/{verdict['total_checks']}")
    print("METAL_WEIGHT_STUDY_END")
    print(f"Saved {OUT}")


if __name__ == "__main__":
    main()
