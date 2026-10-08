#!/usr/bin/env python3
"""Validate mixed immutable legacy + release-corrected v2 general live ledger."""
from __future__ import annotations
import argparse
from pathlib import Path
import ledger_v2

def main():
    p=argparse.ArgumentParser();p.add_argument("--ledger-root",type=Path,required=True);p.add_argument("--verify-git-history",action="store_true");a=p.parse_args();result=ledger_v2.validate_ledger(a.ledger_root,verify_git_history=a.verify_git_history);print(f"Live ledger v2 integrity PASS · forecasts={result['forecast_count']} · entries={result['entry_count']} · outcomes={result['outcome_count']} · manifests={result['manifest_count']} · head={result['latest_manifest_hash']}")
if __name__=="__main__":main()
