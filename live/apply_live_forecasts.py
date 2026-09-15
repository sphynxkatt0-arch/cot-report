#!/usr/bin/env python3
"""Apply staged live forecasts to a live-ledger checkout without overwriting history."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from ledger import LedgerError, atomic_write_json, sha256_file, validate_forecast


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise LedgerError(f"JSON root must be an object: {path}")
    return payload


def apply(staging: Path, ledger_root: Path, metadata_out: Path) -> dict[str, Any]:
    plan_path = staging / "plan.json"
    if not plan_path.exists():
        raise LedgerError(f"staging plan missing: {plan_path}")
    plan = load_json(plan_path)
    new_items: list[dict[str, Any]] = []
    unchanged: list[dict[str, Any]] = []

    for item in plan.get("forecasts") or []:
        relative_text = str(item.get("relative_path") or "")
        if not relative_text.startswith("live/forecasts/") or ".." in Path(relative_text).parts:
            raise LedgerError(f"unsafe forecast path in staging plan: {relative_text!r}")
        source = staging / relative_text
        if not source.exists():
            raise LedgerError(f"staged forecast missing: {relative_text}")
        forecast = load_json(source)
        validate_forecast(forecast)
        expected_hash = str(item.get("forecast_hash") or "")
        actual_hash = sha256_file(source)
        if actual_hash != expected_hash:
            raise LedgerError(f"staged forecast hash mismatch: {relative_text}")
        if forecast.get("signal_id") != item.get("signal_id"):
            raise LedgerError(f"staged forecast signal_id mismatch: {relative_text}")

        destination = ledger_root / relative_text
        if destination.exists():
            if destination.read_bytes() != source.read_bytes():
                raise LedgerError(f"immutable forecast overwrite refused: {relative_text}")
            unchanged.append(item)
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(source.read_bytes())
        new_items.append(item)

    metadata = {
        "schema_version": 1,
        "source_model_version": plan.get("model_version"),
        "source_model_spec_hash": plan.get("model_spec_hash"),
        "new_forecasts": sorted(new_items, key=lambda value: value["relative_path"]),
        "unchanged_forecasts": sorted(unchanged, key=lambda value: value["relative_path"]),
        "new_count": len(new_items),
        "unchanged_count": len(unchanged),
    }
    atomic_write_json(metadata_out, metadata)
    return metadata


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--staging", type=Path, required=True)
    parser.add_argument("--ledger-root", type=Path, required=True)
    parser.add_argument("--metadata-out", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = apply(args.staging, args.ledger_root, args.metadata_out)
    print(
        f"Ledger append preparation · new={result['new_count']} · "
        f"unchanged={result['unchanged_count']}"
    )


if __name__ == "__main__":
    main()
