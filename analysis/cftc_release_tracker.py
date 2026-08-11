#!/usr/bin/env python3
"""Track scheduled, exceptional and first-observed CFTC COT release timing."""
from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from cftc_release_calendar import NEW_YORK, STOCKHOLM, availability_at, parse_date, release_record

ROOT = Path(__file__).resolve().parent
DEFAULT_LEDGER = ROOT / "model_output" / "cftc_release_observations.json"
OBSERVATION_WINDOW_DAYS = 75
DELAY_GRACE_MINUTES = 10


def aware_utc(value: datetime | None = None) -> datetime:
    current = value or datetime.now(UTC)
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC)
    return current.astimezone(UTC)


def scheduled_release_datetime(report_date: str | date | datetime) -> datetime:
    """Backward-compatible name; returns canonical public availability."""
    return availability_at(report_date).astimezone(NEW_YORK)


def expected_latest_report_date(now: datetime | None = None) -> date:
    """Latest weekly report whose canonical public availability has passed.

    Search backward by Tuesday observations rather than assuming the most recent
    Tuesday is already public during delayed-release periods.
    """
    current = aware_utc(now)
    local_day = current.astimezone(NEW_YORK).date()
    candidate = local_day - timedelta(days=(local_day.weekday() - 1) % 7)
    for _ in range(80):
        if availability_at(candidate) <= current:
            return candidate
        candidate -= timedelta(days=7)
    raise RuntimeError("Unable to resolve latest CFTC report date")


def load_ledger(path: Path = DEFAULT_LEDGER) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"schema_version": 2, "reports": {}}
    if not isinstance(payload, dict):
        return {"schema_version": 2, "reports": {}}
    payload.setdefault("schema_version", 2)
    payload.setdefault("reports", {})
    return payload


def save_ledger(payload: dict[str, Any], path: Path = DEFAULT_LEDGER) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def observe_report(report_date: str | date | datetime, *, now: datetime | None = None, path: Path = DEFAULT_LEDGER) -> dict[str, Any] | None:
    current = aware_utc(now)
    report = parse_date(report_date)
    record = release_record(report)
    available = availability_at(report)
    expected = expected_latest_report_date(current)
    if report < expected or current < available:
        return None
    if abs((current.date() - available.date()).days) > OBSERVATION_WINDOW_DAYS:
        return None

    ledger = load_ledger(path)
    reports = ledger["reports"]
    key = report.isoformat()
    if key not in reports:
        delay_minutes = (current - available).total_seconds() / 60.0
        reports[key] = {
            "report_date": key,
            "scheduled_release_utc": record["availability_at_utc"],
            "scheduled_release_stockholm": record["availability_at_stockholm"],
            "effective_release_date": record["actual_release_date"],
            "release_calendar_version": record["calendar_version"],
            "release_calendar_hash": record["release_calendar_hash"],
            "release_source_type": record["availability_source_type"],
            "first_seen_utc": current.isoformat(),
            "first_seen_stockholm": current.astimezone(STOCKHOLM).isoformat(),
            "first_seen_delay_minutes": round(delay_minutes, 1),
            "observation_source": "local_refresh_first_seen",
        }
        ledger["updated_at_utc"] = current.isoformat()
        save_ledger(ledger, path)
    return reports[key]


def resolve_release_state(report_date: str | date | datetime, *, now: datetime | None = None, path: Path = DEFAULT_LEDGER) -> dict[str, Any]:
    current = aware_utc(now)
    report = parse_date(report_date)
    expected = expected_latest_report_date(current)
    record = release_record(report)
    available = availability_at(report)
    entry = load_ledger(path).get("reports", {}).get(report.isoformat())

    if current < available:
        status = "awaiting_release"
    elif report < expected:
        status = "historical"
    else:
        status = "current"

    observed_at = entry.get("first_seen_utc") if entry else None
    observed_delay = entry.get("first_seen_delay_minutes") if entry else None
    return {
        "report_date": report.isoformat(),
        "expected_report_date": expected.isoformat(),
        "scheduled_release_utc": record["availability_at_utc"],
        "scheduled_release_stockholm": record["availability_at_stockholm"],
        "effective_release_date": record["actual_release_date"],
        "release_date_source": record["availability_source_type"],
        "release_calendar_version": record["calendar_version"],
        "release_calendar_hash": record["release_calendar_hash"],
        "release_status": status,
        "first_observed_utc": observed_at,
        "first_observed_delay_minutes": observed_delay,
        "is_delayed": record["exception_type"] is not None,
        "is_awaiting_release": status == "awaiting_release",
    }


def report_is_overdue(latest_report_date: str | date | datetime, *, now: datetime | None = None) -> bool:
    current = aware_utc(now)
    expected = expected_latest_report_date(current)
    latest = parse_date(latest_report_date)
    expected_release = availability_at(expected)
    return latest < expected and current >= expected_release + timedelta(minutes=DELAY_GRACE_MINUTES)
