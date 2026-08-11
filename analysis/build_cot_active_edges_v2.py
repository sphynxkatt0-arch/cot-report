#!/usr/bin/env python3
"""Select current COT threshold edges exclusively from release-corrected v2 evidence."""
from __future__ import annotations
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT=Path(__file__).resolve().parent;WC=ROOT/"worldclass";RESEARCH=WC/"research"
CURRENT=WC/"cot-current-state.json";REGISTRY=WC/"cot-edge-registry-v2.json";INFERENCE=RESEARCH/"cot-threshold-inference-v2.json";ACTOR=RESEARCH/"cot-actor-event-research.json";OUT=WC/"cot-active-edges-v2.json"
HORIZON_ORDER=("monday","tuesday","wednesday","thursday","friday","1w","2w","3w","4w","6w","8w","13w","26w","39w","52w")
RANK={"GLOBAL_FDR":5,"FAMILY_FDR":4,"NONOVERLAP_CONFIRMED":3,"HOLDOUT_DIRECTION_CONFIRMED":2,"DISCOVERY_ONLY":1}

def load(path:Path)->dict[str,Any]:
    p=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(p,dict):raise RuntimeError(path)
    return p

def presentation(actor:dict[str,Any],series:str,direction:str,threshold:int,horizon:str)->dict[str,Any]:
    grid=((((actor.get("individual_actor_thresholds") or {}).get(series) or {}).get(direction) or {}).get("threshold_grid") or {}).get(str(threshold)) or {}
    m=((grid.get("holdout_2022_plus") or {}).get(horizon) or {})
    return {"n":m.get("n"),"conditional_return_pct":m.get("mean_pct"),"median_return_pct":m.get("median_pct"),"positive_rate_pct":m.get("positive_rate_pct"),"baseline_return_pct":m.get("unconditional_mean_pct"),"excess_vs_baseline_pp":m.get("edge_vs_unconditional_pct"),"q25_pct":m.get("q25_pct"),"q75_pct":m.get("q75_pct"),"avg_drawdown_pct":m.get("avg_drawdown_pct"),"worst_drawdown_pct":m.get("worst_drawdown_pct")}
def main()->None:
    current=load(CURRENT);registry=load(REGISTRY);inference=load(INFERENCE);actor=load(ACTOR)
    for name,p in (("registry",registry),("inference",inference),("actor",actor)):
        if p.get("research_generation")!="release-corrected-v2":raise RuntimeError(f"active v2 refuses non-corrected {name}")
    inf_by_key:dict[tuple[str,str,int],dict[str,dict[str,Any]]]=defaultdict(dict)
    for m in inference.get("metrics") or []:
        key=(str(m.get("series")),str(m.get("direction")),int(m.get("threshold") or 0));inf_by_key[key][str(m.get("horizon"))]=m
    states=current.get("actor_states") or {};by_market:dict[str,list[dict[str,Any]]]=defaultdict(list)
    for edge in (registry.get("threshold_edges") or {}).values():
        series=str(edge.get("series") or "");state=states.get(series)
        if not state:continue
        direction=str(state.get("direction") or "FLAT");mag=state.get("change_magnitude_percentile");threshold=int(edge.get("threshold") or 0)
        if direction!=edge.get("direction") or mag is None or threshold<=0 or float(mag)<threshold:continue
        evidence=inf_by_key.get((series,direction,threshold),{});metrics=[];horizons={}
        for horizon in HORIZON_ORDER:
            inf=evidence.get(horizon)
            if not inf:continue
            p= presentation(actor,series,direction,threshold,horizon)
            metric={"horizon":horizon,**p,"evidence_status":inf.get("classification"),"independent_n":inf.get("independent_n"),"independent_edge_pp":inf.get("independent_edge_pp"),"ci95_low_pp":inf.get("ci95_low_pp"),"ci95_high_pp":inf.get("ci95_high_pp"),"block_bootstrap_p":inf.get("block_bootstrap_p"),"family_fdr_q":inf.get("family_fdr_q"),"global_fdr_q":inf.get("global_fdr_q")}
            metrics.append(metric);horizons[horizon]=metric
        cls=str(edge.get("best_classification") or "DISCOVERY_ONLY")
        row={"type":"THRESHOLD_EVENT","edge_key":edge.get("edge_key"),"series":series,"market":edge.get("market"),"dataset":edge.get("dataset"),"actor":edge.get("actor"),"actor_label":state.get("actor_label"),"actor_role":edge.get("actor_role"),"direction":direction,"action_type":state.get("action_type"),"current_position_percentile":state.get("position_percentile"),"current_change_percentile":mag,"current_delta_net_contracts":state.get("delta_net_contracts"),"current_delta_net_oi_pp":state.get("delta_net_oi_pp"),"selected_threshold":threshold,"historical_classification":cls,"evidence_status":cls,"evidence_rank":RANK.get(cls,0),"independent_n":edge.get("best_independent_n"),"family_fdr_q":edge.get("best_family_fdr_q"),"global_fdr_q":edge.get("best_global_fdr_q"),"metrics":metrics,"horizons":horizons,"statistically_strong":edge.get("statistically_strong"),"actor_role_eligible":edge.get("actor_role_eligible"),"promotion_status":"RESEARCH_ONLY_V2","production_promotion_eligible":False}
        by_market[str(edge.get("market"))].append(row)
    output={"schema_version":3,"research_generation":"release-corrected-v2","information_contract_version":"cftc-public-availability-v2","source_registry":"cot-edge-registry-v2.json","pp_definition":"percentage points versus unconditional holdout return, not an absolute price forecast","governance":{"production_model_changed":False,"automatic_promotion_allowed":False,"pp_definition":"percentage points","threshold_trigger_rule":"current direction matches prespecified ADD/CUT and current expanding magnitude percentile >= frozen threshold; evidence label comes from release-corrected moving-block/non-overlap/FDR research","continuous_metrics":"context only in corrected detail payloads; never treated as an active threshold event"},"by_market":{},"active_edge_count":0,"active_threshold_count":0,"production_model_changed":False,"automatic_promotion_allowed":False}
    for market,rows in sorted(by_market.items()):
        rows.sort(key=lambda r:(-int(r["evidence_rank"]),-float(r.get("current_change_percentile") or 0),str(r.get("series"))))
        output["by_market"][market]={"active_thresholds":rows,"continuous_context":[],"strongest":rows[:10]};output["active_edge_count"]+=len(rows)
    output["active_threshold_count"]=output["active_edge_count"]
    OUT.write_text(json.dumps(output,separators=(",",":"),sort_keys=True)+"\n",encoding="utf-8")
    if OUT.stat().st_size>180_000:raise RuntimeError(f"active-edge v2 runtime too large: {OUT.stat().st_size}")
    print(f"Saved {OUT} · active={output['active_edge_count']} · bytes={OUT.stat().st_size}")
if __name__=="__main__":main()
