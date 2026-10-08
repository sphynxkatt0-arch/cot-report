#!/usr/bin/env python3
"""Run actor predictive-power research on strict release-corrected event data."""
from __future__ import annotations
import json
import build_cot_actor_event_research_release_corrected as actor_v2
import evaluate_cot_actor_predictive_power as legacy
from cftc_release_calendar import calendar_hash
RESEARCH_GENERATION="release-corrected-v2"
def stamp(path):
    if not path.exists():return
    p=json.loads(path.read_text(encoding="utf-8"));p["research_generation"]=RESEARCH_GENERATION;p["information_contract_version"]="cftc-public-availability-v2";p["release_calendar_hash"]=calendar_hash();p["legacy_engine_preserved_for_audit"]=True;path.write_text(json.dumps(p,separators=(",",":"),sort_keys=True)+"\n",encoding="utf-8")
def main():
    original=legacy.actor_research;legacy.actor_research=actor_v2
    try:legacy.main()
    finally:legacy.actor_research=original
    stamp(legacy.OUT);stamp(legacy.SUMMARY_OUT);print("Actor predictive-power v2 complete")
if __name__=="__main__":main()
