#!/usr/bin/env python3
"""Run governed raw-position/OI predictive research on release-corrected events."""
from __future__ import annotations
import json

import build_cot_actor_event_research_v2 as actor_v2
import evaluate_cot_actor_predictive_power as base_pp
import evaluate_cot_raw_position_oi_predictive_power as legacy
from cftc_release_calendar import calendar_hash

RESEARCH_GENERATION="release-corrected-v2"

def stamp(path):
    if not path.exists():return
    payload=json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload,dict):
        payload["research_generation"]=RESEARCH_GENERATION
        payload["information_contract_version"]="cftc-public-availability-v2"
        payload["release_calendar_hash"]=calendar_hash()
        payload["legacy_engine_preserved_for_audit"]=True
        path.write_text(json.dumps(payload,separators=(",",":"),sort_keys=True)+"\n",encoding="utf-8")

def main():
    old_actor=legacy.actor_research;old_base_actor=base_pp.actor_research
    legacy.actor_research=actor_v2;base_pp.actor_research=actor_v2
    try:legacy.main()
    finally:
        legacy.actor_research=old_actor;base_pp.actor_research=old_base_actor
    stamp(legacy.OUT);stamp(legacy.SUMMARY_OUT)
    print("Raw position/OI predictive-power v2 complete")

if __name__=="__main__":main()
