#!/usr/bin/env python3
"""Build full-history worldclass research artifacts without bloating runtime data.

`worldclass/base.json` and `worldclass/metals.json` are presentation-optimized.
Backtests must not inherit those retention policies. This orchestrator points
the existing lookahead-safe builders at full-history index and metals research
sources, writes their normal research artifacts, and leaves runtime bundles
untouched.
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
FULL_METALS = WORLDCLASS / "research" / "metals-full.json"

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


def validate_full_metals() -> None:
    if not FULL_METALS.exists():
        raise FileNotFoundError(f"Missing full-history metals research source: {FULL_METALS}")
    payload = json.loads(FULL_METALS.read_text(encoding="utf-8"))
    for market in ("gold", "silver"):
        cot_rows = ((payload.get("markets") or {}).get(market) or {}).get("records") or []
        price_rows = ((payload.get("prices") or {}).get(market) or {}).get("records") or []
        if len(cot_rows) < 500:
            raise RuntimeError(f"{market}: full-history metals source has only {len(cot_rows)} COT rows")
        if len(price_rows) < 1000:
            raise RuntimeError(f"{market}: full-history metals source has only {len(price_rows)} daily price rows")


def main() -> None:
    WORLDCLASS.mkdir(parents=True, exist_ok=True)
    research_base = build_research_base()
    validate_full_metals()
    atomic_write(TEMP_RESEARCH_BASE, research_base)

    original_cot_base = cot_backtest.BASE
    original_cot_metals = cot_backtest.METALS
    original_regime_base = regime_backtest.BASE
    original_regime_metals = regime_backtest.METALS
    try:
        cot_backtest.BASE = TEMP_RESEARCH_BASE
        cot_backtest.METALS = FULL_METALS
        regime_backtest.BASE = TEMP_RESEARCH_BASE
        regime_backtest.METALS = FULL_METALS

        cot_payload = cot_backtest.build()
        atomic_write(cot_backtest.OUT, cot_payload)

        regime_payload = regime_backtest.build()
        atomic_write(regime_backtest.OUT, regime_payload)
    finally:
        cot_backtest.BASE = original_cot_base
        cot_backtest.METALS = original_cot_metals
        regime_backtest.BASE = original_regime_base
        regime_backtest.METALS = original_regime_metals
        TEMP_RESEARCH_BASE.unlink(missing_ok=True)

    print(f"Saved full-history COT backtest: {cot_backtest.OUT} ({cot_backtest.OUT.stat().st_size:,} bytes)")
    print(f"Saved full-history regime backtest: {regime_backtest.OUT} ({regime_backtest.OUT.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
