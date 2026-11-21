#!/usr/bin/env python3
"""Generate the human-readable audit for the release-corrected research generation."""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from cftc_release_calendar import calendar_hash

ROOT=Path(__file__).resolve().parent
RESEARCH=ROOT/"worldclass"/"research"
OUT=RESEARCH/"BACKTEST_CORRECTNESS_REPORT.md"
OLD_ACTOR=RESEARCH/"snapshots"/"2026-08-10"/"cot-actor-event-summary.json"
OLD_RAW_CANDIDATES=(
    RESEARCH/"snapshots"/"2026-08-11-position-oi-all-actors"/"cot-raw-position-oi-predictive-power-summary.json",
    RESEARCH/"snapshots"/"2026-08-11-position-oi"/"cot-raw-position-oi-predictive-power-summary.json",
)
NEW_THRESHOLD=RESEARCH/"cot-threshold-inference-v2-summary.json"
NEW_RAW=RESEARCH/"cot-raw-position-oi-predictive-power-summary.json"
NEW_ACTOR=RESEARCH/"cot-actor-event-summary.json"


def load(path:Path)->dict[str,Any]|None:
    try:p=json.loads(path.read_text(encoding="utf-8"))
    except (OSError,json.JSONDecodeError):return None
    return p if isinstance(p,dict) else None

def sha(path:Path)->str|None:return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None

def classification_counts(payload:dict[str,Any]|None)->dict[str,int]:
    if not payload:return {}
    direct=payload.get("classification_counts")
    if isinstance(direct,dict):return {str(k):int(v) for k,v in direct.items()}
    for key in ("validated_signal_summary","metrics","strongest","top_results"):
        rows=payload.get(key)
        if isinstance(rows,list):return dict(Counter(str(r.get("classification") or r.get("evidence_status") or "UNKNOWN") for r in rows if isinstance(r,dict)))
    return {}

def first_existing(paths)->Path|None:
    return next((p for p in paths if p.exists()),None)

def markdown_table(counts:dict[str,int])->str:
    if not counts:return "_No comparable classification counts found._"
    lines=["| Classification | Count |","|---|---:|"]
    for k,v in sorted(counts.items(),key=lambda kv:(-kv[1],kv[0])):lines.append(f"| `{k}` | {v} |")
    return "\n".join(lines)

def main()->None:
    old_actor=load(OLD_ACTOR);new_actor=load(NEW_ACTOR);new_threshold=load(NEW_THRESHOLD);old_raw_path=first_existing(OLD_RAW_CANDIDATES);old_raw=load(old_raw_path) if old_raw_path else None;new_raw=load(NEW_RAW)
    old_actor_counts=classification_counts(old_actor);new_threshold_counts=classification_counts(new_threshold);old_raw_counts=classification_counts(old_raw);new_raw_counts=classification_counts(new_raw)
    lines=[
        "# COT Backtest Correctness Report — Release-Corrected v2","",
        "## Decision","",
        "The previous frozen snapshots remain immutable and auditable, but are **superseded for predictive use** where they relied on the blanket Tuesday + 3 calendar-day release assumption. The v2 generation uses the canonical CFTC availability calendar. Production promotion remains disabled until the corrected artifacts pass timing, dependence/FDR, and prospective governance gates.","",
        "## Provenance","",
        f"- Research generation: `release-corrected-v2`",f"- Information contract: `cftc-public-availability-v2`",f"- Release-calendar SHA-256: `{calendar_hash()}`",f"- Old actor snapshot: `{OLD_ACTOR.relative_to(ROOT)}` ({sha(OLD_ACTOR) or 'missing'})",f"- Old raw/OI snapshot: `{old_raw_path.relative_to(ROOT) if old_raw_path else 'not found'}` ({sha(old_raw_path) if old_raw_path else 'missing'})",f"- New threshold summary: `{NEW_THRESHOLD.relative_to(ROOT)}` ({sha(NEW_THRESHOLD) or 'missing'})",f"- New raw/OI summary: `{NEW_RAW.relative_to(ROOT)}` ({sha(NEW_RAW) or 'missing'})","",
        "## What changed","",
        "1. Historical signal availability is resolved from the canonical CFTC release calendar, including documented exceptional delays.",
        "2. Exact Monday–Friday returns are defined from the actual publication week rather than blindly from the original Tuesday report week.",
        "3. Threshold-event evidence is reclassified through independent non-overlapping episodes plus family/global BH-FDR.",
        "4. Raw position/OI research keeps its discovery/holdout, OOS and non-overlap/FDR architecture but receives corrected event timing.",
        "5. Financial and metals weight studies are explicitly model-selection research, not pristine final validation.",
        "6. Macro-conditioned results are calendar-aligned but marked not vintage-safe unless true point-in-time macro vintages are available.","",
        "## Legacy actor threshold classifications","",markdown_table(old_actor_counts),"",
        "## Release-corrected threshold inference classifications","",markdown_table(new_threshold_counts),"",
        "## Legacy raw position/OI classifications","",markdown_table(old_raw_counts),"",
        "## Release-corrected raw position/OI classifications","",markdown_table(new_raw_counts),"",
        "## Interpretation rules","",
        "- `GLOBAL_FDR`: strongest retrospective statistical classification in the searched universe; still not automatic production promotion.",
        "- `FAMILY_FDR`: survives multiplicity within its defined actor family.",
        "- `NONOVERLAP_CONFIRMED`: holdout direction survives an independent-episode view but not necessarily multiplicity correction.",
        "- `HOLDOUT_DIRECTION_CONFIRMED`: chronological holdout directional replication only.",
        "- `DISCOVERY_ONLY`: hypothesis generation only.",
        "- Existing historical `OOS_SUPPORTED` labels from the superseded threshold snapshot do not by themselves qualify as validated predictive edges.","",
        "## Production gate","",
        "No retrospective result in this report may automatically change production weights. Promotion additionally requires actor-role eligibility, immutable live forecast issuance after public availability, settlement of prospective outcomes, and the repository promotion policy.","",
    ]
    if not new_threshold or not new_raw:
        lines.extend(["## Incomplete rebuild warning","","One or more v2 generated summaries are missing. This report is therefore a migration/audit scaffold rather than a final numerical before/after certification. Run the `COT release-corrected research v2` workflow and regenerate this report before promotion.",""])
    OUT.write_text("\n".join(lines),encoding="utf-8")
    print(f"Saved {OUT}")
if __name__=="__main__":main()
