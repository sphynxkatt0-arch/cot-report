#!/usr/bin/env python3
"""Append immutable manifest entries after forecast files have been committed."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from ledger import (
    COMMIT_SHA_RE,
    LedgerError,
    canonical_json_bytes,
    sha256_bytes,
    sha256_file,
    validate_manifest_chain,
)


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise LedgerError(f"JSON root must be an object: {path}")
    return payload


def manifest_filename(item: dict[str, Any]) -> str:
    stamp = re.sub(r"[^0-9TZ]", "", str(item.get("created_at_utc") or ""))
    signal_id = str(item.get("signal_id") or "")
    if len(signal_id) != 64:
        raise LedgerError("manifest item signal_id invalid")
    return f"{stamp}-{signal_id}.json"


def append(ledger_root: Path, metadata_path: Path, forecast_commit_sha: str) -> dict[str, Any]:
    if not COMMIT_SHA_RE.fullmatch(forecast_commit_sha):
        raise LedgerError("forecast commit must be a full Git commit SHA")
    metadata = load_json(metadata_path)
    new_items = metadata.get("new_forecasts") or []
    if not new_items:
        state = validate_manifest_chain(ledger_root)
        return {"created": 0, "latest_manifest_hash": state["latest_manifest_hash"]}

    allowed = {str(item.get("relative_path") or "") for item in new_items}
    state = validate_manifest_chain(ledger_root, allowed_uncovered=allowed)
    if state["transition_uncovered_count"] != len(allowed):
        raise LedgerError("live-ledger transition contains an unexpected covered/uncovered forecast set")

    previous_hash = state["latest_manifest_hash"]
    manifest_dir = ledger_root / "live" / "manifests"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    created = 0

    # The validator reads manifest files in lexicographic filename order, so the
    # chain must be constructed in that exact same deterministic order.
    for item in sorted(new_items, key=manifest_filename):
        forecast_path_text = str(item.get("relative_path") or "")
        forecast_path = ledger_root / forecast_path_text
        if not forecast_path.exists():
            raise LedgerError(f"new forecast missing before manifest append: {forecast_path_text}")
        actual_hash = sha256_file(forecast_path)
        if actual_hash != item.get("forecast_hash"):
            raise LedgerError(f"new forecast changed before manifest append: {forecast_path_text}")
        manifest = {
            "schema_version": 1,
            "signal_id": item["signal_id"],
            "forecast_path": forecast_path_text,
            "forecast_hash": actual_hash,
            "git_commit_sha": forecast_commit_sha,
            "created_at_utc": item["created_at_utc"],
            "previous_manifest_hash": previous_hash,
        }
        destination = manifest_dir / manifest_filename(item)
        data = canonical_json_bytes(manifest)
        if destination.exists():
            if destination.read_bytes() != data:
                raise LedgerError(f"immutable manifest overwrite refused: {destination.name}")
        else:
            destination.write_bytes(data)
            created += 1
        previous_hash = sha256_bytes(data)

    result = validate_manifest_chain(ledger_root)
    if result["latest_manifest_hash"] != previous_hash:
        raise LedgerError("manifest chain final hash mismatch")
    return {"created": created, "latest_manifest_hash": previous_hash}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ledger-root", type=Path, required=True)
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--forecast-commit-sha", required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = append(args.ledger_root, args.metadata, args.forecast_commit_sha)
    print(f"Ledger manifests appended · created={result['created']} · head={result['latest_manifest_hash']}")


if __name__ == "__main__":
    main()
