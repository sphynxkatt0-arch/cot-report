#!/usr/bin/env python3
"""Dependence-aware inference for release-corrected COT threshold events."""
from __future__ import annotations

import hashlib
import json
import math
import random
import statistics
from collections import defaultdict
from datetime import UTC,date,datetime
from pathlib import Path
from typing import Any

import build_cot_actor_event_research_release_corrected as actor
import evaluate_analog_robustness as robustness
from cftc_release_calendar import calendar_hash

ROOT=Path(__file__).resolve().parent;OUT=ROOT/"worldclass"/"research"/"cot-threshold-inference-v2.json";SUMMARY=ROOT/"worldclass"/"research"/"cot-threshold-inference-v2-summary.json"
HOLDOUT_START=date(2022,1,1);THRESHOLDS=(60,65,70,75,80,85,90);HORIZON_STEPS={"monday":1,"tuesday":2,"wednesday":3,"thursday":4,"friday":5,**actor.FORWARD_HORIZONS};BOOTSTRAPS=2000;SEED=20260811;MIN_DISCOVERY_N=20;MIN_HOLDOUT_N=10;MIN_INDEPENDENT_N=8

def finite(v:Any)->float|None:
    try:x=float(v)
    except (TypeError,ValueError):return None
    return x if math.isfinite(x) else None
def event_return(e:dict[str,Any],h:str)->float|None:return actor.event_return(e,h)
def report_day(e:dict[str,Any])->date|None:return actor.parse_date(e.get("report_date"))
def stable_seed(*parts:Any)->int:
    digest=hashlib.sha256("|".join(map(str,parts)).encode()).digest();return SEED+int.from_bytes(digest[:4],"big")%1000000

def nonoverlap(events:list[dict[str,Any]],horizon:str)->list[dict[str,Any]]:
    steps=int(HORIZON_STEPS[horizon]);selected=[];last_end=-1
    for e in sorted(events,key=lambda x:int(x.get("signal_index") or -1)):
        idx=int(e.get("signal_index") or -1)
        if idx<0 or event_return(e,horizon) is None:continue
        if idx>last_end:selected.append(e);last_end=idx+steps
    return selected
def values(events:list[dict[str,Any]],horizon:str)->list[float]:return [v for e in events if (v:=finite(event_return(e,horizon))) is not None]
def mean(v:list[float])->float|None:return statistics.mean(v) if v else None

def bootstrap_edge(condition:list[float],baseline:list[float],seed:int)->dict[str,Any]:
    if len(condition)<2 or len(baseline)<2:return {"bootstrap_p":None,"ci95_low_pp":None,"ci95_high_pp":None}
    rng=random.Random(seed);diffs=[]
    for _ in range(BOOTSTRAPS):
        c=[condition[rng.randrange(len(condition))] for _ in condition];b=[baseline[rng.randrange(len(baseline))] for _ in baseline];diffs.append(statistics.mean(c)-statistics.mean(b))
    diffs.sort();lo=diffs[int(.025*(len(diffs)-1))];hi=diffs[int(.975*(len(diffs)-1))];le=sum(d<=0 for d in diffs)/len(diffs);ge=sum(d>=0 for d in diffs)/len(diffs);p=min(1.0,2*min(le,ge))
    return {"bootstrap_p":p,"ci95_low_pp":lo,"ci95_high_pp":hi}

def bh(rows:list[dict[str,Any]],pkey:str,qkey:str)->None:
    valid=[(i,finite(r.get(pkey))) for i,r in enumerate(rows) if finite(r.get(pkey)) is not None];valid.sort(key=lambda x:x[1]);m=len(valid);qvals=[None]*len(rows);running=1.0
    for rank in range(m,0,-1):idx,p=valid[rank-1];running=min(running,p*m/rank);qvals[idx]=running
    for i,r in enumerate(rows):r[qkey]=qvals[i]

def metric(series:str,dataset:str,market:str,actor_name:str,direction:str,threshold:int,horizon:str,events:list[dict[str,Any]])->dict[str,Any]:
    discovery=[e for e in events if (report_day(e) or date.max)<HOLDOUT_START];holdout=[e for e in events if (report_day(e) or date.min)>=HOLDOUT_START]
    dcond=[e for e in discovery if e.get("direction")==direction and finite(e.get("magnitude_percentile")) is not None and float(e["magnitude_percentile"])>=threshold];hcond=[e for e in holdout if e.get("direction")==direction and finite(e.get("magnitude_percentile")) is not None and float(e["magnitude_percentile"])>=threshold]
    dvals=values(dcond,horizon);dbase=values(discovery,horizon);hvals=values(hcond,horizon);hbase=values(holdout,horizon);icond=nonoverlap(hcond,horizon);ibase_events=nonoverlap(holdout,horizon);ivals=values(icond,horizon);ibase=values(ibase_events,horizon)
    dedge=(mean(dvals)-mean(dbase)) if dvals and dbase else None;hedge=(mean(hvals)-mean(hbase)) if hvals and hbase else None;iedge=(mean(ivals)-mean(ibase)) if ivals and ibase else None;same_sign=dedge is not None and hedge is not None and dedge*hedge>0;independent_sign=hedge is not None and iedge is not None and hedge*iedge>0;boot=bootstrap_edge(ivals,ibase,stable_seed(series,direction,threshold,horizon))
    classification="DISCOVERY_ONLY"
    if len(dvals)>=MIN_DISCOVERY_N and same_sign and len(hvals)>=MIN_HOLDOUT_N:classification="HOLDOUT_DIRECTION_CONFIRMED"
    if classification=="HOLDOUT_DIRECTION_CONFIRMED" and independent_sign and len(ivals)>=MIN_INDEPENDENT_N:classification="NONOVERLAP_CONFIRMED"
    return {"series":series,"dataset":dataset,"market":market,"actor":actor_name,"actor_role":actor.ACTOR_ROLES.get(dataset,{}).get(actor_name,"UNCLASSIFIED"),"direction":direction,"threshold":threshold,"horizon":horizon,"discovery_n":len(dvals),"discovery_edge_pp":dedge,"holdout_n":len(hvals),"holdout_edge_pp":hedge,"independent_n":len(ivals),"independent_baseline_n":len(ibase),"independent_edge_pp":iedge,"same_sign_discovery_holdout":same_sign,"same_sign_holdout_independent":independent_sign,"classification":classification,**boot}

def main()->None:
    cot_data,prices=robustness.build_full_inputs();rows=[]
    for dataset in actor.DATASETS:
        for market in actor.SUPPORTED_MARKETS:
            payload=(cot_data.get(dataset) or {}).get(market);price_payload=prices.get(market)
            if not isinstance(payload,dict) or price_payload is None:continue
            built=actor.build_market_actor_events(market,dataset,payload,price_payload)
            for actor_name,events in built.items():
                series=f"{dataset}:{market}:{actor_name}"
                for direction in ("ADD","CUT"):
                    for threshold in THRESHOLDS:
                        for horizon in HORIZON_STEPS:rows.append(metric(series,dataset,market,actor_name,direction,threshold,horizon,events))
    families:dict[str,list[dict[str,Any]]]=defaultdict(list)
    for row in rows:families[f"{row['dataset']}:{row['market']}:{row['actor']}"].append(row)
    for family_rows in families.values():bh(family_rows,"bootstrap_p","family_fdr_q")
    bh(rows,"bootstrap_p","global_fdr_q")
    for row in rows:
        if row["classification"]!="NONOVERLAP_CONFIRMED":continue
        fq=finite(row.get("family_fdr_q"));gq=finite(row.get("global_fdr_q"))
        if fq is not None and fq<=.10:row["classification"]="FAMILY_FDR"
        if gq is not None and gq<=.10:row["classification"]="GLOBAL_FDR"
    counts=defaultdict(int)
    for r in rows:counts[r["classification"]]+=1
    payload={"schema_version":1,"research_generation":"release-corrected-v2","information_contract_version":"cftc-public-availability-v2","release_calendar_hash":calendar_hash(),"strict_release_alignment":True,"generated_at_utc":datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00","Z"),"methodology":{"holdout_start":"2022-01-01","threshold_grid":list(THRESHOLDS),"bootstrap_replicates":BOOTSTRAPS,"bootstrap_seed":SEED,"bootstrap_seed_derivation":"SHA256(series|direction|threshold|horizon)","independent_episode_rule":"greedy chronological non-overlap by signal_index and horizon trading closes","multiple_testing":"Benjamini-Hochberg at actor-family and global searched-universe levels","minimum_discovery_n":MIN_DISCOVERY_N,"minimum_holdout_n":MIN_HOLDOUT_N,"minimum_independent_n":MIN_INDEPENDENT_N},"classification_counts":dict(counts),"metric_count":len(rows),"metrics":rows,"production_model_changed":False,"automatic_promotion_allowed":False}
    OUT.parent.mkdir(parents=True,exist_ok=True);OUT.write_text(json.dumps(payload,separators=(",",":"),sort_keys=True)+"\n",encoding="utf-8")
    priority={"GLOBAL_FDR":0,"FAMILY_FDR":1,"NONOVERLAP_CONFIRMED":2};strongest=sorted([r for r in rows if r["classification"] in priority],key=lambda r:(priority[r["classification"]],float(r.get("global_fdr_q") or 1),-int(r.get("independent_n") or 0)))
    SUMMARY.write_text(json.dumps({"schema_version":1,"research_generation":"release-corrected-v2","release_calendar_hash":calendar_hash(),"strict_release_alignment":True,"classification_counts":dict(counts),"metric_count":len(rows),"strongest":strongest[:250],"automatic_promotion_allowed":False},separators=(",",":"),sort_keys=True)+"\n",encoding="utf-8")
    print(f"Threshold inference strict v2 complete · metrics={len(rows)} · classifications={dict(counts)}")
if __name__=="__main__":main()
