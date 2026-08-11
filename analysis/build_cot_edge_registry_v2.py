#!/usr/bin/env python3
"""Build the release-corrected COT evidence registry.

This registry is intentionally separate from the legacy dashboard registry until
its candidate snapshot passes the full comparison/governance gate.
"""
from __future__ import annotations
import hashlib,json
from collections import defaultdict
from pathlib import Path
from typing import Any

from cftc_release_calendar import calendar_hash

ROOT=Path(__file__).resolve().parent;WORLDCLASS=ROOT/"worldclass";RESEARCH=WORLDCLASS/"research"
THRESHOLD=RESEARCH/"cot-threshold-inference-v2.json";RAW=RESEARCH/"cot-raw-position-oi-predictive-power.json";OUT=WORLDCLASS/"cot-edge-registry-v2.json"
HIERARCHY={"GLOBAL_FDR":6,"FAMILY_FDR":5,"NONOVERLAP_CONFIRMED":4,"HOLDOUT_DIRECTION_CONFIRMED":3,"DISCOVERY_ONLY":1}

def load(path:Path)->dict[str,Any]:
    p=json.loads(path.read_text(encoding="utf-8"));
    if not isinstance(p,dict):raise RuntimeError(f"invalid object: {path}")
    return p
def sha(path:Path)->str:return hashlib.sha256(path.read_bytes()).hexdigest()
def role_eligible(role:str)->bool:return role in {"PRIMARY_DIRECTIONAL","SECONDARY_DIRECTIONAL"}

def main()->None:
    threshold=load(THRESHOLD);raw=load(RAW)
    if threshold.get("research_generation")!="release-corrected-v2" or raw.get("research_generation")!="release-corrected-v2":raise RuntimeError("v2 registry refuses non-release-corrected research")
    grouped:dict[str,list[dict[str,Any]]]=defaultdict(list)
    for row in threshold.get("metrics") or []:
        if not isinstance(row,dict):continue
        grouped[f"{row.get('series')}:{row.get('direction')}:P{row.get('threshold')}"] .append(row)
    threshold_edges={}
    for key,rows in grouped.items():
        rows=sorted(rows,key=lambda r:(-HIERARCHY.get(str(r.get("classification")),0),str(r.get("horizon"))))
        best=rows[0];classification=str(best.get("classification") or "DISCOVERY_ONLY");role=str(best.get("actor_role") or "UNCLASSIFIED")
        threshold_edges[key]={"edge_key":key,"series":best.get("series"),"dataset":best.get("dataset"),"market":best.get("market"),"actor":best.get("actor"),"actor_role":role,"direction":best.get("direction"),"threshold":best.get("threshold"),"best_classification":classification,"best_independent_n":best.get("independent_n"),"best_family_fdr_q":best.get("family_fdr_q"),"best_global_fdr_q":best.get("global_fdr_q"),"horizons":{str(r.get("horizon")):{k:r.get(k) for k in ("classification","holdout_n","holdout_edge_pp","independent_n","independent_edge_pp","ci95_low_pp","ci95_high_pp","bootstrap_p","family_fdr_q","global_fdr_q")} for r in rows},"statistically_strong":classification in {"GLOBAL_FDR","FAMILY_FDR"},"actor_role_eligible":role_eligible(role),"promotion_eligible":False}
    raw_counts=raw.get("classification_counts") or raw.get("final_classification_counts") or {}
    registry={"schema_version":1,"research_generation":"release-corrected-v2","information_contract_version":"cftc-public-availability-v2","release_calendar_hash":calendar_hash(),"sources":{"threshold_inference":{"path":str(THRESHOLD.relative_to(ROOT)),"sha256":sha(THRESHOLD)},"raw_position_oi":{"path":str(RAW.relative_to(ROOT)),"sha256":sha(RAW)}},"evidence_hierarchy":["PROSPECTIVE_CONFIRMED","GLOBAL_FDR","FAMILY_FDR","NONOVERLAP_CONFIRMED","HOLDOUT_DIRECTION_CONFIRMED","DISCOVERY_ONLY","DESCRIPTIVE_ONLY","SUPERSEDED_INVALID_TIMING"],"threshold_edges":dict(sorted(threshold_edges.items())),"raw_position_oi_classification_counts":raw_counts,"production_model_changed":False,"automatic_promotion_allowed":False,"promotion_gate":"Retrospective v2 evidence remains non-promotable until immutable live evidence and policy gates are satisfied."}
    OUT.parent.mkdir(parents=True,exist_ok=True);OUT.write_text(json.dumps(registry,separators=(",",":"),sort_keys=True)+"\n",encoding="utf-8");print(f"Saved {OUT} · threshold_edges={len(threshold_edges)}")
if __name__=="__main__":main()
