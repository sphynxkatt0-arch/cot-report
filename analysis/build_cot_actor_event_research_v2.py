#!/usr/bin/env python3
"""Release-corrected facade for the governed actor-event research engine.

The legacy engine is retained unchanged for audit reproducibility. This facade
normalizes every event to canonical CFTC availability and recomputes exact
weekday returns relative to the publication week, not the original report week.
Downstream v2 research should import this module.
"""
from __future__ import annotations

from datetime import timedelta
from typing import Any

import build_cot_actor_event_research as _legacy
import build_worldclass_backtest as _backtest
from cftc_release_calendar import release_record
from cot_research_core import finite, parse_date

RESEARCH_GENERATION = "release-corrected-v2"
INFORMATION_CONTRACT_VERSION = "cftc-public-availability-v2"


def __getattr__(name: str) -> Any:
    return getattr(_legacy, name)


def exact_cumulative_path_from_release(
    release_date,
    prices: list[dict[str, Any]],
    price_index_by_date: dict,
    signal_index: int,
) -> dict[str, float]:
    """Signal close -> next calendar week's Monday-through-Friday closes.

    Exact weekdays are defined from the actual release date. The chain stops on
    a missing weekday (holiday) rather than silently substituting another day.
    """
    path: dict[str, float] = {}
    if signal_index < 0 or signal_index >= len(prices):
        return path
    start_price = finite(prices[signal_index].get("price"))
    if start_price in (None, 0):
        return path
    # Monday following the release date, then cumulative through Friday.
    days_to_monday = (7 - release_date.weekday()) % 7
    if days_to_monday == 0:
        days_to_monday = 7
    monday = release_date + timedelta(days=days_to_monday)
    for offset, weekday in enumerate(("monday", "tuesday", "wednesday", "thursday", "friday")):
        target = monday + timedelta(days=offset)
        idx = price_index_by_date.get(target)
        if idx is None or idx <= signal_index:
            break
        end_price = finite(prices[idx].get("price"))
        if end_price is None:
            break
        path[weekday] = (end_price / start_price - 1.0) * 100.0
    return path


def build_market_actor_events(
    market: str,
    dataset: str,
    payload: dict[str, Any],
    prices_payload: Any,
) -> dict[str, list[dict[str, Any]]]:
    """Build legacy-governed events, then canonicalize release/outcome metadata."""
    events = _legacy.build_market_actor_events(market, dataset, payload, prices_payload)
    if not events:
        return events
    prices = _backtest.price_records(prices_payload)
    price_index_by_date = {row["date"]: idx for idx, row in enumerate(prices)}
    for actor_events in events.values():
        for event in actor_events:
            report = parse_date(event.get("report_date"))
            if report is None:
                continue
            meta = release_record(report)
            release_day = parse_date(meta["actual_release_date"])
            signal_index = int(event.get("signal_index") or 0)
            if release_day is None or signal_index >= len(prices):
                continue
            if prices[signal_index]["date"] < release_day:
                raise AssertionError(
                    f"lookahead actor event {market}/{dataset}/{event.get('actor')} {report}: "
                    f"signal {prices[signal_index]['date']} < release {release_day}"
                )
            event["release_date"] = release_day.isoformat()
            event["availability_at_utc"] = meta["availability_at_utc"]
            event["availability_source_type"] = meta["availability_source_type"]
            event["release_calendar_version"] = meta["calendar_version"]
            event["release_calendar_hash"] = meta["release_calendar_hash"]
            event["research_generation"] = RESEARCH_GENERATION
            event["information_contract_version"] = INFORMATION_CONTRACT_VERSION
            event["weekday_cumulative"] = {
                key: _legacy.r4(value)
                for key, value in exact_cumulative_path_from_release(
                    release_day, prices, price_index_by_date, signal_index
                ).items()
            }
    return events
