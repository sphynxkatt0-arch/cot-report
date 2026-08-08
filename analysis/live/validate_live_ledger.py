#!/usr/bin/env python3
"""Validate live-ledger forecast immutability and manifest-chain integrity."""
from __future__ import annotations

import argparse
from pathlib import Path

from ledger import validate_manifest_chain


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ledger-root", type=Path, required=True)
    parser.add_argument("--verify-git-history", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = validate_manifest_chain(args.ledger_root, verify_git_history=args.verify_git_history)
    print(
        f"Live ledger integrity PASS · forecasts={result['forecast_count']} · "
        f"manifests={result['manifest_count']} · head={result['latest_manifest_hash']}"
    )


if __name__ == "__main__":
    main()
