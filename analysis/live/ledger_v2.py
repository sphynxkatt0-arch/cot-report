#!/usr/bin/env python3
"""Release-calendar-aware facade for the general prospective COT live ledger.

Legacy forecasts remain immutable and validate under their historical contract.
New v2 forecasts must use canonical CFTC availability and 15:35 New York time.
"""
from __future__ import annotations

from datetime import UTC,date,datetime,timedelta
from typing import Any
from zoneinfo import ZoneInfo

try:
    from . import ledger as legacy
except ImportError:  # direct script/module execution from analysis/live
    import ledger as legacy

# analysis/live -> analysis
import sys
from pathlib import Path
ANALYSIS=Path(__file__).resolve().parents[1]
if str(ANALYSIS) not in sys.path:sys.path.insert(0,str(ANALYSIS))
from cftc_release_calendar import availability_at,release_date as canonical_release_date,release_record

INFORMATION_CONTRACT_V2="cftc-public-availability-v2"
NEW_YORK=ZoneInfo("America/New_York")

def __getattr__(name:str)->Any:return getattr(legacy,name)

def release_vintage_utc(release_target_date:str|date)->datetime:
    day=release_target_date if isinstance(release_target_date,date) else legacy.parse_iso_day(release_target_date)
    return datetime(day.year,day.month,day.day,15,35,tzinfo=NEW_YORK).astimezone(UTC)

def release_vintage_for_report_utc(report_date:str|date)->datetime:return availability_at(report_date)+timedelta(minutes=5)
def within_forecast_window(now_utc:datetime,release_target_date:str|date,*,early_minutes:int=5,window_hours:int=4)->bool:
    vintage=release_vintage_utc(release_target_date);now=now_utc.astimezone(UTC);return vintage-timedelta(minutes=early_minutes)<=now<=vintage+timedelta(hours=window_hours)
def within_report_window(now_utc:datetime,report_date:str|date,*,early_minutes:int=5,window_hours:int=4)->bool:
    vintage=release_vintage_for_report_utc(report_date);now=now_utc.astimezone(UTC);return vintage-timedelta(minutes=early_minutes)<=now<=vintage+timedelta(hours=window_hours)

_UNDERLYING_VALIDATE_FORECAST=legacy.validate_forecast

def validate_forecast(forecast:dict[str,Any])->None:
    explicit=forecast.get("information_contract_version")==INFORMATION_CONTRACT_V2
    report=legacy.parse_iso_day(forecast.get("report_date"));release=legacy.parse_iso_day(forecast.get("release_target_date"));canonical=canonical_release_date(report);canonical_created=legacy.iso_utc(release_vintage_for_report_utc(report))
    inferred=release==canonical and forecast.get("created_at_utc")==canonical_created
    if not explicit and not inferred:
        _UNDERLYING_VALIDATE_FORECAST(forecast);return
    if release!=canonical:raise legacy.LedgerError(f"forecast release_target_date must match canonical CFTC release {canonical}")
    if forecast.get("created_at_utc")!=canonical_created:raise legacy.LedgerError("v2 forecast created_at_utc must be canonical release +5 minutes")
    meta=release_record(report)
    if explicit and forecast.get("release_calendar_hash")!=meta["release_calendar_hash"]:raise legacy.LedgerError("v2 forecast release_calendar_hash mismatch")
    # Reuse every non-timing invariant from the proven legacy validator by
    # validating a timing-normalized shadow copy. The real forecast stays intact.
    shim=dict(forecast);naive=report+timedelta(days=3);shim["release_target_date"]=naive.isoformat();shim["created_at_utc"]=legacy.iso_utc(legacy.release_vintage_utc(naive));_UNDERLYING_VALIDATE_FORECAST(shim)

def write_immutable_forecast(path,forecast):
    validate_forecast(forecast);data=legacy.canonical_json_bytes(forecast)
    if path.exists():
        if path.read_bytes()!=data:raise legacy.LedgerError(f"immutable forecast collision: {path}")
        return "unchanged"
    legacy.atomic_write_bytes(path,data);return "created"

def validate_ledger(ledger_root,*,verify_git_history:bool=False):
    original=legacy.validate_forecast;legacy.validate_forecast=validate_forecast
    try:return legacy.validate_ledger(ledger_root,verify_git_history=verify_git_history)
    finally:legacy.validate_forecast=original
