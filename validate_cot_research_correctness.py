#!/usr/bin/env python3
"""Independent correctness gates for release-aligned COT research.

The validator recomputes known CFTC availability cases and never trusts a
`lookahead_safe` flag merely because a generated artifact declares it.
"""
from __future__ import annotations
import json
from datetime import date
from pathlib import Path

import build_worldclass_backtest as backtest
import cot_release_alignment_v2 as alignment
from cftc_release_calendar import DEFAULT_CALENDAR,availability_at,normal_release_date,release_date,release_record

ROOT=Path(__file__).resolve().parent;BACKTEST=ROOT/"worldclass"/"backtest.json"
def assert_equal(actual,expected,label:str)->None:
    if actual!=expected:raise AssertionError(f"{label}: expected {expected!r}, got {actual!r}")

def validate_known_release_fixtures()->None:
    fixtures={
        "2018-12-24":"2019-02-01",
        "2019-01-08":"2019-02-08",
        "2019-02-26":"2019-03-05",
        "2020-12-21":"2020-12-28",
        "2021-06-15":"2021-06-21",
        "2023-01-31":"2023-02-24",
        "2023-02-07":"2023-03-03",
        "2023-02-14":"2023-03-08",
        "2023-02-21":"2023-03-10",
        "2023-02-28":"2023-03-14",
        "2023-03-07":"2023-03-16",
        "2023-03-14":"2023-03-21",
        "2025-01-07":"2025-01-13",
        "2025-09-30":"2025-11-19",
        "2025-10-07":"2025-11-21",
        "2025-11-10":"2025-12-10",
        "2025-12-23":"2025-12-29",
        "2025-12-30":"2026-01-05",
        "2026-06-16":"2026-06-22",
        "2026-06-30":"2026-07-06",
        "2026-08-04":"2026-08-07",
    }
    for report,expected in fixtures.items():assert_equal(release_date(report).isoformat(),expected,f"release fixture {report}")

def validate_business_day_rule()->None:
    # Thanksgiving falls in the three-day processing interval after Tue Nov 26.
    # Wed=day1, Thu holiday, Fri=day2, Mon=day3 => Monday Dec 2.
    thanksgiving=release_record("2024-11-26")
    assert_equal(thanksgiving["actual_release_date"],"2024-12-02","Thanksgiving third-business-day release")
    assert_equal(thanksgiving["availability_source_type"],"NORMAL_BUSINESS_DAY_SCHEDULE_ASSUMPTION","Thanksgiving derived rule source")
    if not thanksgiving.get("processing_holidays"):raise AssertionError("Thanksgiving processing holiday provenance missing")
    # A Tuesday holiday can shift the CFTC as-of row to Monday. The generic
    # third-business-day rule still produces Friday after skipping Tuesday.
    assert_equal(normal_release_date("2017-07-03").isoformat(),"2017-07-07","Monday as-of before Independence Day")
    prices=[{"date":date(2024,11,29),"date_str":"2024-11-29","price":100.0},{"date":date(2024,12,2),"date_str":"2024-12-02","price":101.0}]
    # Legacy nominal target is report+3 = Nov 29, but strict v2 must select Dec 2.
    assert_equal(alignment.first_price_index_on_or_after(prices,date(2024,11,29)),1,"Thanksgiving compatibility price anchor")

def validate_timezone_fixtures()->None:
    march=release_record("2026-03-10")
    if "T20:30:00+01:00" not in str(march["availability_at_stockholm"]):raise AssertionError(f"DST fixture mismatch: {march['availability_at_stockholm']}")
    april=release_record("2026-03-31")
    if "T21:30:00+02:00" not in str(april["availability_at_stockholm"]):raise AssertionError(f"post-DST fixture mismatch: {april['availability_at_stockholm']}")

def validate_calendar_schema()->None:
    payload=json.loads(DEFAULT_CALENDAR.read_text(encoding="utf-8"))
    if int(payload.get("schema_version") or 0)!=2 or not payload.get("calendar_version"):raise AssertionError("release calendar schema/version invalid")
    required_sources={"release_schedule","historical_special_announcements","cot_faq","third_business_day_history","2019_shutdown_schedule","2023_ion_postponement"}
    if not required_sources.issubset(payload.get("sources") or {}):raise AssertionError("release calendar source provenance incomplete")
    for report,row in (payload.get("exceptions") or {}).items():
        date.fromisoformat(report);date.fromisoformat(str(row["release_date"]))
        if row.get("source_type") not in {"CFTC_ACTUAL_EXCEPTION","CFTC_PUBLISHED_SCHEDULE"}:raise AssertionError(f"invalid source_type for {report}")

def validate_compatibility_price_alignment()->None:
    prices=[{"date":date(2025,10,3),"date_str":"2025-10-03","price":100.0},{"date":date(2025,11,18),"date_str":"2025-11-18","price":105.0},{"date":date(2025,11,19),"date_str":"2025-11-19","price":106.0},{"date":date(2025,11,20),"date_str":"2025-11-20","price":107.0}]
    index=backtest.first_price_index_on_or_after(prices,date(2025,10,3));assert_equal(index,2,"shutdown compatibility price anchor")
    strict=alignment.first_price_index_on_or_after(prices,date(2025,10,3));assert_equal(strict,2,"strict shutdown compatibility price anchor")
    if index is None or prices[index]["date"]<release_date("2025-09-30"):raise AssertionError("shared compatibility bridge selected a pre-release price")
    normal=[{"date":date(2026,8,7),"date_str":"2026-08-07","price":200.0},{"date":date(2026,8,10),"date_str":"2026-08-10","price":201.0}]
    assert_equal(alignment.first_price_index_on_or_after(normal,date(2026,8,7)),0,"normal Friday compatibility price anchor")

def validate_release_corrected_backtest_if_present()->None:
    if not BACKTEST.exists():return
    payload=json.loads(BACKTEST.read_text(encoding="utf-8"))
    if payload.get("research_generation")!="release-corrected-v2":return
    if payload.get("information_contract_version")!="cftc-public-availability-v2":raise AssertionError("release-corrected backtest missing information contract version")
    for market,market_block in (payload.get("markets") or {}).items():
        for dataset,block in (market_block.get("datasets") or {}).items():
            current=block.get("current") or {};report=current.get("report_date");release=current.get("release_target_date")
            if report and release and release_date(report).isoformat()!=release:raise AssertionError(f"{market}/{dataset}: current release date is not canonical")
            if (block.get("methodology") or {}).get("release_calendar_aware") is not True:raise AssertionError(f"{market}/{dataset}: release calendar awareness missing")

def main()->None:
    validate_calendar_schema();validate_known_release_fixtures();validate_business_day_rule();validate_timezone_fixtures();validate_compatibility_price_alignment();validate_release_corrected_backtest_if_present()
    if availability_at("2025-09-30").date()<=date(2025,10,3):raise AssertionError("shutdown anti-lookahead fixture failed")
    print("COT research correctness: PASS")
if __name__=="__main__":main()
