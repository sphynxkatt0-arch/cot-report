#!/usr/bin/env python3
"""Build browser-compatible continuous COT detail payloads from corrected v2 research.

No model is fitted here. The governed raw/OI study already contains frozen
pre-2022 discovery, 2022+ holdout, non-overlap and FDR statistics. This builder
only extracts/ranks those existing metrics into the 59 actor x 15 horizon and 7
market-OI x 15 horizon presentation schema used by COT Intelligence.
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

import extract_position_oi_all_actor_horizons as extractor
from cftc_release_calendar import calendar_hash

ROOT=Path(__file__).resolve().parent;WC=ROOT/"worldclass";RESEARCH=WC/"research"
RAW=RESEARCH/"cot-raw-position-oi-predictive-power.json";ACTOR=RESEARCH/"cot-actor-event-research.json";INFERENCE=RESEARCH/"cot-threshold-inference-v2.json"
AUDIT=RESEARCH/"cot-position-oi-audit-v2.json";TSV=RESEARCH/"cot-position-oi-audit-v2.tsv";DETAIL_DIR=WC/"cot-edge-details-v2"
HORIZONS=("monday","tuesday","wednesday","thursday","friday","1w","2w","3w","4w","6w","8w","13w","26w","39w","52w")
MARKETS=("sp500","nq","vix","rty","dow","gold","silver")

def load(path:Path)->dict[str,Any]:
    p=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(p,dict):raise RuntimeError(path)
    return p

def evidence_label(classification:Any,independent_n:Any)->str:
    cls=str(classification or "NO_OOS_GAIN");n=int(independent_n or 0)
    if n<15:return "INSUFFICIENT_N"
    if cls.startswith("GLOBAL_FDR"):return "GLOBAL_FDR"
    if cls.startswith("FAMILY_FDR"):return "FAMILY_FDR"
    if cls=="OVERLAP_CONFIRMED_NOT_FDR":return "OOS_PLUS_OVERLAP"
    if cls=="POSITIVE_OOS_GAIN_NOT_OVERLAP_CONFIRMED":return "OOS_ONLY"
    return "NO_OOS_GAIN"
def sample_grade(n:Any)->str:
    value=int(n or 0)
    return "FULL" if value>=60 else ("SAMPLE_WARNING" if value>=30 else ("RESEARCH_ONLY" if value>=15 else "INSUFFICIENT"))
def enrich(metric:dict[str,Any]|None)->dict[str,Any]|None:
    if not metric:return None
    m=dict(metric);m["evidence_status"]=evidence_label(m.get("final_classification"),m.get("independent_n"));m["sample_grade"]=sample_grade(m.get("independent_n"));return m

def compact_threshold_profile(block:dict[str,Any])->dict[str,Any]:
    out={}
    for direction in ("ADD","CUT"):
        d=(block or {}).get(direction) or {}
        out[direction]={
            "selected_threshold":d.get("selected_threshold"),"holdout_validation":d.get("holdout_validation"),
            "flow_percentile_bands":{"P0_P50":(d.get("dose_response_full_history") or {}).get("SMALL"),"P50_P75":(d.get("dose_response_full_history") or {}).get("MEDIUM"),"P75_P90":(d.get("dose_response_full_history") or {}).get("LARGE"),"P90_P100":(d.get("dose_response_full_history") or {}).get("EXTREME")},
            "position_percentile_bands_at_selected_flow":{"P0_P10":(d.get("position_level_interaction") or {}).get("EXTREME_SHORT"),"P10_P25":(d.get("position_level_interaction") or {}).get("SHORT"),"P25_P75":(d.get("position_level_interaction") or {}).get("NEUTRAL"),"P75_P90":(d.get("position_level_interaction") or {}).get("LONG"),"P90_P100":(d.get("position_level_interaction") or {}).get("EXTREME_LONG")},
        }
    return out

def build_audit()->dict[str,Any]:
    if not RAW.exists():raise FileNotFoundError(RAW)
    raw=load(RAW)
    if raw.get("research_generation")!="release-corrected-v2":raise RuntimeError("detail v2 refuses non-corrected raw/OI source")
    originals=(extractor.SOURCE,extractor.OUT_DIR,extractor.OUT,extractor.TSV)
    extractor.SOURCE=RAW;extractor.OUT_DIR=RESEARCH;extractor.OUT=AUDIT;extractor.TSV=TSV
    try:extractor.main()
    finally:extractor.SOURCE,extractor.OUT_DIR,extractor.OUT,extractor.TSV=originals
    audit=load(AUDIT);audit["schema_version"]=2;audit["research_generation"]="release-corrected-v2";audit["information_contract_version"]="cftc-public-availability-v2";audit["release_calendar_hash"]=calendar_hash();AUDIT.write_text(json.dumps(audit,separators=(",",":"),sort_keys=True)+"\n",encoding="utf-8");return audit

def main()->None:
    audit=build_audit();raw=load(RAW);actor=load(ACTOR);inference=load(INFERENCE)
    for name,p in (("actor",actor),("inference",inference)):
        if p.get("research_generation")!="release-corrected-v2":raise RuntimeError(f"detail v2 refuses non-corrected {name} source")
    by_market:dict[str,list[dict[str,Any]]]=defaultdict(list)
    for cell in audit.get("actor_horizon_matrix") or []:
        row=dict(cell)
        for key in ("best_overall","best_raw_flow","best_raw_position_level","best_oi_normalized_flow","best_oi_normalized_position"):row[key]=enrich(row.get(key))
        by_market[str(row.get("market"))].append(row)
    oi_by_market:dict[str,dict[str,Any]]=defaultdict(dict)
    for cell in audit.get("market_oi_horizon_matrix") or []:
        oi_by_market[str(cell.get("market"))][str(cell.get("horizon"))]=enrich(cell.get("best_oi_only"))
    profiles:dict[str,dict[str,Any]]=defaultdict(dict)
    for series,block in (actor.get("individual_actor_thresholds") or {}).items():
        parts=str(series).split(":")
        if len(parts)>=3:profiles[parts[1]][series]=compact_threshold_profile(block or {})
    oi_interactions:dict[str,dict[str,Any]]=defaultdict(dict)
    for series,block in (raw.get("actor_series") or {}).items():
        parts=str(series).split(":")
        if len(parts)>=3:oi_interactions[parts[1]][series]=(block or {}).get("actor_flow_x_oi_direction") or {}
    threshold_summary:dict[str,list[dict[str,Any]]]=defaultdict(list)
    for metric in inference.get("metrics") or []:
        market=str(metric.get("market") or "")
        if market and str(metric.get("classification")) in {"GLOBAL_FDR","FAMILY_FDR","NONOVERLAP_CONFIRMED"}:threshold_summary[market].append({k:metric.get(k) for k in ("series","actor_role","direction","threshold","horizon","classification","holdout_n","holdout_edge_pp","independent_n","independent_edge_pp","family_fdr_q","global_fdr_q")})
    DETAIL_DIR.mkdir(parents=True,exist_ok=True)
    for market in MARKETS:
        payload={
            "schema_version":2,"research_generation":"release-corrected-v2","information_contract_version":"cftc-public-availability-v2","release_calendar_hash":calendar_hash(),"market":market,
            "actors":sorted(by_market.get(market,[]),key=lambda r:(str(r.get("series")),HORIZONS.index(str(r.get("horizon"))))),
            "market_oi":oi_by_market.get(market,{}),"threshold_signals":threshold_summary.get(market,[]),"threshold_percentile_profiles":profiles.get(market,{}),"actor_flow_x_oi_direction":oi_interactions.get(market,{}),
            "automatic_promotion_allowed":False,
        }
        (DETAIL_DIR/f"{market}.json").write_text(json.dumps(payload,separators=(",",":"),sort_keys=True)+"\n",encoding="utf-8")
    if sum(len(v) for v in by_market.values())!=885:raise RuntimeError("v2 actor/horizon detail cell count mismatch")
    if sum(len(v) for v in oi_by_market.values())!=105:raise RuntimeError("v2 market-OI detail cell count mismatch")
    print(f"Built release-corrected COT details · actor_cells=885 · market_oi_cells=105 · dir={DETAIL_DIR}")
if __name__=="__main__":main()
