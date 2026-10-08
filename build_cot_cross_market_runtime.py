#!/usr/bin/env python3
"""Build compact cross-market COT Intelligence runtime from frozen discovery research."""
from __future__ import annotations
import hashlib,json
from collections import defaultdict
from pathlib import Path
from typing import Any
ROOT=Path(__file__).resolve().parent;WC=ROOT/"worldclass";CURRENT=WC/"cot-current-state.json";SUMMARY=WC/"research"/"snapshots"/"2026-08-10"/"cot-actor-event-summary.json";OUT=WC/"cot-cross-market.json"
def load(p:Path)->dict[str,Any]:return json.loads(p.read_text(encoding="utf-8"))
def sha(p:Path)->str:return hashlib.sha256(p.read_bytes()).hexdigest()
def current_matrix(states:dict[str,Any])->dict[str,Any]:
    groups=defaultdict(list)
    for row in states.values():
        groups[f"{row.get('dataset')}:{row.get('actor')}"] .append({k:row.get(k) for k in ("series","dataset","market","actor","actor_label","actor_role","direction","position_percentile","change_magnitude_percentile","delta_net_contracts","delta_net_oi_pp","report_date_tuesday","release_date_friday")})
    return {key:sorted(rows,key=lambda r:str(r.get("market"))) for key,rows in sorted(groups.items()) if len(rows)>=2}
def tag(rows:list[dict[str,Any]])->list[dict[str,Any]]:
    out=[]
    for row in rows:
        item=dict(row);item["evidence_status"]="DISCOVERY_ONLY";item["promotion_eligible"]=False;item["sample_grade"]="INSUFFICIENT" if int(item.get("n") or 0)<10 else "EXPLORATORY" if int(item.get("n") or 0)<20 else "RESEARCH_ONLY";out.append(item)
    return out
def main()->None:
    current=load(CURRENT);summary=load(SUMMARY);gov=summary.get("governance") or {}
    output={"schema_version":1,"source_hashes":{"current_state":sha(CURRENT),"frozen_actor_event_summary":sha(SUMMARY)},"current_same_actor_across_markets":current_matrix(current.get("actor_states") or {}),"governance":{"combination_threshold_percentile":gov.get("combination_threshold"),"combination_policy":gov.get("combination_policy"),"status":"DISCOVERY_ONLY","automatic_promotion_allowed":False,"note":"Combination screens were searched after individual actor research. They require a separately preregistered confirmation study before any production eligibility."},"same_actor_cross_instrument_holdout_1w":tag(summary.get("top_same_actor_cross_instrument_holdout_1w") or []),"cross_instrument_breadth_holdout_1w":tag(summary.get("top_cross_instrument_breadth_holdout_1w") or []),"cross_actor_same_instrument_holdout_1w":tag(summary.get("top_cross_actor_same_instrument_holdout_1w") or []),"cross_report_taxonomy_holdout_1w":tag(summary.get("top_cross_report_taxonomy_holdout_1w") or []),"lead_market_holdout_1w":tag(summary.get("top_lead_market_holdout_1w") or []),"cross_sectional_rank_test":summary.get("cross_sectional_rank_test") or {},"production_model_changed":False}
    OUT.write_text(json.dumps(output,separators=(",",":"),sort_keys=True)+"\n",encoding="utf-8");print(f"Saved {OUT} · current_groups={len(output['current_same_actor_across_markets'])} · bytes={OUT.stat().st_size:,}")
if __name__=="__main__":main()
