#!/usr/bin/env python3
"""Macro-liquidity v1.2 validation layered on the governed v1.1 contracts."""
from __future__ import annotations

import csv
import json
from pathlib import Path

import validate_directional_outputs_v11 as v11

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "model_output"
MACRO = OUT / "macro_liquidity_expansion.json"
FISCAL_SOURCES = OUT / "treasury_cash_source_status.csv"
DASHBOARD = ROOT / "interactive_cot_dashboard.html"
REPORT = ROOT / "directional_cot_report.html"


def read_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def validate_v12() -> None:
    failures: list[str] = []
    try:
        payload = json.loads(MACRO.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        failures.append(f"cannot read macro-liquidity v1.2 payload: {exc}")
        payload = {}

    if payload:
        if payload.get("model_version") != "macro-liquidity-control-room-v1.2":
            failures.append("macro-liquidity model_version must be v1.2")
        pillar = (payload.get("pillars") or {}).get("fiscal_cash_flow")
        if not isinstance(pillar, dict):
            failures.append("macro-liquidity payload is missing fiscal_cash_flow pillar")
        context = payload.get("treasury_cash_context")
        if not isinstance(context, dict):
            failures.append("macro-liquidity payload is missing treasury_cash_context")
        sources = payload.get("sources") or []
        fiscal_keys = {
            source.get("key")
            for source in sources
            if isinstance(source, dict) and source.get("dataset") == "fiscaldata"
        }
        if fiscal_keys != {"treasury_operating_cash", "treasury_cash_flows"}:
            failures.append(f"Treasury Fiscal Data sources incomplete: {sorted(fiscal_keys)}")

    fiscal_rows = read_rows(FISCAL_SOURCES)
    if len(fiscal_rows) != 2:
        failures.append(f"Treasury source status expected 2 rows, found {len(fiscal_rows)}")
    else:
        for row in fiscal_rows:
            if row.get("dataset") != "fiscaldata":
                failures.append(f"invalid Treasury source dataset for {row.get('key')}")
            if row.get("status") not in {"fresh", "stale", "unavailable"}:
                failures.append(f"invalid Treasury source status for {row.get('key')}: {row.get('status')}")

    for path, label in ((DASHBOARD, "dashboard"), (REPORT, "directional report")):
        if not path.exists():
            failures.append(f"{label} is missing")
            continue
        source = path.read_text(encoding="utf-8", errors="replace")
        if source.count('id="fiscalCashPath"') != 1:
            failures.append(f"{label} Daily Treasury cash path is missing or duplicated")
        for text in ("Daily Treasury Cash Flow", "Private cash effect · 5d", "Tax deposits · 5d"):
            if text not in source:
                failures.append(f"{label} is missing {text}")

    if DASHBOARD.exists():
        source = DASHBOARD.read_text(encoding="utf-8", errors="replace")
        if source.count('id="marketPlaybook"') != 1:
            failures.append("dashboard market playbook is missing or duplicated")
        if source.count('id="xpResearchToggle"') != 1:
            failures.append("dashboard research toggle is missing or duplicated")
        for anchor in (
            'href="#directionalDecisionSummary"',
            'href="#macroLiquidityControlRoom"',
            'href="#fiscalCashPath"',
            'href="#directionalDecisionQuality"',
        ):
            if anchor not in source:
                failures.append(f"dashboard navigation is missing {anchor}")
        for text in ("What to do, what must confirm", "Next action", "Hide research"):
            if text not in source:
                failures.append(f"dashboard decision experience is missing {text}")

    if failures:
        raise RuntimeError("Directional v1.2 output validation failed:\n- " + "\n- ".join(failures))


def main() -> None:
    v11.main()
    validate_v12()
    print("Directional and macro-liquidity v1.2 output validation passed.")


if __name__ == "__main__":
    main()
