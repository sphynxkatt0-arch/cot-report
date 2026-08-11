#!/usr/bin/env python3
"""Regression contract for the COT Intelligence runtime presentation layer."""
from __future__ import annotations
import json
from datetime import date,timedelta
from pathlib import Path
ROOT=Path(__file__).resolve().parent; WC=ROOT/"worldclass"; CURRENT=WC/"cot-current-state.json"; REGISTRY=WC/"cot-edge-registry.json"; ACTIVE=WC/"cot-active-edges.json"; CROSS=WC/"cot-cross-market.json"; POLICY=ROOT/"config"/"cot_edge_promotion_policy.json"; HTML=ROOT/"worldclass_dashboard.html"
HORIZONS=["monday","tuesday","wednesday","thursday","friday","1w","2w","3w","4w","6w","8w","13w","26w","39w","52w"]; MARKETS=["sp500","nq","vix","rty","dow","gold","silver"]
def load(path): assert path.exists() and path.stat().st_size>100,path; return json.loads(path.read_text(encoding="utf-8"))
def close(a,b,tol=1e-5): return abs(float(a)-float(b))<=tol*max(1.0,abs(float(a)),abs(float(b)))
def main():
 current=load(CURRENT); registry=load(REGISTRY); active=load(ACTIVE); cross=load(CROSS); policy=load(POLICY); assert current["information_contract"]["lookahead_safe"] is True; assert current["production_model_changed"] is False; states=current.get("actor_states") or {}; assert len(states)==59,len(states)
 for key,row in states.items():
  assert key==row["series"]; report=date.fromisoformat(row["report_date_tuesday"]); release=date.fromisoformat(row["release_date_friday"]); assert release==report+timedelta(days=3)
  for field in ("position_percentile","change_magnitude_percentile"):
   value=row.get(field); assert value is None or 0<=float(value)<=100,(key,field,value)
  long_v,short_v,net_v=row.get("long_contracts"),row.get("short_contracts"),row.get("net_contracts")
  if long_v is not None and short_v is not None and net_v is not None: assert close(float(long_v)-float(short_v),net_v),(key,long_v,short_v,net_v)
  oi=row.get("open_interest")
  if oi not in (None,0) and net_v is not None and row.get("net_oi_pct") is not None: assert close(float(net_v)/float(oi)*100.0,row["net_oi_pct"],tol=2e-4),key
 assert registry["horizons"]==HORIZONS; assert len(registry.get("actors") or {})==59; assert registry.get("automatic_promotion_allowed") is False; assert "horizons" not in next(iter(registry["actors"].values())); counts=registry["research_counts"]; assert counts["continuous_metrics"]==12915; assert counts["actor_horizon_cells"]==885; assert counts["market_oi_horizon_cells"]==105
 detail_series=set(); detail_cells=0
 for market in MARKETS:
  detail=load(WC/"cot-edge-details"/f"{market}.json"); assert detail["market"]==market; assert detail.get("actors"); assert "threshold_percentile_profiles" in detail; assert "actor_flow_x_oi_direction" in detail
  for row in detail["actors"]:
   detail_cells+=1; detail_series.add(row["series"]); metric=row["best_overall"]; n=int(metric.get("independent_n") or 0)
   if n<15: assert metric.get("evidence_status")=="INSUFFICIENT_N",(row["series"],row["horizon"],n,metric.get("evidence_status"))
   assert metric.get("sample_grade") in {"FULL","SAMPLE_WARNING","RESEARCH_ONLY","INSUFFICIENT"}
 assert detail_cells==885,detail_cells; assert len(detail_series)==59,len(detail_series)
 assert active["governance"]["production_model_changed"] is False; assert active["governance"]["automatic_promotion_allowed"] is False; assert active["governance"]["pp_definition"]=="percentage points"
 total_active=0
 for _,block in (active.get("by_market") or {}).items():
  for row in block.get("active_thresholds") or []:
   total_active+=1; assert float(row["current_change_percentile"])>=float(row["selected_threshold"]); assert row["direction"] in {"ADD","CUT"}
   for metric in row.get("metrics") or []: assert "conditional_return_pct" in metric and "baseline_return_pct" in metric and "excess_vs_baseline_pp" in metric
 assert total_active==int(active.get("active_threshold_count") or 0)
 assert cross["governance"]["status"]=="DISCOVERY_ONLY"; assert cross["governance"]["automatic_promotion_allowed"] is False; assert cross["current_same_actor_across_markets"]
 for family in ("same_actor_cross_instrument_holdout_1w","cross_instrument_breadth_holdout_1w","cross_actor_same_instrument_holdout_1w","cross_report_taxonomy_holdout_1w","lead_market_holdout_1w"):
  for row in cross.get(family) or []: assert row["evidence_status"]=="DISCOVERY_ONLY" and row["promotion_eligible"] is False
 assert policy["automatic_weight_changes"] is False; assert policy["eligible_actor_roles"]==["PRIMARY_DIRECTIONAL"]; assert policy["decision_states"]["ELIGIBLE_FOR_GOVERNANCE_REVIEW"]
 html=HTML.read_text(encoding="utf-8"); assert 'data-cot-intelligence-asset="css"' in html; assert 'data-cot-intelligence-asset="js"' in html
 js=(WC/"cot-intelligence.js").read_text(encoding="utf-8"); assert "pp = <b>percentage points</b>" in js; assert "Data / decision quality" in js; assert "cot-edge-details/" in js; assert "cot-cross-market.json" in js; assert '"cross"' in js
 for path,limit in {CURRENT:200000,REGISTRY:500000,ACTIVE:180000,CROSS:180000,WC/"cot-intelligence.js":60000,WC/"cot-intelligence.css":45000}.items(): assert path.stat().st_size<=limit,(path,path.stat().st_size,limit)
 print("COT Intelligence contract PASS"); print(f"actor_states={len(states)} actor_horizon_cells={detail_cells} active_thresholds={total_active} registry_bytes={REGISTRY.stat().st_size} active_bytes={ACTIVE.stat().st_size} cross_bytes={CROSS.stat().st_size}")
if __name__=="__main__":main()
