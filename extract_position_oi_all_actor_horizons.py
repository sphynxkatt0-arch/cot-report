#!/usr/bin/env python3
"""Extract the complete actor x horizon audit from the frozen raw-position/OI study.

Presentation/audit only: no model fitting, retuning, or statistic recomputation.
The source study already contains the governed pre-2022 discovery / 2022+ holdout
statistics. This extractor makes all 59 actor series x 15 horizons inspectable with
identical ranking rules, plus 7 market-OI series x 15 horizons.
"""
from __future__ import annotations

import json
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "worldclass" / "research" / "cot-raw-position-oi-predictive-power.json"
OUT_DIR = ROOT / "worldclass" / "research" / "snapshots" / "2026-08-11-position-oi-all-actors"
OUT = OUT_DIR / "all-actor-horizon-audit.json"
TSV = OUT_DIR / "all-actor-horizon-matrix.tsv"

HORIZONS = ("monday", "tuesday", "wednesday", "thursday", "friday", "1w", "2w", "3w", "4w", "6w", "8w", "13w", "26w", "39w", "52w")
SHORT_MEDIUM = ("1w", "2w", "3w", "4w", "6w", "8w", "13w")

ROLE_MAP = {
    "tff": {
        "dealer": "INTERMEDIARY_CONTEXT",
        "asset_mgr": "PRIMARY_DIRECTIONAL",
        "lev_money": "PRIMARY_DIRECTIONAL",
        "other_reportable": "SECONDARY_DIRECTIONAL",
        "non_reportable": "SECONDARY_DIRECTIONAL",
    },
    "legacy": {
        "noncommercial": "PRIMARY_DIRECTIONAL",
        "commercial": "OPPOSITE_SIDE_CONTEXT",
        "total_reportable": "AGGREGATE_CONTEXT",
        "nonreportable": "SECONDARY_DIRECTIONAL",
    },
    "disaggregated": {
        "producer_merchant": "HEDGER_CONTEXT",
        "swap_dealer": "INTERMEDIARY_CONTEXT",
        "managed_money": "PRIMARY_DIRECTIONAL",
        "other_reportable": "SECONDARY_DIRECTIONAL",
        "non_reportable": "SECONDARY_DIRECTIONAL",
    },
}

FAMILY_GROUPS = {
    "raw_flow": {"raw_position_flow", "raw_position_flow_normalized"},
    "raw_position_level": {"raw_position_level", "raw_position_level_normalized"},
    "oi_normalized_flow": {"oi_normalized_flow"},
    "oi_normalized_position": {"oi_normalized_position"},
}

CLASS_RANK = {
    "GLOBAL_FDR05_OOS": 0,
    "GLOBAL_FDR10_OOS": 1,
    "FAMILY_FDR05_OOS": 2,
    "FAMILY_FDR10_OOS": 3,
    "OVERLAP_CONFIRMED_NOT_FDR": 4,
    "POSITIVE_OOS_GAIN_NOT_OVERLAP_CONFIRMED": 5,
    "NO_OOS_GAIN": 6,
}


def finite(value: Any) -> float | None:
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    if x != x or abs(x) == float("inf"):
        return None
    return x


def role_for(series: str) -> str:
    parts = series.split(":")
    if len(parts) < 3:
        return "UNKNOWN"
    return ROLE_MAP.get(parts[0], {}).get(parts[-1], "UNKNOWN")


def rank_key(row: dict[str, Any]) -> tuple[Any, ...]:
    cls = str(row.get("final_classification"))
    r2 = finite(row.get("oos_r2"))
    rho = finite(row.get("independent_spearman_rho"))
    q = finite(row.get("global_fdr_q"))
    n = int(row.get("independent_n") or 0)
    return (
        CLASS_RANK.get(cls, 9),
        q if q is not None else 2.0,
        -(r2 if r2 is not None else -999.0),
        -abs(rho or 0.0),
        -n,
        str(row.get("predictor")),
    )


def compact(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if not row:
        return None
    keys = (
        "series", "scope", "predictor", "predictor_family", "scale_sensitive", "horizon",
        "final_classification", "overlap_classification", "discovery_n", "holdout_n",
        "holdout_pearson_r", "holdout_spearman_rho", "independent_n",
        "independent_spearman_rho", "independent_spearman_p_approx", "oos_r2",
        "rmse_improvement_pct", "direction_lift_pp", "holdout_p90_minus_p10_spread_pp",
        "global_fdr_q", "family_fdr_q",
    )
    return {k: row.get(k) for k in keys}


def best(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    return compact(min(rows, key=rank_key)) if rows else None


def confirmed(row: dict[str, Any] | None) -> bool:
    if not row:
        return False
    cls = str(row.get("final_classification"))
    return cls.startswith("GLOBAL_FDR") or cls.startswith("FAMILY_FDR") or cls == "OVERLAP_CONFIRMED_NOT_FDR"


def fdr_survivor(row: dict[str, Any] | None) -> bool:
    if not row:
        return False
    cls = str(row.get("final_classification"))
    return cls.startswith("GLOBAL_FDR") or cls.startswith("FAMILY_FDR")


def incremental_best(actor_block: dict[str, Any], horizon: str) -> dict[str, Any] | None:
    rows = []
    for model, hblock in (actor_block.get("oi_incremental_models") or {}).items():
        metric = (hblock or {}).get(horizon) or {}
        gain = finite(metric.get("oos_r2_gain"))
        if gain is None:
            continue
        rows.append({
            "model": model,
            "horizon": horizon,
            "holdout_n": metric.get("holdout_n"),
            "base_predictor": metric.get("base_predictor"),
            "base_oos_r2": metric.get("base_oos_r2"),
            "augmented_oos_r2": metric.get("augmented_oos_r2"),
            "oos_r2_gain": metric.get("oos_r2_gain"),
            "incremental_r2_vs_base_model": metric.get("incremental_r2_vs_base_model"),
            "rmse_improvement_vs_base_pct": metric.get("rmse_improvement_vs_base_pct"),
            "note": "Exploratory pre-specified two-feature OOS comparison; no dedicated non-overlap/FDR promotion gate.",
        })
    if not rows:
        return None
    rows.sort(key=lambda r: (-(finite(r.get("oos_r2_gain")) or -999.0), -(finite(r.get("augmented_oos_r2")) or -999.0)))
    return rows[0]


def main() -> None:
    payload = json.loads(SOURCE.read_text(encoding="utf-8"))
    ranking = payload.get("strict_ranking") or []
    actor_rows = [r for r in ranking if r.get("scope") == "actor"]
    oi_rows = [r for r in ranking if r.get("scope") == "market_oi"]

    actor_keys = sorted((payload.get("actor_series") or {}).keys())
    assert len(actor_keys) == 59, len(actor_keys)
    assert tuple(payload.get("horizons") or HORIZONS) == HORIZONS

    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in actor_rows:
        grouped[(str(row.get("series")), str(row.get("horizon")))].append(row)

    matrix = []
    for series in actor_keys:
        actor_block = (payload.get("actor_series") or {}).get(series) or {}
        for horizon in HORIZONS:
            rows = grouped.get((series, horizon), [])
            assert len(rows) == 14, (series, horizon, len(rows))
            cell = {
                "series": series,
                "dataset": series.split(":")[0],
                "market": series.split(":")[1],
                "actor": series.split(":")[-1],
                "actor_role": role_for(series),
                "horizon": horizon,
                "best_overall": best(rows),
                "best_raw_flow": best([r for r in rows if r.get("predictor_family") in FAMILY_GROUPS["raw_flow"]]),
                "best_raw_position_level": best([r for r in rows if r.get("predictor_family") in FAMILY_GROUPS["raw_position_level"]]),
                "best_oi_normalized_flow": best([r for r in rows if r.get("predictor_family") in FAMILY_GROUPS["oi_normalized_flow"]]),
                "best_oi_normalized_position": best([r for r in rows if r.get("predictor_family") in FAMILY_GROUPS["oi_normalized_position"]]),
                "best_incremental_oi_model": incremental_best(actor_block, horizon),
            }
            matrix.append(cell)
    assert len(matrix) == 59 * 15, len(matrix)

    oi_grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in oi_rows:
        oi_grouped[(str(row.get("series")), str(row.get("horizon")))].append(row)
    oi_keys = sorted({str(r.get("series")) for r in oi_rows})
    assert len(oi_keys) == 7, oi_keys
    oi_matrix = []
    for series in oi_keys:
        for horizon in HORIZONS:
            rows = oi_grouped.get((series, horizon), [])
            assert len(rows) == 5, (series, horizon, len(rows))
            oi_matrix.append({"series": series, "market": series.split(":")[-1], "horizon": horizon, "best_oi_only": best(rows)})
    assert len(oi_matrix) == 7 * 15

    horizon_leaders = {}
    for horizon in HORIZONS:
        cells = [c for c in matrix if c["horizon"] == horizon]
        primary = [c for c in cells if c["actor_role"] == "PRIMARY_DIRECTIONAL"]
        all_ranked = sorted(cells, key=lambda c: rank_key(c["best_overall"] or {}))
        primary_ranked = sorted(primary, key=lambda c: rank_key(c["best_overall"] or {}))
        horizon_leaders[horizon] = {
            "primary_directional_top10": [
                {"series": c["series"], "actor_role": c["actor_role"], "metric": c["best_overall"]}
                for c in primary_ranked[:10]
            ],
            "all_actor_top10_context_separated": [
                {"series": c["series"], "actor_role": c["actor_role"], "metric": c["best_overall"]}
                for c in all_ranked[:10]
            ],
            "market_oi_top7": sorted(
                [c for c in oi_matrix if c["horizon"] == horizon],
                key=lambda c: rank_key(c["best_oi_only"] or {}),
            ),
        }

    persistence = []
    for series in actor_keys:
        cells = [c for c in matrix if c["series"] == series]
        short = [c for c in cells if c["horizon"] in SHORT_MEDIUM]
        best_rows = [c["best_overall"] for c in short if c.get("best_overall")]
        positive = [r for r in best_rows if str(r.get("final_classification")) != "NO_OOS_GAIN"]
        confirmed_rows = [r for r in best_rows if confirmed(r)]
        fdr_rows = [r for r in best_rows if fdr_survivor(r)]
        rhos = [abs(finite(r.get("independent_spearman_rho")) or 0.0) for r in confirmed_rows]
        r2s = [finite(r.get("oos_r2")) for r in confirmed_rows if finite(r.get("oos_r2")) is not None]
        persistence.append({
            "series": series,
            "actor_role": role_for(series),
            "short_medium_horizons": list(SHORT_MEDIUM),
            "positive_oos_gain_horizon_count": len(positive),
            "overlap_or_fdr_confirmed_horizon_count": len(confirmed_rows),
            "fdr_surviving_horizon_count": len(fdr_rows),
            "median_abs_independent_rho_on_confirmed": round(statistics.median(rhos), 6) if rhos else None,
            "median_oos_r2_on_confirmed": round(statistics.median(r2s), 6) if r2s else None,
            "confirmed_horizons": [r.get("horizon") for r in confirmed_rows],
            "fdr_horizons": [r.get("horizon") for r in fdr_rows],
        })
    persistence.sort(key=lambda r: (
        -int(r["fdr_surviving_horizon_count"]),
        -int(r["overlap_or_fdr_confirmed_horizon_count"]),
        -int(r["positive_oos_gain_horizon_count"]),
        -(finite(r.get("median_abs_independent_rho_on_confirmed")) or 0.0),
        str(r["series"]),
    ))

    result = {
        "schema_version": 1,
        "study": "Complete COT raw-position/OI actor x horizon audit",
        "derived_from": "analysis/worldclass/research/cot-raw-position-oi-predictive-power.json",
        "information_contract": payload.get("information_contract"),
        "forecast_contract": payload.get("forecast_contract"),
        "horizons": list(HORIZONS),
        "actor_series_count": len(actor_keys),
        "actor_horizon_cell_count": len(matrix),
        "market_oi_series_count": len(oi_keys),
        "market_oi_horizon_cell_count": len(oi_matrix),
        "source_continuous_metric_count": payload.get("continuous_metric_count"),
        "source_strict_counts": payload.get("strict_counts"),
        "selection_rule": "Within each actor/horizon family, rank by predeclared evidence class first, then global q, OOS R2, absolute independent Spearman rho, and independent N. Context actors are never promoted as primary directional evidence.",
        "long_horizon_caveat": "26W/39W/52W effective independent N is small; large correlations there remain fragile unless corroborated. No result is promoted solely from long-horizon magnitude.",
        "incremental_oi_caveat": "Incremental two-feature OLS comparisons do not yet have their own non-overlap/FDR gate and remain exploratory.",
        "horizon_leaders": horizon_leaders,
        "actor_persistence_1w_to_13w": persistence,
        "actor_horizon_matrix": matrix,
        "market_oi_horizon_matrix": oi_matrix,
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    cols = [
        "series", "actor_role", "horizon", "predictor", "predictor_family", "classification",
        "holdout_n", "independent_n", "holdout_spearman_rho", "independent_spearman_rho",
        "oos_r2", "p90_minus_p10_spread_pp", "global_fdr_q", "family_fdr_q",
        "best_incremental_oi_model", "incremental_oi_r2_gain", "augmented_oos_r2",
    ]
    lines = ["\t".join(cols)]
    for cell in matrix:
        m = cell["best_overall"] or {}
        inc = cell["best_incremental_oi_model"] or {}
        vals = [
            cell["series"], cell["actor_role"], cell["horizon"], m.get("predictor"), m.get("predictor_family"), m.get("final_classification"),
            m.get("holdout_n"), m.get("independent_n"), m.get("holdout_spearman_rho"), m.get("independent_spearman_rho"),
            m.get("oos_r2"), m.get("holdout_p90_minus_p10_spread_pp"), m.get("global_fdr_q"), m.get("family_fdr_q"),
            inc.get("model"), inc.get("oos_r2_gain"), inc.get("augmented_oos_r2"),
        ]
        lines.append("\t".join("" if v is None else str(v) for v in vals))
    TSV.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"Wrote {OUT}")
    print(f"Wrote {TSV}")
    print("actor_horizon_cells", len(matrix))
    print("oi_horizon_cells", len(oi_matrix))
    print("TOP PRIMARY BY HORIZON")
    for h in HORIZONS:
        lead = horizon_leaders[h]["primary_directional_top10"][0]
        m = lead["metric"]
        print(h, lead["series"], m.get("predictor"), m.get("final_classification"), "Nind", m.get("independent_n"), "rho", m.get("independent_spearman_rho"), "R2", m.get("oos_r2"), "qG", m.get("global_fdr_q"))
    print("TOP PERSISTENCE")
    for row in [r for r in persistence if r["actor_role"] == "PRIMARY_DIRECTIONAL"][:20]:
        print(json.dumps(row, sort_keys=True))


if __name__ == "__main__":
    main()
