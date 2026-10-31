#!/usr/bin/env python3
"""Build a compact presentation payload from append-only daily sentiment snapshots."""
from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

DEFAULT_OUT = Path(__file__).resolve().parents[1] / "worldclass" / "market-sentiment.json"


def load(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"snapshot root is not an object: {path}")
    return payload


def compact_source(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "label": item.get("label"),
        "status": item.get("status"),
        "sentiment_score": item.get("sentiment_score"),
        "sentiment_index": item.get("sentiment_index"),
        "bullish_pct": item.get("bullish_pct"),
        "bearish_pct": item.get("bearish_pct"),
        "buzz_score": item.get("buzz_score"),
        "trend": item.get("trend"),
        "activity": item.get("activity") or {},
        "drivers": (item.get("drivers") or [])[:8],
        "error": item.get("error"),
    }


def compact_snapshot(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "observation_date": payload.get("observation_date"),
        "retrieved_at_utc": payload.get("retrieved_at_utc"),
        "composite": payload.get("composite") or {},
        "sources": {
            source: compact_source(item)
            for source, item in (payload.get("sources") or {}).items()
            if isinstance(item, dict)
        },
    }


def build(ledger_root: Path, limit: int) -> dict[str, Any]:
    directory = ledger_root / "sentiment"
    files = sorted(directory.rglob("*.json")) if directory.exists() else []
    snapshots = [compact_snapshot(load(path)) for path in files]
    snapshots = [item for item in snapshots if item.get("observation_date")]
    snapshots.sort(key=lambda item: item["observation_date"])
    if limit > 0:
        snapshots = snapshots[-limit:]
    latest = snapshots[-1] if snapshots else None
    return {
        "schema_version": 1,
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "authoritative_history": "sentiment-ledger branch",
        "provider": "Adanos",
        "sources": ["reddit", "x", "news", "polymarket"],
        "history_count": len(snapshots),
        "latest": latest,
        "history": snapshots,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ledger-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--limit", type=int, default=400)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    payload = build(args.ledger_root, args.limit)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    print(f"Market sentiment presentation payload · history={payload['history_count']} · latest={payload['latest'] and payload['latest']['observation_date']}")


if __name__ == "__main__":
    main()
