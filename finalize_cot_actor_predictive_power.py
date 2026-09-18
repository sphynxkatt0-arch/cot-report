#!/usr/bin/env python3
"""Finalize the frozen COT predictive-power study with overlap and multiplicity controls.

Reads the immutable 2026-08-10 predictive-power snapshot. It does not rerun or alter
that snapshot. It adds:
- non-overlapping Spearman confirmation requirements;
- approximate two-sided Fisher-z p-values on non-overlapping Spearman rho;
- Benjamini-Hochberg FDR q-values across the full 2,655 metric family;
- a stricter evidence classification suitable for reporting predictive power.
"""
from __future__ import annotations

import gzip
import json
import math
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
SNAPSHOT = ROOT / "worldclass" / "research" / "snapshots" / "2026-08-10-predictive-power" / "cot-actor-predictive-power.json.gz"
OUT = ROOT / "worldclass" / "research" / "cot-actor-predictive-power-validated-summary.json"


def finite(value: Any) -> float | None:
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def fisher_p_approx(rho: float | None, n: int) -> float | None:
    if rho is None or n <= 3 or abs(rho) >= 1:
        return None
    z = abs(math.atanh(rho)) * math.sqrt(n - 3)
    return math.erfc(z / math.sqrt(2.0))


def initial_classification(row: dict[str, Any]) -> str:
    r2 = finite(row.get("oos_r2"))
    rmse = finite(row.get("rmse_improvement_pct"))
    d = finite(row.get("discovery_spearman_rho"))
    h = finite(row.get("holdout_spearman_rho"))
    i = finite(row.get("independent_spearman_rho"))
    hn = int(row.get("holdout_n") or 0)
    inn = int(row.get("independent_n") or 0)
    positive_gain = r2 is not None and r2 > 0 and rmse is not None and rmse > 0
    overlap_confirmed = (
        positive_gain
        and hn >= 30
        and inn >= 20
        and d is not None
        and h is not None
        and i is not None
        and abs(h) >= 0.10
        and abs(i) >= 0.10
        and d * h > 0
        and h * i > 0
    )
    if overlap_confirmed:
        return "OVERLAP_CONFIRMED_OOS"
    if positive_gain:
        return "POSITIVE_OOS_GAIN_NOT_OVERLAP_CONFIRMED"
    return "NO_OOS_GAIN"


def bh_qvalues(rows: list[dict[str, Any]]) -> None:
    eligible = [(idx, float(row["independent_spearman_p_approx"])) for idx, row in enumerate(rows) if row.get("independent_spearman_p_approx") is not None]
    eligible.sort(key=lambda item: item[1])
    m = len(eligible)
    qvals = [None] * len(rows)
    running = 1.0
    for rank_from_end in range(m - 1, -1, -1):
        idx, p = eligible[rank_from_end]
        rank = rank_from_end + 1
        raw_q = min(1.0, p * m / rank)
        running = min(running, raw_q)
        qvals[idx] = running
    for idx, row in enumerate(rows):
        q = qvals[idx]
        row["fdr_q_nonoverlap_spearman"] = round(q, 8) if q is not None else None
        base = row["overlap_classification"]
        if base == "OVERLAP_CONFIRMED_OOS" and q is not None and q <= 0.05:
            row["final_classification"] = "FDR05_OOS_PREDICTIVE"
        elif base == "OVERLAP_CONFIRMED_OOS" and q is not None and q <= 0.10:
            row["final_classification"] = "FDR10_OOS_PREDICTIVE"
        elif base == "OVERLAP_CONFIRMED_OOS":
            row["final_classification"] = "OVERLAP_CONFIRMED_OOS_NOT_FDR"
        else:
            row["final_classification"] = base


def class_order(label: str) -> int:
    return {
        "FDR05_OOS_PREDICTIVE": 0,
        "FDR10_OOS_PREDICTIVE": 1,
        "OVERLAP_CONFIRMED_OOS_NOT_FDR": 2,
        "POSITIVE_OOS_GAIN_NOT_OVERLAP_CONFIRMED": 3,
        "NO_OOS_GAIN": 4,
    }.get(label, 9)


def main() -> None:
    if not SNAPSHOT.is_file():
        raise SystemExit(f"missing frozen predictive snapshot: {SNAPSHOT}")
    with gzip.open(SNAPSHOT, "rt", encoding="utf-8") as fh:
        payload = json.load(fh)

    rows: list[dict[str, Any]] = []
    for series_key, predictor_block in (payload.get("series") or {}).items():
        for predictor, horizon_block in predictor_block.items():
            for horizon, metric in horizon_block.items():
                discovery = metric.get("discovery_pre_2022") or {}
                holdout = metric.get("holdout_2022_plus") or {}
                independent = metric.get("holdout_non_overlapping") or {}
                oos = metric.get("oos_forecast") or {}
                tails = metric.get("holdout_tail_spread") or {}
                irho = finite(independent.get("spearman_rho"))
                inn = int(independent.get("n") or 0)
                p_approx = fisher_p_approx(irho, inn)
                row = {
                    "series": series_key,
                    "predictor": predictor,
                    "horizon": horizon,
                    "discovery_n": discovery.get("n"),
                    "discovery_spearman_rho": discovery.get("spearman_rho"),
                    "holdout_n": holdout.get("n"),
                    "holdout_pearson_r": holdout.get("pearson_r"),
                    "holdout_spearman_rho": holdout.get("spearman_rho"),
                    "independent_n": inn,
                    "independent_spearman_rho": independent.get("spearman_rho"),
                    "independent_spearman_p_approx": None if p_approx is None else round(p_approx, 8),
                    "oos_r2": oos.get("oos_r2"),
                    "rmse_improvement_pct": oos.get("rmse_improvement_pct"),
                    "direction_lift_pp": oos.get("direction_lift_pp"),
                    "holdout_p90_minus_p10_spread_pp": tails.get("holdout_p90_minus_p10_spread_pp"),
                }
                row["overlap_classification"] = initial_classification(row)
                rows.append(row)

    if len(rows) != 2655:
        raise SystemExit(f"expected 2655 metrics, got {len(rows)}")
    bh_qvalues(rows)
    rows.sort(key=lambda row: (
        class_order(row["final_classification"]),
        finite(row.get("fdr_q_nonoverlap_spearman")) if finite(row.get("fdr_q_nonoverlap_spearman")) is not None else 2.0,
        -(finite(row.get("oos_r2")) or -999.0),
        -abs(finite(row.get("independent_spearman_rho")) or 0.0),
    ))

    counts: dict[str, int] = {}
    for row in rows:
        counts[row["final_classification"]] = counts.get(row["final_classification"], 0) + 1

    output = {
        "schema_version": 1,
        "study": "COT actor predictive power — overlap/FDR validated",
        "source_snapshot": "2026-08-10-predictive-power",
        "source_metric_count": len(rows),
        "validation_contract": {
            "oos_gain": "pre-2022 OLS coefficients frozen and evaluated in 2022+; OOS R2 and RMSE improvement must both be positive",
            "overlap_confirmation": "discovery, holdout and non-overlapping Spearman signs must agree; |holdout rho| and |independent rho| >= 0.10; holdout N>=30 and independent N>=20",
            "multiplicity": "Benjamini-Hochberg FDR on approximate two-sided Fisher-z p-values from non-overlapping Spearman correlations across all 2,655 metrics",
            "caution": "Fisher-z p-values for Spearman are approximate and the metric family is dependent across horizons/predictors; FDR labels are evidence screens, not causal proof",
        },
        "counts": counts,
        "top_all": rows[:300],
        "top_1w": [row for row in rows if row["horizon"] == "1w"][:120],
        "top_4w": [row for row in rows if row["horizon"] == "4w"][:120],
        "top_13w": [row for row in rows if row["horizon"] == "13w"][:120],
        "top_26w": [row for row in rows if row["horizon"] == "26w"][:120],
        "all_rows": rows,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print("COT PREDICTIVE POWER FINAL VALIDATION BEGIN")
    print("counts", json.dumps(counts, sort_keys=True))
    print("TOP STRICT 1W")
    for row in output["top_1w"][:30]:
        print(
            f"{row['final_classification']:34s} {row['series']:40s} {row['predictor']:26s} "
            f"N={int(row.get('holdout_n') or 0):3d}/{int(row.get('independent_n') or 0):3d} "
            f"rho={float(row.get('holdout_spearman_rho') or 0):+7.3f}/{float(row.get('independent_spearman_rho') or 0):+7.3f} "
            f"R2={float(row.get('oos_r2') or 0):+8.4f} q={float(row.get('fdr_q_nonoverlap_spearman') or 1):.4f} "
            f"spread={float(row.get('holdout_p90_minus_p10_spread_pp') or 0):+7.3f}pp"
        )
    print("COT PREDICTIVE POWER FINAL VALIDATION END")
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
