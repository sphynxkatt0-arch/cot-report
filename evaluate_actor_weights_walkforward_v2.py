#!/usr/bin/env python3
"""Nested expanding walk-forward validation for COT actor-weight variants.

The older weight studies are retained as MODEL_SELECTION_RESEARCH. This study
adds the missing out-of-fold layer: at each calendar-year fold, all observations
strictly before the fold choose one predeclared weight variant using a fixed
mean-Pearson objective across the predeclared markets/horizons; that choice is
then frozen for the next chronological year. No holdout year's outcome can alter
its own selected weights, and no result changes production weights automatically.
"""
from __future__ import annotations

import json
import math
import statistics
from collections import Counter,defaultdict
from datetime import date
from pathlib import Path
from typing import Any,Callable

import build_worldclass_research_artifacts as research
import cot_release_alignment_v2 as alignment
import evaluate_financial_actor_weights as financial
import evaluate_disaggregated_weights as metals
from cftc_release_calendar import calendar_hash

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'worldclass'/'research'/'actor-weight-walkforward-v2.json'
EVAL_YEARS=(2022,2023,2024,2025,2026)


def finite(v:Any)->float|None:
    try:x=float(v)
    except (TypeError,ValueError):return None
    return x if math.isfinite(x) else None

def pearson(xs:list[float],ys:list[float])->float|None:
    if len(xs)<3 or len(xs)!=len(ys):return None
    mx=statistics.mean(xs);my=statistics.mean(ys);dx=[x-mx for x in xs];dy=[y-my for y in ys];den=math.sqrt(sum(x*x for x in dx)*sum(y*y for y in dy))
    return None if den<=1e-12 else sum(a*b for a,b in zip(dx,dy))/den

def cells(signals:list[dict[str,Any]],horizons:tuple[str,...],start:date|None=None,end:date|None=None)->dict[str,dict[str,Any]]:
    out={}
    for h in horizons:
        pairs=[]
        for s in signals:
            d=s['report_date'];y=s['returns'].get(h)
            if start and d<start:continue
            if end and d>end:continue
            if y is not None:pairs.append((float(s['score']),float(y)))
        r=pearson([p[0] for p in pairs],[p[1] for p in pairs]) if pairs else None
        out[h]={'n':len(pairs),'pearson_r':r}
    return out

def build_variant_signals(rows:list[dict[str,Any]],price_payload:Any,variants:dict[str,dict[str,float]],builder:Callable)->dict[str,list[dict[str,Any]]]:
    return {name:builder(rows,price_payload,weights) for name,weights in variants.items()}
def objective(per_market:dict[str,dict[str,list[dict[str,Any]]]],variant:str,horizons:tuple[str,...],train_end:date)->dict[str,Any]:
    vals=[];details=[]
    for market,variant_map in per_market.items():
        metrics=cells(variant_map[variant],horizons,None,train_end)
        for h,m in metrics.items():
            r=finite(m.get('pearson_r'));n=int(m.get('n') or 0)
            details.append({'market':market,'horizon':h,'n':n,'pearson_r':r})
            if r is not None and n>=20:vals.append(r)
    return {'objective_mean_pearson':statistics.mean(vals) if vals else None,'eligible_cell_count':len(vals),'cells':details}
def eval_selected(per_market:dict[str,dict[str,list[dict[str,Any]]]],variant:str,horizons:tuple[str,...],start:date,end:date)->dict[str,Any]:
    result={}
    for market,variant_map in per_market.items():result[market]=cells(variant_map[variant],horizons,start,end)
    return result
def pool_oof(folds:list[dict[str,Any]],horizons:tuple[str,...])->dict[str,Any]:
    # Aggregate fold-level evaluation correlations using N-weighted Fisher-z only
    # as a descriptive stability summary; individual fold results remain primary.
    out={}
    for h in horizons:
        rows=[]
        for f in folds:
            for market,m in (f.get('evaluation') or {}).items():
                cell=(m or {}).get(h) or {};r=finite(cell.get('pearson_r'));n=int(cell.get('n') or 0)
                if r is not None and n>=4:
                    clipped=max(-.999999,min(.999999,r));rows.append((math.atanh(clipped),n,market,f['evaluation_year']))
        if rows:
            denom=sum(max(1,n-3) for _,n,_,_ in rows);z=sum(z*max(1,n-3) for z,n,_,_ in rows)/denom;pooled=math.tanh(z)
        else:pooled=None
        out[h]={'fold_market_cells':len(rows),'fisher_z_weighted_oof_r':pooled}
    return out

def run_family(name:str,markets:tuple[str,...],variants:dict[str,dict[str,float]],horizons:tuple[str,...],inputs:dict[str,tuple[list[dict[str,Any]],Any]],builder:Callable)->dict[str,Any]:
    per_market={m:build_variant_signals(inputs[m][0],inputs[m][1],variants,builder) for m in markets};folds=[]
    for year in EVAL_YEARS:
        train_end=date(year-1,12,31);eval_start=date(year,1,1);eval_end=date(year,12,31)
        scored=[]
        for variant in sorted(variants):
            score=objective(per_market,variant,horizons,train_end);value=finite(score['objective_mean_pearson'])
            scored.append((-(value if value is not None else -999.0),variant,score))
        scored.sort(key=lambda x:(x[0],x[1]));_,selected,selection=scored[0]
        folds.append({'evaluation_year':year,'train_end':train_end.isoformat(),'selected_variant':selected,'selection_objective':selection,'evaluation':eval_selected(per_market,selected,horizons,eval_start,eval_end)})
    return {'family':name,'markets':list(markets),'decision_horizons':list(horizons),'variant_names':sorted(variants),'folds':folds,'selection_counts':dict(Counter(f['selected_variant'] for f in folds)),'oof_stability':pool_oof(folds,horizons)}
def main()->None:
    base=research.build_research_base();cot=base.get('COT_DATA') or {};prices=base.get('PRICE_DATA') or {};metal_payload=research.ensure_full_metals()
    old_fin=financial.first_price_index_on_or_after;old_met=metals.first_price_index_on_or_after
    financial.first_price_index_on_or_after=alignment.first_price_index_on_or_after;metals.first_price_index_on_or_after=alignment.first_price_index_on_or_after
    try:
        tff_inputs={m:((((cot.get('tff') or {}).get(m) or {}).get('records') or []),prices.get(m)) for m in ('sp500','nq')}
        legacy_inputs={m:((((cot.get('legacy') or {}).get(m) or {}).get('records') or []),prices.get(m)) for m in ('sp500','nq')}
        metal_inputs={m:((((metal_payload.get('markets') or {}).get(m) or {}).get('records') or []),(metal_payload.get('prices') or {}).get(m)) for m in ('gold','silver')}
        families={
            'financial_tff':run_family('financial_tff',('sp500','nq'),financial.TFF_VARIANTS,('4w','13w'),tff_inputs,financial.build_signals),
            'financial_legacy':run_family('financial_legacy',('sp500','nq'),financial.LEGACY_VARIANTS,('4w','13w'),legacy_inputs,financial.build_signals),
            'metals_disaggregated':run_family('metals_disaggregated',('gold','silver'),metals.VARIANTS,('4w','13w','26w'),metal_inputs,metals.build_signals),
        }
    finally:
        financial.first_price_index_on_or_after=old_fin;metals.first_price_index_on_or_after=old_met
    payload={'schema_version':1,'research_generation':'release-corrected-v2','information_contract_version':'cftc-public-availability-v2','release_calendar_hash':calendar_hash(),'study':'nested expanding walk-forward actor weight validation','selection_rule':'At each annual fold choose one predeclared variant using only prior history; maximize fixed mean Pearson across predeclared market/horizon cells with N>=20; freeze for following year.','evaluation_years':list(EVAL_YEARS),'families':families,'evidence_purpose':'OUT_OF_FOLD_MODEL_SELECTION_VALIDATION','automatic_production_weight_change_allowed':False,'production_model_changed':False}
    OUT.parent.mkdir(parents=True,exist_ok=True);OUT.write_text(json.dumps(payload,separators=(',',':'),sort_keys=True)+'\n',encoding='utf-8');print(f'Saved {OUT} · families={len(families)}')
if __name__=='__main__':main()
