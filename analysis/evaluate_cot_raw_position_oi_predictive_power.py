#!/usr/bin/env python3
"""Lookahead-safe raw COT position-count and open-interest predictive-power study.

Extends the governed actor predictive-power research with raw contract counts,
open-interest variables, scale-normalized versions, and actor-flow x OI interactions.

Information contract:
- COT snapshot is Tuesday.
- Public information is first eligible after Friday release (Tuesday + 3 days).
- Percentiles are expanding-history transforms only.
- Discovery is pre-2022; 2022+ is untouched holdout.
- OLS coefficients and tail cutoffs are frozen from discovery before holdout.
- Longer-horizon correlation confirmation uses greedy non-overlapping episodes.
"""
from __future__ import annotations

import json
import math
import statistics
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import build_cot_actor_event_research as actor_research
import evaluate_cot_actor_predictive_power as base_pp

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "worldclass" / "research" / "cot-raw-position-oi-predictive-power.json"
SUMMARY_OUT = ROOT / "worldclass" / "research" / "cot-raw-position-oi-predictive-power-summary.json"

HORIZONS = tuple(actor_research.EXACT_WEEKDAYS) + tuple(actor_research.FORWARD_HORIZONS)
HOLDOUT_START = actor_research.HOLDOUT_START

ACTOR_PREDICTORS: dict[str, dict[str, Any]] = {
    "net_contracts": {"description": "actor net position in raw contracts", "family": "raw_position_level", "scale_sensitive": True},
    "long_contracts": {"description": "actor gross long position in raw contracts", "family": "raw_position_level", "scale_sensitive": True},
    "short_contracts": {"description": "actor gross short position in raw contracts", "family": "raw_position_level", "scale_sensitive": True},
    "net_contracts_percentile": {"description": "expanding historical percentile of actor raw net contracts", "family": "raw_position_level_normalized", "scale_sensitive": False},
    "delta_net_contracts": {"description": "weekly change in actor raw net contracts", "family": "raw_position_flow", "scale_sensitive": True},
    "delta_long_contracts": {"description": "weekly change in actor raw long contracts", "family": "raw_position_flow", "scale_sensitive": True},
    "delta_short_contracts": {"description": "weekly change in actor raw short contracts", "family": "raw_position_flow", "scale_sensitive": True},
    "signed_delta_net_contracts_percentile": {"description": "expanding percentile of absolute weekly raw-net change with ADD/CUT sign", "family": "raw_position_flow_normalized", "scale_sensitive": False},
    "net_oi_pct": {"description": "actor net position as percent of open interest", "family": "oi_normalized_position", "scale_sensitive": False},
    "long_oi_pct": {"description": "actor gross long contracts as percent of open interest", "family": "oi_normalized_position", "scale_sensitive": False},
    "short_oi_pct": {"description": "actor gross short contracts as percent of open interest", "family": "oi_normalized_position", "scale_sensitive": False},
    "delta_1w_net_oi_pp": {"description": "weekly change in actor net/OI position in percentage points", "family": "oi_normalized_flow", "scale_sensitive": False},
    "position_percentile": {"description": "expanding historical percentile of actor net/OI position", "family": "oi_normalized_position", "scale_sensitive": False, "benchmark_from_prior_study": True},
    "signed_change_percentile": {"description": "expanding percentile of abs weekly net/OI change with ADD/CUT sign", "family": "oi_normalized_flow", "scale_sensitive": False, "benchmark_from_prior_study": True},
}

OI_PREDICTORS: dict[str, dict[str, Any]] = {
    "open_interest": {"description": "total market open interest in raw contracts", "family": "open_interest_level", "scale_sensitive": True},
    "open_interest_percentile": {"description": "expanding historical percentile of total open interest", "family": "open_interest_level_normalized", "scale_sensitive": False},
    "delta_open_interest": {"description": "weekly change in total open interest contracts", "family": "open_interest_flow", "scale_sensitive": True},
    "delta_open_interest_pct": {"description": "weekly percent change in total open interest", "family": "open_interest_flow_normalized", "scale_sensitive": False},
    "signed_delta_open_interest_percentile": {"description": "expanding percentile of absolute weekly OI change with sign", "family": "open_interest_flow_normalized", "scale_sensitive": False},
}

AUGMENTED_MODEL_SPECS = {
    "raw_net_flow_plus_oi_pct": ("delta_net_contracts", "delta_open_interest_pct"),
    "net_oi_flow_plus_oi_pct": ("delta_1w_net_oi_pp", "delta_open_interest_pct"),
    "position_ratio_plus_oi_level": ("net_oi_pct", "open_interest_percentile"),
    "signed_flow_percentiles": ("signed_change_percentile", "signed_delta_open_interest_percentile"),
}

INTERACTION_CONFIGS = ("ADD_OI_ADD", "ADD_OI_CUT", "CUT_OI_ADD", "CUT_OI_CUT")
INTERACTION_THRESHOLD = 75.0


def finite(value: Any) -> float | None:
    return base_pp.finite(value)


def r6(value: float | None) -> float | None:
    return base_pp.r6(value)


def parse_date(value: Any) -> date | None:
    return base_pp.parse_date(value)


def sign(value: float | None) -> int:
    if value is None or abs(value) <= 1e-12:
        return 0
    return 1 if value > 0 else -1


def signed_percentile(magnitude_percentile: float | None, delta: float | None) -> float | None:
    if magnitude_percentile is None or delta is None:
        return None
    s = sign(delta)
    if s == 0:
        return 0.0
    return float(magnitude_percentile) * s


def actor_net(row: dict[str, Any], actor: str) -> float | None:
    return actor_research.actor_net_value(row, actor)


def actor_side(row: dict[str, Any], actor: str, side: str) -> float | None:
    return actor_research.actor_side_value(row, actor, side)


def row_features(payload: dict[str, Any], actor: str) -> dict[str, dict[str, Any]]:
    """Build lookahead-safe raw actor/OI features keyed by Tuesday report date."""
    rows = [row for row in (payload.get("records") or []) if isinstance(row, dict) and parse_date(row.get("date")) is not None]
    rows.sort(key=lambda row: str(row.get("date")))
    out: dict[str, dict[str, Any]] = {}

    oi_history: list[float] = []
    oi_change_magnitude_history: list[float] = []
    net_history: list[float] = []
    net_change_magnitude_history: list[float] = []

    for i, row in enumerate(rows):
        report_date = parse_date(row.get("date"))
        if report_date is None:
            continue

        oi = finite(row.get("open_interest"))
        long_pos = actor_side(row, actor, "long")
        short_pos = actor_side(row, actor, "short")
        net_pos = actor_net(row, actor)

        prev = rows[i - 1] if i > 0 else None
        prev_oi = finite(prev.get("open_interest")) if prev else None
        prev_long = actor_side(prev, actor, "long") if prev else None
        prev_short = actor_side(prev, actor, "short") if prev else None
        prev_net = actor_net(prev, actor) if prev else None

        d_oi = oi - prev_oi if oi is not None and prev_oi is not None else None
        d_oi_pct = (oi / prev_oi - 1.0) * 100.0 if oi is not None and prev_oi not in (None, 0) else None
        d_long = long_pos - prev_long if long_pos is not None and prev_long is not None else None
        d_short = short_pos - prev_short if short_pos is not None and prev_short is not None else None
        d_net = net_pos - prev_net if net_pos is not None and prev_net is not None else None

        if oi is not None:
            oi_history.append(oi)
        if d_oi is not None:
            oi_change_magnitude_history.append(abs(d_oi))
        if net_pos is not None:
            net_history.append(net_pos)
        if d_net is not None:
            net_change_magnitude_history.append(abs(d_net))

        oi_pctile = actor_research.percentile_rank(oi_history, oi) if oi is not None else None
        oi_change_pctile = actor_research.percentile_rank(oi_change_magnitude_history, abs(d_oi)) if d_oi is not None else None
        net_pctile = actor_research.percentile_rank(net_history, net_pos) if net_pos is not None else None
        net_change_pctile = actor_research.percentile_rank(net_change_magnitude_history, abs(d_net)) if d_net is not None else None

        net_oi_pct = finite(row.get(f"{actor}_net_oi_pct"))
        long_oi_pct = long_pos / oi * 100.0 if long_pos is not None and oi not in (None, 0) else None
        short_oi_pct = short_pos / oi * 100.0 if short_pos is not None and oi not in (None, 0) else None

        out[report_date.isoformat()] = {
            "open_interest": r6(oi),
            "open_interest_percentile": r6(oi_pctile),
            "delta_open_interest": r6(d_oi),
            "delta_open_interest_pct": r6(d_oi_pct),
            "delta_open_interest_magnitude_percentile": r6(oi_change_pctile),
            "signed_delta_open_interest_percentile": r6(signed_percentile(oi_change_pctile, d_oi)),
            "net_contracts": r6(net_pos),
            "long_contracts": r6(long_pos),
            "short_contracts": r6(short_pos),
            "net_contracts_percentile": r6(net_pctile),
            "delta_net_contracts": r6(d_net),
            "delta_long_contracts": r6(d_long),
            "delta_short_contracts": r6(d_short),
            "delta_net_contracts_magnitude_percentile": r6(net_change_pctile),
            "signed_delta_net_contracts_percentile": r6(signed_percentile(net_change_pctile, d_net)),
            "net_oi_pct": r6(net_oi_pct),
            "long_oi_pct": r6(long_oi_pct),
            "short_oi_pct": r6(short_oi_pct),
        }
    return out


def enrich_events(payload: dict[str, Any], actor: str, events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    features = row_features(payload, actor)
    enriched = []
    for event in events:
        feature = features.get(str(event.get("report_date")))
        if not feature:
            continue
        row = dict(event)
        row.update(feature)
        enriched.append(row)
    return enriched


def predictor_value(event: dict[str, Any], predictor: str) -> float | None:
    if predictor == "signed_change_percentile":
        return base_pp.predictor_value(event, predictor)
    return finite(event.get(predictor))


def aligned(events: list[dict[str, Any]], predictor: str, horizon: str) -> list[tuple[dict[str, Any], float, float]]:
    rows = []
    for event in events:
        x = predictor_value(event, predictor)
        y = base_pp.horizon_value(event, horizon)
        if x is None or y is None:
            continue
        rows.append((event, x, y))
    return rows


def predictive_metric(events: list[dict[str, Any]], predictor: str, horizon: str) -> dict[str, Any]:
    rows = aligned(events, predictor, horizon)
    discovery = [row for row in rows if (parse_date(row[0].get("report_date")) or date.max) < HOLDOUT_START]
    holdout = [row for row in rows if (parse_date(row[0].get("report_date")) or date.min) >= HOLDOUT_START]
    independent = base_pp.non_overlapping(holdout, horizon)
    return {
        "full_history": base_pp.correlation_block(rows),
        "discovery_pre_2022": base_pp.correlation_block(discovery),
        "holdout_2022_plus": base_pp.correlation_block(holdout),
        "holdout_non_overlapping": base_pp.correlation_block(independent),
        "oos_forecast": base_pp.oos_forecast(discovery, holdout),
        "holdout_tail_spread": base_pp.holdout_tail_spread(discovery, holdout),
        "era_stability": base_pp.era_blocks(rows),
    }


def solve_linear_system(matrix: list[list[float]], vector: list[float]) -> list[float] | None:
    """Small Gaussian-elimination solver with partial pivoting."""
    n = len(vector)
    a = [list(map(float, row)) + [float(vector[i])] for i, row in enumerate(matrix)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda r: abs(a[r][col]))
        if abs(a[pivot][col]) <= 1e-12:
            return None
        if pivot != col:
            a[col], a[pivot] = a[pivot], a[col]
        scale = a[col][col]
        a[col] = [v / scale for v in a[col]]
        for row in range(n):
            if row == col:
                continue
            factor = a[row][col]
            if abs(factor) <= 1e-18:
                continue
            a[row] = [x - factor * y for x, y in zip(a[row], a[col])]
    return [a[i][-1] for i in range(n)]


def multi_fit(rows: list[tuple[dict[str, Any], list[float], float]]) -> list[float] | None:
    if len(rows) < 5:
        return None
    p = len(rows[0][1]) + 1
    xtx = [[0.0] * p for _ in range(p)]
    xty = [0.0] * p
    for _, xs, y in rows:
        v = [1.0] + [float(x) for x in xs]
        for i in range(p):
            xty[i] += v[i] * y
            for j in range(p):
                xtx[i][j] += v[i] * v[j]
    return solve_linear_system(xtx, xty)


def model_rows(events: list[dict[str, Any]], predictors: tuple[str, ...], horizon: str) -> list[tuple[dict[str, Any], list[float], float]]:
    rows = []
    for event in events:
        xs = [predictor_value(event, predictor) for predictor in predictors]
        y = base_pp.horizon_value(event, horizon)
        if y is None or any(x is None for x in xs):
            continue
        rows.append((event, [float(x) for x in xs if x is not None], float(y)))
    return rows


def predict(coefficients: list[float], xs: list[float]) -> float:
    return coefficients[0] + sum(b * x for b, x in zip(coefficients[1:], xs))


def multivariate_oos(events: list[dict[str, Any]], base_predictor: str, oi_predictor: str, horizon: str) -> dict[str, Any]:
    aug_rows = model_rows(events, (base_predictor, oi_predictor), horizon)
    discovery = [r for r in aug_rows if (parse_date(r[0].get("report_date")) or date.max) < HOLDOUT_START]
    holdout = [r for r in aug_rows if (parse_date(r[0].get("report_date")) or date.min) >= HOLDOUT_START]
    if len(discovery) < 20 or len(holdout) < 10:
        return {"holdout_n": len(holdout)}

    means = [statistics.mean(row[1][j] for row in discovery) for j in range(2)]
    stds = [statistics.pstdev(row[1][j] for row in discovery) for j in range(2)]
    if any(s <= 1e-12 for s in stds):
        return {"holdout_n": len(holdout), "note": "zero discovery variance"}

    def scaled(rows: list[tuple[dict[str, Any], list[float], float]]) -> list[tuple[dict[str, Any], list[float], float]]:
        return [(event, [(xs[j] - means[j]) / stds[j] for j in range(2)], y) for event, xs, y in rows]

    d_scaled = scaled(discovery)
    h_scaled = scaled(holdout)
    base_discovery = [(event, [xs[0]], y) for event, xs, y in d_scaled]
    base_fit = multi_fit(base_discovery)
    aug_fit = multi_fit(d_scaled)
    if base_fit is None or aug_fit is None:
        return {"holdout_n": len(holdout), "note": "singular discovery design"}

    train_mean = statistics.mean(y for _, _, y in d_scaled)
    actual = [y for _, _, y in h_scaled]
    base_pred = [predict(base_fit, [xs[0]]) for _, xs, _ in h_scaled]
    aug_pred = [predict(aug_fit, xs) for _, xs, _ in h_scaled]
    mean_pred = [train_mean] * len(actual)

    sse_mean = sum((y - p) ** 2 for y, p in zip(actual, mean_pred))
    sse_base = sum((y - p) ** 2 for y, p in zip(actual, base_pred))
    sse_aug = sum((y - p) ** 2 for y, p in zip(actual, aug_pred))
    if sse_mean <= 0:
        return {"holdout_n": len(actual)}

    base_r2 = 1.0 - sse_base / sse_mean
    augmented_r2 = 1.0 - sse_aug / sse_mean
    incremental_vs_base = 1.0 - sse_aug / sse_base if sse_base > 0 else None
    base_rmse = math.sqrt(sse_base / len(actual))
    aug_rmse = math.sqrt(sse_aug / len(actual))
    return {
        "holdout_n": len(actual),
        "base_predictor": base_predictor,
        "oi_predictor": oi_predictor,
        "standardization": "discovery mean/std frozen into holdout",
        "base_oos_r2": r6(base_r2),
        "augmented_oos_r2": r6(augmented_r2),
        "oos_r2_gain": r6(augmented_r2 - base_r2),
        "incremental_r2_vs_base_model": r6(incremental_vs_base),
        "base_rmse_pct": r6(base_rmse),
        "augmented_rmse_pct": r6(aug_rmse),
        "rmse_improvement_vs_base_pct": r6((base_rmse - aug_rmse) / base_rmse * 100.0 if base_rmse > 0 else None),
        "base_coefficients_standardized": [r6(v) for v in base_fit],
        "augmented_coefficients_standardized": [r6(v) for v in aug_fit],
    }


def fisher_p_approx(rho: float | None, n: int) -> float | None:
    if rho is None or n <= 3 or abs(rho) >= 1:
        return None
    z = abs(math.atanh(rho)) * math.sqrt(n - 3)
    return math.erfc(z / math.sqrt(2.0))


def overlap_classification(metric: dict[str, Any]) -> str:
    discovery = metric.get("discovery_pre_2022") or {}
    holdout = metric.get("holdout_2022_plus") or {}
    independent = metric.get("holdout_non_overlapping") or {}
    oos = metric.get("oos_forecast") or {}
    r2 = finite(oos.get("oos_r2"))
    rmse = finite(oos.get("rmse_improvement_pct"))
    d = finite(discovery.get("spearman_rho"))
    h = finite(holdout.get("spearman_rho"))
    i = finite(independent.get("spearman_rho"))
    hn = int(holdout.get("n") or 0)
    inn = int(independent.get("n") or 0)
    positive_gain = r2 is not None and r2 > 0 and rmse is not None and rmse > 0
    confirmed = positive_gain and hn >= 30 and inn >= 20 and d is not None and h is not None and i is not None and abs(h) >= 0.10 and abs(i) >= 0.10 and d * h > 0 and h * i > 0
    if confirmed:
        return "OVERLAP_CONFIRMED_OOS"
    if positive_gain:
        return "POSITIVE_OOS_GAIN_NOT_OVERLAP_CONFIRMED"
    return "NO_OOS_GAIN"


def apply_bh(rows: list[dict[str, Any]], p_key: str, q_key: str) -> None:
    eligible = [(idx, finite(row.get(p_key))) for idx, row in enumerate(rows)]
    eligible = [(idx, p) for idx, p in eligible if p is not None]
    eligible.sort(key=lambda pair: pair[1])
    m = len(eligible)
    qvals: list[float | None] = [None] * len(rows)
    running = 1.0
    for pos in range(m - 1, -1, -1):
        idx, p = eligible[pos]
        rank = pos + 1
        running = min(running, min(1.0, float(p) * m / rank))
        qvals[idx] = running
    for idx, row in enumerate(rows):
        row[q_key] = r6(qvals[idx])


def compact_row(series: str, scope: str, predictor: str, predictor_meta: dict[str, Any], horizon: str, metric: dict[str, Any]) -> dict[str, Any]:
    discovery = metric.get("discovery_pre_2022") or {}
    holdout = metric.get("holdout_2022_plus") or {}
    independent = metric.get("holdout_non_overlapping") or {}
    oos = metric.get("oos_forecast") or {}
    tails = metric.get("holdout_tail_spread") or {}
    irho = finite(independent.get("spearman_rho"))
    inn = int(independent.get("n") or 0)
    p = fisher_p_approx(irho, inn)
    return {
        "series": series,
        "scope": scope,
        "predictor": predictor,
        "predictor_family": predictor_meta["family"],
        "scale_sensitive": bool(predictor_meta.get("scale_sensitive")),
        "horizon": horizon,
        "overlap_classification": overlap_classification(metric),
        "discovery_n": discovery.get("n"),
        "discovery_spearman_rho": discovery.get("spearman_rho"),
        "holdout_n": holdout.get("n"),
        "holdout_pearson_r": holdout.get("pearson_r"),
        "holdout_spearman_rho": holdout.get("spearman_rho"),
        "independent_n": inn,
        "independent_spearman_rho": independent.get("spearman_rho"),
        "independent_spearman_p_approx": r6(p),
        "oos_r2": oos.get("oos_r2"),
        "rmse_improvement_pct": oos.get("rmse_improvement_pct"),
        "direction_lift_pp": oos.get("direction_lift_pp"),
        "holdout_p90_minus_p10_spread_pp": tails.get("holdout_p90_minus_p10_spread_pp"),
    }


def finalize_fdr(rows: list[dict[str, Any]]) -> None:
    apply_bh(rows, "independent_spearman_p_approx", "global_fdr_q")
    by_family: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_family[str(row.get("predictor_family"))].append(row)
    for family_rows in by_family.values():
        apply_bh(family_rows, "independent_spearman_p_approx", "family_fdr_q")

    for row in rows:
        base = row["overlap_classification"]
        gq = finite(row.get("global_fdr_q"))
        fq = finite(row.get("family_fdr_q"))
        if base == "OVERLAP_CONFIRMED_OOS" and gq is not None and gq <= 0.05:
            label = "GLOBAL_FDR05_OOS"
        elif base == "OVERLAP_CONFIRMED_OOS" and gq is not None and gq <= 0.10:
            label = "GLOBAL_FDR10_OOS"
        elif base == "OVERLAP_CONFIRMED_OOS" and fq is not None and fq <= 0.05:
            label = "FAMILY_FDR05_OOS"
        elif base == "OVERLAP_CONFIRMED_OOS" and fq is not None and fq <= 0.10:
            label = "FAMILY_FDR10_OOS"
        elif base == "OVERLAP_CONFIRMED_OOS":
            label = "OVERLAP_CONFIRMED_NOT_FDR"
        else:
            label = base
        row["final_classification"] = label


def interaction_config(event: dict[str, Any]) -> str | None:
    actor_delta = finite(event.get("delta_net_contracts"))
    oi_delta = finite(event.get("delta_open_interest"))
    a = sign(actor_delta)
    o = sign(oi_delta)
    if a == 0 or o == 0:
        return None
    return ("ADD" if a > 0 else "CUT") + "_OI_" + ("ADD" if o > 0 else "CUT")


def interaction_block(events: list[dict[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for config in INTERACTION_CONFIGS:
        all_rows = [e for e in events if interaction_config(e) == config]
        extreme_rows = [e for e in all_rows if (finite(e.get("delta_net_contracts_magnitude_percentile")) or -1) >= INTERACTION_THRESHOLD and (finite(e.get("delta_open_interest_magnitude_percentile")) or -1) >= INTERACTION_THRESHOLD]
        config_block = {}
        for label, selected in (("all_sign_events", all_rows), ("joint_p75_magnitude", extreme_rows)):
            config_block[label] = {
                "full_history": {h: actor_research.metrics_for_condition(selected, events, h) for h in HORIZONS},
                "discovery_pre_2022": {h: actor_research.metrics_for_condition(selected, events, h, None, HOLDOUT_START - timedelta(days=1)) for h in HORIZONS},
                "holdout_2022_plus": {h: actor_research.metrics_for_condition(selected, events, h, HOLDOUT_START, None) for h in HORIZONS},
            }
        result[config] = config_block
    return result


def class_order(label: str) -> int:
    return {"GLOBAL_FDR05_OOS": 0, "GLOBAL_FDR10_OOS": 1, "FAMILY_FDR05_OOS": 2, "FAMILY_FDR10_OOS": 3, "OVERLAP_CONFIRMED_NOT_FDR": 4, "POSITIVE_OOS_GAIN_NOT_OVERLAP_CONFIRMED": 5, "NO_OOS_GAIN": 6}.get(label, 9)


def main() -> None:
    cot_data, prices_payloads = actor_research.robustness.build_full_inputs()

    actor_events: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    market_reference_events: dict[tuple[str, str], list[dict[str, Any]]] = {}

    for dataset in actor_research.DATASETS:
        dataset_payload = cot_data.get(dataset) or {}
        for market in actor_research.SUPPORTED_MARKETS:
            payload = dataset_payload.get(market)
            prices_payload = prices_payloads.get(market)
            if not isinstance(payload, dict) or prices_payload is None:
                continue
            built = actor_research.build_market_actor_events(market, dataset, payload, prices_payload)
            for actor, events in built.items():
                if not events:
                    continue
                enriched = enrich_events(payload, actor, events)
                if not enriched:
                    continue
                actor_events[(dataset, market, actor)] = enriched
                primary_dataset = actor_research.robustness.MARKET_DATASETS.get(market)
                if dataset == primary_dataset:
                    market_reference_events.setdefault((dataset, market), enriched)

    metric_rows: list[dict[str, Any]] = []
    actor_study: dict[str, Any] = {}

    for (dataset, market, actor), events in actor_events.items():
        key = f"{dataset}:{market}:{actor}"
        predictor_block: dict[str, Any] = {}
        for predictor, meta in ACTOR_PREDICTORS.items():
            horizon_block = {}
            for horizon in HORIZONS:
                metric = predictive_metric(events, predictor, horizon)
                horizon_block[horizon] = metric
                metric_rows.append(compact_row(key, "actor", predictor, meta, horizon, metric))
            predictor_block[predictor] = horizon_block

        multivariate = {}
        for model_name, (actor_predictor, oi_predictor) in AUGMENTED_MODEL_SPECS.items():
            multivariate[model_name] = {horizon: multivariate_oos(events, actor_predictor, oi_predictor, horizon) for horizon in HORIZONS}

        actor_study[key] = {"predictors": predictor_block, "oi_incremental_models": multivariate, "actor_flow_x_oi_direction": interaction_block(events)}

    oi_study: dict[str, Any] = {}
    for (dataset, market), events in market_reference_events.items():
        key = f"{dataset}:{market}"
        block = {}
        for predictor, meta in OI_PREDICTORS.items():
            horizon_block = {}
            for horizon in HORIZONS:
                metric = predictive_metric(events, predictor, horizon)
                horizon_block[horizon] = metric
                metric_rows.append(compact_row(key, "market_oi", predictor, meta, horizon, metric))
            block[predictor] = horizon_block
        oi_study[key] = block

    finalize_fdr(metric_rows)
    metric_rows.sort(key=lambda row: (class_order(str(row.get("final_classification"))), finite(row.get("global_fdr_q")) if finite(row.get("global_fdr_q")) is not None else 2.0, -(finite(row.get("oos_r2")) or -999.0), -abs(finite(row.get("independent_spearman_rho")) or 0.0)))

    counts: dict[str, int] = {}
    for row in metric_rows:
        label = str(row.get("final_classification"))
        counts[label] = counts.get(label, 0) + 1

    gold_mm_key = "disaggregated:gold:managed_money"
    gold_mm_rows = [row for row in metric_rows if row["series"] == gold_mm_key]

    output = {
        "schema_version": 1,
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "study": "COT raw position-count and open-interest predictive power",
        "information_contract": {"cot_snapshot": "Tuesday", "public_availability": "Friday = report date + 3 calendar days", "release_anchor": "first market close on/after Friday release target", "lookahead_safe": True, "percentiles": "expanding history only; current report may enter its own rank but no future report is visible"},
        "forecast_contract": {"discovery": "pre-2022", "holdout": "2022+ untouched", "oos_model": "univariate or pre-specified two-feature OLS fit only on discovery and frozen in holdout", "tail_cutoffs": "discovery q10/q90 frozen before holdout", "overlap_control": "greedy non-overlapping forward episodes", "multiplicity": "Benjamini-Hochberg on approximate Fisher-z p-values of non-overlapping Spearman; global and pre-specified predictor-family q-values", "raw_level_caution": "raw position and raw OI levels are scale-sensitive/nonstationary; percentile and OI-normalized variants are retained as confirmation controls"},
        "actor_predictors": ACTOR_PREDICTORS,
        "oi_predictors": OI_PREDICTORS,
        "augmented_model_specs": AUGMENTED_MODEL_SPECS,
        "interaction_contract": {"actor_direction": "sign of weekly delta_net_contracts", "oi_direction": "sign of weekly delta_open_interest", "joint_extreme_filter": "both expanding absolute-change percentiles >= P75", "status": "research-only interaction screen; not promoted from mean-edge alone"},
        "horizons": list(HORIZONS),
        "actor_series_count": len(actor_events),
        "dataset_market_oi_series_count": len(market_reference_events),
        "continuous_metric_count": len(metric_rows),
        "actor_series": actor_study,
        "oi_series": oi_study,
        "strict_ranking": metric_rows,
        "strict_counts": counts,
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    top_oi = [r for r in metric_rows if r["scope"] == "market_oi"][:300]
    top_actor_raw = [r for r in metric_rows if r["scope"] == "actor" and r["predictor_family"].startswith("raw_")][:400]
    incremental_rows = []
    for key, block in actor_study.items():
        for model_name, horizon_block in block["oi_incremental_models"].items():
            for horizon, metric in horizon_block.items():
                incremental_rows.append({"series": key, "model": model_name, "horizon": horizon, **metric})
    incremental_rows.sort(key=lambda row: (-(finite(row.get("oos_r2_gain")) or -999.0), -(finite(row.get("rmse_improvement_vs_base_pct")) or -999.0)))

    interaction_rows = []
    for key, block in actor_study.items():
        for config, config_block in block["actor_flow_x_oi_direction"].items():
            for filter_name, filter_block in config_block.items():
                for horizon, metric in filter_block["holdout_2022_plus"].items():
                    interaction_rows.append({"series": key, "config": config, "filter": filter_name, "horizon": horizon, "n": metric.get("n"), "mean_pct": metric.get("mean_pct"), "unconditional_mean_pct": metric.get("unconditional_mean_pct"), "edge_vs_unconditional_pct": metric.get("edge_vs_unconditional_pct"), "positive_rate_pct": metric.get("positive_rate_pct")})
    interaction_rows.sort(key=lambda row: (-(int(row.get("n") or 0) >= 10), -abs(finite(row.get("edge_vs_unconditional_pct")) or 0.0)))

    summary = {
        "schema_version": 1,
        "study": output["study"],
        "information_contract": output["information_contract"],
        "forecast_contract": output["forecast_contract"],
        "actor_series_count": len(actor_events),
        "dataset_market_oi_series_count": len(market_reference_events),
        "continuous_metric_count": len(metric_rows),
        "strict_counts": counts,
        "top_strict_all": metric_rows[:500],
        "top_oi_metrics": top_oi,
        "top_raw_actor_metrics": top_actor_raw,
        "top_1w": [r for r in metric_rows if r["horizon"] == "1w"][:200],
        "top_4w": [r for r in metric_rows if r["horizon"] == "4w"][:200],
        "top_13w": [r for r in metric_rows if r["horizon"] == "13w"][:200],
        "top_26w": [r for r in metric_rows if r["horizon"] == "26w"][:200],
        "gold_managed_money_all_horizons": gold_mm_rows,
        "top_oi_incremental_models": incremental_rows[:500],
        "top_actor_flow_x_oi_interactions": interaction_rows[:1000],
    }
    SUMMARY_OUT.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print("COT RAW POSITION + OI PREDICTIVE POWER BEGIN")
    print(f"actor_series={len(actor_events)} oi_series={len(market_reference_events)} continuous_metrics={len(metric_rows)}")
    print("strict_counts", json.dumps(counts, sort_keys=True))
    print("TOP STRICT 1W")
    for row in summary["top_1w"][:40]:
        print(f"{row['final_classification']:36s} {row['series']:42s} {row['predictor']:38s} N={int(row.get('holdout_n') or 0):3d}/{int(row.get('independent_n') or 0):3d} rho={float(row.get('holdout_spearman_rho') or 0):+7.3f}/{float(row.get('independent_spearman_rho') or 0):+7.3f} R2={float(row.get('oos_r2') or 0):+8.4f} qG={float(row.get('global_fdr_q') or 1):.4f} qF={float(row.get('family_fdr_q') or 1):.4f} spread={float(row.get('holdout_p90_minus_p10_spread_pp') or 0):+8.3f}pp")
    print("TOP OI INCREMENTAL MODELS")
    for row in summary["top_oi_incremental_models"][:30]:
        print(f"{row['series']:42s} {row['model']:32s} {row['horizon']:8s} N={int(row.get('holdout_n') or 0):3d} R2gain={float(row.get('oos_r2_gain') or 0):+8.4f} RMSEimp={float(row.get('rmse_improvement_vs_base_pct') or 0):+7.3f}%")
    print("COT RAW POSITION + OI PREDICTIVE POWER END")
    print(f"Wrote {OUT}")
    print(f"Wrote {SUMMARY_OUT}")


if __name__ == "__main__":
    main()
