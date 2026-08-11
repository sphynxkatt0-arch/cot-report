#!/usr/bin/env python3
"""Append immutable manifest entries while validating mixed legacy/v2 ledgers."""
from __future__ import annotations
import argparse
from pathlib import Path

import append_ledger_manifest as legacy
import ledger_v2


def append(ledger_root:Path,metadata_path:Path,forecast_commit_sha:str):
    original=legacy.validate_manifest_chain
    legacy.validate_manifest_chain=ledger_v2.validate_manifest_chain
    try:return legacy.append(ledger_root,metadata_path,forecast_commit_sha)
    finally:legacy.validate_manifest_chain=original

def main()->None:
    p=argparse.ArgumentParser();p.add_argument('--ledger-root',type=Path,required=True);p.add_argument('--metadata',type=Path,required=True);p.add_argument('--forecast-commit-sha',required=True);a=p.parse_args()
    result=append(a.ledger_root,a.metadata,a.forecast_commit_sha)
    print(f"V2 ledger manifests appended · created={result['created']} · head={result['latest_manifest_hash']}")
if __name__=='__main__':main()
