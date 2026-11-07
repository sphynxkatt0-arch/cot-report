#!/usr/bin/env python3
"""Compatibility alignment for legacy COT studies that pass report_date + 3.

This module is only used as a monkeypatch inside v2 COT research. Therefore each
target is interpreted as the legacy nominal target for report_date=target-3 and
is replaced with the canonical third-business-day / explicit-exception release.
"""
from __future__ import annotations
from datetime import date,timedelta
from typing import Any
from cftc_release_calendar import release_date

def canonical_target_from_legacy_target(target:date)->date:
    report_date=target-timedelta(days=3)
    return release_date(report_date)

def first_price_index_on_or_after(prices:list[dict[str,Any]],target:date)->int|None:
    effective=canonical_target_from_legacy_target(target)
    for i,row in enumerate(prices):
        d=row.get("date")
        if d is not None and d>=effective:return i
    return None
