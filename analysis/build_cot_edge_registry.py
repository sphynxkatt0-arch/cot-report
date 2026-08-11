#!/usr/bin/env python3
"""Build browser-safe COT predictive evidence from immutable research snapshots.

The always-loaded registry is intentionally small. Full 885-cell horizon evidence,
percentile curves and OI interactions live in per-market lazy detail payloads.
No statistic is recomputed or re-selected here.
"""
from __future__ import annotations

import gzip
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
WORLDCLASS = ROOT / "worldclass"
SNAPSHOT = WORLDCLASS / "research" / "snapshots" / "2026-08-11-position-oi-all-actors"
AUDIT = SNAPSHOT / "all-actor-horizon-audit.json"
MANIFEST = SNAPSHOT / "verification-manifest.json"
THRESHOLD_SUMMARY = WORLDCLASS / "research" / "snapshots" / "2026-08-10" / "cot-actor-event-summary.json"
THRESHOLD_FULL_GZ = WORLDCLASS / "research" / "snapshots" / "2026-08-10" / "cot-actor-event-research.json.gz"
RAW_FULL_GZ = WORLDCLASS / "research" / "snapshots" / "2026-08-11-position-oi" / "cot-raw-position-oi-predictive-power.json.gz"
OUT = WORLDCLASS / "cot-edge-registry.json"
DETAIL_DIR = WORLDCLASS / "cot-edge-details"

HORIZONS = ("monday","tuesday","wednesday","thursday","friday","1w","2w","3w","4w","6w","8w","13w","26w","39w","52w")
MARKETS = ("sp500","nq","vix","rty","dow","gold","silver")

def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def metric(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if not row:
        return None
    keep = (
        "predictor","predictor_family","scale_sensitive","final_classification",
        "holdout_n","holdout_spearman_rho","independent_n","independent_spearman_rho",
        "oos_r2","rmse_improvement_pct","direction_lift_pp",
        "holdout_p90_minus_p10_spread_pp","global_fdr_q","family_fdr_q",
    )
    return {key: row.get(key) for key in keep if key in row}

def evidence_label(classification: Any, independent_n: int | None) -> str:
    cls = str(classification or "NO_OOS_GAIN")
    n = int(independent_n or 0)
    if n < 15:
        return "INSUFFICIENT_N"
    if cls.startswith("GLOBAL_FDR"):
        return "GLOBAL_FDR"
    if cls.startswith("FAMILY_FDR"):
        return "FAMILY_FDR"
    if cls == "OVERLAP_CONFIRMED_NOT_FDR":
        return "OOS_PLUS_OVERLAP"
    if cls == "POSITIVE_OOS_GAIN_NOT_OVERLAP_CONFIRMED":
        return "OOS_ONLY"
    return "NO_OOS_GAIN"

def sample_grade(n: int | None) -> str:
    value = int(n or 0)
    if value >= 60: return "FULL"
    if value >= 30: return "SAMPLE_WARNING"
    if value >= 15: return "RESEARCH_ONLY"
    return "INSUFFICIENT"

def enrich_metric(row: dict[str, Any] | None) -> dict[str, Any] | None:
    item = metric(row)
    if item is None:
        return None
    item["evidence_status"] = evidence_label(item.get("final_classification"), item.get("independent_n"))
    item["sample_grade"] = sample_grade(item.get("independent_n"))
    return item

def compact_threshold_metric(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if not row or int(row.get("n") or 0) <= 0:
        return None
    return {k: row.get(k) for k in (
        "n","mean_pct","median_pct","positive_rate_pct","q25_pct","q75_pct",
        "unconditional_mean_pct","edge_vs_unconditional_pct","avg_drawdown_pct","worst_drawdown_pct"
    ) if k in row}

def compact_threshold_curve(curve: dict[str, Any]) -> dict[str, Any]:
    holdout = curve.get("holdout_2022_plus") or {}
    return {
        "actor_role": curve.get("actor_role"),
        "promotion_status": curve.get("promotion_status"),
        "threshold": curve.get("threshold"),
        "holdout_2022_plus": {h: m for h in HORIZONS if (m := compact_threshold_metric(holdout.get(h))) is not None},
    }

def main() -> None:
    for path in (AUDIT, MANIFEST, THRESHOLD_SUMMARY, THRESHOLD_FULL_GZ, RAW_FULL_GZ):
        if not path.exists(): raise FileNotFoundError(path)
    audit = json.loads(AUDIT.read_text(encoding="utf-8"))
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    threshold = json.loads(THRESHOLD_SUMMARY.read_text(encoding="utf-8"))
    with gzip.open(THRESHOLD_FULL_GZ, "rt", encoding="utf-8") as fh: threshold_full = json.load(fh)
    with gzip.open(RAW_FULL_GZ, "rt", encoding="utf-8") as fh: raw_full = json.load(fh)
    if int(audit.get("actor_horizon_cell_count") or 0) != 885: raise RuntimeError("frozen actor-horizon audit contract changed")
    if int(audit.get("market_oi_horizon_cell_count") or 0) != 105: raise RuntimeError("frozen market-OI audit contract changed")

    persistence_by_series = {str(row.get("series")): row for row in audit.get("actor_persistence_1w_to_13w") or []}
    actor_meta: dict[str, Any] = {}
    details_by_market: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for cell in audit.get("actor_horizon_matrix") or []:
        series = str(cell.get("series")); market = str(cell.get("market")); actor = str(cell.get("actor")); dataset = str(cell.get("dataset")); horizon = str(cell.get("horizon")); role = str(cell.get("actor_role"))
        best = enrich_metric(cell.get("best_overall"))
        if best is None: continue
        actor_meta.setdefault(series, {"series":series,"dataset":dataset,"market":market,"actor":actor,"actor_role":role,"persistence_1w_to_13w":persistence_by_series.get(series)})
        details_by_market[market].append({
            "series":series,"dataset":dataset,"market":market,"actor":actor,"actor_role":role,"horizon":horizon,
            "best_overall":best,
            "best_raw_flow":enrich_metric(cell.get("best_raw_flow")),
            "best_raw_position_level":enrich_metric(cell.get("best_raw_position_level")),
            "best_oi_normalized_flow":enrich_metric(cell.get("best_oi_normalized_flow")),
            "best_oi_normalized_position":enrich_metric(cell.get("best_oi_normalized_position")),
            "best_incremental_oi_model":cell.get("best_incremental_oi_model"),
        })

    oi_by_market: dict[str, dict[str, Any]] = defaultdict(dict)
    for cell in audit.get("market_oi_horizon_matrix") or []:
        market = str(cell.get("market")); horizon = str(cell.get("horizon")); row = enrich_metric(cell.get("best_oi_only"))
        if row: oi_by_market[market][horizon] = row

    threshold_signals = {signal: compact_threshold_curve(curve) for signal, curve in (threshold.get("selected_signal_curves") or {}).items()}

    threshold_profiles_by_market: dict[str, dict[str, Any]] = defaultdict(dict)
    for series, actor_study in (threshold_full.get("individual_actor_thresholds") or {}).items():
        parts = str(series).split(":")
        if len(parts) < 3: continue
        market = parts[1]; profile = {}
        for direction in ("ADD", "CUT"):
            block = (actor_study or {}).get(direction) or {}
            profile[direction] = {
                "selected_threshold": block.get("selected_threshold"),
                "holdout_validation": block.get("holdout_validation"),
                "flow_percentile_bands": {
                    "P0_P50": (block.get("dose_response_full_history") or {}).get("SMALL"),
                    "P50_P75": (block.get("dose_response_full_history") or {}).get("MEDIUM"),
                    "P75_P90": (block.get("dose_response_full_history") or {}).get("LARGE"),
                    "P90_P100": (block.get("dose_response_full_history") or {}).get("EXTREME"),
                },
                "position_percentile_bands_at_selected_flow": {
                    "P0_P10": (block.get("position_level_interaction") or {}).get("EXTREME_SHORT"),
                    "P10_P25": (block.get("position_level_interaction") or {}).get("SHORT"),
                    "P25_P75": (block.get("position_level_interaction") or {}).get("NEUTRAL"),
                    "P75_P90": (block.get("position_level_interaction") or {}).get("LONG"),
                    "P90_P100": (block.get("position_level_interaction") or {}).get("EXTREME_LONG"),
                },
            }
        threshold_profiles_by_market[market][series] = profile

    oi_interactions_by_market: dict[str, dict[str, Any]] = defaultdict(dict)
    for series, actor_block in (raw_full.get("actor_series") or {}).items():
        parts = str(series).split(":")
        if len(parts) >= 3: oi_interactions_by_market[parts[1]][series] = (actor_block or {}).get("actor_flow_x_oi_direction") or {}

    source_counts = manifest.get("source_strict_counts") or {}
    registry = {
        "schema_version":1,
        "source_snapshot":{"snapshot_id":manifest.get("snapshot_id"),"audit_sha256":sha256(AUDIT),"manifest_sha256":sha256(MANIFEST),"threshold_summary_sha256":sha256(THRESHOLD_SUMMARY),"immutable":True},
        "information_contract":audit.get("information_contract"),"forecast_contract":audit.get("forecast_contract"),"horizons":list(HORIZONS),
        "evidence_status_definitions":{"GLOBAL_FDR":"OOS gain + independent confirmation + global multiple-testing survival.","FAMILY_FDR":"OOS gain + independent confirmation + prespecified predictor-family FDR survival.","OOS_PLUS_OVERLAP":"Positive OOS gain with direction retained in non-overlapping episodes; not FDR significant.","OOS_ONLY":"Positive OOS gain without independent-overlap confirmation.","NO_OOS_GAIN":"No positive out-of-sample forecast improvement.","INSUFFICIENT_N":"Independent sample below 15; descriptive/research only."},
        "sample_grade_definitions":{"FULL":"independent N >= 60","SAMPLE_WARNING":"independent N 30-59","RESEARCH_ONLY":"independent N 15-29","INSUFFICIENT":"independent N < 15"},
        "research_counts":{"continuous_metrics":audit.get("source_continuous_metric_count"),"strict_counts":source_counts,"actor_series":audit.get("actor_series_count"),"actor_horizon_cells":audit.get("actor_horizon_cell_count"),"market_oi_horizon_cells":audit.get("market_oi_horizon_cell_count")},
        "actors":dict(sorted(actor_meta.items())),
        "threshold_signals":threshold_signals,
        "detail_path_template":"worldclass/cot-edge-details/{market}.json",
        "production_model_changed":False,"automatic_promotion_allowed":False,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(registry,separators=(",",":"),sort_keys=True)+"\n",encoding="utf-8")

    DETAIL_DIR.mkdir(parents=True, exist_ok=True)
    registry_hash = sha256(OUT)
    for market in MARKETS:
        detail_payload={
            "schema_version":1,"market":market,"source_registry_sha256":registry_hash,
            "actors":sorted(details_by_market.get(market,[]),key=lambda row:(row["series"],HORIZONS.index(row["horizon"]))),
            "market_oi":oi_by_market.get(market,{}),
            "threshold_signals":{key:value for key,value in threshold_signals.items() if f":{market}:" in f":{key}:"},
            "threshold_percentile_profiles":threshold_profiles_by_market.get(market,{}),
            "actor_flow_x_oi_direction":oi_interactions_by_market.get(market,{}),
        }
        (DETAIL_DIR/f"{market}.json").write_text(json.dumps(detail_payload,separators=(",",":"),sort_keys=True)+"\n",encoding="utf-8")

    print(f"Saved {OUT} · actors={len(actor_meta)} · bytes={OUT.stat().st_size:,}")
    for market in MARKETS:
        path=DETAIL_DIR/f"{market}.json"; print(f"  {market}: {path.stat().st_size:,} bytes")

if __name__ == "__main__": main()
