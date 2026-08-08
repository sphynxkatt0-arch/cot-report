#!/usr/bin/env python3
"""Build regime-conditioned COT, macro, and combined forward-return research.

This extends the existing lookahead-safe COT backtest without replacing it.
Every weekly signal is anchored to the first market close on/after the Friday
COT release target. Macro observations are selected strictly on or before that
release target so future macro data cannot leak into a historical signal.
Model thresholds, weights, horizons and analog-distance coefficients come from
the same canonical specification used by the standard COT backtest.

Output:
  analysis/worldclass/regime_backtest.json
"""
from __future__ import annotations

import json
import math
import statistics
from bisect import bisect_right
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import build_worldclass_backtest as cot_bt

ROOT = Path(__file__).resolve().parent
WORLDCLASS = ROOT / "worldclass"
BASE = WORLDCLASS / "base.json"
METALS = WORLDCLASS / "metals.json"
OUT = WORLDCLASS / "regime_backtest.json"

MODEL_SPEC = cot_bt.MODEL_SPEC
MODEL_VERSION = cot_bt.MODEL_VERSION
MODEL_SPEC_HASH = cot_bt.MODEL_SPEC_HASH
THRESHOLDS = MODEL_SPEC["thresholds"]
ANALOG_SPEC = MODEL_SPEC["analogs"]
BULLISH_THRESHOLD = float(THRESHOLDS["bullish"])
BEARISH_THRESHOLD = float(THRESHOLDS["bearish"])
EXTREME_UPPER = float(THRESHOLDS["extreme_upper_percentile"])
EXTREME_LOWER = float(THRESHOLDS["extreme_lower_percentile"])
MIN_SAMPLE = int(ANALOG_SPEC["minimum_regime_sample"])
DISPLAY_ANALOGS = int(ANALOG_SPEC["display_count"])
MOMENTUM_WEIGHT = float(ANALOG_SPEC["momentum_weight"])
EXTREME_COUNT_WEIGHT = float(ANALOG_SPEC["extreme_count_weight"])
MACRO_SCORE_WEIGHT = float(ANALOG_SPEC["macro_score_weight"])
TRANSMISSION_MISMATCH_PENALTY = float(ANALOG_SPEC["transmission_mismatch_penalty"])
MACRO_SCORE_KEYS = ("liquidity_score", "macro_score", "unified_score", "score")
TRANSMISSION_KEYS = ("real_yield_4w_change", "hy_oas_4w_change", "dollar_4w_change")


def finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def state(value: float | None) -> str:
    if value is None:
        return "unavailable"
    if value >= BULLISH_THRESHOLD:
        return "bullish"
    if value <= BEARISH_THRESHOLD:
        return "bearish"
    return "neutral"


def confidence(n: int) -> str:
    if n >= 40:
        return "High"
    if n >= 20:
        return "Medium"
    return "Low"


def quantile(values: list[float], q: float) -> float | None:
    clean = sorted(v for v in values if math.isfinite(v))
    if not clean:
        return None
    if len(clean) == 1:
        return clean[0]
    pos = (len(clean) - 1) * q
    lo = math.floor(pos)
    hi = math.ceil(pos)
    if lo == hi:
        return clean[lo]
    frac = pos - lo
    return clean[lo] * (1 - frac) + clean[hi] * frac


def score_from_row(row: dict[str, Any]) -> float | None:
    for key in MACRO_SCORE_KEYS:
        value = finite(row.get(key))
        if value is not None and 0 <= value <= 100:
            return value
    return None


def transmission_state(row: dict[str, Any]) -> str:
    values = [finite(row.get(key)) for key in TRANSMISSION_KEYS]
    clean = [v for v in values if v is not None]
    if len(clean) < 2:
        return "unavailable"
    easing = sum(v < 0 for v in clean)
    tightening = sum(v > 0 for v in clean)
    if easing >= 2:
        return "supportive"
    if tightening >= 2:
        return "restrictive"
    return "mixed"


def find_macro_records(node: Any, depth: int = 0) -> list[dict[str, Any]]:
    """Find the richest dated series containing a usable macro score."""
    if depth > 8:
        return []
    best: list[dict[str, Any]] = []
    if isinstance(node, list):
        candidate = [row for row in node if isinstance(row, dict) and row.get("date")]
        usable = [row for row in candidate if score_from_row(row) is not None]
        if usable:
            best = usable
        for child in node[:8]:
            nested = find_macro_records(child, depth + 1)
            if len(nested) > len(best):
                best = nested
        return best
    if isinstance(node, dict):
        for child in node.values():
            nested = find_macro_records(child, depth + 1)
            if len(nested) > len(best):
                best = nested
    return best


def normalize_macro_rows(base: dict[str, Any]) -> list[dict[str, Any]]:
    rows = find_macro_records(base.get("MACRO_MONITOR") or {})
    output = []
    for row in rows:
        parsed = cot_bt.parse_date(row.get("date"))
        score = score_from_row(row)
        if parsed is None or score is None:
            continue
        output.append({
            "date": parsed,
            "date_str": parsed.isoformat(),
            "score": score,
            "transmission": transmission_state(row),
            "raw": row,
        })
    output.sort(key=lambda item: item["date"])
    deduped: dict[date, dict[str, Any]] = {row["date"]: row for row in output}
    return [deduped[key] for key in sorted(deduped)]


def macro_on_or_before(rows: list[dict[str, Any]], target: date) -> dict[str, Any] | None:
    if not rows:
        return None
    dates = [row["date"] for row in rows]
    index = bisect_right(dates, target) - 1
    return rows[index] if index >= 0 else None


def summary(records: list[dict[str, Any]], horizon: str, baseline: list[dict[str, Any]]) -> dict[str, Any]:
    returns = [r["horizons"][horizon]["return_pct"] for r in records if horizon in r["horizons"]]
    drawdowns = [r["horizons"][horizon]["drawdown_pct"] for r in records if horizon in r["horizons"]]
    base_returns = [r["horizons"][horizon]["return_pct"] for r in baseline if horizon in r["horizons"]]
    if not returns:
        return {
            "mean_return_pct": None, "median_return_pct": None, "hit_rate_pct": None,
            "q10_return_pct": None, "q25_return_pct": None, "q75_return_pct": None,
            "q90_return_pct": None, "worst_return_pct": None, "max_drawdown_pct": None,
            "risk_adjusted": None, "observations": 0, "baseline_return_pct": None,
            "excess_return_pct": None, "confidence": "Low",
        }
    mean = statistics.mean(returns)
    median = statistics.median(returns)
    std = statistics.pstdev(returns) if len(returns) >= 2 else 0.0
    baseline_mean = statistics.mean(base_returns) if base_returns else None
    return {
        "mean_return_pct": round(mean, 4),
        "median_return_pct": round(median, 4),
        "hit_rate_pct": round(sum(v > 0 for v in returns) / len(returns) * 100.0, 2),
        "q10_return_pct": round(quantile(returns, 0.10), 4),
        "q25_return_pct": round(quantile(returns, 0.25), 4),
        "q75_return_pct": round(quantile(returns, 0.75), 4),
        "q90_return_pct": round(quantile(returns, 0.90), 4),
        "worst_return_pct": round(min(returns), 4),
        "max_drawdown_pct": round(min(drawdowns), 4) if drawdowns else None,
        "risk_adjusted": round(mean / std, 3) if std > 1e-12 else None,
        "observations": len(returns),
        "baseline_return_pct": round(baseline_mean, 4) if baseline_mean is not None else None,
        "excess_return_pct": round(mean - baseline_mean, 4) if baseline_mean is not None else None,
        "confidence": confidence(len(returns)),
    }


def extreme_count_at(rows: list[dict[str, Any]], index: int, categories: list[str]) -> int:
    count = 0
    for key in categories:
        field = f"{key}_net_oi_pct"
        current = finite(rows[index].get(field))
        if current is None:
            continue
        history = [finite(row.get(field)) for row in rows[: index + 1]]
        clean = [value for value in history if value is not None]
        rank = cot_bt.percentile_rank(clean, current) if clean else None
        if rank is not None and (rank >= EXTREME_UPPER or rank <= EXTREME_LOWER):
            count += 1
    return count


def family_payload(name: str, current: dict[str, Any], history: list[dict[str, Any]]) -> dict[str, Any]:
    if name == "cot":
        selected = [r for r in history if r["cot_state"] == current["cot_state"]]
        rule = f"COT state = {current['cot_state']}"
    elif name == "macro":
        selected = [r for r in history if r["macro_state"] == current["macro_state"]]
        rule = f"Macro state = {current['macro_state']}"
    else:
        selected = [r for r in history if r["cot_state"] == current["cot_state"] and r["macro_state"] == current["macro_state"]]
        rule = f"COT {current['cot_state']} + Macro {current['macro_state']}"

    horizons = {label: summary(selected, label, history) for label in cot_bt.HORIZONS}
    ranked = []
    for row in selected:
        cot_distance = abs((row.get("cot_score") or 50) - (current.get("cot_score") or 50))
        momentum_distance = abs((row.get("cot_score_delta_4w") or 0) - (current.get("cot_score_delta_4w") or 0))
        extreme_distance = abs(int(row.get("extreme_count") or 0) - int(current.get("extreme_count") or 0))
        macro_distance = abs((row.get("macro_score") or 50) - (current.get("macro_score") or 50))
        transmission_penalty = 0 if row.get("transmission_state") == current.get("transmission_state") else TRANSMISSION_MISMATCH_PENALTY
        if name == "cot":
            distance = cot_distance + MOMENTUM_WEIGHT * momentum_distance + EXTREME_COUNT_WEIGHT * extreme_distance
        elif name == "macro":
            distance = macro_distance + transmission_penalty
        else:
            distance = (
                cot_distance
                + MOMENTUM_WEIGHT * momentum_distance
                + EXTREME_COUNT_WEIGHT * extreme_distance
                + MACRO_SCORE_WEIGHT * macro_distance
                + transmission_penalty
            )
        ranked.append((distance, row))
    ranked.sort(key=lambda item: (item[0], item[1]["report_date"]))
    analogs = []
    for distance, row in ranked[:DISPLAY_ANALOGS]:
        analogs.append({
            "report_date": row["report_date"],
            "signal_date": row["signal_date"],
            "cot_score": round(row["cot_score"], 2),
            "cot_score_delta_4w": round(row.get("cot_score_delta_4w") or 0, 2),
            "extreme_count": int(row.get("extreme_count") or 0),
            "macro_score": round(row["macro_score"], 2) if row.get("macro_score") is not None else None,
            "transmission_state": row.get("transmission_state"),
            "distance": round(distance, 3),
            "returns": {key: round(value["return_pct"], 3) for key, value in row["horizons"].items()},
        })
    return {
        "name": name,
        "match_rule": rule,
        "sample_size": len(selected),
        "minimum_recommended_sample": MIN_SAMPLE,
        "horizons": horizons,
        "closest_analogs": analogs,
    }


def build_market_dataset(
    market: str,
    dataset: str,
    payload: dict[str, Any],
    prices_payload: Any,
    macro_rows: list[dict[str, Any]],
) -> dict[str, Any] | None:
    rows = [r for r in (payload.get("records") or []) if isinstance(r, dict) and cot_bt.parse_date(r.get("date"))]
    rows.sort(key=lambda r: str(r.get("date")))
    categories = list((payload.get("categories") or {}).keys())
    prices = cot_bt.price_records(prices_payload)
    if len(rows) < cot_bt.MIN_LOOKBACK_WEEKS or len(prices) < 200 or not categories:
        return None

    history: list[dict[str, Any]] = []
    for index in range(cot_bt.MIN_LOOKBACK_WEEKS - 1, len(rows)):
        report_date = cot_bt.parse_date(rows[index].get("date"))
        cot_score = cot_bt.score_at(rows, index, dataset, categories)
        if report_date is None or cot_score is None:
            continue
        release_target = report_date + timedelta(days=3)
        signal_index = cot_bt.first_price_index_on_or_after(prices, release_target)
        if signal_index is None:
            continue
        macro = macro_on_or_before(macro_rows, release_target)
        macro_score = macro["score"] if macro else None
        prior_index = max(cot_bt.MIN_LOOKBACK_WEEKS - 1, index - 4)
        prior_score = cot_bt.score_at(rows, prior_index, dataset, categories) if prior_index != index else cot_score
        score_delta_4w = cot_score - prior_score if prior_score is not None else 0.0
        extreme_count = extreme_count_at(rows, index, categories)
        horizons = {}
        for label, steps in cot_bt.HORIZONS.items():
            result = cot_bt.horizon_result(prices, signal_index, steps)
            if result is not None:
                horizons[label] = result
        history.append({
            "report_date": report_date.isoformat(),
            "release_target_date": release_target.isoformat(),
            "signal_date": prices[signal_index]["date_str"],
            "cot_score": cot_score,
            "cot_score_delta_4w": score_delta_4w,
            "extreme_count": extreme_count,
            "macro_score": macro_score,
            "cot_state": state(cot_score),
            "macro_state": state(macro_score),
            "transmission_state": macro.get("transmission") if macro else "unavailable",
            "horizons": horizons,
        })

    if not history:
        return None

    latest = history[-1]
    realized = [row for row in history[:-1] if row["horizons"]]
    if not realized:
        return None
    current = {
        key: latest[key]
        for key in ("report_date", "release_target_date", "signal_date", "cot_score", "cot_score_delta_4w", "extreme_count", "macro_score", "cot_state", "macro_state", "transmission_state")
    }
    current["combined_state"] = f"{current['cot_state']} COT / {current['macro_state']} macro"
    families = {name: family_payload(name, current, realized) for name in ("cot", "macro", "combined")}
    return {
        "market": market,
        "dataset": dataset,
        "model_version": MODEL_VERSION,
        "model_spec_hash": MODEL_SPEC_HASH,
        "methodology": {
            "lookahead_safe": True,
            "cot_release_anchor": "first close on/after Tuesday report date + 3 calendar days",
            "macro_alignment": "last macro observation on or before the release target",
            "cot_state_thresholds": f"bullish >={BULLISH_THRESHOLD:g}, bearish <={BEARISH_THRESHOLD:g}, otherwise neutral",
            "macro_state_thresholds": f"bullish >={BULLISH_THRESHOLD:g}, bearish <={BEARISH_THRESHOLD:g}, otherwise neutral",
            "cot_analog_distance": f"score distance + {MOMENTUM_WEIGHT:g}*4w score-momentum distance + {EXTREME_COUNT_WEIGHT:g}*extreme-count distance",
            "macro_analog_distance": f"macro-score distance + {TRANSMISSION_MISMATCH_PENALTY:g} transmission-state mismatch penalty",
            "combined_regime": f"exact COT-state + macro-state match; distance ranks score momentum, extremes, {MACRO_SCORE_WEIGHT:g}*macro score and transmission only within that regime",
        },
        "current": current,
        "families": families,
        "regime_history": [
            {
                "report_date": row["report_date"],
                "signal_date": row["signal_date"],
                "cot_state": row["cot_state"],
                "cot_score_delta_4w": round(row.get("cot_score_delta_4w") or 0, 2),
                "extreme_count": int(row.get("extreme_count") or 0),
                "macro_state": row["macro_state"],
                "transmission_state": row["transmission_state"],
                "combined_state": f"{row['cot_state']} COT / {row['macro_state']} macro",
            }
            for row in history[-260:]
        ],
        "historical_signal_count": len(realized),
    }


def build() -> dict[str, Any]:
    base = json.loads(BASE.read_text(encoding="utf-8"))
    cot_data = base.get("COT_DATA") or {}
    prices = base.get("PRICE_DATA") or {}
    if METALS.exists():
        metals = json.loads(METALS.read_text(encoding="utf-8"))
        cot_data.setdefault("disaggregated", {}).update(metals.get("markets") or {})
        prices.update(metals.get("prices") or {})

    macro_rows = normalize_macro_rows(base)
    result: dict[str, Any] = {
        "schema_version": 2,
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "model_version": MODEL_VERSION,
        "model_spec_hash": MODEL_SPEC_HASH,
        "macro_history_points": len(macro_rows),
        "markets": {},
    }
    for dataset, markets in cot_data.items():
        if dataset not in cot_bt.SCORE_WEIGHTS or not isinstance(markets, dict):
            continue
        for market, payload in markets.items():
            if not isinstance(payload, dict):
                continue
            built = build_market_dataset(market, dataset, payload, prices.get(market), macro_rows)
            if built is None:
                continue
            result["markets"].setdefault(market, {"datasets": {}})["datasets"][dataset] = built
    if not result["markets"]:
        raise RuntimeError("No regime backtests could be built")
    return result


def main() -> None:
    WORLDCLASS.mkdir(parents=True, exist_ok=True)
    payload = build()
    temp = OUT.with_suffix(".json.tmp")
    temp.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    temp.replace(OUT)
    print(f"Saved {OUT} ({OUT.stat().st_size:,} bytes; macro history {payload['macro_history_points']} points)")


if __name__ == "__main__":
    main()
