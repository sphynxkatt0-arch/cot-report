#!/usr/bin/env python3
"""Release-corrected facade for the governed actor-event research engine.

The legacy engine is retained unchanged for audit reproducibility. This facade
normalizes every event to canonical CFTC availability and recomputes exact
weekday returns relative to the publication week, not the original report week.
"""
from __future__ import annotations

import json
from datetime import timedelta
from typing import Any

import build_cot_actor_event_research as _legacy
import build_worldclass_backtest as _backtest
from cftc_release_calendar import calendar_hash, release_record
from cot_research_core import finite, parse_date

RESEARCH_GENERATION = "release-corrected-v2"
INFORMATION_CONTRACT_VERSION = "cftc-public-availability-v2"
_LEGACY_BUILD_MARKET_ACTOR_EVENTS = _legacy.build_market_actor_events


def __getattr__(name: str) -> Any:
    return getattr(_legacy, name)


def exact_cumulative_path_from_release(release_date, prices:list[dict[str,Any]], price_index_by_date:dict, signal_index:int)->dict[str,float]:
    path:dict[str,float]={}
    if signal_index<0 or signal_index>=len(prices):return path
    start=finite(prices[signal_index].get("price"))
    if start in (None,0):return path
    days_to_monday=(7-release_date.weekday())%7
    if days_to_monday==0:days_to_monday=7
    monday=release_date+timedelta(days=days_to_monday)
    for offset,weekday in enumerate(("monday","tuesday","wednesday","thursday","friday")):
        target=monday+timedelta(days=offset);idx=price_index_by_date.get(target)
        if idx is None or idx<=signal_index:break
        end=finite(prices[idx].get("price"))
        if end is None:break
        path[weekday]=(end/start-1.0)*100.0
    return path


def build_market_actor_events(market:str,dataset:str,payload:dict[str,Any],prices_payload:Any)->dict[str,list[dict[str,Any]]]:
    events=_LEGACY_BUILD_MARKET_ACTOR_EVENTS(market,dataset,payload,prices_payload)
    if not events:return events
    prices=_backtest.price_records(prices_payload);by_date={row["date"]:i for i,row in enumerate(prices)}
    for actor_events in events.values():
        for event in actor_events:
            report=parse_date(event.get("report_date"))
            if report is None:continue
            meta=release_record(report);release_day=parse_date(meta["actual_release_date"]);signal_index=int(event.get("signal_index") or 0)
            if release_day is None or signal_index>=len(prices):continue
            if prices[signal_index]["date"]<release_day:raise AssertionError(f"lookahead actor event {market}/{dataset}/{event.get('actor')} {report}: signal {prices[signal_index]['date']} < release {release_day}")
            event.update({"release_date":release_day.isoformat(),"availability_at_utc":meta["availability_at_utc"],"availability_source_type":meta["availability_source_type"],"release_calendar_version":meta["calendar_version"],"release_calendar_hash":meta["release_calendar_hash"],"research_generation":RESEARCH_GENERATION,"information_contract_version":INFORMATION_CONTRACT_VERSION})
            event["weekday_cumulative"]={k:_legacy.r4(v) for k,v in exact_cumulative_path_from_release(release_day,prices,by_date,signal_index).items()}
    return events


def _stamp(path)->None:
    if not path.exists():return
    payload=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload,dict):return
    payload["research_generation"]=RESEARCH_GENERATION
    payload["information_contract_version"]=INFORMATION_CONTRACT_VERSION
    payload["release_calendar_hash"]=calendar_hash()
    payload["legacy_engine_preserved_for_audit"]=True
    contract=payload.setdefault("information_contract",{})
    if isinstance(contract,dict):
        contract["public_availability"]="canonical CFTC release calendar at 15:30 America/New_York"
        contract["release_calendar_aware"]=True
        contract["lookahead_safe_cot_timing"]=True
    path.write_text(json.dumps(payload,separators=(",",":"),sort_keys=True)+"\n",encoding="utf-8")


def main()->None:
    original=_legacy.build_market_actor_events
    _legacy.build_market_actor_events=build_market_actor_events
    try:
        _legacy.main()
    finally:
        _legacy.build_market_actor_events=original
    _stamp(_legacy.OUT);_stamp(_legacy.SUMMARY_OUT)
    print(f"Actor-event v2 stamped · release_calendar={calendar_hash()[:12]}")


if __name__=="__main__":main()
