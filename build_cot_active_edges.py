#!/usr/bin/env python3
"""Resolve current COT actor states against frozen historical evidence.

Discrete threshold events are active only when the current direction and
expanding change percentile meet the frozen threshold. Continuous predictive
metrics are contextual evidence only and are read from per-market lazy detail.
"""
from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
WORLDCLASS = ROOT / "worldclass"
CURRENT = WORLDCLASS / "cot-current-state.json"
REGISTRY = WORLDCLASS / "cot-edge-registry.json"
DETAIL_DIR = WORLDCLASS / "cot-edge-details"
OUT = WORLDCLASS / "cot-active-edges.json"
PRIMARY_HORIZONS = ("monday","tuesday","wednesday","thursday","friday","1w","2w","3w","4w","6w","8w","13w","26w")
CLASS_PRIORITY = {"GLOBAL_FDR":0,"FAMILY_FDR":1,"OOS_PLUS_OVERLAP":2,"OOS_ONLY":3,"NO_OOS_GAIN":4,"INSUFFICIENT_N":5}
ROLE_PRIORITY = {"PRIMARY_DIRECTIONAL":0,"SECONDARY_DIRECTIONAL":1,"INTERMEDIARY_CONTEXT":2,"HEDGER_CONTEXT":2,"OPPOSITE_SIDE_CONTEXT":2,"AGGREGATE_CONTEXT":2}

def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def threshold_metric(curve: dict[str, Any], horizon: str) -> dict[str, Any] | None:
    row = ((curve.get("holdout_2022_plus") or {}).get(horizon) or {})
    if not row or int(row.get("n") or 0) == 0: return None
    return {
        "horizon":horizon,"n":row.get("n"),"conditional_return_pct":row.get("mean_pct"),
        "median_return_pct":row.get("median_pct"),"positive_rate_pct":row.get("positive_rate_pct"),
        "baseline_return_pct":row.get("unconditional_mean_pct"),"excess_vs_baseline_pp":row.get("edge_vs_unconditional_pct"),
        "q25_pct":row.get("q25_pct"),"q75_pct":row.get("q75_pct"),
        "avg_drawdown_pct":row.get("avg_drawdown_pct"),"worst_drawdown_pct":row.get("worst_drawdown_pct"),
    }

def detail_index() -> dict[str, dict[str, dict[str, Any]]]:
    out: dict[str, dict[str, dict[str, Any]]] = {}
    for path in sorted(DETAIL_DIR.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        by_series: dict[str, dict[str, Any]] = {}
        for row in payload.get("actors") or []:
            by_series.setdefault(str(row.get("series")), {})[str(row.get("horizon"))] = row.get("best_overall") or {}
        out[str(payload.get("market"))] = by_series
    return out

def compact_continuous_metric(horizon: str, metric: dict[str, Any]) -> dict[str, Any]:
    n = int(metric.get("independent_n") or 0)
    return {
        "horizon":horizon,"predictor":metric.get("predictor"),"predictor_family":metric.get("predictor_family"),
        "evidence_status":metric.get("evidence_status"),"holdout_spearman_rho":metric.get("holdout_spearman_rho"),
        "independent_spearman_rho":metric.get("independent_spearman_rho"),"oos_r2":metric.get("oos_r2"),
        "holdout_p90_minus_p10_spread_pp":metric.get("holdout_p90_minus_p10_spread_pp"),"independent_n":n,
        "sample_warning":"INSUFFICIENT INDEPENDENT SAMPLE" if n<15 else ("RESEARCH ONLY" if n<30 else ("SAMPLE WARNING" if n<60 else None)),
    }

def main() -> None:
    current=json.loads(CURRENT.read_text(encoding="utf-8")); registry=json.loads(REGISTRY.read_text(encoding="utf-8")); details=detail_index()
    by_market:dict[str,dict[str,list[Any]]]={}
    active_threshold_count=0
    for series,state in (current.get("actor_states") or {}).items():
        market=str(state.get("market")); role=str(state.get("actor_role")); market_block=by_market.setdefault(market,{"active_thresholds":[],"continuous_context":[]})
        frozen=state.get("frozen_threshold_signal") or {}; signal=str(frozen.get("signal") or ""); curve=(registry.get("threshold_signals") or {}).get(signal)
        if bool(frozen.get("active_now")) and curve:
            metrics=[m for horizon in PRIMARY_HORIZONS if (m:=threshold_metric(curve,horizon)) is not None]
            row={
                "type":"THRESHOLD_EVENT","series":series,"dataset":state.get("dataset"),"actor":state.get("actor"),
                "actor_label":state.get("actor_label"),"actor_role":role,"direction":state.get("direction"),"action_type":state.get("action_type"),
                "current_position_percentile":state.get("position_percentile"),"current_change_percentile":state.get("change_magnitude_percentile"),
                "current_delta_net_contracts":state.get("delta_net_contracts"),"current_delta_net_oi_pp":state.get("delta_net_oi_pp"),
                "selected_threshold":frozen.get("selected_threshold"),"historical_classification":frozen.get("classification"),
                "promotion_status":frozen.get("promotion_status"),"metrics":metrics,
            }
            market_block["active_thresholds"].append(row); active_threshold_count+=1

        candidates=[]
        for horizon in PRIMARY_HORIZONS:
            metric=((details.get(market) or {}).get(series) or {}).get(horizon) or {}
            status=str(metric.get("evidence_status") or "NO_OOS_GAIN")
            if status=="NO_OOS_GAIN": continue
            candidates.append(compact_continuous_metric(horizon,metric))
        candidates.sort(key=lambda row:(CLASS_PRIORITY.get(str(row.get("evidence_status")),9),-int(row.get("independent_n") or 0),-abs(float(row.get("independent_spearman_rho") or 0))))
        if candidates:
            market_block["continuous_context"].append({
                "type":"CONTINUOUS_EVIDENCE","series":series,"dataset":state.get("dataset"),"actor":state.get("actor"),
                "actor_label":state.get("actor_label"),"actor_role":role,"current_position_percentile":state.get("position_percentile"),
                "current_change_percentile":state.get("change_magnitude_percentile"),"current_direction":state.get("direction"),
                "current_delta_net_contracts":state.get("delta_net_contracts"),"current_delta_net_oi_pp":state.get("delta_net_oi_pp"),
                "top_horizons":candidates[:3],
            })

    for market_block in by_market.values():
        market_block["active_thresholds"].sort(key=lambda row:(ROLE_PRIORITY.get(str(row.get("actor_role")),9),-float(row.get("current_change_percentile") or 0),row.get("series") or ""))
        market_block["continuous_context"].sort(key=lambda row:(ROLE_PRIORITY.get(str(row.get("actor_role")),9),CLASS_PRIORITY.get(str(((row.get("top_horizons") or [{}])[0]).get("evidence_status")),9),-int(((row.get("top_horizons") or [{}])[0]).get("independent_n") or 0),row.get("series") or ""))

    output={
        "schema_version":1,"generated_at_utc":datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00","Z"),
        "source_hashes":{"cot-current-state.json":sha256(CURRENT),"cot-edge-registry.json":sha256(REGISTRY)},
        "governance":{"production_model_changed":False,"automatic_promotion_allowed":False,
            "threshold_trigger_rule":"current direction must match frozen ADD/CUT signal and current expanding change percentile must be >= frozen threshold",
            "continuous_metrics":"context only; never called an active threshold signal","pp_definition":"percentage points"},
        "active_threshold_count":active_threshold_count,"by_market":by_market,
    }
    OUT.write_text(json.dumps(output,separators=(",",":"),sort_keys=True)+"\n",encoding="utf-8")
    print(f"Saved {OUT} · active_thresholds={active_threshold_count} · bytes={OUT.stat().st_size:,}")

if __name__ == "__main__": main()
