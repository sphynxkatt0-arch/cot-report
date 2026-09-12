#!/usr/bin/env python3
"""Build compact current actor positioning state for the COT Intelligence dashboard.

Current positions are recomputed from full-history normalized inputs. Legacy
threshold snapshots remain visible for audit/context but are not promotion-
eligible until replaced by a release-corrected research generation.
"""
from __future__ import annotations

import hashlib
import json
import math
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import build_cot_actor_event_research_release_corrected as actor_research
import evaluate_analog_robustness as robustness
from cftc_release_calendar import calendar_hash, release_record

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "worldclass" / "cot-current-state.json"
THRESHOLD_SNAPSHOT = ROOT / "worldclass" / "research" / "snapshots" / "2026-08-10" / "cot-actor-event-summary.json"
THRESHOLD_MANIFEST = ROOT / "worldclass" / "research" / "snapshots" / "2026-08-10" / "verification-manifest.json"
REQUIRED_RESEARCH_GENERATION = "release-corrected-v2"

def finite(value: Any) -> float | None:
    try:x=float(value)
    except (TypeError,ValueError):return None
    return x if math.isfinite(x) else None

def r4(value: Any) -> float | None:
    x=finite(value);return round(x,4) if x is not None else None

def sha256(path: Path) -> str:return hashlib.sha256(path.read_bytes()).hexdigest()
def ratio_pct(value: float | None, oi: float | None) -> float | None:return (value/oi*100.0) if value is not None and oi not in (None,0) else None

def load_threshold_snapshot() -> tuple[dict[str,dict[str,Any]],dict[str,Any]]:
    payload=json.loads(THRESHOLD_SNAPSHOT.read_text(encoding="utf-8"))
    rows={str(row.get("signal")):row for row in payload.get("validated_signal_summary") or []}
    generation=str(payload.get("research_generation") or payload.get("information_contract_version") or "legacy-pre-release-correction")
    eligible=generation==REQUIRED_RESEARCH_GENERATION
    return rows,{"research_generation":generation,"release_corrected":eligible,"promotion_eligible":eligible}

def main() -> None:
    if not THRESHOLD_SNAPSHOT.exists() or not THRESHOLD_MANIFEST.exists():raise FileNotFoundError("immutable threshold research snapshot is missing")
    threshold_rows,threshold_status=load_threshold_snapshot()
    cot_data,prices_payloads=robustness.build_full_inputs();states:dict[str,Any]={};market_meta:dict[str,Any]={}
    for dataset in actor_research.DATASETS:
        dataset_payload=cot_data.get(dataset) or {}
        for market in actor_research.SUPPORTED_MARKETS:
            payload=dataset_payload.get(market);prices_payload=prices_payloads.get(market)
            if not isinstance(payload,dict) or prices_payload is None:continue
            built=actor_research.build_market_actor_events(market,dataset,payload,prices_payload)
            if not built:continue
            rows=[row for row in (payload.get("records") or []) if isinstance(row,dict) and row.get("date")]
            by_date={str(row.get("date"))[:10]:(idx,row) for idx,row in enumerate(rows)}
            market_meta[f"{dataset}:{market}"]={"dataset":dataset,"market":market,"record_count":len(rows),"latest_report_date":str(rows[-1].get("date"))[:10] if rows else None}
            for actor,events in built.items():
                if not events:continue
                event=max(events,key=lambda e:e["report_date"]);match=by_date.get(str(event["report_date"])[:10])
                if not match:continue
                idx,row=match;prev=rows[idx-1] if idx>0 else {}
                long_now=actor_research.actor_side_value(row,actor,"long");short_now=actor_research.actor_side_value(row,actor,"short");net_now=actor_research.actor_net_value(row,actor)
                long_prev=actor_research.actor_side_value(prev,actor,"long");short_prev=actor_research.actor_side_value(prev,actor,"short");net_prev=actor_research.actor_net_value(prev,actor)
                oi=finite(row.get("open_interest"));prev_oi=finite(prev.get("open_interest"));delta_oi=(oi-prev_oi) if oi is not None and prev_oi is not None else None;delta_oi_pct=((oi/prev_oi)-1.0)*100.0 if oi is not None and prev_oi not in (None,0) else None
                direction=str(event.get("direction") or "FLAT");signal=f"{dataset}:{market}:{actor}:{direction}";frozen=threshold_rows.get(signal) or {};threshold=frozen.get("threshold");mag=finite(event.get("magnitude_percentile"))
                threshold_active=(threshold_status["promotion_eligible"] and direction in {"ADD","CUT"} and threshold is not None and mag is not None and mag>=float(threshold) and frozen.get("classification") in {"GLOBAL_FDR","FAMILY_FDR","NONOVERLAP_CONFIRMED","OOS_SUPPORTED"})
                report_date=str(event.get("report_date"));rel=release_record(report_date)
                state_key=f"{dataset}:{market}:{actor}"
                states[state_key]={
                    "series":state_key,"dataset":dataset,"market":market,"actor":actor,"actor_label":actor_research.ACTORS.get(dataset,{}).get(actor,actor),"actor_role":actor_research.ACTOR_ROLES.get(dataset,{}).get(actor,"UNCLASSIFIED"),
                    "report_date_tuesday":report_date,"release_date_friday":rel["actual_release_date"],"availability_at_utc":rel["availability_at_utc"],"availability_source_type":rel["availability_source_type"],"release_calendar_version":rel["calendar_version"],"release_calendar_hash":rel["release_calendar_hash"],"signal_date":event.get("signal_date"),
                    "direction":direction,"action_type":event.get("action_type"),"long_contracts":r4(long_now),"short_contracts":r4(short_now),"net_contracts":r4(net_now),"open_interest":r4(oi),"long_oi_pct":r4(ratio_pct(long_now,oi)),"short_oi_pct":r4(ratio_pct(short_now,oi)),"net_oi_pct":r4(event.get("net_oi_pct")),"position_percentile":r4(event.get("position_percentile")),
                    "delta_long_contracts":r4((long_now-long_prev) if long_now is not None and long_prev is not None else None),"delta_short_contracts":r4((short_now-short_prev) if short_now is not None and short_prev is not None else None),"delta_net_contracts":r4((net_now-net_prev) if net_now is not None and net_prev is not None else None),"delta_net_oi_pp":r4(event.get("delta_1w_net_oi_pp")),"change_magnitude_percentile":r4(event.get("magnitude_percentile")),"delta_open_interest":r4(delta_oi),"delta_open_interest_pct":r4(delta_oi_pct),
                    "frozen_threshold_signal":{"signal":signal,"selected_threshold":threshold,"classification":frozen.get("classification"),"promotion_status":frozen.get("promotion_status"),"holdout_n_1w":frozen.get("holdout_n_1w"),"holdout_edge_1w_pp":frozen.get("holdout_edge_1w_pct"),"research_generation":threshold_status["research_generation"],"release_corrected":threshold_status["release_corrected"],"promotion_eligible":threshold_status["promotion_eligible"],"active_now":bool(threshold_active)},
                }
    output={
        "schema_version":2,"research_generation":"release-corrected-runtime-v2","generated_at_utc":datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00","Z"),
        "information_contract":{"cot_snapshot":"CFTC as-of report date","public_availability":"canonical CFTC release calendar at 15:30 America/New_York","release_anchor":"first market close on/after canonical public availability","release_calendar_hash":calendar_hash(),"strict_release_alignment":True,"current_percentiles":"expanding full-history only; no future report","lookahead_safe":True},
        "research_threshold_snapshot":{"path":str(THRESHOLD_SNAPSHOT.relative_to(ROOT)).replace("\\","/"),"sha256":sha256(THRESHOLD_SNAPSHOT),"manifest_sha256":sha256(THRESHOLD_MANIFEST),"frozen":True,**threshold_status},
        "market_sources":market_meta,"actor_states":dict(sorted(states.items())),"production_model_changed":False,
    }
    OUT.parent.mkdir(parents=True,exist_ok=True);OUT.write_text(json.dumps(output,separators=(",",":"),sort_keys=True)+"\n",encoding="utf-8");print(f"Saved {OUT} · actor_states={len(states)} · bytes={OUT.stat().st_size:,}")
if __name__=="__main__":main()
