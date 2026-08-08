#!/usr/bin/env python3
"""Build full-history worldclass research artifacts without bloating runtime data.

`worldclass/base.json` is intentionally optimized for browser startup and may
retain only a bounded chart history. Backtests must not inherit that retention
policy. This orchestrator extracts the full COT/price/macro research constants
from the canonical interactive dashboard into a temporary research base, points
the existing lookahead-safe backtest builders at it, writes their normal output
artifacts, and leaves the compact runtime bundle untouched.
"""
from __future__ import annotations

import json
from pathlib import Path

import build_worldclass_backtest as cot_backtest
import build_worldclass_bundle as bundle
import build_worldclass_regime_backtest as regime_backtest

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "interactive_cot_dashboard.html"
WORLDCLASS = ROOT / "worldclass"
TEMP_RESEARCH_BASE = WORLDCLASS / ".research-base.tmp.json"

RESEARCH_CONSTANTS = (
    "COT_DATA",
    "PRICE_DATA",
    "MACRO_MONITOR",
)


def atomic_write(path: Path, payload: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    temporary.replace(path)


def build_research_base() -> dict:
    if not SOURCE.exists():
        raise FileNotFoundError(f"Missing canonical research dashboard: {SOURCE}")
    text = SOURCE.read_text(encoding="utf-8")
    payload = {name: bundle.extract_json_constant(text, name) for name in RESEARCH_CONSTANTS}
    if not payload.get("COT_DATA") or not payload.get("PRICE_DATA"):
        raise RuntimeError("Canonical research dashboard is missing full COT or price history")
    return payload


def main() -> None:
    WORLDCLASS.mkdir(parents=True, exist_ok=True)
    research_base = build_research_base()
    atomic_write(TEMP_RESEARCH_BASE, research_base)

    original_cot_base = cot_backtest.BASE
    original_regime_base = regime_backtest.BASE
    try:
        cot_backtest.BASE = TEMP_RESEARCH_BASE
        regime_backtest.BASE = TEMP_RESEARCH_BASE

        cot_payload = cot_backtest.build()
        atomic_write(cot_backtest.OUT, cot_payload)

        regime_payload = regime_backtest.build()
        atomic_write(regime_backtest.OUT, regime_payload)
    finally:
        cot_backtest.BASE = original_cot_base
        regime_backtest.BASE = original_regime_base
        TEMP_RESEARCH_BASE.unlink(missing_ok=True)

    print(f"Saved full-history COT backtest: {cot_backtest.OUT} ({cot_backtest.OUT.stat().st_size:,} bytes)")
    print(f"Saved full-history regime backtest: {regime_backtest.OUT} ({regime_backtest.OUT.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
