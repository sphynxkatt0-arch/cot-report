#!/usr/bin/env python3
"""Canonical CFTC COT public-availability resolver.

Historical research must use this module rather than assuming report_date + 3
calendar days. Official exceptions in analysis/reference/cftc_release_calendar.json
override the normal Friday 15:30 America/New_York schedule.
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


def normal_release_date(report_date: str | date | datetime) -> date:
    report = parse_date(report_date)
    return report + timedelta(days=(4 - report.weekday()) % 7)


def release_record(report_date: str | date | datetime, path: Path = DEFAULT_CALENDAR) -> dict[str, Any]:
    report = parse_date(report_date)
    payload = load_calendar(str(path))
    exception = payload["exceptions"].get(report.isoformat())
    scheduled_date = normal_release_date(report)
    if exception:
        release_date = parse_date(exception["release_date"])
        source_type = str(exception.get("source_type") or "CFTC_ACTUAL_EXCEPTION")
        confidence = str(exception.get("confidence") or "official")
        exception_type = str(exception.get("exception_type") or "OTHER")
        notes = exception.get("notes")
    else:
        release_date = scheduled_date
        source_type = "NORMAL_SCHEDULE_ASSUMPTION"
        confidence = "assumed-normal"
        exception_type = None
        notes = None

    local_et = datetime.combine(release_date, RELEASE_TIME_ET, tzinfo=NEW_YORK)
    utc = local_et.astimezone(UTC)
    stockholm = local_et.astimezone(STOCKHOLM)
    return {
        "report_date": report.isoformat(),
        "scheduled_release_date": scheduled_date.isoformat(),
        "actual_release_date": release_date.isoformat(),
        "release_time_et": "15:30",
        "availability_at_et": local_et.isoformat(),
        "availability_at_utc": utc.isoformat().replace("+00:00", "Z"),
        "availability_at_stockholm": stockholm.isoformat(),
        "availability_source_type": source_type,
        "exception_type": exception_type,
        "confidence": confidence,
        "notes": notes,
        "calendar_version": payload.get("calendar_version"),
        "release_calendar_hash": calendar_hash(path),
    }


def availability_at(report_date: str | date | datetime, path: Path = DEFAULT_CALENDAR) -> datetime:
    record = release_record(report_date, path)
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
    """Return first daily observation whose date is on/after official availability.

    Daily close datasets do not carry intraday timestamps. Since COT is released
    before the US cash close at 15:30 ET, the release-date close is a conservative
    actionable anchor. Intraday datasets should compare timestamps directly.
    """
    target = release_date(report_date, path)
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
    available_date = release_date(report_date, path)
    entry = parse_date(entry_date)
    if entry < available_date:
        raise AssertionError(
            f"Lookahead violation: report {parse_date(report_date)} available {available_date} but entry is {entry}"
        )
