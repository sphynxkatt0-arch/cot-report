#!/usr/bin/env python3
"""Build release-corrected regime-conditioned COT/macro research."""

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
MACRO_VINTAGE_SAFE = False
MACRO_EVIDENCE_STATUS = "CALENDAR_ALIGNED_NOT_VINTAGE_SAFE"


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


def confidence(n: float) -> str:
    if n >= 40:
        return "High"
    if n >= 20:
        return "Medium"
    return "Low"


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


def score_from_row(row: dict[str, Any]) -> float | None:
    for key in MACRO_SCORE_KEYS:
        value = finite(row.get(key))
        if value is not None and 0 <= value <= 100:
            return value
    return None


def transmission_state(row: dict[str, Any]) -> str:
    clean = [
        value
        for value in (finite(row.get(key)) for key in TRANSMISSION_KEYS)
        if value is not None
    ]
    if len(clean) < 2:
        return "unavailable"
    easing = sum(value < 0 for value in clean)
    tightening = sum(value > 0 for value in clean)
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
        output.append({
            "date": parsed,
            "date_str": parsed.isoformat(),
            "score": score,
            "transmission": transmission_state(row),
            "raw": row,
            "macro_vintage_safe": MACRO_VINTAGE_SAFE,
        })
    deduplicated = {row["date"]: row for row in sorted(output, key=lambda item: item["date"])}
    return [deduplicated[key] for key in sorted(deduplicated)]


def macro_on_or_before(rows: list[dict[str, Any]], target: date) -> dict[str, Any] | None:
    if not rows:
        return None
    idx = bisect_right([row["date"] for row in rows], target) - 1
    return rows[idx] if idx >= 0 else None


def autocorrelation(values: list[float], lag: int) -> float | None:
    n = len(values)
    if lag <= 0 or lag >= n or n < 3:
        return None
    mean = statistics.mean(values)
    denominator = sum((value - mean) ** 2 for value in values)
    if denominator <= 1e-12:
        return 0.0
    numerator = sum(
        (values[index] - mean) * (values[index - lag] - mean)
        for index in range(lag, n)
    )
    return numerator / denominator


def horizon_overlap_lags(horizon: str) -> int:
    trading_days = int(cot_bt.HORIZONS[horizon])
    horizon_weeks = max(1, math.ceil(trading_days / 5))
    return max(0, horizon_weeks - 1)


def effective_sample_size(values: list[float], max_lag: int) -> float:
    n = len(values)
    if n == 0:
        return 0.0
    if n == 1 or max_lag <= 0:
        return float(n)
    max_lag = min(max_lag, n - 1)
    variance_inflation = 1.0
    for lag in range(1, max_lag + 1):
        rho = autocorrelation(values, lag)
        if rho is None:
            continue
        weight = 1.0 - lag / (max_lag + 1.0)
        variance_inflation += 2.0 * weight * rho
    if variance_inflation <= 1e-9:
        return float(n)
    return max(1.0, min(float(n), n / variance_inflation))


def non_overlapping_records(records: list[dict[str, Any]], horizon: str) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    last_exit: date | None = None
    for row in sorted(records, key=lambda item: item["signal_date"]):
        result = (row.get("horizons") or {}).get(horizon)
        if not result:
            continue
        signal_date = date.fromisoformat(str(row["signal_date"]))
        exit_date = cot_bt.parse_date(result.get("exit_date"))
        if exit_date is None:
            continue
        if last_exit is None or signal_date > last_exit:
            selected.append(row)
            last_exit = exit_date
    return selected


def family_matcher(name: str, current: dict[str, Any]) -> Callable[[dict[str, Any]], bool]:
    if name == "cot":
        return lambda row: row.get("cot_state") == current.get("cot_state")
    if name == "macro":
        return lambda row: row.get("macro_state") == current.get("macro_state")
    return lambda row: (
        row.get("cot_state") == current.get("cot_state")
        and row.get("macro_state") == current.get("macro_state")
    )


def regime_episode_count(
    history: list[dict[str, Any]],
    matcher: Callable[[dict[str, Any]], bool],
    horizon: str | None = None,
) -> int:
    count = 0
    in_episode = False
    episode_has_usable = False
    for row in sorted(history, key=lambda item: item["signal_date"]):
        matched = matcher(row)
        if matched:
            if not in_episode:
                in_episode = True
                episode_has_usable = False
            if horizon is None or horizon in (row.get("horizons") or {}):
                episode_has_usable = True
            continue
        if in_episode:
            if episode_has_usable:
                count += 1
            in_episode = False
            episode_has_usable = False
    if in_episode and episode_has_usable:
        count += 1
    return count


def summary(
    records: list[dict[str, Any]],
    horizon: str,
    baseline: list[dict[str, Any]],
    full_history: list[dict[str, Any]],
    matcher: Callable[[dict[str, Any]], bool],
) -> dict[str, Any]:
    returns = [
        float(row["horizons"][horizon]["return_pct"])
        for row in records
        if horizon in (row.get("horizons") or {})
    ]
    drawdowns = [
        float(row["horizons"][horizon]["max_drawdown_pct"])
        for row in records
        if horizon in (row.get("horizons") or {})
        and row["horizons"][horizon].get("max_drawdown_pct") is not None
    ]
    base_returns = [
        float(row["horizons"][horizon]["return_pct"])
        for row in baseline
        if horizon in (row.get("horizons") or {})
    ]

    episode_n = regime_episode_count(full_history, matcher, horizon)
    non_overlap = non_overlapping_records(records, horizon)
    non_overlap_returns = [
        float(row["horizons"][horizon]["return_pct"])
        for row in non_overlap
    ]
    effective_n = effective_sample_size(returns, horizon_overlap_lags(horizon))
    confidence_basis = (
        min(
            effective_n,
            float(episode_n),
            float(len(non_overlap_returns)),
        )
        if returns
        else 0.0
    )

    if not returns:
        return {
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
            "effective_n": 0.0,
            "regime_episode_n": episode_n,
            "non_overlapping_observations": 0,
            "non_overlapping_mean_return_pct": None,
            "non_overlapping_median_return_pct": None,
            "non_overlapping_hit_rate_pct": None,
            "baseline_return_pct": None,
            "excess_return_pct": None,
            "confidence_basis_n": 0.0,
            "confidence": "Low",
        }

    avg = statistics.mean(returns)
    std = statistics.pstdev(returns) if len(returns) >= 2 else 0.0
    baseline_avg = statistics.mean(base_returns) if base_returns else None
    non_overlap_avg = statistics.mean(non_overlap_returns) if non_overlap_returns else None
    non_overlap_median = statistics.median(non_overlap_returns) if non_overlap_returns else None
    non_overlap_hit = (
        sum(value > 0 for value in non_overlap_returns) / len(non_overlap_returns) * 100.0
        if non_overlap_returns
        else None
    )

    return {
        "mean_return_pct": round(avg, 4),
        "median_return_pct": round(statistics.median(returns), 4),
        "hit_rate_pct": round(sum(value > 0 for value in returns) / len(returns) * 100.0, 2),
        "q10_return_pct": round(quantile(returns, 0.10), 4),
        "q25_return_pct": round(quantile(returns, 0.25), 4),
        "q75_return_pct": round(quantile(returns, 0.75), 4),
        "q90_return_pct": round(quantile(returns, 0.90), 4),
        "worst_return_pct": round(min(returns), 4),
        "max_drawdown_pct": round(min(drawdowns), 4) if drawdowns else None,
        "risk_adjusted": round(avg / std, 3) if std > 1e-12 else None,
        "observations": len(returns),
        "effective_n": round(effective_n, 2),
        "regime_episode_n": episode_n,
        "non_overlapping_observations": len(non_overlap_returns),
        "non_overlapping_mean_return_pct": round(non_overlap_avg, 4) if non_overlap_avg is not None else None,
        "non_overlapping_median_return_pct": round(non_overlap_median, 4) if non_overlap_median is not None else None,
        "non_overlapping_hit_rate_pct": round(non_overlap_hit, 2) if non_overlap_hit is not None else None,
        "baseline_return_pct": round(baseline_avg, 4) if baseline_avg is not None else None,
        "excess_return_pct": round(avg - baseline_avg, 4) if baseline_avg is not None else None,
        "confidence_basis_n": round(confidence_basis, 2),
        "confidence": confidence(confidence_basis),
    }


def extreme_count_at(rows: list[dict[str, Any]], index: int, categories: list[str]) -> int:
    count = 0
    for key in categories:
        field = f"{key}_net_oi_pct"
        current = finite(rows[index].get(field))
        if current is None:
            continue
        clean = [
            value
            for value in (finite(row.get(field)) for row in rows[: index + 1])
            if value is not None
        ]
        rank = cot_bt.percentile_rank(clean, current) if clean else None
        if rank is not None and (rank >= EXTREME_UPPER or rank <= EXTREME_LOWER):
            count += 1
    return count


def family_payload(
    name: str,
    current: dict[str, Any],
    history: list[dict[str, Any]],
) -> dict[str, Any]:
    matcher = family_matcher(name, current)
    selected = [row for row in history if matcher(row)]
    if name == "cot":
        rule = f"COT state = {current['cot_state']}"
    elif name == "macro":
        rule = f"Macro state = {current['macro_state']}"
    else:
        rule = f"COT {current['cot_state']} + Macro {current['macro_state']}"

    horizons = {
        label: summary(selected, label, history, history, matcher)
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
            0.0
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
        analogs.append({
            "report_date": row["report_date"],
            "signal_date": row["signal_date"],
            "cot_score": round(row["cot_score"], 2),
            "cot_score_delta_4w": round(row.get("cot_score_delta_4w") or 0, 2),
            "extreme_count": int(row.get("extreme_count") or 0),
            "macro_score": round(row["macro_score"], 2) if row.get("macro_score") is not None else None,
            "macro_vintage_safe": False,
            "transmission_state": row.get("transmission_state"),
            "distance": round(distance, 3),
            "returns": {
                key: round(value["return_pct"], 3)
                for key, value in row["horizons"].items()
            },
        })

    return {
        "name": name,
        "match_rule": rule,
        "sample_size": len(selected),
        "regime_episode_n": regime_episode_count(history, matcher),
        "minimum_recommended_sample": MIN_SAMPLE,
        "macro_vintage_safe": False,
        "macro_directional_weight": 0.0,
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
        prior_score = (
            cot_bt.score_at(rows, prior, dataset, categories)
            if prior != index
            else cot_score
        )
        score_delta = cot_score - prior_score if prior_score is not None else 0.0
        extreme_count = extreme_count_at(rows, index, categories)

        horizons: dict[str, Any] = {}
        for label, steps in cot_bt.HORIZONS.items():
            result = cot_bt.horizon_result(prices, signal_index, steps)
            if result is not None:
                horizons[label] = result

        history.append({
            "report_date": report_date.isoformat(),
            "release_target_date": release_target.isoformat(),
            "availability_at": release_meta["availability_at_utc"],
            "availability_source": release_meta["availability_source_type"],
            "signal_date": prices[signal_index]["date_str"],
            "cot_score": cot_score,
            "cot_score_delta_4w": score_delta,
            "extreme_count": extreme_count,
            "macro_score": macro_score,
            "macro_observation_date": macro["date_str"] if macro else None,
            "macro_vintage_safe": False,
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
        "macro_vintage_safe",
        "cot_state",
        "macro_state",
        "transmission_state",
    )
    current = {key: latest[key] for key in keys}
    current["combined_state"] = f"{current['cot_state']} COT / {current['macro_state']} macro"
    current["macro_directional_weight"] = 0.0

    families = {
        name: family_payload(name, current, realized)
        for name in ("cot", "macro", "combined")
    }

    methodology = {
        "lookahead_safe_cot": True,
        "macro_vintage_safe": False,
        "macro_evidence_status": MACRO_EVIDENCE_STATUS,
        "macro_directional_weight": 0.0,
        "cot_release_anchor": "first close on/after canonical CFTC public availability; unresolved release weeks excluded",
        "unresolved_release_policy": "EXCLUDE",
        "release_calendar_aware": True,
        "release_calendar_hash": calendar_hash(),
        "macro_alignment": "last dated macro observation on or before canonical COT availability; present-day revised series may remain",
        "dependency_reporting": "raw weekly n + Bartlett effective_n + contiguous regime_episode_n + greedy non-overlapping forward windows",
        "confidence_basis": "minimum of effective_n, regime_episode_n and non-overlapping observations",
        "cot_state_thresholds": f"bullish >={BULLISH_THRESHOLD:g}, bearish <={BEARISH_THRESHOLD:g}, otherwise neutral",
        "macro_state_thresholds": f"bullish >={BULLISH_THRESHOLD:g}, bearish <={BEARISH_THRESHOLD:g}, otherwise neutral",
    }

    regime_history = [
        {
            "report_date": row["report_date"],
            "release_target_date": row["release_target_date"],
            "signal_date": row["signal_date"],
            "cot_state": row["cot_state"],
            "cot_score_delta_4w": round(row.get("cot_score_delta_4w") or 0, 2),
            "extreme_count": int(row.get("extreme_count") or 0),
            "macro_state": row["macro_state"],
            "macro_vintage_safe": False,
            "transmission_state": row["transmission_state"],
            "combined_state": f"{row['cot_state']} COT / {row['macro_state']} macro",
        }
        for row in history[-260:]
    ]

    return {
        "market": market,
        "dataset": dataset,
        "model_version": MODEL_VERSION,
        "model_spec_hash": MODEL_SPEC_HASH,
        "methodology": methodology,
        "current": current,
        "families": families,
        "regime_history": regime_history,
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
        "macro_evidence_status": MACRO_EVIDENCE_STATUS,
        "macro_directional_weight": 0.0,
        "provenance": {
            "cot_release_lookahead_safe": True,
            "macro_vintage_safe": False,
            "macro_alignment_only": True,
            "dependency_adjusted_reporting": True,
        },
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
            built = build_market_dataset(
                market,
                dataset,
                payload,
                prices.get(market),
                macro_rows,
            )
            if built is not None:
                result["markets"].setdefault(market, {"datasets": {}})["datasets"][dataset] = built

    if not result["markets"]:
        raise RuntimeError("No regime backtests could be built")
    return result


def main() -> None:
    WORLDCLASS.mkdir(parents=True, exist_ok=True)
    payload = build()
    temp = OUT.with_suffix(".json.tmp")
    temp.write_text(
        json.dumps(payload, separators=(",", ":")), encoding="utf-8"
    )
    temp.replace(OUT)
    print(
        f"Saved {OUT} ({OUT.stat().st_size:,} bytes; "
        f"macro history {payload['macro_history_points']} points; macro vintage safe=false)"
    )


if __name__ == "__main__":
    main()
