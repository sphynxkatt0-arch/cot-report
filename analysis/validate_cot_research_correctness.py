#!/usr/bin/env python3
"""Independent correctness gates for release-aligned COT research.

This validator intentionally recomputes calendar expectations and does not trust
`lookahead_safe` metadata emitted by research artifacts.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from cftc_release_calendar import DEFAULT_CALENDAR, availability_at, release_date, release_record

ROOT = Path(__file__).resolve().parent
BACKTEST = ROOT / "worldclass" / "backtest.json"


def assert_equal(actual, expected, label: str) -> None:
    if actual != expected:
        raise AssertionError(f"{label}: expected {expected!r}, got {actual!r}")


def validate_known_release_fixtures() -> None:
    fixtures = {
        "2025-01-07": "2025-01-13",
        "2025-09-30": "2025-11-19",
        "2025-10-07": "2025-11-21",
        "2025-11-10": "2025-12-10",
        "2025-12-23": "2025-12-29",
        "2025-12-30": "2026-01-05",
        "2026-06-16": "2026-06-22",
        "2026-06-30": "2026-07-06",
        "2026-08-04": "2026-08-07",
    }
    for report, expected_release in fixtures.items():
        assert_equal(release_date(report).isoformat(), expected_release, f"release fixture {report}")


def validate_timezone_fixtures() -> None:
    # US DST begins before Sweden in March. A fixed 21:30 Stockholm assumption
    # is therefore wrong for this release week.
    march = release_record("2026-03-10")
    if "T20:30:00+01:00" not in str(march["availability_at_stockholm"]):
        raise AssertionError(f"DST fixture mismatch: {march['availability_at_stockholm']}")
    april = release_record("2026-03-31")
    if "T21:30:00+02:00" not in str(april["availability_at_stockholm"]):
        raise AssertionError(f"post-DST fixture mismatch: {april['availability_at_stockholm']}")


def validate_calendar_schema() -> None:
    payload = json.loads(DEFAULT_CALENDAR.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1 or not payload.get("calendar_version"):
        raise AssertionError("release calendar schema/version invalid")
    for report, row in (payload.get("exceptions") or {}).items():
        date.fromisoformat(report)
        date.fromisoformat(str(row["release_date"]))
        if row.get("source_type") not in {"CFTC_ACTUAL_EXCEPTION", "CFTC_PUBLISHED_SCHEDULE"}:
            raise AssertionError(f"invalid source_type for {report}")


def validate_release_corrected_backtest_if_present() -> None:
    if not BACKTEST.exists():
        return
    payload = json.loads(BACKTEST.read_text(encoding="utf-8"))
    if payload.get("research_generation") != "release-corrected-v2":
        # Old frozen/runtime artifacts are intentionally preserved until rebuilt.
        return
    if payload.get("information_contract_version") != "cftc-public-availability-v2":
        raise AssertionError("release-corrected backtest missing information contract version")
    for market, market_block in (payload.get("markets") or {}).items():
        for dataset, block in (market_block.get("datasets") or {}).items():
            current = block.get("current") or {}
            report = current.get("report_date")
            release = current.get("release_target_date")
            if report and release and release_date(report).isoformat() != release:
                raise AssertionError(f"{market}/{dataset}: current release date is not canonical")
            methodology = block.get("methodology") or {}
            if methodology.get("release_calendar_aware") is not True:
                raise AssertionError(f"{market}/{dataset}: release calendar awareness missing")


def main() -> None:
    validate_calendar_schema()
    validate_known_release_fixtures()
    validate_timezone_fixtures()
    validate_release_corrected_backtest_if_present()
    # Hard proof that the 2025 shutdown fixture is weeks later than the naive +3 rule.
    if availability_at("2025-09-30").date() <= date(2025, 10, 3):
        raise AssertionError("shutdown anti-lookahead fixture failed")
    print("COT research correctness: PASS")


if __name__ == "__main__":
    main()
