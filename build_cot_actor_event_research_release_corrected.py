#!/usr/bin/env python3
"""Strict release-corrected facade for governed actor-event research.

The legacy actor engine remains unchanged for audit reproducibility. This module
applies canonical CFTC release alignment at execution time and deliberately does
not dereference the partially initialized legacy module during import, keeping
existing research import graphs compatible.
"""
from __future__ import annotations
import json
from datetime import timedelta
from typing import Any, Callable

import build_cot_actor_event_research as legacy
import build_worldclass_backtest as backtest
import cot_release_alignment_v2 as alignment
from cftc_release_calendar import calendar_hash,release_record
from cot_research_core import finite,parse_date

RESEARCH_GENERATION="release-corrected-v2"
INFORMATION_CONTRACT_VERSION="cftc-public-availability-v2"
_ORIGINAL_BUILD: Callable[..., Any] | None = None

def __getattr__(name:str)->Any:return getattr(legacy,name)

def exact_path(release_day,prices,by_date,signal_index):
    out={};start=finite(prices[signal_index].get("price")) if 0<=signal_index<len(prices) else None
    if start in (None,0):return out
    gap=(7-release_day.weekday())%7
    if gap==0:gap=7
    monday=release_day+timedelta(days=gap)
    for offset,name in enumerate(("monday","tuesday","wednesday","thursday","friday")):
        idx=by_date.get(monday+timedelta(days=offset))
        if idx is None or idx<=signal_index:break
        end=finite(prices[idx].get("price"))
        if end is None:break
        out[name]=(end/start-1)*100
    return out

def _legacy_builder():
    builder=_ORIGINAL_BUILD or getattr(legacy,"build_market_actor_events",None)
    if builder is None or builder is build_market_actor_events:
        raise RuntimeError("legacy actor-event builder is not initialized")
    return builder

def build_market_actor_events(market:str,dataset:str,payload:dict[str,Any],prices_payload:Any):
    original_index=backtest.first_price_index_on_or_after
    backtest.first_price_index_on_or_after=alignment.first_price_index_on_or_after
    try:events=_legacy_builder()(market,dataset,payload,prices_payload)
    finally:backtest.first_price_index_on_or_after=original_index
    prices=backtest.price_records(prices_payload);by_date={r["date"]:i for i,r in enumerate(prices)}
    for actor_events in (events or {}).values():
        for event in actor_events:
            report=parse_date(event.get("report_date"))
            if report is None:continue
            meta=release_record(report);release_day=parse_date(meta["actual_release_date"]);idx=int(event.get("signal_index") or 0)
            if release_day is None or idx>=len(prices):continue
            if prices[idx]["date"]<release_day:
                raise AssertionError(f"lookahead actor event {market}/{dataset}/{event.get('actor')} {report}: {prices[idx]['date']} < {release_day}")
            event.update({
                "release_date":release_day.isoformat(),
                "availability_at_utc":meta["availability_at_utc"],
                "availability_source_type":meta["availability_source_type"],
                "release_calendar_version":meta["calendar_version"],
                "release_calendar_hash":meta["release_calendar_hash"],
                "research_generation":RESEARCH_GENERATION,
                "information_contract_version":INFORMATION_CONTRACT_VERSION,
                "weekday_cumulative":{k:legacy.r4(v) for k,v in exact_path(release_day,prices,by_date,idx).items()},
            })
    return events

def stamp(path):
    if not path.exists():return
    p=json.loads(path.read_text(encoding="utf-8"));p["research_generation"]=RESEARCH_GENERATION;p["information_contract_version"]=INFORMATION_CONTRACT_VERSION;p["release_calendar_hash"]=calendar_hash();p["legacy_engine_preserved_for_audit"]=True;p["strict_release_alignment"]=True
    contract=p.setdefault("information_contract",{});contract["public_availability"]="canonical CFTC release calendar at 15:30 America/New_York";contract["release_calendar_aware"]=True;contract["lookahead_safe_cot_timing"]=True
    path.write_text(json.dumps(p,separators=(",",":"),sort_keys=True)+"\n",encoding="utf-8")

def main():
    global _ORIGINAL_BUILD
    original=legacy.build_market_actor_events;_ORIGINAL_BUILD=original;legacy.build_market_actor_events=build_market_actor_events
    try:legacy.main()
    finally:legacy.build_market_actor_events=original;_ORIGINAL_BUILD=None
    stamp(legacy.OUT);stamp(legacy.SUMMARY_OUT);print("Strict actor-event release-corrected v2 complete")
if __name__=="__main__":main()
