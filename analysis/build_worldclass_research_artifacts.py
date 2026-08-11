#!/usr/bin/env python3
"""Build current COT context and install frozen release-corrected research.

Fresh COT/price inputs may update current scores and analog context, but the
browser evidence registry, continuous actor/horizon details and threshold
statistics come only from the immutable release-corrected v2 snapshot.
"""
from __future__ import annotations
import json
import subprocess
from pathlib import Path

import build_worldclass_backtest as cot_backtest
import build_worldclass_bundle as bundle
import build_worldclass_metals as metals_builder
import build_worldclass_regime_backtest as regime_backtest
import install_release_corrected_runtime_v2 as v2_runtime
import install_cot_intelligence_shell as cot_shell

ROOT=Path(__file__).resolve().parent;SOURCE=ROOT/'interactive_cot_dashboard.html';WORLDCLASS=ROOT/'worldclass';TEMP_RESEARCH_BASE=WORLDCLASS/'.research-base.tmp.json';FULL_METALS=metals_builder.RESEARCH_OUT;RUNTIME_METALS=metals_builder.OUT
RESEARCH_CONSTANTS=('COT_DATA','PRICE_DATA','MACRO_MONITOR')

def atomic_write(path:Path,payload:dict)->None:
    path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_suffix(path.suffix+'.tmp');tmp.write_text(json.dumps(payload,separators=(',',':')),encoding='utf-8');tmp.replace(path)
def build_research_base()->dict:
    if not SOURCE.exists():raise FileNotFoundError(f'Missing canonical research dashboard: {SOURCE}')
    text=SOURCE.read_text(encoding='utf-8');payload={name:bundle.extract_json_constant(text,name) for name in RESEARCH_CONSTANTS}
    if not payload.get('COT_DATA') or not payload.get('PRICE_DATA'):raise RuntimeError('Canonical research dashboard is missing full COT or price history')
    return payload
def metals_history_is_full(payload:dict)->bool:
    for market in ('gold','silver'):
        cot_rows=((payload.get('markets') or {}).get(market) or {}).get('records') or [];price_rows=((payload.get('prices') or {}).get(market) or {}).get('records') or []
        if len(cot_rows)<500 or len(price_rows)<1000:return False
    return True
def read_json(path:Path)->dict:return json.loads(path.read_text(encoding='utf-8'))
def restore_full_metals_from_gh_pages()->bool:
    for revision in ('FETCH_HEAD:worldclass/research/metals-full.json','origin/gh-pages:worldclass/research/metals-full.json'):
        result=subprocess.run(['git','show',revision],cwd=ROOT.parent,text=True,capture_output=True,check=False)
        if result.returncode!=0 or not result.stdout.strip():continue
        try:payload=json.loads(result.stdout)
        except json.JSONDecodeError:continue
        if metals_history_is_full(payload):atomic_write(FULL_METALS,payload);print(f'Restored persistent full-history metals source from {revision}');return True
    return False
def rebuild_full_metals_from_official()->dict:
    print('No persisted full-history metals source found; rebuilding from official inputs.')
    try:runtime,research=metals_builder.build_payloads()
    except Exception as exc:raise FileNotFoundError('Full-history metals research unavailable and official reconstruction failed; refusing to shorten Gold/Silver research.') from exc
    if not metals_history_is_full(research):raise RuntimeError('Official metals reconstruction did not meet full-history research floors')
    atomic_write(FULL_METALS,research);atomic_write(RUNTIME_METALS,runtime);return research
def ensure_full_metals()->dict:
    if FULL_METALS.exists():
        payload=read_json(FULL_METALS)
        if metals_history_is_full(payload):return payload
    if RUNTIME_METALS.exists():
        payload=read_json(RUNTIME_METALS)
        if metals_history_is_full(payload):atomic_write(FULL_METALS,payload);return payload
    if restore_full_metals_from_gh_pages():return read_json(FULL_METALS)
    return rebuild_full_metals_from_official()
def validate_cot_intelligence_outputs()->None:
    required={WORLDCLASS/'cot-current-state.json':200000,WORLDCLASS/'cot-edge-registry.json':500000,WORLDCLASS/'cot-active-edges.json':180000,WORLDCLASS/'cot-cross-market.json':180000,WORLDCLASS/'cot-research-provenance.json':100000,WORLDCLASS/'cot-intelligence.js':60000,WORLDCLASS/'cot-intelligence.css':45000}
    for path,maximum in required.items():
        if not path.exists() or path.stat().st_size<=100:raise RuntimeError(f'COT Intelligence output missing/empty: {path}')
        if path.stat().st_size>maximum:raise RuntimeError(f'COT Intelligence performance budget exceeded: {path} = {path.stat().st_size:,} > {maximum:,}')
    for market in ('sp500','nq','vix','rty','dow','gold','silver'):
        path=WORLDCLASS/'cot-edge-details'/f'{market}.json'
        if not path.exists() or path.stat().st_size<=100:raise RuntimeError(f'COT Intelligence detail missing: {market}')
        if path.stat().st_size>3000000:raise RuntimeError(f'COT Intelligence lazy detail too large: {market} = {path.stat().st_size:,}')
    provenance=read_json(WORLDCLASS/'cot-research-provenance.json')
    if provenance.get('research_generation')!='release-corrected-v2' or provenance.get('historical_research_frozen') is not True:raise RuntimeError('canonical runtime is not installed from frozen v2 research')
def main()->None:
    WORLDCLASS.mkdir(parents=True,exist_ok=True);research_base=build_research_base();full_metals=ensure_full_metals();atomic_write(TEMP_RESEARCH_BASE,research_base)
    original_cot_base=cot_backtest.BASE;original_cot_metals=cot_backtest.METALS;original_regime_base=regime_backtest.BASE;original_regime_metals=regime_backtest.METALS
    try:
        cot_backtest.BASE=TEMP_RESEARCH_BASE;cot_backtest.METALS=FULL_METALS;regime_backtest.BASE=TEMP_RESEARCH_BASE;regime_backtest.METALS=FULL_METALS
        atomic_write(cot_backtest.OUT,cot_backtest.build());atomic_write(regime_backtest.OUT,regime_backtest.build())
    finally:
        cot_backtest.BASE=original_cot_base;cot_backtest.METALS=original_cot_metals;regime_backtest.BASE=original_regime_base;regime_backtest.METALS=original_regime_metals;TEMP_RESEARCH_BASE.unlink(missing_ok=True)
    atomic_write(RUNTIME_METALS,metals_builder.runtime_from_research(full_metals))
    v2_runtime.main();cot_shell.main();v2_runtime.install_copy_asset();validate_cot_intelligence_outputs()
    print(f'Saved current release-corrected COT backtest: {cot_backtest.OUT} ({cot_backtest.OUT.stat().st_size:,} bytes)')
    print(f'Saved current release-corrected regime backtest: {regime_backtest.OUT} ({regime_backtest.OUT.stat().st_size:,} bytes)')
    print('COT Intelligence frozen-v2 runtime contract PASS')
if __name__=='__main__':main()
