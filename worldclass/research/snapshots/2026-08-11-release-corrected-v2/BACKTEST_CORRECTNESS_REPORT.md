# COT Backtest Correctness Report

## Decision

**The previous predictive snapshots are superseded for live/forecast use.** They remain immutable audit records, but all new edge selection must use `release-corrected-v2`.

The repaired generation anchors every COT observation to canonical CFTC public availability, including the documented 2025 shutdown backlog. It also separates overlapping descriptive observations from the independent/FDR evidence used for classification.

## Release timing correction

- Old studies commonly used `report_date + 3 days` or Tuesday-to-Tuesday alignment.
- New studies resolve `actual_release_date` from `analysis/reference/cftc_release_calendar.json`, then enter on the first available market close on/after that date.
- Ordinary weeks are labeled as schedule assumptions rather than falsely claimed observed release timestamps.
- Known exceptional CFTC dates use explicit authoritative overrides.

## Evidence hierarchy

- `DISCOVERY_ONLY` — discovery signal only.
- `HOLDOUT_DIRECTION_CONFIRMED` — 2022+ holdout retained the discovery direction.
- `NONOVERLAP_CONFIRMED` — direction also survives greedy non-overlapping episodes.
- `FAMILY_FDR` — family-level BH-FDR q <= 0.10.
- `GLOBAL_FDR` — global searched-universe BH-FDR q <= 0.10.

Threshold inference uses a **circular moving-block bootstrap on the chronological holdout weekly sequence**. Non-overlap is a separate confirmation gate.

## Before / after classification counts

- Old frozen actor-event `OOS_SUPPORTED`: **0**
- New threshold inference: `{"DISCOVERY_ONLY": 8431, "FAMILY_FDR": 25, "GLOBAL_FDR": 3, "HOLDOUT_DIRECTION_CONFIRMED": 1317, "NONOVERLAP_CONFIRMED": 2614}`
- Old raw/OI classifications: `{}`
- New raw/OI classifications: `{}`

## Artifact provenance

- Threshold inference SHA256: `7c2dfb7844957597307b70656208b23582360aaf7d60e3e57899321fb6eeed18`
- Raw/OI v2 SHA256: `55523b3eb935a9f4681a45457cdfe3d78126902ac5228e2be25b952548a7cb5c`
- Actor-event v2 SHA256: `f3b3c22cf1a5a4b45fec1dac0c9449f2f3949c18ce516aae921f56b3fd0a1783`

## Quarantined legacy predictive families

- `cot_overlay_exact.py` predictive return columns
- `cot_legacy_correlations.py` predictive return columns
- `verify_findings.py` predictive findings
- `cot_weekly_position_effects.py`
- old `cot_cross_market_predictivity.py` output
- pre-v2 frozen threshold and raw/OI snapshots for live edge selection

Their files are not deleted; their status is **SUPERSEDED_RELEASE_TIMING_V1** for predictive use.

## Percentage-point semantics

`pp` means **percentage points of historical conditional return minus historical unconditional baseline return**. Example: `-1.56 pp` does **not** mean the market is forecast to fall 1.56%. It means the historical conditional sample averaged 1.56 percentage points below its matched unconditional baseline over that horizon.

## Remaining statistical governance

- Macro-conditioned regime research is labeled `CALENDAR_ALIGNED_NOT_VINTAGE_SAFE` until a point-in-time macro source is installed.
- Actor-weight grids remain **model-selection research**, not a final untouched validation set.
- Retrospective research may not automatically alter production weights.
- Prospective live settlement remains the promotion gate for production model changes.

## Snapshot policy

- Existing frozen snapshots were not rewritten.
- The v2 candidate snapshot must receive its own manifest and hashes.
- Production promotion is disabled until the corrected build + CI contract passes.

