#!/usr/bin/env python3
"""Release-corrected runner for analog robustness research."""
from __future__ import annotations
import json

import evaluate_analog_robustness as legacy
from cftc_release_calendar import calendar_hash


def main():
    legacy.main()
    payload=json.loads(legacy.OUT.read_text(encoding="utf-8"))
    payload["research_generation"]="release-corrected-v2"
    payload["information_contract_version"]="cftc-public-availability-v2"
    payload["release_calendar_hash"]=calendar_hash()
    payload["evidence_purpose"]="ANALOG_CONTEXT_RESEARCH"
    payload["automatic_promotion_allowed"]=False
    methodology=payload.setdefault("methodology",{})
    methodology["release_anchor"]="canonical CFTC public availability via shared worldclass backtest compatibility bridge"
    methodology["release_calendar_aware"]=True
    legacy.OUT.write_text(json.dumps(payload,separators=(",",":"),sort_keys=True)+"\n",encoding="utf-8")
    print("Analog robustness v2 complete")

if __name__=="__main__":main()
