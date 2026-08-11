#!/usr/bin/env python3
"""Build the authoritative release-corrected COT evidence registry.

Inferential evidence comes from moving-block/non-overlap/FDR research. Return,
hit-rate and drawdown presentation metrics come from the separately generated
release-corrected actor-event grid for the exact same prespecified threshold.
"""
from __future__ import annotations
import hashlib,json
from collections import defaultdict
from pathlib import Path
from typing import Any

from cftc_release_calendar import calendar_hash

ROOT=Path(__file__).resolve().parent;WORLDCLASS=ROOT/"worldclass";RESEARCH=WORLDCLASS/"research"
THRESHOLD=RESEARCH/"cot-threshold-inference-v2.json";ACTOR=RESEARCH/"cot-actor-event-research.json";RAW=RESEARCH/"cot-raw-position-oi-predictive-power.json";OUT=WORLDCLASS/"cot-edge-registry-v2.json"
HIERARCHY={"GLOBAL_FDR":6,"FAMILY_FDR":5,"NONOVERLAP_CONFIRMED":4,"HOLDOUT_DIRECTION_CONFIRMED":3,"DISCOVERY_ONLY":1}

def load(path:Path)->dict[str,Any]:
    p=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(p,dict):raise RuntimeError(f"invalid object: {path}")
    return p
def sha(path:Path)->str:return hashlib.sha256(path.read_bytes()).hexdigest()
def role_eligible(role:str)->bool:return role in {"PRIMARY_DIRECTIONAL","SECONDARY_DIRECTIONAL"}
def presentation_metric(actor_payload:dict[str,Any],series:str,direction:str,threshold:int,horizon:str)->dict[str,Any]:
    row=((((actor_payload.get("individual_actor_thresholds") or {}).get(series) or {}).get(direction) or {}).get("threshold_grid") or {}).get(str(threshold)) or {}
    metric=((row.get("holdout_2022_plus") or {}).get(horizon) or {})
    return {
        "n":metric.get("n"),"conditional_return_pct":metric.get("mean_pct"),"median_return_pct":metric.get("median_pct"),"positive_rate_pct":metric.get("positive_rate_pct"),
        "baseline_return_pct":metric.get("unconditional_mean_pct"),"excess_vs_baseline_pp":metric.get("edge_vs_unconditional_pct"),"q25_pct":metric.get("q25_pct"),"q75_pct":metric.get("q75_pct"),"avg_drawdown_pct":metric.get("avg_drawdown_pct"),"worst_drawdown_pct":metric.get("worst_drawdown_pct"),
    }

def main()->None:
    threshold=load(THRESHOLD);actor_payload=load(ACTOR);raw=load(RAW)
    for name,payload in (("threshold",threshold),("actor",actor_payload),("raw",raw)):
        if payload.get("research_generation")!="release-corrected-v2":raise RuntimeError(f"v2 registry refuses non-release-corrected {name} research")
    if threshold.get("strict_release_alignment") is not True or actor_payload.get("strict_release_alignment") is not True:raise RuntimeError("v2 registry requires strict release alignment")
    grouped:dict[str,list[dict[str,Any]]]=defaultdict(list)
    for row in threshold.get("metrics") or []:
        if not isinstance(row,dict):continue
        grouped[f"{row.get('series')}:{row.get('direction')}:P{row.get('threshold')}"] .append(row)
    threshold_edges={}
    for key,rows in grouped.items():
        rows=sorted(rows,key=lambda r:(-HIERARCHY.get(str(r.get("classification")),0),str(r.get("horizon"))))
        best=rows[0];classification=str(best.get("classification") or "DISCOVERY_ONLY");role=str(best.get("actor_role") or "UNCLASSIFIED");series=str(best.get("series"));direction=str(best.get("direction"));threshold_value=int(best.get("threshold"))
        horizons={}
        for r in rows:
            horizon=str(r.get("horizon"));present=presentation_metric(actor_payload,series,direction,threshold_value,horizon)
            horizons[horizon]={
                "horizon":horizon,**present,
                "classification":r.get("classification"),"holdout_n":r.get("holdout_n"),"holdout_edge_pp":r.get("holdout_edge_pp"),"independent_n":r.get("independent_n"),"independent_edge_pp":r.get("independent_edge_pp"),
                "ci95_low_pp":r.get("ci95_low_pp"),"ci95_high_pp":r.get("ci95_high_pp"),"block_bootstrap_p":r.get("block_bootstrap_p"),"bootstrap_se_pp":r.get("bootstrap_se_pp"),"block_length_weeks":r.get("block_length_weeks"),"family_fdr_q":r.get("family_fdr_q"),"global_fdr_q":r.get("global_fdr_q"),
            }
        threshold_edges[key]={
            "edge_key":key,"series":series,"dataset":best.get("dataset"),"market":best.get("market"),"actor":best.get("actor"),"actor_role":role,"direction":direction,"threshold":threshold_value,
            "best_classification":classification,"best_independent_n":best.get("independent_n"),"best_family_fdr_q":best.get("family_fdr_q"),"best_global_fdr_q":best.get("global_fdr_q"),"horizons":horizons,
            "statistically_strong":classification in {"GLOBAL_FDR","FAMILY_FDR"},"actor_role_eligible":role_eligible(role),"promotion_eligible":False,
        }
    raw_counts=raw.get("classification_counts") or raw.get("final_classification_counts") or {}
    registry={
        "schema_version":3,"research_generation":"release-corrected-v2","information_contract_version":"cftc-public-availability-v2","release_calendar_hash":calendar_hash(),
        "sources":{"threshold_inference":{"path":str(THRESHOLD.relative_to(ROOT)),"sha256":sha(THRESHOLD)},"actor_event":{"path":str(ACTOR.relative_to(ROOT)),"sha256":sha(ACTOR)},"raw_position_oi":{"path":str(RAW.relative_to(ROOT)),"sha256":sha(RAW)}},
        "evidence_hierarchy":["PROSPECTIVE_CONFIRMED","GLOBAL_FDR","FAMILY_FDR","NONOVERLAP_CONFIRMED","HOLDOUT_DIRECTION_CONFIRMED","DISCOVERY_ONLY","DESCRIPTIVE_ONLY","SUPERSEDED_INVALID_TIMING"],
        "threshold_inference":"circular moving-block bootstrap + non-overlapping confirmation + family/global BH-FDR","pp_definition":"percentage points relative to the unconditional holdout return; not an absolute price forecast",
        "threshold_edges":dict(sorted(threshold_edges.items())),"raw_position_oi_classification_counts":raw_counts,
        "production_model_changed":False,"automatic_promotion_allowed":False,"promotion_gate":"Retrospective v2 evidence remains non-promotable until immutable live evidence and policy gates are satisfied.",
    }
    OUT.parent.mkdir(parents=True,exist_ok=True);OUT.write_text(json.dumps(registry,separators=(",",":"),sort_keys=True)+"\n",encoding="utf-8");print(f"Saved {OUT} · threshold_edges={len(threshold_edges)}")
if __name__=="__main__":main()
