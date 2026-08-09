#!/usr/bin/env python3
"""Build full-history research without bloating browser runtime data.

Index research is extracted from the canonical interactive dashboard. Metals
research uses a separately persisted full-history source with daily prices. The
orchestrator can bootstrap that source from a pre-split deployed metals cache,
restore it from gh-pages, or reconstruct it from official CFTC/Yahoo inputs on
the first split-aware deployment. Browser presentation is always rewritten to
its bounded runtime form only after full-history research completes.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import build_worldclass_backtest as cot_backtest
import build_worldclass_bundle as bundle
import build_worldclass_metals as metals_builder
import build_worldclass_regime_backtest as regime_backtest

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "interactive_cot_dashboard.html"
WORLDCLASS = ROOT / "worldclass"
TEMP_RESEARCH_BASE = WORLDCLASS / ".research-base.tmp.json"
FULL_METALS = metals_builder.RESEARCH_OUT
RUNTIME_METALS = metals_builder.OUT

RESEARCH_CONSTANTS = (
    "COT_DATA",
    "PRICE_DATA",
    "MACRO_MONITOR",
)


def atomic_write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
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


def metals_history_is_full(payload: dict) -> bool:
    for market in ("gold", "silver"):
        cot_rows = ((payload.get("markets") or {}).get(market) or {}).get("records") or []
        price_rows = ((payload.get("prices") or {}).get(market) or {}).get("records") or []
        if len(cot_rows) < 500 or len(price_rows) < 1000:
            return False
    return True


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def restore_full_metals_from_gh_pages() -> bool:
    candidates = (
        "FETCH_HEAD:worldclass/research/metals-full.json",
        "origin/gh-pages:worldclass/research/metals-full.json",
    )
    for revision in candidates:
        result = subprocess.run(
            ["git", "show", revision],
            cwd=ROOT.parent,
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode != 0 or not result.stdout.strip():
            continue
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError:
            continue
        if metals_history_is_full(payload):
            atomic_write(FULL_METALS, payload)
            print(f"Restored persistent full-history metals source from {revision}")
            return True
    return False


def rebuild_full_metals_from_official() -> dict:
    """One-time migration/recovery path when no valid full source exists.

    Never manufacture research history from the compact browser bundle. Fetch
    the canonical CFTC Disaggregated history and Yahoo daily price history using
    the same governed metals builder used by scheduled refreshes.
    """
    print("No persisted full-history metals source found; rebuilding from official inputs.")
    try:
        runtime, research = metals_builder.build_payloads()
    except Exception as exc:
        raise FileNotFoundError(
            "Full-history metals research is unavailable and official reconstruction failed; refusing to shorten Gold/Silver research."
        ) from exc
    if not metals_history_is_full(research):
        raise RuntimeError("Official metals reconstruction did not meet full-history research floors")
    atomic_write(FULL_METALS, research)
    atomic_write(RUNTIME_METALS, runtime)
    print(f"Reconstructed persistent full-history metals source at {FULL_METALS}")
    return research


def ensure_full_metals() -> dict:
    if FULL_METALS.exists():
        payload = read_json(FULL_METALS)
        if metals_history_is_full(payload):
            return payload

    # Migration compatibility: a genuinely pre-split production cache can still
    # seed the persistent source. A compact runtime never qualifies here.
    if RUNTIME_METALS.exists():
        runtime_payload = read_json(RUNTIME_METALS)
        if metals_history_is_full(runtime_payload):
            atomic_write(FULL_METALS, runtime_payload)
            print("Bootstrapped persistent full-history metals source from pre-split runtime cache")
            return runtime_payload

    if restore_full_metals_from_gh_pages():
        return read_json(FULL_METALS)

    return rebuild_full_metals_from_official()


def main() -> None:
    WORLDCLASS.mkdir(parents=True, exist_ok=True)
    research_base = build_research_base()
    full_metals = ensure_full_metals()
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

    atomic_write(RUNTIME_METALS, metals_builder.runtime_from_research(full_metals))

    print(f"Saved full-history COT backtest: {cot_backtest.OUT} ({cot_backtest.OUT.stat().st_size:,} bytes)")
    print(f"Saved full-history regime backtest: {regime_backtest.OUT} ({regime_backtest.OUT.stat().st_size:,} bytes)")
    print(f"Preserved full-history metals research: {FULL_METALS}")
    print(f"Compacted browser metals runtime: {RUNTIME_METALS}")


if __name__ == "__main__":
    main()
