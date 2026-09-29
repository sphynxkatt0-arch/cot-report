#!/usr/bin/env python3
"""Merge actor-edge prospective analytics into presentation-only track record."""
from __future__ import annotations
import argparse,json
from pathlib import Path

def main()->None:
    p=argparse.ArgumentParser();p.add_argument("--core",type=Path,required=True);p.add_argument("--edge",type=Path,required=True);p.add_argument("--output",type=Path,required=True);a=p.parse_args()
    core=json.loads(a.core.read_text(encoding="utf-8"));edge=json.loads(a.edge.read_text(encoding="utf-8"))
    if not isinstance(core,dict) or not isinstance(edge,dict):raise RuntimeError("track record root must be object")
    core["edge_evidence"]=edge;core.setdefault("evidence_policy",{})["actor_edge_live"]="Separate append-only actor-edge namespace; no historical backfill; presentation merge only."
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(core,separators=(",",":"),sort_keys=True)+"\n",encoding="utf-8");print(f"Merged actor-edge evidence · forecasts={edge.get('forecast_count',0)} outcomes={edge.get('outcome_count',0)}")
if __name__=="__main__":main()
