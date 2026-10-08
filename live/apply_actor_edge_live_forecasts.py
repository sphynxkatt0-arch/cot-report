#!/usr/bin/env python3
"""Append staged actor-edge forecasts and a hash-chained immutable manifest."""
from __future__ import annotations
import argparse
import json
import re
from pathlib import Path
from typing import Any
from actor_edge_ledger import EdgeLedgerError,canonical,load,sha_bytes,sha_file,validate_forecast,validate_ledger,validate_manifest_chain,write_immutable

def manifest_name(item:dict[str,Any])->str:
    stamp=re.sub(r"[^0-9TZ]","",str(item.get("created_at_utc") or ""));sid=str(item.get("signal_id") or "")
    if len(sid)!=64:raise EdgeLedgerError("invalid staged signal id")
    return f"{stamp}-{sid}.json"

def apply(staging:Path,ledger_root:Path,metadata_out:Path)->dict[str,Any]:
    plan_path=staging/"plan.json"
    if not plan_path.exists():raise EdgeLedgerError("actor-edge staging plan missing")
    plan=load(plan_path);state=validate_ledger(ledger_root);new=[];unchanged=[]
    for item in plan.get("forecasts") or []:
        rel=str(item.get("relative_path") or "")
        if not rel.startswith("live/actor_edge/forecasts/") or ".." in Path(rel).parts:raise EdgeLedgerError(f"unsafe path: {rel}")
        src=staging/rel
        if not src.exists() or sha_file(src)!=item.get("forecast_hash"):raise EdgeLedgerError(f"staged hash mismatch: {rel}")
        f=load(src);validate_forecast(f)
        if f.get("signal_id")!=item.get("signal_id"):raise EdgeLedgerError("staging signal mismatch")
        dst=ledger_root/rel
        if dst.exists():
            if dst.read_bytes()!=src.read_bytes():raise EdgeLedgerError(f"immutable actor-edge forecast overwrite refused: {rel}")
            unchanged.append(item);continue
        dst.parent.mkdir(parents=True,exist_ok=True);dst.write_bytes(src.read_bytes());new.append(item)
    if new:
        allowed={str(i["relative_path"]) for i in new};transition=validate_manifest_chain(ledger_root,allowed_uncovered=allowed);previous=transition["latest_manifest_hash"]
        mdir=ledger_root/"live"/"actor_edge"/"manifests";mdir.mkdir(parents=True,exist_ok=True)
        for item in sorted(new,key=manifest_name):
            rel=str(item["relative_path"]);m={"schema_version":1,"signal_id":item["signal_id"],"forecast_path":rel,"forecast_hash":item["forecast_hash"],"created_at_utc":item["created_at_utc"],"previous_manifest_hash":previous}
            path=mdir/manifest_name(item);write_immutable(path,m);previous=sha_bytes(canonical(m))
    final=validate_ledger(ledger_root);metadata={"schema_version":1,"new_count":len(new),"unchanged_count":len(unchanged),"new_forecasts":sorted(new,key=lambda x:x["relative_path"]),"unchanged_forecasts":sorted(unchanged,key=lambda x:x["relative_path"]),"ledger":final,"source_research_snapshot_hash":plan.get("research_snapshot_hash"),"policy_hash":plan.get("policy_hash")}
    metadata_out.parent.mkdir(parents=True,exist_ok=True);metadata_out.write_bytes(canonical(metadata));return metadata

def args()->argparse.Namespace:
    p=argparse.ArgumentParser();p.add_argument("--staging",type=Path,required=True);p.add_argument("--ledger-root",type=Path,required=True);p.add_argument("--metadata-out",type=Path,required=True);return p.parse_args()
def main()->None:
    a=args();r=apply(a.staging,a.ledger_root,a.metadata_out);print(f"Actor-edge ledger append · new={r['new_count']} · unchanged={r['unchanged_count']} · integrity={r['ledger']['integrity']}")
if __name__=="__main__":main()
