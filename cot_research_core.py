#!/usr/bin/env python3
"""Shared point-in-time primitives for COT research.

All new research should import percentile, release and outcome alignment helpers
from here rather than reimplementing them per study.
"""
from __future__ import annotations

import math
from bisect import bisect_left
from datetime import date
from typing import Any

from cftc_release_calendar import (
    assert_available_before_entry,
    availability_at,
    first_tradable_price_index,
    release_record,
)


def finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def parse_date(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value or "")[:10])
    except ValueError:
        return None


def percentile_rank(values: list[float], current: float) -> float | None:
    """Mid-rank percentile of current within only the supplied historical values."""
    clean = sorted(v for v in values if math.isfinite(v))
    if not clean:
        return None
    left = bisect_left(clean, current)
    right = left
    while right < len(clean) and clean[right] == current:
        right += 1
    equal = max(1, right - left)
    return (left + equal / 2.0) / len(clean) * 100.0


def expanding_percentile(rows: list[dict[str, Any]], index: int, field: str) -> float | None:
    current = finite(rows[index].get(field))
    if current is None:
        return None
    history = [finite(row.get(field)) for row in rows[: index + 1]]
    return percentile_rank([v for v in history if v is not None], current)


def price_records(payload: Any) -> list[dict[str, Any]]:
    rows = payload.get("records") if isinstance(payload, dict) else payload if isinstance(payload, list) else []
    normalized: list[dict[str, Any]] = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        d = parse_date(row.get("date"))
        p = finite(row.get("price"))
        if d is not None and p is not None:
            normalized.append({"date": d, "date_str": d.isoformat(), "price": p})
    normalized.sort(key=lambda row: row["date"])
    return normalized


def release_aligned_entry(prices: list[dict[str, Any]], report_date: Any) -> dict[str, Any] | None:
    record = release_record(report_date)
    index = first_tradable_price_index(prices, report_date)
    if index is None:
        return None
    row = prices[index]
    assert_available_before_entry(report_date, row["date"])
    return {
        "index": index,
        "report_date": str(record["report_date"]),
        "availability_at": str(record["availability_at_utc"]),
        "availability_source": str(record["availability_source_type"]),
        "availability_confidence": str(record["confidence"]),
        "release_calendar_version": str(record["calendar_version"]),
        "release_calendar_hash": str(record["release_calendar_hash"]),
        "entry_date": row["date_str"],
        "entry_price": row["price"],
    }


def horizon_result(prices: list[dict[str, Any]], start_index: int, trading_closes: int) -> dict[str, Any] | None:
    end_index = start_index + trading_closes
    if end_index >= len(prices):
        return None
    start = finite(prices[start_index].get("price"))
    end = finite(prices[end_index].get("price"))
    if start is None or end is None or start == 0:
        return None
    window = [finite(row.get("price")) for row in prices[start_index : end_index + 1]]
    clean = [v for v in window if v is not None]
    if not clean:
        return None
    return {
        "entry_date": prices[start_index]["date_str"],
        "exit_date": prices[end_index]["date_str"],
        "entry_price": start,
        "exit_price": end,
        "return_pct": (end / start - 1.0) * 100.0,
        "max_adverse_excursion_pct": (min(clean) / start - 1.0) * 100.0,
        "max_favorable_excursion_pct": (max(clean) / start - 1.0) * 100.0,
    }


def nonoverlap_indices(rows: list[dict[str, Any]], horizon_closes: int, *, entry_key: str = "entry_date") -> list[int]:
    """Greedy chronological independent-episode selector for daily-close horizons."""
    selected: list[int] = []
    last_end_ordinal: int | None = None
    # trading-close overlap cannot be proven from calendar days alone; callers with
    # exact price indices should supply rows with entry_index and use that instead.
    for i, row in enumerate(rows):
        idx = row.get("entry_index")
        if isinstance(idx, int):
            if last_end_ordinal is None or idx > last_end_ordinal:
                selected.append(i)
                last_end_ordinal = idx + horizon_closes
    return selected
