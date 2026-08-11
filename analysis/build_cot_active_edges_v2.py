#!/usr/bin/env python3
"""Select a compact current COT edge stack from release-corrected v2 evidence.

Nested percentile triggers are one current event, not independent signals. Keep
one evidence-best crossed threshold per actor series. Weekday cells carry only
fields rendered by the weekday path; 1W/2W/4W/13W/26W retain the richer fields
required by the current-edge UI and immutable prospective actor-edge ledger.
Full 15-horizon evidence stays in lazy cot-edge-details payloads.
"""
from __future__ import annotations
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT=Path(__file__).resolve().parent;WC=ROOT/"worldclass";RESEARCH=WC/"research"
CURRENT=WC/"cot-current-state.json";REGISTRY=WC/"cot-edge-registry-v2.json";INFERENCE=RESEARCH/"cot-threshold-inference-v2.json";ACTOR=RESEARCH/"cot-actor-event-research.json";OUT=WC/"cot-active-edges-v2.json"
WEEKDAYS=("monday","tuesday","wednesday","thursday","friday");FORWARD=("1w","2w","4w","13w","26w");ACTIVE_HORIZONS=WEEKDAYS+FORWARD
RANK={"GLOBAL_FDR":5,"FAMILY_FDR":4,"NONOVERLAP_CONFIRMED":3,"HOLDOUT_DIRECTION_CONFIRMED":2,"DISCOVERY_ONLY":1}

def load(path:Path)->dict[str,Any]:
    payload=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload,dict):raise RuntimeError(path)
    return payload

def presentation(actor:dict[str,Any],series:str,direction:str,threshold:int,horizon:str)->dict[str,Any]:
    grid=((((actor.get("individual_actor_thresholds") or {}).get(series) or {}).get(direction) or {}).get("threshold_grid") or {}).get(str(threshold)) or {}
    m=((grid.get("holdout_2022_plus") or {}).get(horizon) or {})
    return {"n":m.get("n"),"conditional_return_pct":m.get("mean_pct"),"median_return_pct":m.get("median_pct"),"positive_rate_pct":m.get("positive_rate_pct"),"baseline_return_pct":m.get("unconditional_mean_pct"),"excess_vs_baseline_pp":m.get("edge_vs_unconditional_pct"),"avg_drawdown_pct":m.get("avg_drawdown_pct"),"worst_drawdown_pct":m.get("worst_drawdown_pct")}

def metric_payload(actor:dict[str,Any],series:str,direction:str,threshold:int,horizon:str,inf:dict[str,Any])->dict[str,Any]:
    p=presentation(actor,series,direction,threshold,horizon)
    if horizon in WEEKDAYS:
        return {"horizon":horizon,"n":p.get("n"),"conditional_return_pct":p.get("conditional_return_pct"),"excess_vs_baseline_pp":p.get("excess_vs_baseline_pp")}
    return {
        "horizon":horizon,**p,"evidence_status":inf.get("classification"),"independent_n":inf.get("independent_n"),
        "family_fdr_q":inf.get("family_fdr_q"),"global_fdr_q":inf.get("global_fdr_q"),
    }

def main()->None:
    current=load(CURRENT);registry=load(REGISTRY);inference=load(INFERENCE);actor=load(ACTOR)
    for name,payload in (("registry",registry),("inference",inference),("actor",actor)):
        if payload.get("research_generation")!="release-corrected-v2":raise RuntimeError(f"active v2 refuses non-corrected {name}")
    inf_by_key:dict[tuple[str,str,int],dict[str,dict[str,Any]]]=defaultdict(dict)
    for metric in inference.get("metrics") or []:
        inf_by_key[(str(metric.get("series")),str(metric.get("direction")),int(metric.get("threshold") or 0))][str(metric.get("horizon"))]=metric
    states=current.get("actor_states") or {};crossed:dict[str,list[dict[str,Any]]]=defaultdict(list)
    for edge in (registry.get("threshold_edges") or {}).values():
        series=str(edge.get("series") or "");state=states.get(series)
        if not state:continue
        direction=str(state.get("direction") or "FLAT");magnitude=state.get("change_magnitude_percentile");threshold=int(edge.get("threshold") or 0)
        if direction==edge.get("direction") and magnitude is not None and threshold>0 and float(magnitude)>=threshold:crossed[series].append(edge)
    by_market:dict[str,list[dict[str,Any]]]=defaultdict(list)
    for series,edges in crossed.items():
        state=states[series]
        edge=max(edges,key=lambda e:(RANK.get(str(e.get("best_classification") or "DISCOVERY_ONLY"),0),int(e.get("threshold") or 0),int(e.get("best_independent_n") or 0)))
        direction=str(state.get("direction") or "FLAT");threshold=int(edge.get("threshold") or 0);evidence=inf_by_key.get((series,direction,threshold),{});metrics=[]
        for horizon in ACTIVE_HORIZONS:
            inf=evidence.get(horizon)
            if inf:metrics.append(metric_payload(actor,series,direction,threshold,horizon,inf))
        cls=str(edge.get("best_classification") or "DISCOVERY_ONLY")
        row={
            "series":series,"dataset":edge.get("dataset"),"actor_label":state.get("actor_label"),"actor_role":edge.get("actor_role"),"direction":direction,
            "current_position_percentile":state.get("position_percentile"),"current_change_percentile":state.get("change_magnitude_percentile"),
            "current_delta_net_contracts":state.get("delta_net_contracts"),"current_delta_net_oi_pp":state.get("delta_net_oi_pp"),"selected_threshold":threshold,
            "historical_classification":cls,"evidence_status":cls,"metrics":metrics,
        }
        by_market[str(edge.get("market"))].append(row)
    output={
        "schema_version":5,"research_generation":"release-corrected-v2","information_contract_version":"cftc-public-availability-v2","source_registry":"cot-edge-registry-v2.json",
        "pp_definition":"percentage points versus unconditional holdout return, not an absolute price forecast",
        "governance":{"production_model_changed":False,"automatic_promotion_allowed":False,"nested_threshold_policy":"one evidence-best crossed threshold per actor series; evidence rank first then highest crossed percentile","weekday_metric_schema":"horizon,n,conditional_return_pct,excess_vs_baseline_pp","forward_metric_schema":"full ledger/display fields for 1w,2w,4w,13w,26w","materialized_horizons":list(ACTIVE_HORIZONS),"continuous_metrics":"full 15-horizon context remains lazy in corrected detail payloads"},
        "by_market":{},"active_edge_count":0,"active_threshold_count":0,"production_model_changed":False,"automatic_promotion_allowed":False,
    }
    for market,rows in sorted(by_market.items()):
        def rank_key(row:dict[str,Any]):
            cls=RANK.get(str(row.get("evidence_status") or "DISCOVERY_ONLY"),0);one_week=next((m for m in row.get("metrics") or [] if m.get("horizon")=="1w"),{});edge=abs(float(one_week.get("excess_vs_baseline_pp") or 0));return (-cls,-edge,-float(row.get("current_change_percentile") or 0),str(row.get("series")))
        rows.sort(key=rank_key);output["by_market"][market]={"active_thresholds":rows,"continuous_context":[]};output["active_edge_count"]+=len(rows)
    output["active_threshold_count"]=output["active_edge_count"]
    OUT.write_text(json.dumps(output,separators=(",",":"),sort_keys=True)+"\n",encoding="utf-8")
    if OUT.stat().st_size>180_000:raise RuntimeError(f"active-edge v2 runtime too large: {OUT.stat().st_size}")
    print(f"Saved {OUT} · active={output['active_edge_count']} · bytes={OUT.stat().st_size}")
if __name__=="__main__":main()
