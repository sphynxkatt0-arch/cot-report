#!/usr/bin/env python3
"""Extract a compact audit view from the frozen raw-position/OI predictive study.

This is a presentation/audit extractor only. It does not recompute statistics.
It reads the already-generated full study and emits a compact JSON containing:
- OI-only rankings by key horizon;
- Gold Managed Money raw-count / OI-normalized predictor rows;
- Gold Managed Money pre-specified incremental-OI model results;
- Gold Managed Money actor-flow x OI-direction interaction results;
- strongest short-horizon incremental-OI models across the universe.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "worldclass" / "research" / "cot-raw-position-oi-predictive-power.json"
OUT = ROOT / "worldclass" / "research" / "snapshots" / "2026-08-11-position-oi-derived" / "key-results.json"

KEY_HORIZONS = ("1w", "4w", "13w", "26w")
GOLD_KEY = "disaggregated:gold:managed_money"
GOLD_PREDICTORS = (
    "net_contracts",
    "long_contracts",
    "short_contracts",
    "net_contracts_percentile",
    "delta_net_contracts",
    "delta_long_contracts",
    "delta_short_contracts",
    "signed_delta_net_contracts_percentile",
    "net_oi_pct",
    "long_oi_pct",
    "short_oi_pct",
    "delta_1w_net_oi_pp",
    "position_percentile",
    "signed_change_percentile",
)


def finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number and abs(number) != float("inf") else None


def sort_key(row: dict[str, Any]) -> tuple[Any, ...]:
    classes = {
        "GLOBAL_FDR05_OOS": 0,
        "GLOBAL_FDR10_OOS": 1,
        "FAMILY_FDR05_OOS": 2,
        "FAMILY_FDR10_OOS": 3,
        "OVERLAP_CONFIRMED_NOT_FDR": 4,
        "POSITIVE_OOS_GAIN_NOT_OVERLAP_CONFIRMED": 5,
        "NO_OOS_GAIN": 6,
    }
    q = finite(row.get("global_fdr_q"))
    r2 = finite(row.get("oos_r2"))
    rho = finite(row.get("independent_spearman_rho"))
    return (
        classes.get(str(row.get("final_classification")), 9),
        q if q is not None else 2.0,
        -(r2 if r2 is not None else -999.0),
        -abs(rho or 0.0),
    )


def compact_continuous(row: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "series", "scope", "predictor", "predictor_family", "scale_sensitive", "horizon",
        "final_classification", "overlap_classification",
        "discovery_n", "discovery_spearman_rho",
        "holdout_n", "holdout_pearson_r", "holdout_spearman_rho",
        "independent_n", "independent_spearman_rho", "independent_spearman_p_approx",
        "oos_r2", "rmse_improvement_pct", "direction_lift_pp",
        "holdout_p90_minus_p10_spread_pp", "global_fdr_q", "family_fdr_q",
    )
    return {key: row.get(key) for key in keys}


def main() -> None:
    payload = json.loads(SOURCE.read_text(encoding="utf-8"))
    ranking = payload.get("strict_ranking") or []

    oi_only = {}
    for horizon in KEY_HORIZONS:
        rows = [compact_continuous(row) for row in ranking if row.get("scope") == "market_oi" and row.get("horizon") == horizon]
        rows.sort(key=sort_key)
        oi_only[horizon] = rows

    gold_continuous = {}
    for horizon in KEY_HORIZONS:
        rows = [
            compact_continuous(row)
            for row in ranking
            if row.get("series") == GOLD_KEY
            and row.get("horizon") == horizon
            and row.get("predictor") in GOLD_PREDICTORS
        ]
        rows.sort(key=lambda row: GOLD_PREDICTORS.index(str(row.get("predictor"))))
        gold_continuous[horizon] = rows

    gold_block = ((payload.get("actor_series") or {}).get(GOLD_KEY) or {})
    gold_incremental = {}
    for model_name, horizon_block in (gold_block.get("oi_incremental_models") or {}).items():
        gold_incremental[model_name] = {
            horizon: (horizon_block or {}).get(horizon)
            for horizon in KEY_HORIZONS
        }

    gold_interactions = {}
    for config, config_block in (gold_block.get("actor_flow_x_oi_direction") or {}).items():
        rendered_filters = {}
        for filter_name, filter_block in (config_block or {}).items():
            holdout = (filter_block or {}).get("holdout_2022_plus") or {}
            rendered_filters[filter_name] = {
                horizon: {
                    key: (holdout.get(horizon) or {}).get(key)
                    for key in (
                        "n", "mean_pct", "median_pct", "positive_rate_pct",
                        "unconditional_mean_pct", "edge_vs_unconditional_pct",
                        "avg_drawdown_pct", "worst_drawdown_pct",
                    )
                }
                for horizon in KEY_HORIZONS
            }
        gold_interactions[config] = rendered_filters

    short_incremental = []
    for series, block in (payload.get("actor_series") or {}).items():
        for model_name, horizon_block in (block.get("oi_incremental_models") or {}).items():
            for horizon in ("1w", "4w"):
                metric = (horizon_block or {}).get(horizon) or {}
                n = int(metric.get("holdout_n") or 0)
                gain = finite(metric.get("oos_r2_gain"))
                if n < 30 or gain is None:
                    continue
                short_incremental.append({
                    "series": series,
                    "model": model_name,
                    "horizon": horizon,
                    "holdout_n": n,
                    "base_oos_r2": metric.get("base_oos_r2"),
                    "augmented_oos_r2": metric.get("augmented_oos_r2"),
                    "oos_r2_gain": metric.get("oos_r2_gain"),
                    "incremental_r2_vs_base_model": metric.get("incremental_r2_vs_base_model"),
                    "rmse_improvement_vs_base_pct": metric.get("rmse_improvement_vs_base_pct"),
                    "augmented_coefficients_standardized": metric.get("augmented_coefficients_standardized"),
                })
    short_incremental.sort(key=lambda row: (-(finite(row.get("oos_r2_gain")) or -999.0), -(finite(row.get("rmse_improvement_vs_base_pct")) or -999.0)))

    result = {
        "schema_version": 1,
        "derived_from": "analysis/worldclass/research/cot-raw-position-oi-predictive-power.json",
        "study": payload.get("study"),
        "information_contract": payload.get("information_contract"),
        "forecast_contract": payload.get("forecast_contract"),
        "continuous_metric_count": payload.get("continuous_metric_count"),
        "strict_counts": payload.get("strict_counts"),
        "key_horizons": list(KEY_HORIZONS),
        "oi_only_by_horizon": oi_only,
        "gold_managed_money_continuous": gold_continuous,
        "gold_managed_money_incremental_oi_models": gold_incremental,
        "gold_managed_money_flow_x_oi_interactions": gold_interactions,
        "top_short_horizon_incremental_oi_models_n30": short_incremental[:250],
        "caveat": "Incremental two-feature OLS rows are pre-specified discovery-fitted OOS comparisons but do not yet have their own non-overlap/FDR gate. Do not promote long-horizon incremental R2 from this file as validated predictive power.",
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote {OUT}")
    print("OI ONLY 1W")
    for row in oi_only["1w"][:20]:
        print(json.dumps(row, sort_keys=True))
    print("GOLD MM 1W")
    for row in gold_continuous["1w"]:
        print(json.dumps(row, sort_keys=True))
    print("GOLD MM INCREMENTAL")
    for model_name, block in gold_incremental.items():
        print(model_name, json.dumps(block, sort_keys=True))
    print("GOLD MM INTERACTIONS 1W")
    for config, block in gold_interactions.items():
        print(config, json.dumps({k: v.get("1w") for k, v in block.items()}, sort_keys=True))
    print("TOP SHORT INCREMENTAL")
    for row in short_incremental[:30]:
        print(json.dumps(row, sort_keys=True))


if __name__ == "__main__":
    main()
