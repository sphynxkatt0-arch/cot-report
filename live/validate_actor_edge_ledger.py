#!/usr/bin/env python3
from __future__ import annotations
import argparse,json
from pathlib import Path
from actor_edge_ledger import validate_ledger

def main()->None:
    p=argparse.ArgumentParser();p.add_argument("--ledger-root",type=Path,required=True);a=p.parse_args();state=validate_ledger(a.ledger_root);print(json.dumps(state,sort_keys=True));assert state["integrity"]=="PASS"
if __name__=="__main__":main()
