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
DECISIONS = OUT / "cot_direction_latest.json"
FISCAL_SOURCES = OUT / "treasury_cash_source_status.csv"
DASHBOARD = ROOT / "interactive_cot_dashboard.html"
REPORT = ROOT / "directional_cot_report.html"


def read_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def read_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_v12() -> None:
    failures: list[str] = []
    try:
        payload = read_json(MACRO)
    except (OSError, json.JSONDecodeError) as exc:
        failures.append(f"cannot read macro-liquidity v1.2 payload: {exc}")
        payload = {}

    if isinstance(payload, dict) and payload:
        if payload.get("model_version") != "macro-liquidity-control-room-v1.2":
            failures.append("macro-liquidity model_version must be v1.2")
        pillars = payload.get("pillars") or {}
        for pillar_name in ("fiscal_cash_flow", "auction_absorption"):
            if not isinstance(pillars.get(pillar_name), dict):
                failures.append(f"macro-liquidity payload is missing {pillar_name} pillar")
        if not isinstance(payload.get("treasury_cash_context"), dict):
            failures.append("macro-liquidity payload is missing treasury_cash_context")
        if not isinstance(payload.get("treasury_auction_context"), dict):
            failures.append("macro-liquidity payload is missing treasury_auction_context")
        sources = payload.get("sources") or []
        fiscal_keys = {
            source.get("key")
            for source in sources
            if isinstance(source, dict) and source.get("dataset") == "fiscaldata"
        }
        expected_fiscal_keys = {
            "treasury_operating_cash",
            "treasury_cash_flows",
            "treasury_auction_absorption",
        }
        if fiscal_keys != expected_fiscal_keys:
            failures.append(f"Treasury Fiscal Data sources incomplete: {sorted(fiscal_keys)}")
    elif not failures:
        failures.append("macro-liquidity v1.2 payload must be a non-empty object")

    fiscal_rows = read_rows(FISCAL_SOURCES)
    if len(fiscal_rows) != 3:
        failures.append(f"Treasury source status expected 3 rows, found {len(fiscal_rows)}")
    else:
        for row in fiscal_rows:
            if row.get("dataset") != "fiscaldata":
                failures.append(f"invalid Treasury source dataset for {row.get('key')}")
            if row.get("status") not in {"fresh", "stale", "unavailable"}:
                failures.append(f"invalid Treasury source status for {row.get('key')}: {row.get('status')}")

    try:
        decisions = read_json(DECISIONS)
    except (OSError, json.JSONDecodeError) as exc:
        failures.append(f"cannot read governed decisions for v1.2 validation: {exc}")
        decisions = []
    if not isinstance(decisions, list) or len(decisions) != 2:
        failures.append("v1.2 decisions must contain exactly S&P 500 and Nasdaq-100")
    else:
        for row in decisions:
            market = str(row.get("market") or "unknown")
            for field in (
                "liquidity_plumbing_guard",
                "liquidity_plumbing_guard_active",
                "liquidity_plumbing_guard_reliable",
            ):
                if field not in row:
                    failures.append(f"{market}: missing {field}")
            evaluation = row.get("liquidity_plumbing_guard")
            if not isinstance(evaluation, dict):
                failures.append(f"{market}: liquidity plumbing guard must be an object")
                continue
            if evaluation.get("model_version") != "macro-liquidity-guard-v1.0":
                failures.append(f"{market}: invalid liquidity plumbing guard model version")
            active = bool(row.get("liquidity_plumbing_guard_active"))
            reliable = bool(row.get("liquidity_plumbing_guard_reliable"))
            severe = evaluation.get("severe_pillars") or []
            minimum = int(evaluation.get("minimum_severe_pillars") or 0)
            if active and not reliable:
                failures.append(f"{market}: active plumbing guard cannot be unreliable")
            if active and len(severe) < minimum:
                failures.append(f"{market}: active plumbing guard has too few severe pillars")
            if active and float(row.get("exposure_multiplier") or 0.0) != 0.0:
                failures.append(f"{market}: active plumbing guard must set exposure to zero")
            release = str(row.get("release_status") or "current")
            action = str(row.get("final_action") or "")
            if active and release == "current" and action not in {
                "Wait — Liquidity Plumbing Stress",
                "Hedge / Risk Override",
                "Wait — Macro Data Incomplete",
            }:
                failures.append(f"{market}: active plumbing guard is not reflected in final action")

    for path, label in ((DASHBOARD, "dashboard"), (REPORT, "directional report")):
        if not path.exists():
            failures.append(f"{label} is missing")
            continue
        source = path.read_text(encoding="utf-8", errors="replace")
        if source.count('id="fiscalCashPath"') != 1:
            failures.append(f"{label} Daily Treasury cash path is missing or duplicated")
        if source.count('id="auctionAbsorption"') != 1:
            failures.append(f"{label} Treasury auction absorption is missing or duplicated")
        for text in (
            "Daily Treasury Cash Flow",
            "Private cash effect · 5d",
            "Tax deposits · 5d",
            "Treasury Auction Demand Quality",
            "Average bid-to-cover delta",
        ):
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
            'href="#auctionAbsorption"',
            'href="#directionalDecisionQuality"',
        ):
            if anchor not in source:
                failures.append(f"dashboard navigation is missing {anchor}")
        for text in (
            "What to do, what must confirm",
            "Next action",
            "Plumbing guard",
            "Show research",
        ):
            if text not in source:
                failures.append(f"dashboard decision experience is missing {text}")
        if "document.body.classList.add('xp-research-hidden')" not in source:
            failures.append("dashboard must hide research-only surfaces by default")

    if failures:
        raise RuntimeError("Directional v1.2 output validation failed:\n- " + "\n- ".join(failures))


def main() -> None:
    v11.main()
    validate_v12()
    print("Directional and macro-liquidity v1.2 output validation passed.")


if __name__ == "__main__":
    main()
