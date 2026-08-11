#!/usr/bin/env python3
"""Select current COT threshold edges exclusively from the release-corrected v2 registry."""
from __future__ import annotations
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT=Path(__file__).resolve().parent;WORLDCLASS=ROOT/"worldclass";CURRENT=WORLDCLASS/"cot-current-state.json";REGISTRY=WORLDCLASS/"cot-edge-registry-v2.json";OUT=WORLDCLASS/"cot-active-edges-v2.json"
RANK={"GLOBAL_FDR":5,"FAMILY_FDR":4,"NONOVERLAP_CONFIRMED":3,"HOLDOUT_DIRECTION_CONFIRMED":2,"DISCOVERY_ONLY":1}

def load(path:Path)->dict[str,Any]:
    p=json.loads(path.read_text(encoding="utf-8"));
    if not isinstance(p,dict):raise RuntimeError(path)
    return p

def main()->None:
    current=load(CURRENT);registry=load(REGISTRY)
    if registry.get("research_generation")!="release-corrected-v2":raise RuntimeError("active-edge v2 refuses legacy registry")
    states=current.get("actor_states") or {};by_market:dict[str,list[dict[str,Any]]]=defaultdict(list)
    for edge in (registry.get("threshold_edges") or {}).values():
        series=str(edge.get("series") or "");state=states.get(series)
        if not state:continue
        direction=str(state.get("direction") or "FLAT");mag=state.get("change_magnitude_percentile");threshold=edge.get("threshold")
        if direction!=edge.get("direction") or mag is None or threshold is None or float(mag)<float(threshold):continue
        cls=str(edge.get("best_classification") or "DISCOVERY_ONLY")
        row={"edge_key":edge.get("edge_key"),"series":series,"market":edge.get("market"),"dataset":edge.get("dataset"),"actor":edge.get("actor"),"actor_label":state.get("actor_label"),"actor_role":edge.get("actor_role"),"direction":direction,"action_type":state.get("action_type"),"current_position_percentile":state.get("position_percentile"),"current_change_percentile":mag,"selected_threshold":threshold,"evidence_status":cls,"evidence_rank":RANK.get(cls,0),"independent_n":edge.get("best_independent_n"),"family_fdr_q":edge.get("best_family_fdr_q"),"global_fdr_q":edge.get("best_global_fdr_q"),"horizons":edge.get("horizons"),"statistically_strong":edge.get("statistically_strong"),"actor_role_eligible":edge.get("actor_role_eligible"),"production_promotion_eligible":False}
        by_market[str(edge.get("market"))].append(row)
    output={"schema_version":1,"research_generation":"release-corrected-v2","source_registry":"cot-edge-registry-v2.json","by_market":{},"active_edge_count":0,"production_model_changed":False,"automatic_promotion_allowed":False}
    for market,rows in sorted(by_market.items()):
        rows.sort(key=lambda r:(-int(r["evidence_rank"]),-float(r.get("current_change_percentile") or 0),str(r.get("series"))))
        output["by_market"][market]={"active_thresholds":rows,"strongest":rows[:10]};output["active_edge_count"]+=len(rows)
    OUT.write_text(json.dumps(output,separators=(",",":"),sort_keys=True)+"\n",encoding="utf-8");print(f"Saved {OUT} · active={output['active_edge_count']}")
if __name__=="__main__":main()
