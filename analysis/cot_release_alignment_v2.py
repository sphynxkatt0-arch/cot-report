#!/usr/bin/env python3
"""Compatibility alignment for legacy studies that pass report_date + 3 as target."""
from __future__ import annotations
from datetime import date,timedelta
from typing import Any
from cftc_release_calendar import release_record


def canonical_target_from_legacy_target(target:date)->date:
    candidate=target-timedelta(days=3);meta=release_record(candidate)
    # Ordinary studies historically pass Tuesday+3. Official exceptions may
    # have non-Tuesday report dates, so an explicit calendar record also proves
    # this is a legacy COT release target that needs correction.
    if candidate.weekday()==1 or meta["availability_source_type"]!="NORMAL_SCHEDULE_ASSUMPTION":
        return date.fromisoformat(str(meta["actual_release_date"]))
    return target

def first_price_index_on_or_after(prices:list[dict[str,Any]],target:date)->int|None:
    effective=canonical_target_from_legacy_target(target)
    for i,row in enumerate(prices):
        d=row.get("date")
        if d is not None and d>=effective:return i
    return None
