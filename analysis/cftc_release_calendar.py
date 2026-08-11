#!/usr/bin/env python3
"""Canonical CFTC COT public-availability resolver.

Historical research must use this module rather than assuming report_date + 3
calendar days. Official exceptions in analysis/reference/cftc_release_calendar.json
override the normal Friday 15:30 America/New_York schedule.

The CFTC does not publish a complete historical release-date archive. Therefore
an old reporting week that contains a US federal holiday, or an unexplained
non-Tuesday report date, is research-ineligible unless an explicit official CFTC
release record is present in the canonical calendar. This is deliberately
conservative: uncertain rows are dropped rather than assigned a guessed release.
"""
from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime, time, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
DEFAULT_CALENDAR = ROOT / "reference" / "cftc_release_calendar.json"
NEW_YORK = ZoneInfo("America/New_York")
STOCKHOLM = ZoneInfo("Europe/Stockholm")
RELEASE_TIME_ET = time(15, 30)


def parse_date(value: str | date | datetime) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


@lru_cache(maxsize=4)
def load_calendar(path_str: str | None = None) -> dict[str, Any]:
    path = Path(path_str) if path_str else DEFAULT_CALENDAR
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise ValueError(f"Invalid CFTC release calendar: {path}")
    if not isinstance(payload.get("exceptions"), dict):
        raise ValueError(f"CFTC release calendar exceptions missing: {path}")
    return payload


def calendar_hash(path: Path = DEFAULT_CALENDAR) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _observed_fixed(day: date) -> date:
    if day.weekday() == 5:  # Saturday -> Friday
        return day - timedelta(days=1)
    if day.weekday() == 6:  # Sunday -> Monday
        return day + timedelta(days=1)
    return day


def _nth_weekday(year: int, month: int, weekday: int, nth: int) -> date:
    first = date(year, month, 1)
    offset = (weekday - first.weekday()) % 7
    return first + timedelta(days=offset + 7 * (nth - 1))


def _last_weekday(year: int, month: int, weekday: int) -> date:
    if month == 12:
        next_month = date(year + 1, 1, 1)
    else:
        next_month = date(year, month + 1, 1)
    current = next_month - timedelta(days=1)
    return current - timedelta(days=(current.weekday() - weekday) % 7)


def federal_holiday_observed_dates(year: int) -> dict[date, str]:
    """Observed US federal holidays relevant to the CFTC reporting week."""
    holidays: dict[date, str] = {
        _observed_fixed(date(year, 1, 1)): "NEW_YEAR",
        _nth_weekday(year, 1, 0, 3): "MLK_DAY",
        _nth_weekday(year, 2, 0, 3): "WASHINGTON_BIRTHDAY",
        _last_weekday(year, 5, 0): "MEMORIAL_DAY",
        _observed_fixed(date(year, 7, 4)): "INDEPENDENCE_DAY",
        _nth_weekday(year, 9, 0, 1): "LABOR_DAY",
        _nth_weekday(year, 10, 0, 2): "COLUMBUS_DAY",
        _observed_fixed(date(year, 11, 11)): "VETERANS_DAY",
        _nth_weekday(year, 11, 3, 4): "THANKSGIVING",
        _observed_fixed(date(year, 12, 25)): "CHRISTMAS",
    }
    if year >= 2021:
        holidays[_observed_fixed(date(year, 6, 19))] = "JUNETEENTH"
    # New Year's Day for the following year can be observed on Dec 31.
    next_new_year = _observed_fixed(date(year + 1, 1, 1))
    if next_new_year.year == year:
        holidays[next_new_year] = "NEW_YEAR_NEXT"
    return holidays


def report_week_holidays(report_date: str | date | datetime) -> list[dict[str, str]]:
    report = parse_date(report_date)
    monday = report - timedelta(days=report.weekday())
    friday = monday + timedelta(days=4)
    candidates: dict[date, str] = {}
    for year in {monday.year - 1, monday.year, friday.year, friday.year + 1}:
        candidates.update(federal_holiday_observed_dates(year))
    return [
        {"date": day.isoformat(), "holiday": name}
        for day, name in sorted(candidates.items())
        if monday <= day <= friday
    ]


def normal_release_date(report_date: str | date | datetime) -> date:
    report = parse_date(report_date)
    return report + timedelta(days=(4 - report.weekday()) % 7)


def release_record(report_date: str | date | datetime, path: Path = DEFAULT_CALENDAR) -> dict[str, Any]:
    report = parse_date(report_date)
    payload = load_calendar(str(path))
    exception = payload["exceptions"].get(report.isoformat())
    scheduled_date = normal_release_date(report)
    holidays = report_week_holidays(report)
    if exception:
        release_date = parse_date(exception["release_date"])
        source_type = str(exception.get("source_type") or "CFTC_ACTUAL_EXCEPTION")
        confidence = str(exception.get("confidence") or "official")
        exception_type = str(exception.get("exception_type") or "OTHER")
        notes = exception.get("notes")
        research_eligible = True
        availability_status = "OFFICIAL"
    elif report.weekday() != 1:
        release_date = scheduled_date
        source_type = "UNRESOLVED_NON_TUESDAY_REPORT_DATE"
        confidence = "unknown-historical"
        exception_type = "UNRESOLVED_SCHEDULE"
        notes = "Non-Tuesday COT as-of date has no explicit archived CFTC release record; excluded from predictive research."
        research_eligible = False
        availability_status = "UNRESOLVED"
    elif holidays:
        release_date = scheduled_date
        source_type = "UNRESOLVED_HOLIDAY_SCHEDULE"
        confidence = "unknown-historical-holiday"
        exception_type = "UNRESOLVED_SCHEDULE"
        notes = "Federal holiday occurred in the reporting week and no explicit archived CFTC release record is stored; excluded rather than guessing availability."
        research_eligible = False
        availability_status = "UNRESOLVED"
    else:
        release_date = scheduled_date
        source_type = "NORMAL_SCHEDULE_ASSUMPTION"
        confidence = "assumed-normal-nonholiday"
        exception_type = None
        notes = None
        research_eligible = True
        availability_status = "SCHEDULE_ASSUMPTION"

    local_et = datetime.combine(release_date, RELEASE_TIME_ET, tzinfo=NEW_YORK)
    utc = local_et.astimezone(UTC)
    stockholm = local_et.astimezone(STOCKHOLM)
    return {
        "report_date": report.isoformat(),
        "scheduled_release_date": scheduled_date.isoformat(),
        "actual_release_date": release_date.isoformat() if research_eligible else None,
        "release_time_et": "15:30",
        "availability_at_et": local_et.isoformat() if research_eligible else None,
        "availability_at_utc": utc.isoformat().replace("+00:00", "Z") if research_eligible else None,
        "availability_at_stockholm": stockholm.isoformat() if research_eligible else None,
        "availability_source_type": source_type,
        "availability_status": availability_status,
        "research_eligible": research_eligible,
        "exception_type": exception_type,
        "report_week_holidays": holidays,
        "confidence": confidence,
        "notes": notes,
        "calendar_version": payload.get("calendar_version"),
        "release_calendar_hash": calendar_hash(path),
    }


def availability_at(report_date: str | date | datetime, path: Path = DEFAULT_CALENDAR) -> datetime:
    record = release_record(report_date, path)
    if not record["research_eligible"] or not record["availability_at_utc"]:
        raise ValueError(f"CFTC availability unresolved for report {record['report_date']}: {record['availability_source_type']}")
    return datetime.fromisoformat(str(record["availability_at_utc"]).replace("Z", "+00:00")).astimezone(UTC)


def release_date(report_date: str | date | datetime, path: Path = DEFAULT_CALENDAR) -> date:
    return availability_at(report_date, path).astimezone(NEW_YORK).date()


def release_source(report_date: str | date | datetime, path: Path = DEFAULT_CALENDAR) -> str:
    return str(release_record(report_date, path)["availability_source_type"])


def release_confidence(report_date: str | date | datetime, path: Path = DEFAULT_CALENDAR) -> str:
    return str(release_record(report_date, path)["confidence"])


def first_tradable_price_index(
    prices: list[dict[str, Any]],
    report_date: str | date | datetime,
    *,
    date_key: str = "date",
    path: Path = DEFAULT_CALENDAR,
) -> int | None:
    """Return first daily observation on/after known CFTC availability.

    Unresolved historical holiday/non-Tuesday release weeks return None and are
    excluded from research rather than being aligned to a guessed date.
    """
    record = release_record(report_date, path)
    if not record["research_eligible"]:
        return None
    target = parse_date(record["actual_release_date"])
    for index, row in enumerate(prices):
        try:
            row_date = parse_date(row.get(date_key))
        except (TypeError, ValueError):
            continue
        if row_date >= target:
            return index
    return None


def assert_available_before_entry(
    report_date: str | date | datetime,
    entry_date: str | date | datetime,
    path: Path = DEFAULT_CALENDAR,
) -> None:
    record = release_record(report_date, path)
    if not record["research_eligible"]:
        raise AssertionError(f"Availability unresolved; research row must be excluded: {record['report_date']}")
    available_date = parse_date(record["actual_release_date"])
    entry = parse_date(entry_date)
    if entry < available_date:
        raise AssertionError(
            f"Lookahead violation: report {parse_date(report_date)} available {available_date} but entry is {entry}"
        )
