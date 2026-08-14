#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,math
from pathlib import Path
import numpy as np,pandas as pd

H={"1w":1,"2w":2,"4w":4,"13w":13,"26w":26}
M={"sp500":"sp500","nasdaq":"nasdaq"}
AGG=["macro_score_level","macro_score_delta_1w","macro_score_delta_4w","macro_score_delta_8w","macro_score_accel_4w"]
RAW=["net_liquidity","net_liquidity_4w_change","net_liquidity_13w_change","bank_reserves","bank_reserves_4w_change","tga","tga_4w_change","rrp","rrp_4w_change","sofr_iorb_spread","sofr_iorb_spread_4w_change","effr_iorb_spread","effr_iorb_spread_4w_change","real_yield_10y","real_yield_4w_change","real_yield_5y","real_yield_5y_4w_change","nominal_yield_10y","nominal_yield_2y","nominal_yield_30y","nominal_yield_30y_4w_change","yield_curve_10y_2y","yield_curve_10y_3m","yield_curve_30y_10y","hy_oas","hy_oas_4w_change","ig_oas","ig_oas_4w_change","dollar_index","dollar_4w_change","vix","vix_4w_change","treasury_issuance_7d","treasury_issuance_28d","treasury_issuance_next_7d","slr_balance_sheet_load","slr_balance_sheet_load_4w_change","reserves_to_bank_assets_pct","reserves_to_bank_assets_4w_change"]

def num(x,d=6):
    try:v=float(x)
    except:return None
    return round(v,d) if math.isfinite(v) else None

def reg(x,y):
    z=pd.DataFrame({'x':pd.to_numeric(x,errors='coerce'),'y':pd.to_numeric(y,errors='coerce')}).dropna()
    if len(z)<3 or z.x.std(ddof=0)==0 or z.y.std(ddof=0)==0:return {'n':len(z),'r':None,'rho':None,'slope':None,'r2':None}
    r=float(z.x.corr(z.y));rho=float(z.x.rank().corr(z.y.rank()));vx=float(np.mean((z.x-z.x.mean())**2));slope=float(np.mean((z.x-z.x.mean())*(z.y-z.y.mean()))/vx)
    return {'n':len(z),'r':num(r),'rho':num(rho),'slope':num(slope),'r2':num(r*r)}

def lag(s,days):return pd.Series([s.get(i-pd.Timedelta(days=days),np.nan) for i in s.index],index=s.index,dtype=float)
def fwd(price,anchors,weeks):return pd.Series([((price.get(i+pd.Timedelta(days=7*weeks),np.nan)/price.get(i,np.nan)-1)*100) if pd.notna(price.get(i,np.nan)) and pd.notna(price.get(i+pd.Timedelta(days=7*weeks),np.nan)) and price.get(i,np.nan)!=0 else np.nan for i in anchors],index=anchors)

def exp_pct(s):
    out=pd.Series(np.nan,index=s.index);hist=[]
    for i,v in pd.to_numeric(s,errors='coerce').items():
        if pd.notna(v):
            if len(hist)>=26:
                a=np.asarray(hist);out.loc[i]=(np.sum(a<v)+.5*np.sum(a==v))/len(a)*100
            hist.append(float(v))
    return out

def summ(s,base):
    x=pd.to_numeric(s,errors='coerce').dropna()
    return {'n':len(x),'mean':num(x.mean(),4) if len(x) else None,'median':num(x.median(),4) if len(x) else None,'hit':num((x>0).mean()*100,2) if len(x) else None,'excess':num(x.mean()-base,4) if len(x) else None}

def extremes(x,y):
    p=exp_pct(x);yy=pd.to_numeric(y,errors='coerce').dropna();base=float(yy.mean()) if len(yy) else np.nan
    lo=summ(y[p<=10],base);hi=summ(y[p>=90],base);mid=summ(y[(p>10)&(p<90)],base)
    spread=num(hi['mean']-lo['mean'],4) if hi['mean'] is not None and lo['mean'] is not None else None
    return {'bottom10':lo,'middle80':mid,'top10':hi,'top_minus_bottom_pp':spread}

def overlap(df,x,y,w):
    q=df[[x,y]].dropna().reset_index(drop=True);rs=[]
    for off in range(max(1,w)):
        z=q.iloc[off::max(1,w)];r=reg(z[x],z[y])
        if r['r'] is not None and r['n']>=8:rs.append(float(r['r']))
    if not rs:return {'offsets':0,'median_r':None,'min_r':None,'max_r':None,'sign_consistency':None}
    med=float(np.median(rs));sg=1 if med>0 else -1 if med<0 else 0
    return {'offsets':len(rs),'median_r':num(med),'min_r':num(min(rs)),'max_r':num(max(rs)),'sign_consistency':num(sum((1 if r>0 else -1 if r<0 else 0)==sg for r in rs)/len(rs)*100,2)}

def oos(df,x,y):
    q=df[[x,y]].dropna().reset_index(drop=True);n=len(q)
    if n<30:return {'train_n':0,'test_n':0,'train_r':None,'test_r':None,'test_rho':None,'oos_r2':None,'sign_consistent':None}
    k=max(20,min(n-10,int(.7*n)));tr=q.iloc[:k];te=q.iloc[k:];a=reg(tr[x],tr[y]);b=reg(te[x],te[y])
    if a['slope'] is None:return {'train_n':len(tr),'test_n':len(te),'train_r':a['r'],'test_r':b['r'],'test_rho':b['rho'],'oos_r2':None,'sign_consistent':None}
    intercept=float(tr[y].mean())-float(a['slope'])*float(tr[x].mean());pred=intercept+float(a['slope'])*te[x];sst=float(np.sum((te[y]-te[y].mean())**2));r2=1-float(np.sum((te[y]-pred)**2))/sst if sst>1e-12 else np.nan
    same=None if a['r'] is None or b['r'] is None else ((a['r']>0)==(b['r']>0))
    return {'train_n':len(tr),'test_n':len(te),'train_r':a['r'],'test_r':b['r'],'test_rho':b['rho'],'oos_r2':num(r2),'sign_consistent':same}

def eras(df,x,y):
    q=df[['date',x,y]].dropna().sort_values('date');out=[]
    if len(q)<30:return out
    for n,idx in enumerate(np.array_split(np.arange(len(q)),3),1):
        z=q.iloc[idx];r=reg(z[x],z[y]);out.append({'era':n,'start':z.date.iloc[0].strftime('%Y-%m-%d'),'end':z.date.iloc[-1].strftime('%Y-%m-%d'),'n':r['n'],'r':r['r'],'rho':r['rho']})
    return out

def analyze(df,x,y,w):
    r=reg(df[x],df[y]);e=extremes(df[x],df[y]);ov=overlap(df,x,y,w);oo=oos(df,x,y);ar=abs(r['r'] or 0);stable=oo.get('sign_consistent') and oo.get('test_r') is not None and ov.get('median_r') is not None and ((oo['test_r']>0)==(r['r']>0)) and ((ov['median_r']>0)==(r['r']>0))
    label='ROBUST_ASSOCIATION' if ar>=.20 and stable and e['top_minus_bottom_pp'] is not None and abs(e['top_minus_bottom_pp'])>=1 else 'MODEST_ASSOCIATION' if ar>=.10 and stable else 'UNSTABLE_ASSOCIATION' if ar>=.10 else 'WEAK_OR_NONE'
    return {**r,'extremes':e,'nonoverlap':ov,'oos':oo,'eras':eras(df,x,y),'evidence':label}

def prep(path):
    d=pd.read_csv(path,low_memory=False);d['date']=pd.to_datetime(d.date,errors='coerce');d=d.dropna(subset=['date']).sort_values('date').drop_duplicates('date').set_index('date')
    for c in d.columns:
        if c not in {'regime_label','retirement_flow_signal','credit_override'}:d[c]=pd.to_numeric(d[c],errors='coerce')
    s=d.liquidity_score;d['macro_score_level']=s;d['macro_score_delta_1w']=s-lag(s,7);d['macro_score_delta_4w']=s-lag(s,28);d['macro_score_delta_8w']=s-lag(s,56);d['macro_score_accel_4w']=d.macro_score_delta_4w-(lag(s,28)-lag(s,56))
    wk=d[d.index.weekday==4].copy()
    for m,pcol in M.items():
        p=d[pcol]
        for h,w in H.items():wk[f'{m}_forward_{h}']=fwd(p,wk.index,w)
    meta={'input_rows':len(d),'weekly_rows':len(wk),'start':d.index.min().strftime('%Y-%m-%d'),'end':d.index.max().strftime('%Y-%m-%d'),'anchor':'Friday canonical macro state','availability_lag_safe':True,'macro_vintage_safe':False}
    return wk.reset_index(),meta

def main():
    a=argparse.ArgumentParser();a.add_argument('--input',type=Path,required=True);a.add_argument('--out-dir',type=Path,required=True);z=a.parse_args();df,meta=prep(z.input);res={'schema_version':1,'methodology':meta,'aggregate':{},'factors':{}};rows=[]
    for m in M:
        res['aggregate'][m]={}
        for x in AGG:
            res['aggregate'][m][x]={}
            for h,w in H.items():
                y=f'{m}_forward_{h}';r=analyze(df,x,y,w);res['aggregate'][m][x][h]=r;rows.append({'family':'aggregate','market':m,'predictor':x,'horizon':h,'n':r['n'],'pearson_r':r['r'],'spearman_rho':r['rho'],'r2':r['r2'],'oos_test_r':r['oos']['test_r'],'oos_r2':r['oos']['oos_r2'],'nonoverlap_median_r':r['nonoverlap']['median_r'],'nonoverlap_sign_consistency':r['nonoverlap']['sign_consistency'],'top10_mean':r['extremes']['top10']['mean'],'bottom10_mean':r['extremes']['bottom10']['mean'],'top_minus_bottom_pp':r['extremes']['top_minus_bottom_pp'],'evidence':r['evidence']})
    factors=[c for c in df.columns if c.startswith('score_') and c not in {'score_market_trend','score_retirement_proxy'}]+[c for c in RAW if c in df.columns]
    for m in M:
        res['factors'][m]={}
        for x in factors:
            res['factors'][m][x]={}
            for h,w in H.items():
                y=f'{m}_forward_{h}';r=analyze(df,x,y,w);res['factors'][m][x][h]=r;rows.append({'family':'factor','market':m,'predictor':x,'horizon':h,'n':r['n'],'pearson_r':r['r'],'spearman_rho':r['rho'],'r2':r['r2'],'oos_test_r':r['oos']['test_r'],'oos_r2':r['oos']['oos_r2'],'nonoverlap_median_r':r['nonoverlap']['median_r'],'nonoverlap_sign_consistency':r['nonoverlap']['sign_consistency'],'top10_mean':r['extremes']['top10']['mean'],'bottom10_mean':r['extremes']['bottom10']['mean'],'top_minus_bottom_pp':r['extremes']['top_minus_bottom_pp'],'evidence':r['evidence']})
    z.out_dir.mkdir(parents=True,exist_ok=True);Path(z.out_dir/'macro_predictivity_results.json').write_text(json.dumps(res,indent=2)+'\n');tab=pd.DataFrame(rows);tab.to_csv(z.out_dir/'macro_predictivity_summary.csv',index=False)
    agg=tab[tab.family=='aggregate'];fac=tab[tab.family=='factor'].copy();fac['rank_abs_r']=fac.pearson_r.abs();lines=['# Macro → PA predictivity','',f"Canonical history: {meta['start']} → {meta['end']} | {meta['weekly_rows']} Friday anchors",'', '## Aggregate score','',agg.to_markdown(index=False),'','## Strongest factor associations','',fac.sort_values('rank_abs_r',ascending=False).head(30).drop(columns='rank_abs_r').to_markdown(index=False),'','Caveat: availability-lag safe, but not fully real-time-vintage safe. Research only; does not create/reverse COT direction.'];report='\n'.join(lines)+'\n';Path(z.out_dir/'macro_predictivity_report.md').write_text(report);print(report)
if __name__=='__main__':main()
