#!/usr/bin/env python3
"""Production refresh entrypoint for release-corrected COT Intelligence.

Only raw/normalized COT source extraction and market/macro inputs are refreshed.
Superseded Tuesday-aligned predictive studies are deliberately not rerun. The
legacy source HTML is rebuilt only as a normalized data container, using
contained-date source selection from build_interactive_cot_dashboard_v2.py.
"""
from __future__ import annotations
import argparse,sys
from datetime import UTC,datetime

import serve_interactive_cot_dashboard as legacy
import build_interactive_cot_dashboard_v2 as builder_v2


def validate_raw_refresh(start:int,end:int,include_legacy:bool)->None:
    exact=legacy.summary_cutoffs(legacy.ROOT/'cot_exact_output'/f'cot_exact_summary_{start}_{end}.csv')
    legacy_rows=legacy.summary_cutoffs(legacy.ROOT/'cot_legacy_output'/f'cot_legacy_summary_{start}_{end}.csv') if include_legacy else {}
    failures=[]
    for market,dates in exact.items():
        if dates['latest']!=dates['source']:failures.append(f"TFF {market}: output {dates['latest']} != source {dates['source']}")
    for market,dates in legacy_rows.items():
        if dates['latest']!=dates['source']:failures.append(f"Legacy {market}: output {dates['latest']} != source {dates['source']}")
    if failures:raise RuntimeError('Raw COT refresh freshness failed:\n- '+'\n- '.join(failures))
    legacy.log('Raw COT freshness validated: '+', '.join(f"TFF {m} {d['latest']}" for m,d in exact.items())+(('; '+', '.join(f"Legacy {m} {d['latest']}" for m,d in legacy_rows.items())) if legacy_rows else ''))

def refresh_data(start:int,end:int,include_legacy:bool=True)->None:
    legacy.log(f'V2 raw refresh started. start={start}, end={end}, legacy={"yes" if include_legacy else "no"}')
    legacy.write_refresh_status('running','Release-corrected raw refresh is in progress.')
    for series_id,dest in legacy.FRED_SERIES.items():
        try:legacy.fetch_fred_csv(series_id,dest)
        except Exception as exc:
            if dest.exists():
                legacy.log(f'WARNING: {series_id} refresh failed; using existing {dest} (latest cached date: {legacy.cached_csv_latest_date(dest)}): {exc}')
                continue
            raise
    legacy.refresh_cnn_factors()
    # These two scripts remain the normalized CFTC ingestion layer. Their old
    # forward-return columns are ignored by v2 research/runtime consumers.
    legacy.run_python('cot_overlay_exact.py','--market','all','--start',str(start),'--end',str(end))
    if include_legacy:legacy.run_python('cot_legacy_correlations.py','--market','all','--start',str(start),'--end',str(end))
    validate_raw_refresh(start,end,include_legacy)
    builder_v2.main()
    legacy.write_refresh_status('ok','Raw COT/source refresh completed. Predictive evidence is supplied only by frozen release-corrected v2 research.')
    legacy.log(f'V2 raw refresh completed. Source dashboard rebuilt: {legacy.HTML}')

def main()->None:
    p=argparse.ArgumentParser();p.add_argument('--start',type=int,default=2016);p.add_argument('--end',type=int,default=datetime.now(UTC).year);p.add_argument('--no-legacy',action='store_true');p.add_argument('--refresh-only',action='store_true',default=True);a=p.parse_args()
    try:refresh_data(a.start,a.end,include_legacy=not a.no_legacy)
    except Exception as exc:
        legacy.write_refresh_status('failed',str(exc));legacy.log(f'WARNING: v2 raw refresh failed: {exc}',file=sys.stderr);raise
if __name__=='__main__':main()
