#!/usr/bin/env python3
"""Build presentation analytics only from prospective actor-edge ledger evidence."""
from __future__ import annotations
import argparse,json,math,statistics
from collections import defaultdict
from datetime import UTC,datetime
from pathlib import Path
from typing import Any
from actor_edge_ledger import EDGE_HORIZONS,entry_files,finite,forecast_files,load,outcome_files,validate_ledger

ANALYSIS=Path(__file__).resolve().parents[1];DEFAULT_OUT=ANALYSIS/"worldclass"/"actor-edge-live-track-record.json";POLICY=ANALYSIS/"config"/"cot_edge_promotion_policy.json"
def mean(v):return statistics.mean(v) if v else None
def rnd(v,d=6):return round(v,d) if v is not None and math.isfinite(v) else None
def stage(n:int)->str:return "INSUFFICIENT SAMPLE" if n<10 else "PRELIMINARY" if n<20 else "EARLY" if n<40 else "MEANINGFUL"
def metrics(rows:list[dict[str,Any]])->dict[str,Any]:
    matured=[r for r in rows if r.get("outcome")];real=[];pred=[];base=[];directions=[];errors=[]
    for r in matured:
        o=r["outcome"];m=r["meta"];rv=finite(o.get("realized_return_pct"));pv=finite(m.get("expected_return_pct"));bv=finite(m.get("historical_unconditional_return_pct"))
        if rv is None:continue
        real.append(rv)
        if pv is not None:pred.append(pv);errors.append(rv-pv)
        if bv is not None:base.append(bv)
        if o.get("direction_correct") is not None:directions.append(1.0 if o["direction_correct"] else 0.0)
    live=mean(real);b=mean(base);vintages={str(r["forecast"].get("release_target_date")) for r in matured}
    return {"forecasts_issued":len(rows),"forecasts_matured":len(matured),"matured_vintages":len(vintages),"sample_stage":stage(len(vintages)),"historical_expected_return_pct":rnd(mean(pred)),"average_realized_return_pct":rnd(live),"average_unconditional_return_pct":rnd(b),"live_edge_vs_unconditional_pp":rnd(live-b if live is not None and b is not None else None),"directional_hit_rate_pct":rnd(mean(directions)*100 if directions else None,3),"mean_forecast_error_pct":rnd(mean(errors)),"rmse_pct":rnd(math.sqrt(mean([x*x for x in errors])) if errors else None)}
def promotion(series_rows:dict[str,dict[str,list[dict[str,Any]]]],policy:dict[str,Any])->list[dict[str,Any]]:
    out=[];live_req=policy.get("required_live_checks") or {}
    for series,hmap in sorted(series_rows.items()):
        any_rows=next(iter(hmap.values()),[])
        if not any_rows:continue
        f=any_rows[0]["forecast"];reasons=[]
        if f.get("actor_role") not in set(policy.get("eligible_actor_roles") or []):reasons.append("actor role is not promotion eligible")
        if f.get("historical_classification") not in set((policy.get("required_research_status") or {}).get("threshold",[])):reasons.append("historical threshold evidence status is not eligible")
        horizon_results={}
        for h,req in live_req.items():
            m=metrics(hmap.get(h,[]));need=int(req.get("matured_signals") or 0);same=True
            hist=m.get("historical_expected_return_pct");base=m.get("average_unconditional_return_pct");live=m.get("average_realized_return_pct")
            if req.get("same_direction_as_historical") and hist is not None and base is not None and live is not None:same=(hist-base)*(live-base)>0
            if int(m.get("forecasts_matured") or 0)<need:reasons.append(f"{h} live sample {m.get('forecasts_matured')} < {need}")
            elif not same:reasons.append(f"{h} live direction disagrees with frozen historical edge")
            horizon_results[h]={"required":need,"matured":m.get("forecasts_matured"),"same_direction":same}
        decision="ELIGIBLE_FOR_GOVERNANCE_REVIEW" if not reasons else "RESEARCH_ONLY"
        out.append({"series":series,"actor":f.get("actor"),"actor_label":f.get("actor_label"),"actor_role":f.get("actor_role"),"market":f.get("market"),"direction":f.get("direction"),"threshold":f.get("frozen_threshold_percentile"),"decision":decision,"automatic_weight_change":False,"reasons":reasons,"live_gates":horizon_results})
    return out
def build(root:Path,now:datetime)->dict[str,Any]:
    integrity=validate_ledger(root);forecasts={};entries={};outcomes=defaultdict(dict)
    for p in forecast_files(root):f=load(p);forecasts[f["signal_id"]]=f
    for p in entry_files(root):e=load(p);entries[e["signal_id"]]=e
    for p in outcome_files(root):o=load(p);outcomes[o["signal_id"]][o["horizon"]]=o
    groups=defaultdict(list);series_rows=defaultdict(lambda:defaultdict(list));current=[]
    for sid,f in sorted(forecasts.items(),key=lambda x:(x[1].get("created_at_utc",""),x[0])):
        complete="26w" in outcomes.get(sid,{})
        if not complete:current.append({"signal_id":sid,"market":f.get("market"),"dataset":f.get("dataset"),"actor":f.get("actor"),"actor_label":f.get("actor_label"),"actor_role":f.get("actor_role"),"direction":f.get("direction"),"threshold":f.get("frozen_threshold_percentile"),"current_position_percentile":f.get("current_position_percentile"),"current_change_percentile":f.get("current_change_percentile"),"release_target_date":f.get("release_target_date"),"status":"live" if sid in entries else "awaiting close"})
        series=f"{f.get('dataset')}:{f.get('market')}:{f.get('actor')}:{f.get('direction')}:P{f.get('frozen_threshold_percentile')}"
        for h in EDGE_HORIZONS:
            row={"forecast":f,"meta":(f.get("historical_horizons") or {}).get(h) or {},"outcome":outcomes.get(sid,{}).get(h)};groups[(f.get("market"),f.get("dataset"),f.get("actor"),f.get("direction"),f.get("frozen_threshold_percentile"),h)].append(row);series_rows[series][h].append(row)
    stats=[]
    for key,rows in sorted(groups.items()):
        market,dataset,actor,direction,threshold,h=key;stats.append({"market":market,"dataset":dataset,"actor":actor,"direction":direction,"threshold":threshold,"horizon":h,**metrics(rows)})
    policy=json.loads(POLICY.read_text(encoding="utf-8"));matured=sum(1 for sid in forecasts if outcomes.get(sid))
    return {"schema_version":1,"generated_at_utc":now.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00","Z"),"forecast_count":len(forecasts),"entry_count":len(entries),"outcome_count":sum(len(v) for v in outcomes.values()),"matured_signal_count":matured,"ledger":integrity,"current_predictions":current,"statistics":stats,"promotion_evaluations":promotion(series_rows,policy),"governance":{"historical_backfill_allowed":False,"automatic_weight_changes":False,"promotion_policy_id":policy.get("policy_id"),"historical_and_live_layers_separate":True}}
def args():
    p=argparse.ArgumentParser();p.add_argument("--ledger-root",type=Path,required=True);p.add_argument("--output",type=Path,default=DEFAULT_OUT);return p.parse_args()
def main():
    a=args();r=build(a.ledger_root,datetime.now(UTC));a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(r,separators=(",",":"),sort_keys=True)+"\n",encoding="utf-8");print(f"Actor-edge track record · forecasts={r['forecast_count']} outcomes={r['outcome_count']} integrity={r['ledger']['integrity']}")
if __name__=="__main__":main()
