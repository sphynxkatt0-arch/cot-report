#!/usr/bin/env python3
"""Release-corrected runner for financial actor weight selection research."""
from __future__ import annotations
import json

import cot_release_alignment_v2 as alignment
import evaluate_financial_actor_weights as legacy
from cftc_release_calendar import calendar_hash


def main():
    original=legacy.first_price_index_on_or_after
    legacy.first_price_index_on_or_after=alignment.first_price_index_on_or_after
    try:legacy.main()
    finally:legacy.first_price_index_on_or_after=original
    payload=json.loads(legacy.OUT.read_text(encoding="utf-8"))
    payload["schema_version"]=2
    payload["research_generation"]="release-corrected-v2"
    payload["information_contract_version"]="cftc-public-availability-v2"
    payload["release_calendar_hash"]=calendar_hash()
    payload["evidence_purpose"]="MODEL_SELECTION_RESEARCH"
    payload["final_validation_claimed"]=False
    payload["automatic_production_weight_change_allowed"]=False
    methodology=payload.setdefault("methodology",{})
    methodology["release_anchor"]="first available close on/after canonical CFTC public availability; unresolved historical release weeks excluded"
    methodology["release_calendar_aware"]=True
    methodology["unresolved_release_policy"]="EXCLUDE"
    methodology["validation_warning"]="2022+ comparisons participate in model selection and are not a pristine final validation set"
    legacy.OUT.write_text(json.dumps(payload,separators=(",",":"),sort_keys=True)+"\n",encoding="utf-8")
    print("Financial actor weight study v2 complete · MODEL_SELECTION_RESEARCH")

if __name__=="__main__":main()
