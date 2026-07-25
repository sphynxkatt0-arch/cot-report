#!/usr/bin/env python3
"""Compare old TFF/Legacy scores with the new release-aligned model."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from build_directional_cot_system import HISTORY_OUT, OUT_DIR, write_csv

ROOT = Path(__file__).resolve().parent
OLD_TFF = ROOT / "cot_regime_backtest_output" / "regime_score_history.csv"
OLD_LEGACY = ROOT / "cot_legacy_regime_backtest_output" / "regime_score_history.csv"
ALIGNED_OUT = OUT_DIR / "directional_model_comparison_aligned.csv"
SUMMARY_OUT = OUT_DIR / "directional_model_comparison_summary.csv"
AGREEMENT_OUT = OUT_DIR / "directional_model_agreement.csv"

MODEL_COLUMNS = {
    "old_tff": "old_tff_score",
    "old_legacy": "old_legacy_score",
    "new_structural": "structural_score",
    "new_structural_tactical": "adjusted_cot_score",
}
NEW_MODELS = {"new_structural", "new_structural_tactical"}


def load_old(path: Path, prefix: str) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=["market", "report_date", f"{prefix}_score", f"{prefix}_bucket"])
    frame = pd.read_csv(path)
    frame["report_date"] = pd.to_datetime(frame["report_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    frame[f"{prefix}_score"] = pd.to_numeric(frame["score"], errors="coerce")
    frame[f"{prefix}_bucket"] = frame.get("bucket")
    return frame[["market", "report_date", f"{prefix}_score", f"{prefix}_bucket"]].dropna(subset=["market", "report_date"])


def load_aligned() -> pd.DataFrame:
    history = pd.read_csv(HISTORY_OUT)
    history["report_date"] = pd.to_datetime(history["report_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    aligned = history.merge(load_old(OLD_TFF, "old_tff"), on=["market", "report_date"], how="left")
    aligned = aligned.merge(load_old(OLD_LEGACY, "old_legacy"), on=["market", "report_date"], how="left")
    return aligned


def threshold_for_model(model: str) -> float:
    return 0.25 if model in NEW_MODELS else 0.0


def model_summary_rows(frame: pd.DataFrame) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for market, market_frame in frame.groupby("market"):
        for horizon in ("1w", "4w", "13w", "26w"):
            returns = pd.to_numeric(market_frame[f"forward_return_{horizon}"], errors="coerce")
            for model, score_col in MODEL_COLUMNS.items():
                scores = pd.to_numeric(market_frame.get(score_col), errors="coerce")
                paired = pd.DataFrame({"score": scores, "return": returns}).dropna()
                threshold = threshold_for_model(model)
                positive = paired.loc[paired["score"] > threshold, "return"]
                negative = paired.loc[paired["score"] < -threshold, "return"]
                neutral = paired.loc[paired["score"].abs() <= threshold, "return"]
                rows.append({
                    "market": market,
                    "horizon": horizon,
                    "model": model,
                    "observations": int(len(paired)),
                    "pearson_r": float(paired["score"].corr(paired["return"])) if len(paired) >= 3 else None,
                    "spearman_r": float(paired["score"].corr(paired["return"], method="spearman")) if len(paired) >= 3 else None,
                    "positive_n": int(len(positive)),
                    "positive_avg_return": float(positive.mean()) if len(positive) else None,
                    "negative_n": int(len(negative)),
                    "negative_avg_return": float(negative.mean()) if len(negative) else None,
                    "neutral_n": int(len(neutral)),
                    "neutral_avg_return": float(neutral.mean()) if len(neutral) else None,
                    "positive_minus_negative": float(positive.mean() - negative.mean()) if len(positive) and len(negative) else None,
                    "directional_coverage_pct": float((len(positive) + len(negative)) / len(paired) * 100.0) if len(paired) else None,
                    "status": "exploratory_release_aligned",
                })
    return rows


def sign_bucket(series: pd.Series, threshold: float) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    output = pd.Series("neutral", index=values.index, dtype="object")
    output.loc[values > threshold] = "positive"
    output.loc[values < -threshold] = "negative"
    output.loc[values.isna()] = None
    return output


def agreement_rows(frame: pd.DataFrame) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    model_names = list(MODEL_COLUMNS)
    for market, market_frame in frame.groupby("market"):
        buckets = {
            model: sign_bucket(market_frame[column], threshold_for_model(model))
            for model, column in MODEL_COLUMNS.items()
        }
        for left_index, left in enumerate(model_names):
            for right in model_names[left_index + 1:]:
                pair = pd.DataFrame({"left": buckets[left], "right": buckets[right]}).dropna()
                directional = pair.loc[(pair["left"] != "neutral") & (pair["right"] != "neutral")]
                rows.append({
                    "market": market,
                    "left_model": left,
                    "right_model": right,
                    "overlap_n": int(len(pair)),
                    "directional_overlap_n": int(len(directional)),
                    "directional_agreement_pct": float((directional["left"] == directional["right"]).mean() * 100.0) if len(directional) else None,
                    "neutral_disagreement_n": int(((pair["left"] == "neutral") ^ (pair["right"] == "neutral")).sum()),
                })
    return rows


def main() -> None:
    if not HISTORY_OUT.exists():
        raise FileNotFoundError(f"Missing {HISTORY_OUT}; run rebuild_directional_history.py first")
    aligned = load_aligned()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    aligned.to_csv(ALIGNED_OUT, index=False)
    write_csv(SUMMARY_OUT, model_summary_rows(aligned))
    write_csv(AGREEMENT_OUT, agreement_rows(aligned))
    print(f"Wrote {ALIGNED_OUT}")
    print(f"Wrote {SUMMARY_OUT}")
    print(f"Wrote {AGREEMENT_OUT}")


if __name__ == "__main__":
    main()
