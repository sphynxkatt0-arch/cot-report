#!/usr/bin/env python3
"""Compatibility alignment for legacy studies that pass report_date + 3 as target.

Known official exceptions are mapped to their documented release dates. Old
holiday/non-Tuesday weeks whose exact publication is not in the canonical CFTC
calendar return no price index, preventing a guessed availability date from
entering v2 research.
"""
from __future__ import annotations
from datetime import date,timedelta
from typing import Any
from cftc_release_calendar import release_record


def canonical_target_from_legacy_target(target:date)->date|None:
    candidate=target-timedelta(days=3)
    meta=release_record(candidate)
    # Legacy COT engines construct target=report_date+3. A Tuesday candidate is
    # therefore a normal COT call shape; an explicit/non-normal source also
    # identifies an exceptional COT row even when its as-of date shifted.
    is_cot_target=candidate.weekday()==1 or meta["availability_source_type"]!="NORMAL_SCHEDULE_ASSUMPTION"
    if not is_cot_target:
        return target
    if not meta.get("research_eligible") or not meta.get("actual_release_date"):
        return None
    return date.fromisoformat(str(meta["actual_release_date"]))

def first_price_index_on_or_after(prices:list[dict[str,Any]],target:date)->int|None:
    effective=canonical_target_from_legacy_target(target)
    if effective is None:return None
    for i,row in enumerate(prices):
        d=row.get("date")
        if d is not None and d>=effective:return i
    return None
