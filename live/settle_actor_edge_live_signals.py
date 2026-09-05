#!/usr/bin/env python3
"""Settle prospective actor-edge forecasts without rewriting forecast history."""
from __future__ import annotations
import argparse
from bisect import bisect_left
from datetime import UTC,datetime
from pathlib import Path
from typing import Any
from actor_edge_ledger import EDGE_HORIZONS,TRADING_CLOSES,canonical,entry_path,finite,forecast_files,load,outcome_path,parse_day,sha_file,validate_forecast,validate_ledger,write_immutable
from settle_live_signals import load_price_sources

def first_index(prices:list[dict[str,Any]],target:str)->int|None:
    dates=[r["date"] for r in prices];i=bisect_left(dates,target);return i if i<len(prices) else None

def settle(ledger_root:Path,price_sources:dict[str,dict[str,Any]],now:datetime,metadata_out:Path|None=None)->dict[str,Any]:
    created_entries=[];created_outcomes=[];open_entries=[];open_horizons=[]
    for fp in forecast_files(ledger_root):
        f=load(fp);validate_forecast(f);sid=f["signal_id"];source=price_sources.get(str(f.get("market")))
        if not source or not source.get("records"):open_entries.append(sid);continue
        prices=source["records"];fh=sha_file(fp);ep=ledger_root/entry_path(sid)
        if ep.exists():
            entry=load(ep);idx=first_index(prices,str(entry.get("entry_date")))
            if idx is None or prices[idx]["date"]!=entry.get("entry_date"):raise RuntimeError("frozen actor-edge entry date disappeared from price source")
        else:
            idx=first_index(prices,str(f["release_target_date"]))
            if idx is None:open_entries.append(sid);continue
            entry={"schema_version":1,"signal_id":sid,"forecast_hash":fh,"market":f["market"],"release_target_date":f["release_target_date"],"entry_date":prices[idx]["date"],"entry_price":prices[idx]["price"],"price_source":source.get("price_source"),"price_source_timestamp":source.get("price_source_timestamp"),"settled_at_utc":now.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00","Z")}
            if write_immutable(ep,entry)=="created":created_entries.append(str(entry_path(sid)).replace("\\","/"))
        entry_price=finite(entry.get("entry_price"))
        if entry_price is None or entry_price<=0:raise RuntimeError("invalid frozen actor-edge entry price")
        for h in EDGE_HORIZONS:
            op=ledger_root/outcome_path(sid,h)
            if op.exists():continue
            exit_idx=idx+TRADING_CLOSES[h]
            if exit_idx>=len(prices):open_horizons.append(f"{sid}:{h}");continue
            exit_price=finite(prices[exit_idx].get("price"))
            window=[finite(r.get("price")) for r in prices[idx:exit_idx+1]]
            if exit_price is None or any(v is None for v in window):raise RuntimeError("invalid price in actor-edge settlement window")
            clean=[float(v) for v in window if v is not None];realized=(exit_price/entry_price-1)*100;mae=(min(clean)/entry_price-1)*100;mfe=(max(clean)/entry_price-1)*100;meta=f["historical_horizons"][h];pred=finite(meta.get("expected_return_pct"));prob=finite(meta.get("probability_positive"));error=realized-pred if pred is not None else None;direction=None if pred is None or abs(pred)<=1e-12 else (realized>0 if pred>0 else realized<0)
            outcome={"schema_version":1,"signal_id":sid,"forecast_hash":fh,"horizon":h,"trading_closes":TRADING_CLOSES[h],"entry_date":entry["entry_date"],"entry_price":entry_price,"exit_date":prices[exit_idx]["date"],"exit_price":exit_price,"realized_return_pct":round(realized,8),"max_adverse_excursion_pct":round(mae,8),"max_favorable_excursion_pct":round(mfe,8),"predicted_return_pct":pred,"historical_unconditional_return_pct":meta.get("historical_unconditional_return_pct"),"historical_excess_vs_baseline_pp":meta.get("historical_excess_vs_baseline_pp"),"forecast_error_pct":round(error,8) if error is not None else None,"predicted_probability_positive":prob,"direction_correct":direction,"settled_at_utc":now.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00","Z"),"price_source":source.get("price_source"),"price_source_timestamp":source.get("price_source_timestamp")}
            if write_immutable(op,outcome)=="created":created_outcomes.append(str(outcome_path(sid,h)).replace("\\","/"))
    result={"schema_version":1,"settled_at_utc":now.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00","Z"),"created_entries":sorted(created_entries),"created_outcomes":sorted(created_outcomes),"created_entry_count":len(created_entries),"created_outcome_count":len(created_outcomes),"open_entry_count":len(set(open_entries)),"open_horizon_count":len(set(open_horizons))}
    validate_ledger(ledger_root)
    if metadata_out:metadata_out.parent.mkdir(parents=True,exist_ok=True);metadata_out.write_bytes(canonical(result))
    return result

def args()->argparse.Namespace:
    p=argparse.ArgumentParser();p.add_argument("--ledger-root",type=Path,required=True);p.add_argument("--interactive",type=Path,default=Path(__file__).resolve().parents[1]/"interactive_cot_dashboard.html");p.add_argument("--metals",type=Path,default=Path(__file__).resolve().parents[1]/"worldclass"/"metals.json");p.add_argument("--metadata-out",type=Path);p.add_argument("--now-utc");return p.parse_args()
def main()->None:
    a=args();now=datetime.fromisoformat(a.now_utc.replace("Z","+00:00")).astimezone(UTC) if a.now_utc else datetime.now(UTC);sources=load_price_sources(a.interactive,a.metals);r=settle(a.ledger_root,sources,now,a.metadata_out);print(f"Actor-edge settlement · entries={r['created_entry_count']} · outcomes={r['created_outcome_count']} · open={r['open_horizon_count']}")
if __name__=="__main__":main()
