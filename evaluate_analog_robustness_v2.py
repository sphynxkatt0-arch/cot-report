#!/usr/bin/env python3
"""Release-corrected runner for analog robustness research."""
from __future__ import annotations
import json

import cot_release_alignment_v2 as alignment
import evaluate_analog_robustness as legacy
from cftc_release_calendar import calendar_hash


def main():
    original=legacy.backtest.first_price_index_on_or_after
    legacy.backtest.first_price_index_on_or_after=alignment.first_price_index_on_or_after
    try:legacy.main()
    finally:legacy.backtest.first_price_index_on_or_after=original
    payload=json.loads(legacy.OUT.read_text(encoding="utf-8"))
    payload["research_generation"]="release-corrected-v2"
    payload["information_contract_version"]="cftc-public-availability-v2"
    payload["release_calendar_hash"]=calendar_hash()
    payload["evidence_purpose"]="ANALOG_CONTEXT_RESEARCH"
    payload["automatic_promotion_allowed"]=False
    methodology=payload.setdefault("methodology",{})
    methodology["release_anchor"]="canonical CFTC public availability; unresolved historical release weeks excluded"
    methodology["release_calendar_aware"]=True
    methodology["unresolved_release_policy"]="EXCLUDE"
    legacy.OUT.write_text(json.dumps(payload,separators=(",",":"),sort_keys=True)+"\n",encoding="utf-8")
    print("Analog robustness v2 complete")

if __name__=="__main__":main()
