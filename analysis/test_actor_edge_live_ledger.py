#!/usr/bin/env python3
"""End-to-end synthetic contract for prospective release-corrected actor-edge evidence."""
from __future__ import annotations
import json,sys,tempfile
from datetime import date,datetime,timedelta,UTC
from pathlib import Path
ROOT=Path(__file__).resolve().parent;sys.path.insert(0,str(ROOT/'live'))
import actor_edge_ledger as ledger
import generate_actor_edge_live_forecasts as generator
import apply_actor_edge_live_forecasts as applier
import settle_actor_edge_live_signals as settler
import build_actor_edge_track_record as tracker
from cftc_release_calendar import release_record

def dump(path:Path,payload):path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(payload),encoding='utf-8')
def business_dates(start:date,count:int):
 out=[];d=start
 while len(out)<count:
  if d.weekday()<5:out.append(d.isoformat())
  d+=timedelta(days=1)
 return out

def main():
 with tempfile.TemporaryDirectory() as td:
  t=Path(td);cfg=t/'cfg';report='2026-08-11';meta=release_record(report);release=meta['actual_release_date'];series='tff:nq:asset_mgr';snapshot_hash='a'*64;metrics=[]
  for i,h in enumerate(ledger.EDGE_HORIZONS):metrics.append({'horizon':h,'n':40+i,'conditional_return_pct':-1.0-i*.1,'median_return_pct':-.5,'positive_rate_pct':40.0,'baseline_return_pct':.4,'excess_vs_baseline_pp':-1.4-i*.1,'avg_drawdown_pct':-3.0,'worst_drawdown_pct':-12.0,'evidence_status':'FAMILY_FDR','independent_n':20+i,'family_fdr_q':.05,'global_fdr_q':.15})
  current={'research_generation':'release-corrected-runtime-v2','actor_states':{series:{'series':series,'dataset':'tff','market':'nq','actor':'asset_mgr','actor_label':'Asset Manager / Institutional','actor_role':'PRIMARY_DIRECTIONAL','report_date_tuesday':report,'release_date_friday':release,'availability_at_utc':meta['availability_at_utc'],'direction':'CUT','action_type':'LONG_LIQUIDATE','position_percentile':82.0,'change_magnitude_percentile':93.0,'delta_net_contracts':-20000,'delta_net_oi_pp':-1.2}}}
  active={'research_generation':'release-corrected-v2','automatic_promotion_allowed':False,'by_market':{'nq':{'active_thresholds':[{'series':series,'dataset':'tff','actor':'asset_mgr','actor_label':'Asset Manager / Institutional','actor_role':'PRIMARY_DIRECTIONAL','direction':'CUT','action_type':'LONG_LIQUIDATE','current_position_percentile':82.0,'current_change_percentile':93.0,'current_delta_net_contracts':-20000,'current_delta_net_oi_pp':-1.2,'selected_threshold':60,'historical_classification':'FAMILY_FDR','evidence_status':'FAMILY_FDR','promotion_status':'RESEARCH_ONLY_V2','metrics':metrics}],'continuous_context':[]}}}
  registry={'research_generation':'release-corrected-v2','automatic_promotion_allowed':False,'sources':{'threshold_inference':{'sha256':'b'*64}}}
  provenance={'research_generation':'release-corrected-v2','historical_research_frozen':True,'snapshot_manifest_sha256':snapshot_hash}
  policy={'policy_id':'test-policy','eligible_actor_roles':['PRIMARY_DIRECTIONAL'],'required_research_status':{'threshold':['FAMILY_FDR']},'required_live_checks':{'1w':{'matured_signals':30,'same_direction_as_historical':True},'4w':{'matured_signals':20,'same_direction_as_historical':True},'13w':{'matured_signals':12,'same_direction_as_historical':True}}}
  paths={'current':cfg/'current.json','active':cfg/'active.json','registry':cfg/'registry.json','provenance':cfg/'provenance.json','policy':cfg/'policy.json'}
  for key,payload in (('current',current),('active',active),('registry',registry),('provenance',provenance),('policy',policy)):dump(paths[key],payload)
  generator.CURRENT=paths['current'];generator.ACTIVE=paths['active'];generator.REGISTRY=paths['registry'];generator.PROVENANCE=paths['provenance'];generator.POLICY=paths['policy']
  now=ledger.release_vintage_for_report_utc(report);staging=t/'staging';plan=generator.generate(staging,now);assert plan['forecast_count']==1;assert plan['research_generation']=='release-corrected-v2';assert plan['research_snapshot_hash']==snapshot_hash
  ledger_root=t/'ledger';metadata=t/'append.json';first=applier.apply(staging,ledger_root,metadata);assert first['new_count']==1 and first['ledger']['integrity']=='PASS'
  second=applier.apply(staging,ledger_root,t/'append2.json');assert second['new_count']==0 and second['unchanged_count']==1
  state=ledger.validate_ledger(ledger_root);assert state['forecast_count']==1 and state['manifest_count']==1
  outside=generator.generate(t/'outside',datetime(2026,8,11,12,tzinfo=UTC));assert outside['forecast_count']==0,'historical/backfilled issuance must be refused'
  dates=business_dates(date.fromisoformat(release),140);prices=[{'date':d,'price':100+i*.15} for i,d in enumerate(dates)];sources={'nq':{'records':prices,'price_source':'synthetic-test','price_source_timestamp':'2026-08-31T00:00:00Z'}}
  settled=settler.settle(ledger_root,sources,datetime(2027,3,1,tzinfo=UTC),t/'settle.json');assert settled['created_entry_count']==1 and settled['created_outcome_count']==len(ledger.EDGE_HORIZONS)
  assert ledger.validate_ledger(ledger_root)['outcome_count']==len(ledger.EDGE_HORIZONS)
  tracker.POLICY=paths['policy'];track=tracker.build(ledger_root,datetime(2027,3,1,tzinfo=UTC));assert track['forecast_count']==1 and track['outcome_count']==8;assert track['promotion_evaluations'][0]['decision']=='RESEARCH_ONLY';assert track['governance']['historical_backfill_allowed'] is False
  core_paths=list((ledger_root/'live'/'forecasts').rglob('*.json')) if (ledger_root/'live'/'forecasts').exists() else [];assert core_paths==[],'actor-edge lifecycle must not write core ledger namespace'
  print('Actor-edge release-corrected prospective ledger contract PASS')
if __name__=='__main__':main()
