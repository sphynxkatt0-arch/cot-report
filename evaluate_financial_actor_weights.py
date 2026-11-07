#!/usr/bin/env python3
"""Evaluate incremental directional value of secondary financial COT actors.

This study is deliberately separate from the production model. It uses the same
lookahead-safe expanding percentile transform and Friday release anchoring as
production, then asks whether the remaining inverse/context actors add stable
out-of-sample information beyond the directional participants.

Precommitted 2022+ holdout decision rules:
- TFF baseline: Asset Manager + Leveraged Funds. Other Reportables and
  Nonreportables only earn non-zero directional weight if adding them improves
  BOTH Pearson score/forward-return correlation and top-minus-bottom score
  quintile return spread for BOTH S&P 500 and Nasdaq-100 at BOTH 4W and 13W.
- Legacy baseline: Non-Commercial only. Nonreportables must pass the same 8
  checks to earn directional weight.

Dealer/Intermediary, Commercial and Total Reportable are intentionally not
re-tested as directional actors; model governance already classifies them as
intermediary/opposite-side or aggregate context.

Output:
  analysis/worldclass/financial-weight-study.json
"""
from __future__ import annotations

import json
import math
import statistics
from bisect import bisect_left
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import build_worldclass_bundle as bundle
import model_spec as model_cfg

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "interactive_cot_dashboard.html"
OUT = ROOT / "worldclass" / "financial-weight-study.json"
MODEL_SPEC = model_cfg.load_model_spec()
MIN_LOOKBACK_WEEKS = int(MODEL_SPEC["lookback"]["minimum_weeks"])
HORIZONS = model_cfg.horizons(MODEL_SPEC)
HOLDOUT_START = date(2022, 1, 1)
MARKETS = ("sp500", "nq")
DECISION_HORIZONS = ("4w", "13w")

TFF_ZERO = {
    "dealer": 0.0,
    "asset_mgr": 0.0,
    "lev_money": 0.0,
    "other_reportable": 0.0,
    "non_reportable": 0.0,
}
TFF_VARIANTS: dict[str, dict[str, float]] = {
    "directional_only": {**TFF_ZERO, "asset_mgr": 1.25, "lev_money": 0.75},
    "plus_other_reportable": {**TFF_ZERO, "asset_mgr": 1.25, "lev_money": 0.75, "other_reportable": -1.0},
    "plus_non_reportable": {**TFF_ZERO, "asset_mgr": 1.25, "lev_money": 0.75, "non_reportable": -1.0},
    "v1_2_blend": {**TFF_ZERO, "asset_mgr": 1.25, "lev_money": 0.75, "other_reportable": -1.0, "non_reportable": -1.0},
}
TFF_SECONDARY = {
    "other_reportable": "plus_other_reportable",
    "non_reportable": "plus_non_reportable",
}

LEGACY_ZERO = {
    "noncommercial": 0.0,
    "commercial": 0.0,
    "total_reportable": 0.0,
    "nonreportable": 0.0,
}
LEGACY_VARIANTS: dict[str, dict[str, float]] = {
    "noncommercial_only": {**LEGACY_ZERO, "noncommercial": 1.0},
    "plus_nonreportable": {**LEGACY_ZERO, "noncommercial": 1.0, "nonreportable": -0.75},
    "v1_2_blend": {**LEGACY_ZERO, "noncommercial": 1.0, "nonreportable": -0.75},
}
LEGACY_SECONDARY = {"nonreportable": "plus_nonreportable"}


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
        current = finite(rows[index].get(f"{key}_net_oi_pct"))
        if current is None:
            continue
        history = [finite(row.get(f"{key}_net_oi_pct")) for row in rows[: index + 1]]
        rank = percentile_rank([value for value in history if value is not None], current)
        if rank is None:
            continue
        centered = (rank - 50.0) / 50.0
        numerator += weight * centered
        denominator += abs(weight)
    if denominator == 0:
        return None
    return max(0.0, min(100.0, 50.0 + 50.0 * numerator / denominator))


def price_records(payload: Any) -> list[dict[str, Any]]:
    rows = payload.get("records") if isinstance(payload, dict) else payload
    output = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        d = parse_date(row.get("date"))
        p = finite(row.get("price"))
        if d is not None and p is not None:
            output.append({"date": d, "price": p})
    output.sort(key=lambda row: row["date"])
    return output


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
    denom = math.sqrt(sum(value * value for value in dx) * sum(value * value for value in dy))
    if denom <= 1e-12:
        return None
    return sum(a * b for a, b in zip(dx, dy)) / denom


def build_signals(rows: list[dict[str, Any]], prices_payload: Any, weights: dict[str, float]) -> list[dict[str, Any]]:
    rows = [row for row in rows if isinstance(row, dict) and parse_date(row.get("date"))]
    rows.sort(key=lambda row: str(row.get("date")))
    prices = price_records(prices_payload)
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
            if start_price == 0 or end_index >= len(prices):
                returns[horizon] = None
            else:
                returns[horizon] = (prices[end_index]["price"] / start_price - 1.0) * 100.0
        signals.append({"report_date": report_date, "score": score, "returns": returns})
    return signals


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
    scores = [score for score, _ in usable]
    returns = [ret for _, ret in usable]
    ranked = sorted(usable, key=lambda item: item[0])
    bucket = max(1, len(ranked) // 5)
    bottom = [ret for _, ret in ranked[:bucket]]
    top = [ret for _, ret in ranked[-bucket:]]
    return {
        "n": len(usable),
        "pearson_r": round(pearson(scores, returns) or 0.0, 6),
        "extreme_spread_pct": round(statistics.mean(top) - statistics.mean(bottom), 6),
        "top_quintile_return_pct": round(statistics.mean(top), 6),
        "bottom_quintile_return_pct": round(statistics.mean(bottom), 6),
        "unconditional_return_pct": round(statistics.mean(returns), 6),
    }


def evaluate_dataset(cot_data: dict[str, Any], prices: dict[str, Any], dataset: str, variants: dict[str, dict[str, float]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for market in MARKETS:
        rows = ((cot_data.get(dataset) or {}).get(market) or {}).get("records") or []
        market_result = {"variant_results": {}}
        for variant, weights in variants.items():
            signals = build_signals(rows, prices.get(market), weights)
            market_result["variant_results"][variant] = {
                "signal_count": len(signals),
                "full_history": {h: horizon_metrics(signals, h, None) for h in HORIZONS},
                "holdout_2022_plus": {h: horizon_metrics(signals, h, HOLDOUT_START) for h in HORIZONS},
            }
        result[market] = market_result
    return result


def verdicts(results: dict[str, Any], baseline: str, secondary: dict[str, str]) -> dict[str, Any]:
    output = {}
    for actor, variant in secondary.items():
        checks = []
        details = []
        for market in MARKETS:
            base = results[market]["variant_results"][baseline]["holdout_2022_plus"]
            candidate = results[market]["variant_results"][variant]["holdout_2022_plus"]
            for horizon in DECISION_HORIZONS:
                corr_ok = candidate[horizon]["pearson_r"] is not None and candidate[horizon]["pearson_r"] > base[horizon]["pearson_r"]
                spread_ok = candidate[horizon]["extreme_spread_pct"] is not None and candidate[horizon]["extreme_spread_pct"] > base[horizon]["extreme_spread_pct"]
                checks.extend((corr_ok, spread_ok))
                details.append({
                    "market": market,
                    "horizon": horizon,
                    "baseline_r": base[horizon]["pearson_r"],
                    "candidate_r": candidate[horizon]["pearson_r"],
                    "baseline_spread_pct": base[horizon]["extreme_spread_pct"],
                    "candidate_spread_pct": candidate[horizon]["extreme_spread_pct"],
                    "correlation_improved": corr_ok,
                    "spread_improved": spread_ok,
                })
        output[actor] = {
            "candidate": variant,
            "eligible_for_directional_weight": all(checks),
            "passed_checks": sum(1 for value in checks if value),
            "total_checks": len(checks),
            "details": details,
        }
    return output


def main() -> None:
    if not SOURCE.exists():
        raise FileNotFoundError(f"Missing {SOURCE}")
    text = SOURCE.read_text(encoding="utf-8")
    cot_data = bundle.extract_json_constant(text, "COT_DATA")
    prices = bundle.extract_json_constant(text, "PRICE_DATA")
    if not cot_data or not prices:
        raise RuntimeError("Canonical dashboard is missing COT_DATA or PRICE_DATA")

    tff_results = evaluate_dataset(cot_data, prices, "tff", TFF_VARIANTS)
    legacy_results = evaluate_dataset(cot_data, prices, "legacy", LEGACY_VARIANTS)
    result = {
        "schema_version": 1,
        "study": "financial COT secondary actor incremental predictive value",
        "production_model_at_study_start": str(MODEL_SPEC["model_version"]),
        "holdout_start": HOLDOUT_START.isoformat(),
        "markets": list(MARKETS),
        "decision_horizons": list(DECISION_HORIZONS),
        "methodology": {
            "score_transform": "expanding percentile of actor net/open-interest percentage",
            "release_anchor": "first available close on/after report date + 3 calendar days",
            "extremes": "top score quintile return minus bottom score quintile return",
            "eligibility_rule": "secondary actor must improve both Pearson r and extreme spread versus directional-only baseline for S&P 500 and Nasdaq-100 at both 4w and 13w on the 2022+ holdout",
            "lookahead_safe": True,
        },
        "tff": {
            "baseline": "directional_only",
            "variants": TFF_VARIANTS,
            "markets": tff_results,
            "secondary_actor_verdicts": verdicts(tff_results, "directional_only", TFF_SECONDARY),
        },
        "legacy": {
            "baseline": "noncommercial_only",
            "variants": LEGACY_VARIANTS,
            "markets": legacy_results,
            "secondary_actor_verdicts": verdicts(legacy_results, "noncommercial_only", LEGACY_SECONDARY),
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2, default=str) + "\n", encoding="utf-8")

    print("FINANCIAL_WEIGHT_STUDY_BEGIN")
    for dataset, baseline, variants in (("tff", "directional_only", TFF_VARIANTS), ("legacy", "noncommercial_only", LEGACY_VARIANTS)):
        print(dataset.upper())
        results = result[dataset]["markets"]
        for market in MARKETS:
            print(f"  {market.upper()} holdout 2022+")
            for variant in variants:
                metrics = results[market]["variant_results"][variant]["holdout_2022_plus"]
                m4, m13 = metrics["4w"], metrics["13w"]
                print(f"    {variant:24s} 4w r={m4['pearson_r']:+.4f} spread={m4['extreme_spread_pct']:+.3f}% | 13w r={m13['pearson_r']:+.4f} spread={m13['extreme_spread_pct']:+.3f}%")
        print("  SECONDARY ACTOR ELIGIBILITY")
        for actor, verdict in result[dataset]["secondary_actor_verdicts"].items():
            print(f"    {actor:20s} eligible={verdict['eligible_for_directional_weight']} checks={verdict['passed_checks']}/{verdict['total_checks']}")
    print("FINANCIAL_WEIGHT_STUDY_END")
    print(f"Saved {OUT}")


if __name__ == "__main__":
    main()
