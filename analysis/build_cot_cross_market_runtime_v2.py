#!/usr/bin/env python3
"""Build cross-market COT context exclusively from release-corrected v2 research.

Cross-market combinations remain DISCOVERY_ONLY because they were searched after
the individual actor study. Correcting timing does not upgrade their evidence.
"""
from __future__ import annotations
import hashlib,json
from collections import defaultdict
from pathlib import Path
from typing import Any
from cftc_release_calendar import calendar_hash
ROOT=Path(__file__).resolve().parent;WC=ROOT/"worldclass";CURRENT=WC/"cot-current-state.json";SUMMARY=WC/"research"/"cot-actor-event-summary.json";OUT=WC/"cot-cross-market-v2.json"
def load(p:Path)->dict[str,Any]:
    x=json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(x,dict):raise RuntimeError(p)
    return x
def sha(p:Path)->str:return hashlib.sha256(p.read_bytes()).hexdigest()
def current_matrix(states:dict[str,Any])->dict[str,Any]:
    groups=defaultdict(list)
    for row in states.values():groups[f"{row.get('dataset')}:{row.get('actor')}"] .append({k:row.get(k) for k in ("series","dataset","market","actor","actor_label","actor_role","direction","position_percentile","change_magnitude_percentile","delta_net_contracts","delta_net_oi_pp","report_date_tuesday","release_date_friday","availability_at_utc")})
    return {k:sorted(v,key=lambda r:str(r.get("market"))) for k,v in sorted(groups.items()) if len(v)>=2}
def tag(rows:list[dict[str,Any]])->list[dict[str,Any]]:
    out=[]
    for row in rows:
        item=dict(row);item["evidence_status"]="DISCOVERY_ONLY";item["promotion_eligible"]=False;item["release_corrected"]=True;n=int(item.get("n") or 0);item["sample_grade"]="INSUFFICIENT" if n<10 else ("EXPLORATORY" if n<20 else "RESEARCH_ONLY");out.append(item)
    return out
def main()->None:
    current=load(CURRENT);summary=load(SUMMARY)
    if summary.get("research_generation")!="release-corrected-v2":raise RuntimeError("cross-market v2 refuses legacy actor-event research")
    gov=summary.get("governance") or {}
    output={
        "schema_version":2,"research_generation":"release-corrected-v2","information_contract_version":"cftc-public-availability-v2","release_calendar_hash":calendar_hash(),
        "source_hashes":{"current_state":sha(CURRENT),"actor_event_summary_v2":sha(SUMMARY)},"current_same_actor_across_markets":current_matrix(current.get("actor_states") or {}),
        "governance":{"combination_threshold_percentile":gov.get("combination_threshold"),"combination_policy":gov.get("combination_policy"),"status":"DISCOVERY_ONLY","automatic_promotion_allowed":False,"note":"Release timing is corrected, but combination screens remain post-discovery research and require a separately preregistered confirmation study."},
        "same_actor_cross_instrument_holdout_1w":tag(summary.get("top_same_actor_cross_instrument_holdout_1w") or []),"cross_instrument_breadth_holdout_1w":tag(summary.get("top_cross_instrument_breadth_holdout_1w") or []),"cross_actor_same_instrument_holdout_1w":tag(summary.get("top_cross_actor_same_instrument_holdout_1w") or []),"cross_report_taxonomy_holdout_1w":tag(summary.get("top_cross_report_taxonomy_holdout_1w") or []),"lead_market_holdout_1w":tag(summary.get("top_lead_market_holdout_1w") or []),"cross_sectional_rank_test":summary.get("cross_sectional_rank_test") or {},"production_model_changed":False,
    }
    OUT.write_text(json.dumps(output,separators=(",",":"),sort_keys=True)+"\n",encoding="utf-8");print(f"Saved {OUT} · current_groups={len(output['current_same_actor_across_markets'])} · bytes={OUT.stat().st_size}")
if __name__=="__main__":main()
