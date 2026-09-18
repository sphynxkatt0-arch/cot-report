#!/usr/bin/env python3
"""Generate general COT/macro/combined forecasts under the v2 release contract."""
from __future__ import annotations
import argparse,json
from datetime import UTC,datetime
from pathlib import Path

import generate_live_forecasts as legacy
import ledger_v2

ANALYSIS=Path(__file__).resolve().parents[1]
if str(ANALYSIS) not in __import__('sys').path:__import__('sys').path.insert(0,str(ANALYSIS))
from cftc_release_calendar import release_record

_ORIGINAL_BUILD=legacy.build_forecast

def build_forecast_v2(**kwargs):
    forecast=_ORIGINAL_BUILD(**kwargs)
    meta=release_record(forecast["report_date"])
    forecast["information_contract_version"]=ledger_v2.INFORMATION_CONTRACT_V2
    forecast["availability_at_utc"]=meta["availability_at_utc"]
    forecast["availability_source_type"]=meta["availability_source_type"]
    forecast["release_calendar_version"]=meta["calendar_version"]
    forecast["release_calendar_hash"]=meta["release_calendar_hash"]
    ledger_v2.validate_forecast(forecast)
    return forecast

def generate(*,worldclass:Path,model_output:Path,staging:Path,now_utc:datetime,allow_outside_window:bool=False):
    originals=(legacy.build_forecast,legacy.release_vintage_utc,legacy.within_forecast_window,legacy.validate_forecast,legacy.write_immutable_forecast)
    legacy.build_forecast=build_forecast_v2;legacy.release_vintage_utc=ledger_v2.release_vintage_utc;legacy.within_forecast_window=ledger_v2.within_forecast_window;legacy.validate_forecast=ledger_v2.validate_forecast;legacy.write_immutable_forecast=ledger_v2.write_immutable_forecast
    try:plan=legacy.generate(worldclass=worldclass,model_output=model_output,staging=staging,now_utc=now_utc,allow_outside_window=allow_outside_window)
    finally:legacy.build_forecast,legacy.release_vintage_utc,legacy.within_forecast_window,legacy.validate_forecast,legacy.write_immutable_forecast=originals
    plan["information_contract_version"]=ledger_v2.INFORMATION_CONTRACT_V2
    (staging/"plan.json").write_bytes(ledger_v2.canonical_json_bytes(plan))
    return plan

def args():
    p=argparse.ArgumentParser();p.add_argument("--worldclass",type=Path,default=legacy.WORLDCLASS);p.add_argument("--model-output",type=Path,default=legacy.MODEL_OUTPUT);p.add_argument("--staging",type=Path,default=legacy.DEFAULT_STAGING);p.add_argument("--now-utc");p.add_argument("--allow-outside-window",action="store_true");return p.parse_args()
def main():
    a=args();now=datetime.fromisoformat(a.now_utc.replace("Z","+00:00")).astimezone(UTC) if a.now_utc else datetime.now(UTC);plan=generate(worldclass=a.worldclass,model_output=a.model_output,staging=a.staging,now_utc=now,allow_outside_window=a.allow_outside_window);print(f"General live forecast v2 staging · forecasts={len(plan.get('forecasts') or [])} · skipped={len(plan.get('skipped') or [])}")
if __name__=="__main__":main()
