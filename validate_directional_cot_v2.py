#!/usr/bin/env python3
"""Dependence-aware validation for the existing directional COT model.

The directional model itself is unchanged. This layer grades its fixed two-market
x four-horizon research using a pre-2022 discovery split, a 2022+ holdout,
greedily non-overlapping holdout episodes and deterministic permutation p-values
with BH-FDR across the eight prespecified market/horizon tests.
"""
from __future__ import annotations
import json,math,random,statistics
from datetime import date
from pathlib import Path
from typing import Any

from build_directional_cot_system import build_history_for_market,load_market_inputs
from cot_direction_model import load_config
from cftc_release_calendar import calendar_hash

ROOT=Path(__file__).resolve().parent;OUT=ROOT/'worldclass'/'research'/'directional-validation-v2.json';HOLDOUT=date(2022,1,1);HORIZONS={'1w':5,'4w':20,'13w':65,'26w':130};PERMUTATIONS=2000;SEED=20260811

def finite(v:Any)->float|None:
    try:x=float(v)
    except (TypeError,ValueError):return None
    return x if math.isfinite(x) else None
def ranks(values:list[float])->list[float]:
    order=sorted(range(len(values)),key=lambda i:values[i]);out=[0.0]*len(values);i=0
    while i<len(order):
        j=i+1
        while j<len(order) and values[order[j]]==values[order[i]]:j+=1
        rank=(i+j-1)/2+1
        for k in range(i,j):out[order[k]]=rank
        i=j
    return out
def pearson(xs:list[float],ys:list[float])->float|None:
    if len(xs)<3 or len(xs)!=len(ys):return None
    mx=statistics.mean(xs);my=statistics.mean(ys);dx=[x-mx for x in xs];dy=[y-my for y in ys];den=math.sqrt(sum(x*x for x in dx)*sum(y*y for y in dy))
    return None if den<=1e-12 else sum(a*b for a,b in zip(dx,dy))/den
def spearman(xs:list[float],ys:list[float])->float|None:return pearson(ranks(xs),ranks(ys))
def permutation_p(xs:list[float],ys:list[float],seed:int)->float|None:
    obs=spearman(xs,ys)
    if obs is None or len(xs)<5:return None
    rng=random.Random(seed);extreme=0;work=list(ys)
    for _ in range(PERMUTATIONS):
        rng.shuffle(work);r=spearman(xs,work)
        if r is not None and abs(r)>=abs(obs):extreme+=1
    return (extreme+1)/(PERMUTATIONS+1)
def bh(rows:list[dict[str,Any]])->None:
    valid=[(i,finite(r.get('independent_permutation_p'))) for i,r in enumerate(rows) if finite(r.get('independent_permutation_p')) is not None];valid.sort(key=lambda x:x[1]);m=len(valid);running=1.0;q=[None]*len(rows)
    for rank in range(m,0,-1):
        idx,p=valid[rank-1];running=min(running,p*m/rank);q[idx]=running
    for i,row in enumerate(rows):row['global_fdr_q']=q[i]
def nonoverlap(rows:list[dict[str,Any]],price_index:dict[str,int],steps:int)->list[dict[str,Any]]:
    selected=[];last_end=-1
    for row in sorted(rows,key=lambda r:price_index.get(str(r.get('signal_price_date')),-1)):
        idx=price_index.get(str(row.get('signal_price_date')),-1)
        if idx<0:continue
        if idx>last_end:selected.append(row);last_end=idx+steps
    return selected
def paired(rows:list[dict[str,Any]],horizon:str)->tuple[list[float],list[float]]:
    pairs=[]
    for r in rows:
        x=finite(r.get('adjusted_cot_score'));y=finite(r.get(f'forward_return_{horizon}'))
        if x is not None and y is not None:pairs.append((x,y))
    return [x for x,_ in pairs],[y for _,y in pairs]
def main()->None:
    config=load_config(ROOT/'config'/'cot_direction_model_v1.json');metrics=[]
    for market in ('sp500','nq'):
        legacy,tff,prices=load_market_inputs(market);history=build_history_for_market(market,legacy,tff,prices,config);price_index={row['date'].date().isoformat():int(i) for i,row in prices.iterrows()}
        discovery=[r for r in history if date.fromisoformat(r['report_date'])<HOLDOUT];holdout=[r for r in history if date.fromisoformat(r['report_date'])>=HOLDOUT]
        for horizon,steps in HORIZONS.items():
            dx,dy=paired(discovery,horizon);hx,hy=paired(holdout,horizon);ind=nonoverlap(holdout,price_index,steps);ix,iy=paired(ind,horizon);dr=spearman(dx,dy);hr=spearman(hx,hy);ir=spearman(ix,iy);same=dr is not None and hr is not None and dr*hr>0;ind_same=hr is not None and ir is not None and hr*ir>0
            p=permutation_p(ix,iy,SEED+sum(ord(c) for c in f'{market}:{horizon}'))
            cls='DISCOVERY_ONLY'
            if same and len(hx)>=20:cls='HOLDOUT_DIRECTION_CONFIRMED'
            if cls=='HOLDOUT_DIRECTION_CONFIRMED' and ind_same and len(ix)>=8:cls='NONOVERLAP_CONFIRMED'
            metrics.append({'market':market,'horizon':horizon,'discovery_n':len(dx),'discovery_spearman_rho':dr,'holdout_n':len(hx),'holdout_spearman_rho':hr,'independent_n':len(ix),'independent_spearman_rho':ir,'same_sign_discovery_holdout':same,'same_sign_holdout_independent':ind_same,'independent_permutation_p':p,'classification':cls})
    bh(metrics)
    for row in metrics:
        if row['classification']=='NONOVERLAP_CONFIRMED' and finite(row.get('global_fdr_q')) is not None and float(row['global_fdr_q'])<=.10:row['classification']='GLOBAL_FDR'
    payload={'schema_version':1,'research_generation':'release-corrected-v2','information_contract_version':'cftc-public-availability-v2','release_calendar_hash':calendar_hash(),'study':'directional COT model dependence-aware validation','model_changed':False,'holdout_start':'2022-01-01','permutations':PERMUTATIONS,'multiple_testing':'BH-FDR across the fixed two-market x four-horizon grid','metrics':metrics,'classification_counts':{c:sum(r['classification']==c for r in metrics) for c in sorted({r['classification'] for r in metrics})},'evidence_status':'EXPLORATORY_UNLESS_NONOVERLAP_OR_FDR','automatic_production_weight_change_allowed':False}
    OUT.parent.mkdir(parents=True,exist_ok=True);OUT.write_text(json.dumps(payload,separators=(',',':'),sort_keys=True)+'\n',encoding='utf-8');print(f'Saved {OUT} · metrics={len(metrics)} · {payload["classification_counts"]}')
if __name__=='__main__':main()
