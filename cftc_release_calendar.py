#!/usr/bin/env python3
"""Canonical CFTC COT public-availability resolver.

Normal COT publication is modeled from the CFTC's stated historical timing rule:
the third U.S. federal business day after the report's as-of date at 15:30
America/New_York. Explicit CFTC special announcements / catch-up schedules
always override this rule (shutdowns, ION, mourning, special closures, etc.).
"""
from __future__ import annotations

import hashlib
import json
from datetime import UTC,date,datetime,time,timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parent
DEFAULT_CALENDAR=ROOT/"reference"/"cftc_release_calendar.json"
NEW_YORK=ZoneInfo("America/New_York");STOCKHOLM=ZoneInfo("Europe/Stockholm");RELEASE_TIME_ET=time(15,30)

def parse_date(value:str|date|datetime)->date:
    if isinstance(value,datetime):return value.date()
    if isinstance(value,date):return value
    return date.fromisoformat(str(value)[:10])

@lru_cache(maxsize=4)
def load_calendar(path_str:str|None=None)->dict[str,Any]:
    path=Path(path_str) if path_str else DEFAULT_CALENDAR
    payload=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload,dict) or int(payload.get("schema_version") or 0) not in {1,2}:raise ValueError(f"Invalid CFTC release calendar: {path}")
    if not isinstance(payload.get("exceptions"),dict):raise ValueError(f"CFTC release calendar exceptions missing: {path}")
    return payload

def calendar_hash(path:Path=DEFAULT_CALENDAR)->str:return hashlib.sha256(path.read_bytes()).hexdigest()

def _observed_fixed(day:date)->date:
    if day.weekday()==5:return day-timedelta(days=1)
    if day.weekday()==6:return day+timedelta(days=1)
    return day

def _nth_weekday(year:int,month:int,weekday:int,nth:int)->date:
    first=date(year,month,1);return first+timedelta(days=(weekday-first.weekday())%7+7*(nth-1))
def _last_weekday(year:int,month:int,weekday:int)->date:
    nxt=date(year+1,1,1) if month==12 else date(year,month+1,1);last=nxt-timedelta(days=1);return last-timedelta(days=(last.weekday()-weekday)%7)

def federal_holiday_observed_dates(year:int)->dict[date,str]:
    holidays={
        _observed_fixed(date(year,1,1)):"NEW_YEAR",
        _nth_weekday(year,1,0,3):"MLK_DAY",
        _nth_weekday(year,2,0,3):"WASHINGTON_BIRTHDAY",
        _last_weekday(year,5,0):"MEMORIAL_DAY",
        _observed_fixed(date(year,7,4)):"INDEPENDENCE_DAY",
        _nth_weekday(year,9,0,1):"LABOR_DAY",
        _nth_weekday(year,10,0,2):"COLUMBUS_DAY",
        _observed_fixed(date(year,11,11)):"VETERANS_DAY",
        _nth_weekday(year,11,3,4):"THANKSGIVING",
        _observed_fixed(date(year,12,25)):"CHRISTMAS",
    }
    if year>=2021:holidays[_observed_fixed(date(year,6,19))]="JUNETEENTH"
    next_new_year=_observed_fixed(date(year+1,1,1))
    if next_new_year.year==year:holidays[next_new_year]="NEW_YEAR_NEXT"
    return holidays

def is_federal_business_day(day:date)->bool:
    if day.weekday()>=5:return False
    holidays={}
    for year in {day.year-1,day.year,day.year+1}:holidays.update(federal_holiday_observed_dates(year))
    return day not in holidays

def third_business_day_after(as_of:str|date|datetime)->date:
    day=parse_date(as_of);count=0;cursor=day
    while count<3:
        cursor+=timedelta(days=1)
        if is_federal_business_day(cursor):count+=1
    return cursor

def normal_release_date(report_date:str|date|datetime)->date:return third_business_day_after(report_date)

def report_week_holidays(report_date:str|date|datetime)->list[dict[str,str]]:
    report=parse_date(report_date);end=normal_release_date(report);holidays={}
    for year in {report.year-1,report.year,end.year,end.year+1}:holidays.update(federal_holiday_observed_dates(year))
    return [{"date":d.isoformat(),"holiday":name} for d,name in sorted(holidays.items()) if report<d<=end]

def release_record(report_date:str|date|datetime,path:Path=DEFAULT_CALENDAR)->dict[str,Any]:
    report=parse_date(report_date);payload=load_calendar(str(path));exception=payload["exceptions"].get(report.isoformat());scheduled=normal_release_date(report)
    if exception:
        release=parse_date(exception["release_date"]);source_type=str(exception.get("source_type") or "CFTC_ACTUAL_EXCEPTION");confidence=str(exception.get("confidence") or "official");exception_type=str(exception.get("exception_type") or "OTHER");notes=exception.get("notes");status="OFFICIAL_OVERRIDE"
    else:
        release=scheduled;source_type="NORMAL_BUSINESS_DAY_SCHEDULE_ASSUMPTION";confidence="derived-official-third-business-day-rule";exception_type=None;notes=None;status="DERIVED_NORMAL_RULE"
    local_et=datetime.combine(release,RELEASE_TIME_ET,tzinfo=NEW_YORK);utc=local_et.astimezone(UTC);stockholm=local_et.astimezone(STOCKHOLM)
    return {
        "report_date":report.isoformat(),"scheduled_release_date":scheduled.isoformat(),"actual_release_date":release.isoformat(),"release_time_et":"15:30",
        "availability_at_et":local_et.isoformat(),"availability_at_utc":utc.isoformat().replace("+00:00","Z"),"availability_at_stockholm":stockholm.isoformat(),
        "availability_source_type":source_type,"availability_status":status,"research_eligible":True,"exception_type":exception_type,"processing_holidays":report_week_holidays(report),
        "confidence":confidence,"notes":notes,"calendar_version":payload.get("calendar_version"),"release_calendar_hash":calendar_hash(path),
    }
def availability_at(report_date:str|date|datetime,path:Path=DEFAULT_CALENDAR)->datetime:
    rec=release_record(report_date,path);return datetime.fromisoformat(str(rec["availability_at_utc"]).replace("Z","+00:00")).astimezone(UTC)
def release_date(report_date:str|date|datetime,path:Path=DEFAULT_CALENDAR)->date:return availability_at(report_date,path).astimezone(NEW_YORK).date()
def release_source(report_date:str|date|datetime,path:Path=DEFAULT_CALENDAR)->str:return str(release_record(report_date,path)["availability_source_type"])
def release_confidence(report_date:str|date|datetime,path:Path=DEFAULT_CALENDAR)->str:return str(release_record(report_date,path)["confidence"])
def first_tradable_price_index(prices:list[dict[str,Any]],report_date:str|date|datetime,*,date_key:str="date",path:Path=DEFAULT_CALENDAR)->int|None:
    target=release_date(report_date,path)
    for i,row in enumerate(prices):
        try:d=parse_date(row.get(date_key))
        except (TypeError,ValueError):continue
        if d>=target:return i
    return None
def assert_available_before_entry(report_date:str|date|datetime,entry_date:str|date|datetime,path:Path=DEFAULT_CALENDAR)->None:
    available=release_date(report_date,path);entry=parse_date(entry_date)
    if entry<available:raise AssertionError(f"Lookahead violation: report {parse_date(report_date)} available {available} but entry is {entry}")
