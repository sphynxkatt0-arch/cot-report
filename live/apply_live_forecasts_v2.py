#!/usr/bin/env python3
"""Apply staged v2 forecasts without weakening immutable-ledger validation."""
from __future__ import annotations
import argparse
from pathlib import Path

import apply_live_forecasts as legacy
import ledger_v2


def apply(staging:Path,ledger_root:Path,metadata_out:Path):
    original_validate=legacy.validate_forecast
    legacy.validate_forecast=ledger_v2.validate_forecast
    try:return legacy.apply(staging,ledger_root,metadata_out)
    finally:legacy.validate_forecast=original_validate

def main()->None:
    p=argparse.ArgumentParser();p.add_argument('--staging',type=Path,required=True);p.add_argument('--ledger-root',type=Path,required=True);p.add_argument('--metadata-out',type=Path,required=True);a=p.parse_args()
    result=apply(a.staging,a.ledger_root,a.metadata_out)
    print(f"V2 ledger append preparation · new={result['new_count']} · unchanged={result['unchanged_count']}")
if __name__=='__main__':main()
