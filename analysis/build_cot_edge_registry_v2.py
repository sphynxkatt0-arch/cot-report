#!/usr/bin/env python3
"""Build the compact authoritative release-corrected COT evidence registry."""
from __future__ import annotations
import hashlib,json
from collections import defaultdict
from pathlib import Path
from typing import Any
from cftc_release_calendar import calendar_hash

ROOT=Path(__file__).resolve().parent;WC=ROOT/"worldclass";RESEARCH=WC/"research"
THRESHOLD=RESEARCH/"cot-threshold-inference-v2.json";ACTOR=RESEARCH/"cot-actor-event-research.json";RAW=RESEARCH/"cot-raw-position-oi-predictive-power.json";AUDIT=RESEARCH/"cot-position-oi-audit-v2.json";OUT=WC/"cot-edge-registry-v2.json"
HORIZONS=("monday","tuesday","wednesday","thursday","friday","1w","2w","3w","4w","6w","8w","13w","26w","39w","52w")
HIERARCHY={"GLOBAL_FDR":6,"FAMILY_FDR":5,"NONOVERLAP_CONFIRMED":4,"HOLDOUT_DIRECTION_CONFIRMED":3,"DISCOVERY_ONLY":1}

def load(path:Path)->dict[str,Any]:
    p=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(p,dict):raise RuntimeError(path)
    return p
def sha(path:Path)->str:return hashlib.sha256(path.read_bytes()).hexdigest()
def role_eligible(role:str)->bool:return role in {"PRIMARY_DIRECTIONAL","SECONDARY_DIRECTIONAL"}

def main()->None:
    threshold=load(THRESHOLD);actor_payload=load(ACTOR);raw=load(RAW);audit=load(AUDIT)
    for name,p in (("threshold",threshold),("actor",actor_payload),("raw",raw),("audit",audit)):
        if p.get("research_generation")!="release-corrected-v2":raise RuntimeError(f"v2 registry refuses non-release-corrected {name}")
    grouped:dict[str,list[dict[str,Any]]]=defaultdict(list)
    for row in threshold.get("metrics") or []:
        if isinstance(row,dict):grouped[f"{row.get('series')}:{row.get('direction')}:P{row.get('threshold')}"] .append(row)
    threshold_edges={}
    for key,rows in grouped.items():
        rows=sorted(rows,key=lambda r:(-HIERARCHY.get(str(r.get("classification")),0),str(r.get("horizon"))))
        best=rows[0];cls=str(best.get("classification") or "DISCOVERY_ONLY");role=str(best.get("actor_role") or "UNCLASSIFIED")
        threshold_edges[key]={
            "edge_key":key,"series":best.get("series"),"dataset":best.get("dataset"),"market":best.get("market"),"actor":best.get("actor"),"actor_role":role,"direction":best.get("direction"),"threshold":best.get("threshold"),
            "best_classification":cls,"best_horizon":best.get("horizon"),"best_holdout_edge_pp":best.get("holdout_edge_pp"),"best_independent_edge_pp":best.get("independent_edge_pp"),"best_independent_n":best.get("independent_n"),"best_family_fdr_q":best.get("family_fdr_q"),"best_global_fdr_q":best.get("global_fdr_q"),
            "statistically_strong":cls in {"GLOBAL_FDR","FAMILY_FDR"},"actor_role_eligible":role_eligible(role),"promotion_eligible":False,
        }
    actors={}
    for cell in audit.get("actor_horizon_matrix") or []:
        series=str(cell.get("series") or "")
        if series and series not in actors:actors[series]={k:cell.get(k) for k in ("series","dataset","market","actor","actor_role")}
    registry={
        "schema_version":4,"research_generation":"release-corrected-v2","information_contract_version":"cftc-public-availability-v2","release_calendar_hash":calendar_hash(),"horizons":list(HORIZONS),
        "sources":{"threshold_inference":{"path":str(THRESHOLD.relative_to(ROOT)),"sha256":sha(THRESHOLD)},"actor_event":{"path":str(ACTOR.relative_to(ROOT)),"sha256":sha(ACTOR)},"raw_position_oi":{"path":str(RAW.relative_to(ROOT)),"sha256":sha(RAW)},"continuous_audit":{"path":str(AUDIT.relative_to(ROOT)),"sha256":sha(AUDIT)}},
        "evidence_hierarchy":["PROSPECTIVE_CONFIRMED","GLOBAL_FDR","FAMILY_FDR","NONOVERLAP_CONFIRMED","HOLDOUT_DIRECTION_CONFIRMED","DISCOVERY_ONLY","DESCRIPTIVE_ONLY","SUPERSEDED_INVALID_TIMING"],
        "evidence_status_definitions":{"GLOBAL_FDR":"Holdout direction + non-overlap confirmation + global BH-FDR <=10%.","FAMILY_FDR":"Holdout direction + non-overlap confirmation + actor-family BH-FDR <=10%.","NONOVERLAP_CONFIRMED":"Holdout direction retained in independent episodes but not FDR significant.","HOLDOUT_DIRECTION_CONFIRMED":"Discovery direction replicated in chronological holdout; dependence gate not passed.","DISCOVERY_ONLY":"Not independently validated for predictive use.","INSUFFICIENT_N":"Independent sample below 15 for continuous evidence."},
        "sample_grade_definitions":{"FULL":"independent N >= 60","SAMPLE_WARNING":"independent N 30-59","RESEARCH_ONLY":"independent N 15-29","INSUFFICIENT":"independent N < 15"},
        "threshold_inference":"circular moving-block bootstrap + non-overlapping confirmation + family/global BH-FDR","pp_definition":"percentage points relative to unconditional holdout return; not an absolute price forecast",
        "actors":dict(sorted(actors.items())),"threshold_edges":dict(sorted(threshold_edges.items())),"detail_path_template":"worldclass/cot-edge-details-v2/{market}.json",
        "research_counts":{"continuous_metrics":audit.get("source_continuous_metric_count"),"actor_series":audit.get("actor_series_count"),"actor_horizon_cells":audit.get("actor_horizon_cell_count"),"market_oi_series":audit.get("market_oi_series_count"),"market_oi_horizon_cells":audit.get("market_oi_horizon_cell_count"),"threshold_metrics":threshold.get("metric_count")},
        "raw_position_oi_classification_counts":raw.get("classification_counts") or raw.get("final_classification_counts") or {},
        "production_model_changed":False,"automatic_promotion_allowed":False,"promotion_gate":"Retrospective evidence cannot change production weights; prospective immutable live evidence remains a separate gate.",
    }
    OUT.write_text(json.dumps(registry,separators=(",",":"),sort_keys=True)+"\n",encoding="utf-8")
    if OUT.stat().st_size>500_000:raise RuntimeError(f"v2 registry too large for always-loaded runtime: {OUT.stat().st_size}")
    print(f"Saved {OUT} · actors={len(actors)} · threshold_edges={len(threshold_edges)} · bytes={OUT.stat().st_size}")
if __name__=="__main__":main()
