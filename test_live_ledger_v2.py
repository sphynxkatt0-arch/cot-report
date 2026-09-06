#!/usr/bin/env python3
"""Regression tests for mixed immutable legacy/v2 forecast validation."""
from __future__ import annotations
import json,tempfile
from pathlib import Path

from live import ledger as legacy
from live import ledger_v2 as v2
from cftc_release_calendar import calendar_hash,release_date

HASH='a'*64

def horizons():
    return {h:{'trading_closes':steps,'expected_return_pct':1.0,'median_return_pct':.5,'probability_positive':.55,'historical_average_drawdown_pct':-2.0,'historical_worst_drawdown_pct':-5.0,'historical_unconditional_return_pct':.4} for h,steps in {'1w':5,'2w':10,'4w':20,'13w':65,'26w':130}.items()}
def forecast(report:str,release:str,created:str,v2_contract:bool):
    model='test-v2';sid=legacy.deterministic_signal_id(report,'nq','tff','cot',model,HASH)
    f={'schema_version':1,'signal_id':sid,'created_at_utc':created,'report_date':report,'release_target_date':release,'market':'nq','dataset':'tff','model_family':'cot','model_version':model,'model_spec_hash':HASH,'cot_score':55.0,'cot_state':'neutral','macro_score':None,'macro_state':'unavailable','historical_sample_size':100,'historical_horizons':horizons(),'input_manifest_hash':HASH,'research_artifact_hash':HASH}
    f['forecast_filename']=legacy.forecast_relative_path(f).name
    if v2_contract:
        f['information_contract_version']='cftc-public-availability-v2';f['release_calendar_hash']=calendar_hash()
    return f
def main()->None:
    # Legacy immutable forecast remains valid under its original timing contract.
    legacy_report='2026-08-04';legacy_release='2026-08-07';legacy_created=legacy.iso_utc(legacy.release_vintage_utc(legacy_release));old=forecast(legacy_report,legacy_release,legacy_created,False);v2.validate_forecast(old)
    # March DST gap proves v2 timestamp is release+5m New York, not fixed Stockholm.
    report='2026-03-10';release=release_date(report).isoformat();created=legacy.iso_utc(v2.release_vintage_for_report_utc(report));new=forecast(report,release,created,True);v2.validate_forecast(new)
    assert created!=legacy.iso_utc(legacy.release_vintage_utc(release)),(created,legacy.iso_utc(legacy.release_vintage_utc(release)))
    bad=dict(new);bad['created_at_utc']=legacy.iso_utc(legacy.release_vintage_utc(release))
    try:v2.validate_forecast(bad)
    except legacy.LedgerError:pass
    else:raise AssertionError('fixed Stockholm v2 timestamp was incorrectly accepted')
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp);p=root/v2.forecast_relative_path(new);v2.write_immutable_forecast(p,new);assert v2.write_immutable_forecast(p,new)=='unchanged'
        changed=dict(new);changed['cot_score']=56.0
        try:v2.write_immutable_forecast(p,changed)
        except legacy.LedgerError:pass
        else:raise AssertionError('immutable v2 collision was not rejected')
    print('Mixed legacy/v2 live ledger timing and immutability PASS')
if __name__=='__main__':main()
