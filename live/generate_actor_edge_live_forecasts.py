#!/usr/bin/env python3
"""Stage prospective actor-edge forecasts from current frozen threshold conditions.

Only discrete threshold conditions are issued. Continuous correlations remain
context and are never converted into a forecast by this script.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from datetime import UTC,datetime
from pathlib import Path
from typing import Any

from actor_edge_ledger import EDGE_HORIZONS,TRADING_CLOSES,canonical,deterministic_id,forecast_path,iso_utc,release_vintage_utc,within_window,write_immutable,validate_forecast

ANALYSIS=Path(__file__).resolve().parents[1]
CURRENT=ANALYSIS/"worldclass"/"cot-current-state.json"; ACTIVE=ANALYSIS/"worldclass"/"cot-active-edges.json"; REGISTRY=ANALYSIS/"worldclass"/"cot-edge-registry.json"; POLICY=ANALYSIS/"config"/"cot_edge_promotion_policy.json"

def load(path:Path)->dict[str,Any]:
    p=json.loads(path.read_text(encoding="utf-8"));
    if not isinstance(p,dict):raise RuntimeError(f"invalid JSON root: {path}")
    return p

def sha(path:Path)->str:return hashlib.sha256(path.read_bytes()).hexdigest()
def semantic_hash(*items:Any)->str:return hashlib.sha256(canonical(list(items))).hexdigest()
def metric_map(row:dict[str,Any])->dict[str,dict[str,Any]]:return {str(m.get("horizon")):m for m in row.get("metrics") or []}

def build_forecast(edge:dict[str,Any],state:dict[str,Any],registry:dict[str,Any],policy_hash:str)->dict[str,Any]:
    report=str(state["report_date_tuesday"]);release=str(state["release_date_friday"]);threshold=int(edge["selected_threshold"]);series=str(edge["series"]);direction=str(edge["direction"]);key=f"{series}:{direction}:P{threshold}"
    research_hash=str((registry.get("source_snapshot") or {}).get("threshold_summary_sha256") or "")
    sid=deterministic_id(report,str(state["market"]),str(state["dataset"]),key,research_hash);metrics=metric_map(edge);horizons={}
    for h in EDGE_HORIZONS:
        m=metrics.get(h)
        if not m:raise RuntimeError(f"active edge {key} lacks frozen {h} historical metric")
        probability=m.get("positive_rate_pct"); horizons[h]={
            "trading_closes":TRADING_CLOSES[h],"expected_return_pct":m.get("conditional_return_pct"),"median_return_pct":m.get("median_return_pct"),
            "probability_positive":float(probability)/100.0 if probability is not None else None,
            "historical_unconditional_return_pct":m.get("baseline_return_pct"),"historical_excess_vs_baseline_pp":m.get("excess_vs_baseline_pp"),
            "historical_average_drawdown_pct":m.get("avg_drawdown_pct"),"historical_worst_drawdown_pct":m.get("worst_drawdown_pct"),"historical_sample_size":m.get("n"),
        }
    input_hash=semantic_hash({k:state.get(k) for k in ("series","report_date_tuesday","release_date_friday","direction","position_percentile","change_magnitude_percentile","delta_net_contracts","delta_net_oi_pp")},{k:edge.get(k) for k in ("selected_threshold","historical_classification","promotion_status")},research_hash,policy_hash)
    forecast={
        "schema_version":1,"signal_id":sid,"edge_signal_key":key,"market":state["market"],"dataset":state["dataset"],"actor":state["actor"],"actor_label":state["actor_label"],"actor_role":state["actor_role"],"direction":direction,"action_type":state.get("action_type"),
        "report_date":report,"release_target_date":release,"created_at_utc":iso_utc(release_vintage_utc(release)),
        "current_position_percentile":state.get("position_percentile"),"current_change_percentile":state.get("change_magnitude_percentile"),"current_delta_net_contracts":state.get("delta_net_contracts"),"current_delta_net_oi_pp":state.get("delta_net_oi_pp"),
        "frozen_threshold_percentile":threshold,"historical_classification":edge.get("historical_classification"),"historical_promotion_status":edge.get("promotion_status"),
        "research_snapshot_hash":research_hash,"input_manifest_hash":input_hash,"policy_hash":policy_hash,"historical_horizons":horizons,
        "forecast_filename":forecast_path({"release_target_date":release,"market":state["market"],"dataset":state["dataset"],"edge_signal_key":key}).name,
        "production_model_changed":False,"evidence_family":"COT_ACTOR_THRESHOLD",
    }
    validate_forecast(forecast);return forecast

def generate(output_root:Path,now:datetime)->dict[str,Any]:
    current=load(CURRENT);active=load(ACTIVE);registry=load(REGISTRY);policy_hash=sha(POLICY);states=current.get("actor_states") or {};staged=[];skipped=[]
    for market,block in sorted((active.get("by_market") or {}).items()):
        for edge in block.get("active_thresholds") or []:
            state=states.get(str(edge.get("series")))
            if not state:raise RuntimeError(f"active edge has no current state: {edge.get('series')}")
            release=str(state.get("release_date_friday"))
            if not within_window(now,release):skipped.append({"series":edge.get("series"),"reason":"outside deterministic Friday 21:35 issuance window","release_target_date":release});continue
            forecast=build_forecast(edge,state,registry,policy_hash);rel=forecast_path(forecast);dest=output_root/rel;write_immutable(dest,forecast);staged.append({"signal_id":forecast["signal_id"],"edge_signal_key":forecast["edge_signal_key"],"relative_path":str(rel).replace("\\","/"),"forecast_hash":sha(dest),"created_at_utc":forecast["created_at_utc"]})
    plan={"schema_version":1,"generated_at_utc":iso_utc(now),"forecast_count":len(staged),"forecasts":sorted(staged,key=lambda x:x["relative_path"]),"skipped":skipped,"research_snapshot_hash":(registry.get("source_snapshot") or {}).get("threshold_summary_sha256"),"policy_hash":policy_hash,"historical_backfill_allowed":False}
    output_root.mkdir(parents=True,exist_ok=True);(output_root/"plan.json").write_bytes(canonical(plan));return plan

def args()->argparse.Namespace:
    p=argparse.ArgumentParser();p.add_argument("--output-root",type=Path,required=True);p.add_argument("--now-utc");return p.parse_args()
def main()->None:
    a=args();now=datetime.fromisoformat(a.now_utc.replace("Z","+00:00")).astimezone(UTC) if a.now_utc else datetime.now(UTC);r=generate(a.output_root,now);print(f"Actor-edge staging complete · forecasts={r['forecast_count']} · skipped={len(r['skipped'])}")
if __name__=="__main__":main()
