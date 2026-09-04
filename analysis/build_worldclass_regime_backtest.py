#!/usr/bin/env python3
"""Build release-corrected regime-conditioned COT/macro research.

COT rows are usable only when the canonical CFTC calendar resolves their public
availability. Historical holiday/non-Tuesday rows with unknown publication are
excluded. Macro observations are calendar-aligned on/before that availability,
but are explicitly not claimed point-in-time vintage safe.

Statistical sample reporting is conservative. Weekly observations can overlap
at multi-week horizons and contiguous weeks in the same regime are not treated
as independent regime discoveries. Every horizon therefore reports raw N,
non-overlapping N, regime episode N, and an effective N defined as the smaller
of non-overlapping N and regime episode N.
"""
from __future__ import annotations

import json
import math
import statistics
from bisect import bisect_right
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Callable

import build_worldclass_backtest as cot_bt
from cftc_release_calendar import calendar_hash, release_record
from cot_research_core import release_aligned_entry

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
    return "High" if n >= 40 else ("Medium" if n >= 20 else "Low")


def quantile(values: list[float], q: float) -> float | None:
    clean = sorted(v for v in values if math.isfinite(v))
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


def score_from_row(row: dict[str, Any]) -> float | None:
    for key in MACRO_SCORE_KEYS:
        value = finite(row.get(key))
        if value is not None and 0 <= value <= 100:
            return value
    return None


def transmission_state(row: dict[str, Any]) -> str:
    clean = [v for v in (finite(row.get(key)) for key in TRANSMISSION_KEYS) if v is not None]
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
    output: list[dict[str, Any]] = []
    for row in find_macro_records(base.get("MACRO_MONITOR") or {}):
        parsed = cot_bt.parse_date(row.get("date"))
        score = score_from_row(row)
        if parsed is None or score is None:
            continue
        output.append(
            {
                "date": parsed,
                "date_str": parsed.isoformat(),
                "score": score,
                "transmission": transmission_state(row),
                "raw": row,
            }
        )
    deduplicated = {row["date"]: row for row in sorted(output, key=lambda item: item["date"])}
    return [deduplicated[key] for key in sorted(deduplicated)]


def macro_on_or_before(rows: list[dict[str, Any]], target: date) -> dict[str, Any] | None:
    if not rows:
        return None
    index = bisect_right([row["date"] for row in rows], target) - 1
    return rows[index] if index >= 0 else None


def records_with_horizon(records: list[dict[str, Any]], horizon: str) -> list[dict[str, Any]]:
    return [row for row in records if horizon in row.get("horizons", {})]


def non_overlapping_records(records: list[dict[str, Any]], horizon: str) -> list[dict[str, Any]]:
    """Select chronologically spaced signals whose forward windows do not overlap."""
    spacing = int(cot_bt.HORIZONS[horizon])
    eligible = records_with_horizon(records, horizon)
    eligible.sort(key=lambda row: (int(row.get("signal_index", -1)), str(row.get("signal_date") or "")))
    selected: list[dict[str, Any]] = []
    next_allowed_index: int | None = None
    for row in eligible:
        try:
            signal_index = int(row["signal_index"])
        except (KeyError, TypeError, ValueError):
            continue
        if next_allowed_index is not None and signal_index < next_allowed_index:
            continue
        selected.append(row)
        next_allowed_index = signal_index + spacing
    return selected


def count_regime_episodes(
    history: list[dict[str, Any]],
    matches: Callable[[dict[str, Any]], bool],
) -> int:
    """Collapse each contiguous matching weekly run into one regime episode."""
    episodes = 0
    inside_episode = False
    for row in sorted(history, key=lambda item: str(item.get("report_date") or "")):
        current_match = bool(matches(row))
        if current_match and not inside_episode:
            episodes += 1
        inside_episode = current_match
    return episodes


def summary(
    records: list[dict[str, Any]],
    horizon: str,
    baseline: list[dict[str, Any]],
    regime_episode_n: int,
) -> dict[str, Any]:
    realized = records_with_horizon(records, horizon)
    returns = [float(row["horizons"][horizon]["return_pct"]) for row in realized]
    drawdowns = [float(row["horizons"][horizon]["drawdown_pct"]) for row in realized]
    base_returns = [
        float(row["horizons"][horizon]["return_pct"])
        for row in records_with_horizon(baseline, horizon)
    ]
    independent = non_overlapping_records(records, horizon)
    independent_returns = [float(row["horizons"][horizon]["return_pct"]) for row in independent]
    effective_n = min(len(independent_returns), int(regime_episode_n)) if returns else 0

    empty = {
        "mean_return_pct": None,
        "median_return_pct": None,
        "hit_rate_pct": None,
        "q10_return_pct": None,
        "q25_return_pct": None,
        "q75_return_pct": None,
        "q90_return_pct": None,
        "worst_return_pct": None,
        "max_drawdown_pct": None,
        "risk_adjusted": None,
        "observations": 0,
        "effective_n": 0,
        "regime_episode_n": int(regime_episode_n),
        "non_overlapping_n": 0,
        "non_overlapping_mean_return_pct": None,
        "non_overlapping_median_return_pct": None,
        "non_overlapping_hit_rate_pct": None,
        "non_overlapping_worst_return_pct": None,
        "baseline_return_pct": None,
        "excess_return_pct": None,
        "confidence": "Low",
    }
    if not returns:
        return empty

    average = statistics.mean(returns)
    standard_deviation = statistics.pstdev(returns) if len(returns) >= 2 else 0.0
    baseline_average = statistics.mean(base_returns) if base_returns else None
    independent_average = statistics.mean(independent_returns) if independent_returns else None

    return {
        "mean_return_pct": round(average, 4),
        "median_return_pct": round(statistics.median(returns), 4),
        "hit_rate_pct": round(sum(value > 0 for value in returns) / len(returns) * 100, 2),
        "q10_return_pct": round(quantile(returns, 0.10), 4),
        "q25_return_pct": round(quantile(returns, 0.25), 4),
        "q75_return_pct": round(quantile(returns, 0.75), 4),
        "q90_return_pct": round(quantile(returns, 0.90), 4),
        "worst_return_pct": round(min(returns), 4),
        "max_drawdown_pct": round(min(drawdowns), 4) if drawdowns else None,
        "risk_adjusted": round(average / standard_deviation, 3) if standard_deviation > 1e-12 else None,
        "observations": len(returns),
        "effective_n": effective_n,
        "regime_episode_n": int(regime_episode_n),
        "non_overlapping_n": len(independent_returns),
        "non_overlapping_mean_return_pct": round(independent_average, 4) if independent_average is not None else None,
        "non_overlapping_median_return_pct": round(statistics.median(independent_returns), 4) if independent_returns else None,
        "non_overlapping_hit_rate_pct": (
            round(sum(value > 0 for value in independent_returns) / len(independent_returns) * 100, 2)
            if independent_returns
            else None
        ),
        "non_overlapping_worst_return_pct": round(min(independent_returns), 4) if independent_returns else None,
        "baseline_return_pct": round(baseline_average, 4) if baseline_average is not None else None,
        "excess_return_pct": round(average - baseline_average, 4) if baseline_average is not None else None,
        "confidence": confidence(effective_n),
    }


def extreme_count_at(rows: list[dict[str, Any]], index: int, categories: list[str]) -> int:
    count = 0
    for key in categories:
        field = f"{key}_net_oi_pct"
        current = finite(rows[index].get(field))
        if current is None:
            continue
        clean = [v for v in (finite(row.get(field)) for row in rows[: index + 1]) if v is not None]
        rank = cot_bt.percentile_rank(clean, current) if clean else None
        if rank is not None and (rank >= EXTREME_UPPER or rank <= EXTREME_LOWER):
            count += 1
    return count


def family_payload(name: str, current: dict[str, Any], history: list[dict[str, Any]]) -> dict[str, Any]:
    if name == "cot":
        matches = lambda row: row["cot_state"] == current["cot_state"]
        rule = f"COT state = {current['cot_state']}"
    elif name == "macro":
        matches = lambda row: row["macro_state"] == current["macro_state"]
        rule = f"Macro state = {current['macro_state']}"
    else:
        matches = lambda row: (
            row["cot_state"] == current["cot_state"]
            and row["macro_state"] == current["macro_state"]
        )
        rule = f"COT {current['cot_state']} + Macro {current['macro_state']}"

    selected = [row for row in history if matches(row)]
    regime_episode_n = count_regime_episodes(history, matches)
    horizons = {
        label: summary(selected, label, history, regime_episode_n)
        for label in cot_bt.HORIZONS
    }

    ranked: list[tuple[float, dict[str, Any]]] = []
    for row in selected:
        cot_distance = abs((row.get("cot_score") or 50) - (current.get("cot_score") or 50))
        momentum_distance = abs(
            (row.get("cot_score_delta_4w") or 0) - (current.get("cot_score_delta_4w") or 0)
        )
        extreme_distance = abs(
            int(row.get("extreme_count") or 0) - int(current.get("extreme_count") or 0)
        )
        macro_distance = abs((row.get("macro_score") or 50) - (current.get("macro_score") or 50))
        penalty = (
            0
            if row.get("transmission_state") == current.get("transmission_state")
            else TRANSMISSION_MISMATCH_PENALTY
        )
        if name == "cot":
            distance = (
                cot_distance
                + MOMENTUM_WEIGHT * momentum_distance
                + EXTREME_COUNT_WEIGHT * extreme_distance
            )
        elif name == "macro":
            distance = macro_distance + penalty
        else:
            distance = (
                cot_distance
                + MOMENTUM_WEIGHT * momentum_distance
                + EXTREME_COUNT_WEIGHT * extreme_distance
                + MACRO_SCORE_WEIGHT * macro_distance
                + penalty
            )
        ranked.append((distance, row))

    ranked.sort(key=lambda item: (item[0], item[1]["report_date"]))
    analogs: list[dict[str, Any]] = []
    for distance, row in ranked[:DISPLAY_ANALOGS]:
        analogs.append(
            {
                "report_date": row["report_date"],
                "signal_date": row["signal_date"],
                "cot_score": round(row["cot_score"], 2),
                "cot_score_delta_4w": round(row.get("cot_score_delta_4w") or 0, 2),
                "extreme_count": int(row.get("extreme_count") or 0),
                "macro_score": round(row["macro_score"], 2) if row.get("macro_score") is not None else None,
                "transmission_state": row.get("transmission_state"),
                "distance": round(distance, 3),
                "returns": {
                    horizon: round(result["return_pct"], 3)
                    for horizon, result in row["horizons"].items()
                },
            }
        )

    return {
        "name": name,
        "match_rule": rule,
        "sample_size": len(selected),
        "regime_episode_n": regime_episode_n,
        "effective_n": {label: payload["effective_n"] for label, payload in horizons.items()},
        "non_overlapping_sample_n": {
            label: payload["non_overlapping_n"] for label, payload in horizons.items()
        },
        "minimum_recommended_sample": MIN_SAMPLE,
        "sample_independence_policy": (
            "effective_n = min(non_overlapping_n, regime_episode_n); confidence uses effective_n"
        ),
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
    rows = [
        row
        for row in (payload.get("records") or [])
        if isinstance(row, dict) and cot_bt.parse_date(row.get("date"))
    ]
    rows.sort(key=lambda row: str(row.get("date")))
    categories = list((payload.get("categories") or {}).keys())
    prices = cot_bt.price_records(prices_payload)
    if len(rows) < cot_bt.MIN_LOOKBACK_WEEKS or len(prices) < 200 or not categories:
        return None

    history: list[dict[str, Any]] = []
    excluded_unresolved = 0
    for index in range(cot_bt.MIN_LOOKBACK_WEEKS - 1, len(rows)):
        report_date = cot_bt.parse_date(rows[index].get("date"))
        cot_score = cot_bt.score_at(rows, index, dataset, categories)
        if report_date is None or cot_score is None:
            continue

        release_meta = release_record(report_date)
        if not release_meta.get("research_eligible") or not release_meta.get("actual_release_date"):
            excluded_unresolved += 1
            continue

        entry = release_aligned_entry(prices, report_date)
        if entry is None:
            continue
        release_target = date.fromisoformat(str(release_meta["actual_release_date"]))
        signal_index = int(entry["index"])
        macro = macro_on_or_before(macro_rows, release_target)
        macro_score = macro["score"] if macro else None
        prior = max(cot_bt.MIN_LOOKBACK_WEEKS - 1, index - 4)
        prior_score = cot_bt.score_at(rows, prior, dataset, categories) if prior != index else cot_score
        score_delta = cot_score - prior_score if prior_score is not None else 0.0
        extreme_count = extreme_count_at(rows, index, categories)
        horizons: dict[str, Any] = {}
        for label, steps in cot_bt.HORIZONS.items():
            result = cot_bt.horizon_result(prices, signal_index, steps)
            if result is not None:
                horizons[label] = result

        history.append(
            {
                "report_date": report_date.isoformat(),
                "release_target_date": release_target.isoformat(),
                "availability_at": release_meta["availability_at_utc"],
                "availability_source": release_meta["availability_source_type"],
                "signal_date": prices[signal_index]["date_str"],
                "signal_index": signal_index,
                "cot_score": cot_score,
                "cot_score_delta_4w": score_delta,
                "extreme_count": extreme_count,
                "macro_score": macro_score,
                "macro_observation_date": macro["date_str"] if macro else None,
                "cot_state": state(cot_score),
                "macro_state": state(macro_score),
                "transmission_state": macro.get("transmission") if macro else "unavailable",
                "horizons": horizons,
            }
        )

    if not history:
        return None
    latest = history[-1]
    realized = [row for row in history[:-1] if row["horizons"]]
    if not realized:
        return None

    keys = (
        "report_date",
        "release_target_date",
        "availability_at",
        "availability_source",
        "signal_date",
        "cot_score",
        "cot_score_delta_4w",
        "extreme_count",
        "macro_score",
        "macro_observation_date",
        "cot_state",
        "macro_state",
        "transmission_state",
    )
    current = {key: latest[key] for key in keys}
    current["combined_state"] = f"{current['cot_state']} COT / {current['macro_state']} macro"
    families = {
        name: family_payload(name, current, realized)
        for name in ("cot", "macro", "combined")
    }

    return {
        "market": market,
        "dataset": dataset,
        "model_version": MODEL_VERSION,
        "model_spec_hash": MODEL_SPEC_HASH,
        "methodology": {
            "lookahead_safe_cot": True,
            "macro_vintage_safe": False,
            "macro_evidence_status": "CALENDAR_ALIGNED_NOT_VINTAGE_SAFE",
            "cot_release_anchor": (
                "first close on/after canonical CFTC public availability; unresolved release weeks excluded"
            ),
            "unresolved_release_policy": "EXCLUDE",
            "release_calendar_aware": True,
            "release_calendar_hash": calendar_hash(),
            "macro_alignment": (
                "last dated macro observation on or before canonical COT availability; present-day revised series may remain"
            ),
            "sample_independence_policy": (
                "report raw observations, horizon-specific non-overlapping samples, contiguous regime episodes, "
                "and effective_n=min(non_overlapping_n, regime_episode_n)"
            ),
            "non_overlapping_definition": (
                "selected signal indices must be separated by at least the forward horizon in trading days"
            ),
            "regime_episode_definition": (
                "contiguous weekly matches to the regime rule collapse to one episode"
            ),
            "cot_state_thresholds": (
                f"bullish >={BULLISH_THRESHOLD:g}, bearish <={BEARISH_THRESHOLD:g}, otherwise neutral"
            ),
            "macro_state_thresholds": (
                f"bullish >={BULLISH_THRESHOLD:g}, bearish <={BEARISH_THRESHOLD:g}, otherwise neutral"
            ),
        },
        "current": current,
        "families": families,
        "regime_history": [
            {
                "report_date": row["report_date"],
                "release_target_date": row["release_target_date"],
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
        "excluded_unresolved_release_rows": excluded_unresolved,
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
        "schema_version": 3,
        "research_generation": "release-corrected-v2",
        "information_contract_version": "cftc-public-availability-v2",
        "release_calendar_hash": calendar_hash(),
        "macro_vintage_safe": False,
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
            if built is not None:
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
    print(
        f"Saved {OUT} ({OUT.stat().st_size:,} bytes; "
        f"macro history {payload['macro_history_points']} points)"
    )


if __name__ == "__main__":
    main()
