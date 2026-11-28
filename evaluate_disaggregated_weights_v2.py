#!/usr/bin/env python3
"""Release-corrected runner for Gold/Silver actor weight selection research.

Persisted full-history metals payloads created before the research/runtime split
may lack the explicit research_contract metadata. V2 may reconstruct that
metadata only after independently proving the same full-history and daily-price
floors required by the governed legacy validator; it never treats a compact
browser payload as research input.
"""
from __future__ import annotations
import hashlib
import json

import cot_release_alignment_v2 as alignment
import evaluate_disaggregated_weights as legacy
from cftc_release_calendar import calendar_hash


def ensure_research_contract() -> None:
    payload=json.loads(legacy.METALS.read_text(encoding="utf-8"))
    contract=payload.get("research_contract")
    if isinstance(contract,dict):
        legacy.validate_research_payload(payload)
        return
    markets=payload.get("markets") or {};prices=payload.get("prices") or {};counts={}
    for market in ("gold","silver"):
        cot_rows=((markets.get(market) or {}).get("records") or [])
        price_rows=((prices.get(market) or {}).get("records") or [])
        if len(cot_rows)<legacy.MIN_FULL_HISTORY_COT_ROWS:
            raise RuntimeError(f"cannot reconstruct metals research contract: {market} COT history is incomplete ({len(cot_rows)})")
        if len(price_rows)<int(len(cot_rows)*legacy.MIN_DAILY_TO_WEEKLY_RATIO):
            raise RuntimeError(f"cannot reconstruct metals research contract: {market} daily price history is incomplete ({len(price_rows)} vs {len(cot_rows)})")
        counts[market]=len(cot_rows)
    payload["research_contract"]={
        "full_history":True,
        "daily_price_history":True,
        "browser_loaded":False,
        "source_cot_rows":counts,
        "contract_origin":"V2_RECONSTRUCTED_AFTER_FULL_HISTORY_VALIDATION",
        "pre_contract_payload_sha256":hashlib.sha256(legacy.METALS.read_bytes()).hexdigest(),
    }
    legacy.METALS.write_text(json.dumps(payload,separators=(",",":"),sort_keys=True)+"\n",encoding="utf-8")
    legacy.validate_research_payload(payload)
    print("Reconstructed missing metals research_contract after full-history validation")


def main():
    ensure_research_contract()
    original=legacy.first_price_index_on_or_after
    legacy.first_price_index_on_or_after=alignment.first_price_index_on_or_after
    try:legacy.main()
    finally:legacy.first_price_index_on_or_after=original
    payload=json.loads(legacy.OUT.read_text(encoding="utf-8"))
    payload["schema_version"]=max(2,int(payload.get("schema_version") or 1))
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
    print("Disaggregated weight study v2 complete · MODEL_SELECTION_RESEARCH")

if __name__=="__main__":main()
