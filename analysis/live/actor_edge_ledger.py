#!/usr/bin/env python3
"""Append-only prospective ledger primitives for COT actor-edge research."""
from __future__ import annotations

import hashlib
import json
import math
import re
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

ANALYSIS = Path(__file__).resolve().parents[1]
if str(ANALYSIS) not in sys.path:
    sys.path.insert(0, str(ANALYSIS))
from cftc_release_calendar import availability_at, release_date as canonical_release_date, release_record

SCHEMA_VERSION = 1
INFORMATION_CONTRACT_V2 = "cftc-public-availability-v2"
EDGE_HORIZONS = ("1w", "2w", "3w", "4w", "6w", "8w", "13w", "26w")
TRADING_CLOSES = {"1w":5,"2w":10,"3w":15,"4w":20,"6w":30,"8w":40,"13w":65,"26w":130}
STOCKHOLM = ZoneInfo("Europe/Stockholm")
HEX64 = re.compile(r"^[a-f0-9]{64}$")

class EdgeLedgerError(RuntimeError):
    pass

def canonical(payload:Any)->bytes:return (json.dumps(payload,sort_keys=True,separators=(",",":"),ensure_ascii=False)+"\n").encode()
def sha_bytes(data:bytes)->str:return hashlib.sha256(data).hexdigest()
def sha_file(path:Path)->str:return sha_bytes(path.read_bytes())
def finite(v:Any)->float|None:
    try:n=float(v)
    except (TypeError,ValueError):return None
    return n if math.isfinite(n) else None

def parse_day(v:Any)->date:
    try:return date.fromisoformat(str(v)[:10])
    except (TypeError,ValueError) as exc:raise EdgeLedgerError(f"invalid ISO date: {v!r}") from exc

def parse_utc(v:Any)->datetime:
    text=str(v or "").strip().replace("Z","+00:00")
    try:d=datetime.fromisoformat(text)
    except ValueError as exc:raise EdgeLedgerError(f"invalid UTC timestamp: {v!r}") from exc
    return (d if d.tzinfo else d.replace(tzinfo=UTC)).astimezone(UTC)

def iso_utc(d:datetime)->str:return d.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00","Z")

def legacy_release_vintage_utc(release:str|date)->datetime:
    d=release if isinstance(release,date) else parse_day(release)
    return datetime(d.year,d.month,d.day,21,35,tzinfo=STOCKHOLM).astimezone(UTC)

def release_vintage_utc(release:str|date)->datetime:
    """15:35 America/New_York on an already-resolved release date.

    Kept for API compatibility. New forecast creation should use
    release_vintage_for_report_utc so exceptional release dates are resolved
    from the report date first.
    """
    d=release if isinstance(release,date) else parse_day(release)
    # availability_at() accepts report dates, not release dates; derive 15:35 ET
    # directly from the release day using the timezone embedded in the calendar.
    from zoneinfo import ZoneInfo
    ny=ZoneInfo("America/New_York")
    return datetime(d.year,d.month,d.day,15,35,tzinfo=ny).astimezone(UTC)

def release_vintage_for_report_utc(report:str|date)->datetime:
    return availability_at(report)+timedelta(minutes=5)

def within_window(now:datetime,release:str|date,early_minutes:int=5,window_hours:int=4)->bool:
    v=release_vintage_utc(release);n=now.astimezone(UTC);return v-timedelta(minutes=early_minutes)<=n<=v+timedelta(hours=window_hours)

def within_report_window(now:datetime,report:str|date,early_minutes:int=5,window_hours:int=4)->bool:
    v=release_vintage_for_report_utc(report);n=now.astimezone(UTC);return v-timedelta(minutes=early_minutes)<=n<=v+timedelta(hours=window_hours)

def deterministic_id(report_date:str,market:str,dataset:str,edge_signal_key:str,research_hash:str)->str:
    return sha_bytes("|".join((report_date,market,dataset,edge_signal_key,research_hash)).encode())
def slug(v:str)->str:
    s=re.sub(r"[^A-Za-z0-9._-]+","-",str(v)).strip("-")
    if not s:raise EdgeLedgerError("empty slug")
    return s

def forecast_path(f:dict[str,Any])->Path:
    release=parse_day(f.get("release_target_date"));return Path("live")/"actor_edge"/"forecasts"/str(release.year)/release.isoformat()/f"{slug(f['market'])}-{slug(f['dataset'])}-{slug(f['edge_signal_key'])}.json"
def entry_path(signal_id:str)->Path:
    if not HEX64.fullmatch(signal_id):raise EdgeLedgerError("invalid signal id")
    return Path("live")/"actor_edge"/"entries"/f"{signal_id}.json"
def outcome_path(signal_id:str,horizon:str)->Path:
    if not HEX64.fullmatch(signal_id) or horizon not in EDGE_HORIZONS:raise EdgeLedgerError("invalid outcome identity")
    return Path("live")/"actor_edge"/"outcomes"/signal_id/f"{horizon}.json"
def manifest_dir(root:Path)->Path:return root/"live"/"actor_edge"/"manifests"
def forecast_files(root:Path)->list[Path]:
    d=root/"live"/"actor_edge"/"forecasts";return sorted(d.rglob("*.json")) if d.exists() else []
def entry_files(root:Path)->list[Path]:
    d=root/"live"/"actor_edge"/"entries";return sorted(d.glob("*.json")) if d.exists() else []
def outcome_files(root:Path)->list[Path]:
    d=root/"live"/"actor_edge"/"outcomes";return sorted(d.glob("*/*.json")) if d.exists() else []
def manifest_files(root:Path)->list[Path]:
    d=manifest_dir(root);return sorted(d.glob("*.json")) if d.exists() else []
def load(path:Path)->dict[str,Any]:
    try:p=json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:raise EdgeLedgerError(f"invalid JSON: {path}") from exc
    if not isinstance(p,dict):raise EdgeLedgerError(f"JSON root not object: {path}")
    return p

def write_immutable(path:Path,payload:dict[str,Any])->str:
    data=canonical(payload)
    if path.exists():
        if path.read_bytes()!=data:raise EdgeLedgerError(f"immutable collision: {path}")
        return "unchanged"
    path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_suffix(path.suffix+".tmp");tmp.write_bytes(data);tmp.replace(path);return "created"

def validate_forecast(f:dict[str,Any])->None:
    if f.get("schema_version")!=SCHEMA_VERSION:raise EdgeLedgerError("forecast schema mismatch")
    report=parse_day(f.get("report_date"));release=parse_day(f.get("release_target_date"))
    is_v2=f.get("information_contract_version")==INFORMATION_CONTRACT_V2
    if is_v2:
        expected_release=canonical_release_date(report)
        if release!=expected_release:raise EdgeLedgerError(f"release must match canonical CFTC availability date {expected_release}")
        expected_created=iso_utc(release_vintage_for_report_utc(report))
        if f.get("created_at_utc")!=expected_created:raise EdgeLedgerError("created_at must be canonical release +5 minutes")
        rec=release_record(report)
        if f.get("release_calendar_hash")!=rec["release_calendar_hash"]:raise EdgeLedgerError("release calendar hash mismatch")
    else:
        # Preserve validation for immutable pre-migration forecasts.
        if release!=report+timedelta(days=3):raise EdgeLedgerError("legacy release must equal Tuesday report +3 days")
        if f.get("created_at_utc")!=iso_utc(legacy_release_vintage_utc(release)):raise EdgeLedgerError("legacy created_at must be deterministic 21:35 Stockholm vintage")
    key=str(f.get("edge_signal_key") or "");rh=str(f.get("research_snapshot_hash") or "")
    if not key or not HEX64.fullmatch(rh):raise EdgeLedgerError("edge identity/research hash invalid")
    expected=deterministic_id(report.isoformat(),str(f.get("market") or ""),str(f.get("dataset") or ""),key,rh)
    if f.get("signal_id")!=expected:raise EdgeLedgerError("edge signal id not deterministic")
    if f.get("actor_role") not in {"PRIMARY_DIRECTIONAL","SECONDARY_DIRECTIONAL","INTERMEDIARY_CONTEXT","HEDGER_CONTEXT","OPPOSITE_SIDE_CONTEXT","AGGREGATE_CONTEXT"}:raise EdgeLedgerError("actor role invalid")
    if f.get("direction") not in {"ADD","CUT"}:raise EdgeLedgerError("edge direction invalid")
    horizons=f.get("historical_horizons")
    if not isinstance(horizons,dict) or set(horizons)!=set(EDGE_HORIZONS):raise EdgeLedgerError("edge horizons incomplete")
    for h in EDGE_HORIZONS:
        m=horizons[h]
        if int(m.get("trading_closes") or 0)!=TRADING_CLOSES[h]:raise EdgeLedgerError(f"{h} close definition mismatch")
        p=finite(m.get("probability_positive"))
        if p is not None and not 0<=p<=1:raise EdgeLedgerError(f"{h} probability invalid")
        for k in ("expected_return_pct","median_return_pct","historical_unconditional_return_pct","historical_excess_vs_baseline_pp","historical_average_drawdown_pct","historical_worst_drawdown_pct"):
            if m.get(k) is not None and finite(m.get(k)) is None:raise EdgeLedgerError(f"{h} {k} non-finite")
    for k in ("input_manifest_hash","policy_hash"):
        if not HEX64.fullmatch(str(f.get(k) or "")):raise EdgeLedgerError(f"{k} invalid")
    if "entry_price" in f or "exit_price" in f:raise EdgeLedgerError("forecast contains realized price")

def validate_manifest_chain(root:Path,allowed_uncovered:set[str]|None=None)->dict[str,Any]:
    prev="GENESIS";covered={};signals=set()
    for path in manifest_files(root):
        m=load(path)
        if m.get("schema_version")!=1 or m.get("previous_manifest_hash")!=prev:raise EdgeLedgerError(f"broken manifest chain: {path}")
        sid=str(m.get("signal_id") or "");rel=str(m.get("forecast_path") or "")
        if not HEX64.fullmatch(sid) or sid in signals:raise EdgeLedgerError("invalid/duplicate manifest signal")
        fp=root/rel
        if not rel.startswith("live/actor_edge/forecasts/") or not fp.exists():raise EdgeLedgerError("manifest forecast path invalid")
        if rel in covered or sha_file(fp)!=m.get("forecast_hash"):raise EdgeLedgerError("manifest forecast hash mismatch")
        f=load(fp);validate_forecast(f)
        if f.get("signal_id")!=sid:raise EdgeLedgerError("manifest signal mismatch")
        signals.add(sid);covered[rel]=sid;prev=sha_file(path)
    paths={str(p.relative_to(root)).replace("\\","/") for p in forecast_files(root)};allowed=set(allowed_uncovered or set());uncovered=paths-set(covered)
    if uncovered-allowed:raise EdgeLedgerError(f"uncovered actor-edge forecasts: {sorted(uncovered-allowed)[:3]}")
    return {"integrity":"TRANSITION" if uncovered else "PASS","forecast_count":len(paths),"manifest_count":len(covered),"latest_manifest_hash":prev,"transition_uncovered_count":len(uncovered)}
def validate_entry(e:dict[str,Any],f:dict[str,Any],fh:str)->None:
    if e.get("schema_version")!=1 or e.get("signal_id")!=f.get("signal_id") or e.get("forecast_hash")!=fh:raise EdgeLedgerError("entry identity mismatch")
    if parse_day(e.get("entry_date"))<parse_day(f.get("release_target_date")):raise EdgeLedgerError("entry predates release")
    if finite(e.get("entry_price")) is None or float(e["entry_price"])<=0:raise EdgeLedgerError("entry price invalid")
def validate_outcome(o:dict[str,Any],f:dict[str,Any],fh:str,e:dict[str,Any])->None:
    h=str(o.get("horizon") or "")
    if o.get("schema_version")!=1 or h not in EDGE_HORIZONS or o.get("signal_id")!=f.get("signal_id") or o.get("forecast_hash")!=fh:raise EdgeLedgerError("outcome identity invalid")
    if int(o.get("trading_closes") or 0)!=TRADING_CLOSES[h]:raise EdgeLedgerError("outcome closes mismatch")
    ep=finite(o.get("entry_price"));xp=finite(o.get("exit_price"));rr=finite(o.get("realized_return_pct"))
    if ep is None or ep<=0 or xp is None or xp<=0 or rr is None:raise EdgeLedgerError("outcome price invalid")
    if abs(rr-((xp/ep-1)*100))>1e-5:raise EdgeLedgerError("outcome return arithmetic mismatch")
    if o.get("entry_date")!=e.get("entry_date"):raise EdgeLedgerError("outcome entry mismatch")
def validate_ledger(root:Path)->dict[str,Any]:
    state=validate_manifest_chain(root);forecasts={}
    for p in forecast_files(root):f=load(p);validate_forecast(f);forecasts[f["signal_id"]]=(f,sha_file(p))
    entries={}
    for p in entry_files(root):
        e=load(p);sid=str(e.get("signal_id") or "")
        if sid not in forecasts:raise EdgeLedgerError("orphan entry")
        validate_entry(e,*forecasts[sid]);entries[sid]=e
    count=0
    for p in outcome_files(root):
        o=load(p);sid=str(o.get("signal_id") or "")
        if sid not in forecasts or sid not in entries:raise EdgeLedgerError("orphan outcome")
        validate_outcome(o,*forecasts[sid],entries[sid]);count+=1
    state.update({"entry_count":len(entries),"outcome_count":count,"open_entry_count":max(0,len(forecasts)-len(entries)),"integrity":"PASS"});return state
