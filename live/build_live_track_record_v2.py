#!/usr/bin/env python3
"""Build presentation track record after validating mixed legacy/v2 ledger."""
from __future__ import annotations
import sys
import build_live_track_record as legacy
import ledger_v2

def main()->None:
    original=legacy.validate_ledger;legacy.validate_ledger=ledger_v2.validate_ledger
    try:legacy.main()
    finally:legacy.validate_ledger=original
if __name__=='__main__':main()
