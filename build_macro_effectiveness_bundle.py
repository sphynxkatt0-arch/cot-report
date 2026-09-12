"""Build a compact browser payload for governed macro-effectiveness research."""

from __future__ import annotations

import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "macro_backtest_2026-08-14"
OUT = ROOT / "worldclass" / "macro-effectiveness.json"


NUMERIC_FIELDS = {
    "n",
    "pearson",
    "pearson_p",
    "spearman",
    "spearman_p",
    "hac_p",
    "hac_t",
    "oos_r2",
    "oos_pred_spearman",
    "era_23_24_rho",
    "era_25_26_rho",
    "spearman_q_global",
    "hac_q_global",
    "beta",
    "p_hac_incremental",
    "r2_full",
    "r2_baseline",
    "delta_r2_in",
    "oos_r2_base",
    "oos_r2_full",
    "delta_oos_r2",
    "full_pred_spear",
    "base_pred_spear",
}


def read_csv(path: Path) -> list[dict]:
    rows: list[dict] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            clean = dict(row)
            for key in NUMERIC_FIELDS:
                if key not in clean or clean[key] in (None, ""):
                    continue
                try:
                    clean[key] = int(clean[key]) if key == "n" else float(clean[key])
                except ValueError:
                    pass
            rows.append(clean)
    return rows


def main() -> None:
    methodology = json.loads((SOURCE / "methodology_and_formula.json").read_text(encoding="utf-8"))
    payload = {
        "schema_version": 1,
        "study_date": "2026-08-14",
        "governance": {
            "aggregate_score_directional_weight": 0.0,
            "aggregate_score_verdict": "NOT_VALIDATED",
            "aggregate_score_verdict_label": "No robust standalone predictive edge",
            "production_role": "Descriptive macro context only",
            "reason": "Aggregate liquidity_score failed robustness across SPX and Nasdaq-100 at 1W, 2W, 4W, 13W and 26W.",
            "vintage_safe": False,
            "promotion_rule": "Require point-in-time vintages, actual publication lags and stable HAC/non-overlap/era/OOS evidence before assigning non-zero directional weight.",
        },
        "sample": {
            "date_range": methodology.get("date_range"),
            "daily_rows": methodology.get("daily_rows"),
            "weekly_rows": methodology.get("weekly_rows"),
            "markets": ["SPX", "NQ"],
            "horizons": ["1W", "2W", "4W", "13W", "26W"],
        },
        "score_weights": methodology.get("production_liquidity_score_inferred_weights", {}),
        "aggregate": read_csv(SOURCE / "aggregate_score_summary.csv"),
        "factor_candidates": read_csv(SOURCE / "top_factor_findings.csv"),
        "incremental_controls": read_csv(SOURCE / "net_liquidity_incremental_controls.csv"),
        "provenance": {
            "source_dir": "analysis/macro_backtest_2026-08-14",
            "source_history": "model_output/macro_history.csv",
            "note": "Decision-critical rows only; broader exploratory matrices remain research-only.",
        },
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"saved {OUT} ({OUT.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
