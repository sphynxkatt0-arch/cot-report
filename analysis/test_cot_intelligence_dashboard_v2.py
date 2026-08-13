#!/usr/bin/env python3
"""Regression contract for the release-corrected COT Intelligence runtime."""
from __future__ import annotations
import json
import re
from pathlib import Path
from cftc_release_calendar import release_date
ROOT=Path(__file__).resolve().parent;WC=ROOT/'worldclass';CURRENT=WC/'cot-current-state.json';REGISTRY=WC/'cot-edge-registry.json';ACTIVE=WC/'cot-active-edges.json';CROSS=WC/'cot-cross-market.json';PROV=WC/'cot-research-provenance.json';POLICY=ROOT/'config'/'cot_edge_promotion_policy.json';HTML=ROOT/'worldclass_dashboard.html';LIGHT_CSS=WC/'cot-intelligence-light.css';EDGE_MODEL=WC/'current-edge-model.js';EDGE_JS=WC/'current-edge-command.js';EDGE_CSS=WC/'current-edge-command.css';MOBILE_CSS=WC/'mobile-ux.css';MOBILE_RUNTIME=WC/'mobile-ux-runtime.js'
HORIZONS=['monday','tuesday','wednesday','thursday','friday','1w','2w','3w','4w','6w','8w','13w','26w','39w','52w'];MARKETS=['sp500','nq','vix','rty','dow','gold','silver'];WEEKDAYS={'monday','tuesday','wednesday','thursday','friday'};FORWARD={'1w','2w','4w','13w','26w'}
def load(path):assert path.exists() and path.stat().st_size>100,path;return json.loads(path.read_text(encoding='utf-8'))
def close(a,b,tol=1e-5):return abs(float(a)-float(b))<=tol*max(1.0,abs(float(a)),abs(float(b)))
def main():
 current=load(CURRENT);registry=load(REGISTRY);active=load(ACTIVE);cross=load(CROSS);prov=load(PROV);policy=load(POLICY)
 assert current['information_contract']['lookahead_safe'] is True;assert current['information_contract']['strict_release_alignment'] is True;assert current['production_model_changed'] is False
 assert registry['research_generation']==active['research_generation']==cross['research_generation']==prov['research_generation']=='release-corrected-v2';assert prov['historical_research_frozen'] is True;assert registry['automatic_promotion_allowed'] is False;assert active['automatic_promotion_allowed'] is False;assert cross['governance']['automatic_promotion_allowed'] is False
 states=current.get('actor_states') or {};assert len(states)==59
 for key,row in states.items():
  assert key==row['series'];report=row['report_date_tuesday'];assert row['release_date_friday']==release_date(report).isoformat();assert row.get('availability_at_utc') and row.get('release_calendar_hash')
  for field in ('position_percentile','change_magnitude_percentile'):
   value=row.get(field);assert value is None or 0<=float(value)<=100
  long_v,short_v,net_v=row.get('long_contracts'),row.get('short_contracts'),row.get('net_contracts')
  if long_v is not None and short_v is not None and net_v is not None:assert close(float(long_v)-float(short_v),net_v)
 assert registry['horizons']==HORIZONS;assert len(registry.get('actors') or {})==59;counts=registry['research_counts'];assert counts['actor_horizon_cells']==885;assert counts['market_oi_horizon_cells']==105;assert counts['threshold_metrics']==12390
 detail_series=set();detail_cells=0;oi_cells=0
 for market in MARKETS:
  detail=load(WC/'cot-edge-details'/f'{market}.json');assert detail['market']==market and detail['research_generation']=='release-corrected-v2';detail_cells+=len(detail['actors']);oi_cells+=len(detail.get('market_oi') or {})
  for row in detail['actors']:
   detail_series.add(row['series']);metric=row.get('best_overall') or {};n=int(metric.get('independent_n') or 0)
   if n<15:assert metric.get('evidence_status')=='INSUFFICIENT_N'
   assert metric.get('sample_grade') in {'FULL','SAMPLE_WARNING','RESEARCH_ONLY','INSUFFICIENT'}
 assert detail_cells==885 and oi_cells==105 and len(detail_series)==59
 assert active['schema_version']==5;assert active['governance']['automatic_promotion_allowed'] is False;assert active['governance']['nested_threshold_policy'].startswith('one evidence-best crossed threshold')
 total_active=0;seen=set()
 for block in (active.get('by_market') or {}).values():
  for row in block.get('active_thresholds') or []:
   total_active+=1;assert row['series'] not in seen;seen.add(row['series']);assert float(row['current_change_percentile'])>=float(row['selected_threshold']);assert row['direction'] in {'ADD','CUT'}
   metrics={m['horizon']:m for m in row.get('metrics') or []};assert FORWARD<=set(metrics);assert set(metrics)<=WEEKDAYS|FORWARD
   for h,m in metrics.items():
    assert {'conditional_return_pct','excess_vs_baseline_pp','n'}<=set(m)
    if h in FORWARD:assert {'baseline_return_pct','median_return_pct','positive_rate_pct','avg_drawdown_pct','worst_drawdown_pct','evidence_status','independent_n','family_fdr_q','global_fdr_q'}<=set(m)
 assert total_active==int(active.get('active_threshold_count') or 0) and total_active<=59;assert ACTIVE.stat().st_size<=180000
 assert cross['governance']['status']=='DISCOVERY_ONLY';assert policy['automatic_weight_changes'] is False
 html=HTML.read_text(encoding='utf-8')
 for marker in ('data-cot-intelligence-asset="css"','data-cot-intelligence-asset="light-css"','data-cot-intelligence-asset="js"','data-cot-intelligence-asset="current-edge-model"','data-cot-intelligence-asset="current-edge-js"','data-cot-intelligence-asset="mobile-ux-css"','data-cot-intelligence-asset="mobile-ux-runtime"','data-cot-intelligence-asset="v2-copy-js"'):assert marker in html
 edge_model=EDGE_MODEL.read_text(encoding='utf-8');edge_js=EDGE_JS.read_text(encoding='utf-8');assert 'GLOBAL_FDR' in edge_model and 'NONOVERLAP_CONFIRMED' in edge_model and 'historical excess' in edge_model;assert 'Prospective combined model is frozen separately from historical actor edges.' in edge_model;assert re.search(r'Conditional watch[\s\S]{0,32}not a prediction',edge_js)
 mobile_runtime=MOBILE_RUNTIME.read_text(encoding='utf-8');assert 'mobileUxReady' in mobile_runtime and 'repeat(4, minmax(0, 1fr))' in mobile_runtime
 for path,limit in {CURRENT:200000,REGISTRY:500000,ACTIVE:180000,CROSS:180000,PROV:100000,WC/'cot-intelligence.js':60000,WC/'cot-intelligence.css':45000,LIGHT_CSS:20000,EDGE_MODEL:30000,EDGE_JS:40000,EDGE_CSS:32000,MOBILE_CSS:30000,MOBILE_RUNTIME:12000}.items():assert path.stat().st_size<=limit,(path,path.stat().st_size,limit)
 print(f'COT Intelligence v2 PASS · actors={len(states)} actor_cells={detail_cells} oi_cells={oi_cells} active={total_active} active_bytes={ACTIVE.stat().st_size}')
if __name__=='__main__':main()
