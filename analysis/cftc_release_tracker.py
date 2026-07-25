#!/usr/bin/env python3
"""Track scheduled and first-observed CFTC COT release timing.

The COT observation is normally as of Tuesday and published Friday at 15:30
America/New_York. The repository cannot reconstruct exact historical release
timestamps, so this module stores the first time the local refresher observes a
new report and clearly distinguishes that from an official timestamp.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
DEFAULT_LEDGER = ROOT / "model_output" / "cftc_release_observations.json"
NEW_YORK = ZoneInfo("America/New_York")
STOCKHOLM = ZoneInfo("Europe/Stockholm")
RELEASE_TIME_ET = time(15, 30)
OBSERVATION_WINDOW_DAYS = 14
DELAY_GRACE_MINUTES = 10


def parse_date(value: str | date | datetime) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def scheduled_release_datetime(report_date: str | date | datetime) -> datetime:
    """Return the normal Friday 15:30 ET release timestamp for a report date."""
    report = parse_date(report_date)
    friday = report + timedelta(days=(4 - report.weekday()) % 7)
    return datetime.combine(friday, RELEASE_TIME_ET, tzinfo=NEW_YORK)


def expected_latest_report_date(now: datetime | None = None) -> date:
    """Latest Tuesday report whose normal Friday release time has passed."""
    current = now or datetime.now(UTC)
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC)
    local = current.astimezone(NEW_YORK)
    candidate = local.date() - timedelta(days=(local.date().weekday() - 1) % 7)
    while scheduled_release_datetime(candidate) > current:
        candidate -= timedelta(days=7)
    return candidate


def load_ledger(path: Path = DEFAULT_LEDGER) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"schema_version": 1, "reports": {}}
    if not isinstance(payload, dict):
        return {"schema_version": 1, "reports": {}}
    payload.setdefault("schema_version", 1)
    payload.setdefault("reports", {})
    return payload


def save_ledger(payload: dict[str, Any], path: Path = DEFAULT_LEDGER) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def observe_report(
    report_date: str | date | datetime,
    *,
    now: datetime | None = None,
    path: Path = DEFAULT_LEDGER,
) -> dict[str, Any] | None:
    """Record first local observation for a recent report.

    Old reports are not backfilled with the current timestamp because that would
    falsely imply a delayed historical release.
    """
    current = now or datetime.now(UTC)
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC)
    report = parse_date(report_date)
    scheduled = scheduled_release_datetime(report)
    if abs((current.date() - scheduled.date()).days) > OBSERVATION_WINDOW_DAYS:
        return None

    ledger = load_ledger(path)
    reports = ledger["reports"]
    key = report.isoformat()
    if key not in reports:
        delay_minutes = (current - scheduled.astimezone(UTC)).total_seconds() / 60.0
        reports[key] = {
            "report_date": key,
            "scheduled_release_utc": scheduled.astimezone(UTC).isoformat(),
            "scheduled_release_stockholm": scheduled.astimezone(STOCKHOLM).isoformat(),
            "first_seen_utc": current.astimezone(UTC).isoformat(),
            "first_seen_stockholm": current.astimezone(STOCKHOLM).isoformat(),
            "first_seen_delay_minutes": round(delay_minutes, 1),
            "observation_source": "local_refresh_first_seen",
        }
        ledger["updated_at_utc"] = current.astimezone(UTC).isoformat()
        save_ledger(ledger, path)
    return reports[key]


def resolve_release_state(
    report_date: str | date | datetime,
    *,
    now: datetime | None = None,
    path: Path = DEFAULT_LEDGER,
) -> dict[str, Any]:
    current = now or datetime.now(UTC)
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC)
    report = parse_date(report_date)
    expected = expected_latest_report_date(current)
    scheduled = scheduled_release_datetime(report)
    entry = load_ledger(path).get("reports", {}).get(report.isoformat())

    if report < expected:
        status = "delayed"
    elif current < scheduled.astimezone(UTC):
        status = "awaiting_release"
    else:
        status = "current"

    source = "scheduled_assumption"
    effective = scheduled.date()
    observed_at = None
    observed_delay = None
    if entry:
        observed_at = entry.get("first_seen_utc")
        observed_delay = entry.get("first_seen_delay_minutes")
        first_seen = datetime.fromisoformat(str(entry["first_seen_utc"]))
        delay_value = float(observed_delay or 0.0)
        if delay_value > 12 * 60 or first_seen.astimezone(NEW_YORK).date() > scheduled.date():
            source = "first_observed_delayed"
            effective = first_seen.astimezone(NEW_YORK).date()
        else:
            source = "first_observed_on_schedule"

    return {
        "report_date": report.isoformat(),
        "expected_report_date": expected.isoformat(),
        "scheduled_release_utc": scheduled.astimezone(UTC).isoformat(),
        "scheduled_release_stockholm": scheduled.astimezone(STOCKHOLM).isoformat(),
        "effective_release_date": effective.isoformat(),
        "release_date_source": source,
        "release_status": status,
        "first_observed_utc": observed_at,
        "first_observed_delay_minutes": observed_delay,
        "is_delayed": status == "delayed",
        "is_awaiting_release": status == "awaiting_release",
    }


def report_is_overdue(
    latest_report_date: str | date | datetime,
    *,
    now: datetime | None = None,
) -> bool:
    current = now or datetime.now(UTC)
    expected = expected_latest_report_date(current)
    latest = parse_date(latest_report_date)
    expected_release = scheduled_release_datetime(expected).astimezone(UTC)
    return latest < expected and current >= expected_release + timedelta(minutes=DELAY_GRACE_MINUTES)
