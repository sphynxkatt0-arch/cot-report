#!/usr/bin/env python3
"""Compare old TFF/Legacy scores with the new release-aligned model.

All models share the same report dates, Friday-aligned price bases, terminal
returns, and within-horizon path outcomes. Statistics are exploratory but use
Newey-West HAC covariance to reduce false confidence from overlapping returns.
"""

from __future__ import annotations

from math import erfc, sqrt
from pathlib import Path
from typing import Any

import numpy as np
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
HORIZON_LAGS = {"1w": 1, "4w": 4, "13w": 13, "26w": 26}
MIN_STABILITY_SUBPERIOD_N = 10


def normal_two_sided_p(t_stat: float | None) -> float | None:
    if t_stat is None or not np.isfinite(t_stat):
        return None
    return float(erfc(abs(float(t_stat)) / sqrt(2.0)))


def hac_slope_stats(
    x: pd.Series,
    y: pd.Series,
    lags: int,
) -> dict[str, float | int | None]:
    pair = pd.DataFrame({"x": pd.to_numeric(x, errors="coerce"), "y": pd.to_numeric(y, errors="coerce")}).dropna()
    n = len(pair)
    if n < max(20, lags + 5) or pair["x"].nunique() < 2:
        return {"n": n, "slope": None, "hac_se": None, "hac_t": None, "hac_p": None}
    x_values = pair["x"].to_numpy(dtype=float)
    y_values = pair["y"].to_numpy(dtype=float)
    design = np.column_stack([np.ones(n), x_values])
    try:
        bread = np.linalg.inv(design.T @ design)
    except np.linalg.LinAlgError:
        return {"n": n, "slope": None, "hac_se": None, "hac_t": None, "hac_p": None}
    beta = bread @ design.T @ y_values
    residual = y_values - design @ beta
    meat = np.zeros((2, 2), dtype=float)
    for index in range(n):
        vector = design[index][:, None]
        meat += residual[index] ** 2 * (vector @ vector.T)
    maximum_lag = min(int(lags), n - 1)
    for lag in range(1, maximum_lag + 1):
        weight = 1.0 - lag / (maximum_lag + 1.0)
        gamma = np.zeros((2, 2), dtype=float)
        for index in range(lag, n):
            current = design[index][:, None]
            previous = design[index - lag][:, None]
            gamma += residual[index] * residual[index - lag] * (current @ previous.T)
        meat += weight * (gamma + gamma.T)
    covariance = bread @ meat @ bread
    variance = float(covariance[1, 1])
    if variance <= 0 or not np.isfinite(variance):
        return {"n": n, "slope": float(beta[1]), "hac_se": None, "hac_t": None, "hac_p": None}
    standard_error = sqrt(variance)
    t_stat = float(beta[1] / standard_error) if standard_error else None
    return {
        "n": n,
        "slope": float(beta[1]),
        "hac_se": float(standard_error),
        "hac_t": t_stat,
        "hac_p": normal_two_sided_p(t_stat),
    }


def load_old(path: Path, prefix: str) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Missing baseline model history: {path}")
    frame = pd.read_csv(path)
    required = {"market", "report_date", "score", "bucket"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise KeyError(f"{path} missing columns {missing}")
    frame["report_date"] = pd.to_datetime(frame["report_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    frame[f"{prefix}_score"] = pd.to_numeric(frame["score"], errors="coerce")
    frame[f"{prefix}_bucket"] = frame["bucket"]
    return frame[["market", "report_date", f"{prefix}_score", f"{prefix}_bucket"]].dropna(
        subset=["market", "report_date", f"{prefix}_score"]
    )


def load_aligned() -> pd.DataFrame:
    if not HISTORY_OUT.exists():
        raise FileNotFoundError(f"Missing {HISTORY_OUT}; run rebuild_directional_history.py first")
    history = pd.read_csv(HISTORY_OUT)
    history["report_date"] = pd.to_datetime(history["report_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    aligned = history.merge(load_old(OLD_TFF, "old_tff"), on=["market", "report_date"], how="left")
    aligned = aligned.merge(load_old(OLD_LEGACY, "old_legacy"), on=["market", "report_date"], how="left")
    return aligned.sort_values(["market", "report_date"]).reset_index(drop=True)


def threshold_for_model(model: str) -> float:
    return 0.25 if model in NEW_MODELS else 0.0


def chronological_stability(
    dates: pd.Series,
    scores: pd.Series,
    returns: pd.Series,
) -> dict[str, float | int | None]:
    paired = pd.DataFrame({
        "date": pd.to_datetime(dates, errors="coerce"),
        "score": pd.to_numeric(scores, errors="coerce"),
        "return": pd.to_numeric(returns, errors="coerce"),
    }).dropna().sort_values("date")
    if len(paired) < MIN_STABILITY_SUBPERIOD_N * 3:
        return {"subperiods": 0, "sign_agreement_pct": None, "min_abs_spearman": None}
    full = paired["score"].corr(paired["return"], method="spearman")
    if pd.isna(full) or abs(float(full)) < 1e-12:
        return {"subperiods": 0, "sign_agreement_pct": None, "min_abs_spearman": None}
    values: list[float] = []
    for indices in np.array_split(np.arange(len(paired)), 3):
        part = paired.iloc[indices]
        if len(part) < MIN_STABILITY_SUBPERIOD_N or part["score"].nunique() < 2:
            continue
        correlation = part["score"].corr(part["return"], method="spearman")
        if pd.notna(correlation):
            values.append(float(correlation))
    if not values:
        return {"subperiods": 0, "sign_agreement_pct": None, "min_abs_spearman": None}
    full_sign = 1 if full > 0 else -1
    agreements = sum((1 if value > 0 else -1) == full_sign for value in values)
    return {
        "subperiods": len(values),
        "sign_agreement_pct": agreements / len(values) * 100.0,
        "min_abs_spearman": min(abs(value) for value in values),
    }


def drift_adjusted_accuracy(
    dates: pd.Series,
    scores: pd.Series,
    returns: pd.Series,
    threshold: float,
) -> tuple[int, float | None]:
    frame = pd.DataFrame({
        "date": pd.to_datetime(dates, errors="coerce"),
        "score": pd.to_numeric(scores, errors="coerce"),
        "return": pd.to_numeric(returns, errors="coerce"),
    }).dropna().sort_values("date")
    frame["prior_mean"] = frame["return"].expanding(min_periods=26).mean().shift(1)
    directional = frame.loc[(frame["score"] > threshold) | (frame["score"] < -threshold)].dropna(subset=["prior_mean"])
    if directional.empty:
        return 0, None
    correct = (
        ((directional["score"] > threshold) & (directional["return"] > directional["prior_mean"]))
        | ((directional["score"] < -threshold) & (directional["return"] < directional["prior_mean"]))
    )
    return int(len(directional)), float(correct.mean() * 100.0)


def directional_path_metrics(
    scores: pd.Series,
    returns: pd.Series,
    worst_path: pd.Series,
    best_path: pd.Series,
    threshold: float,
) -> dict[str, float | int | None]:
    frame = pd.DataFrame({
        "score": pd.to_numeric(scores, errors="coerce"),
        "return": pd.to_numeric(returns, errors="coerce"),
        "worst": pd.to_numeric(worst_path, errors="coerce"),
        "best": pd.to_numeric(best_path, errors="coerce"),
    }).dropna()
    frame = frame.loc[(frame["score"] > threshold) | (frame["score"] < -threshold)].copy()
    if frame.empty:
        return {
            "directional_n": 0,
            "avg_directional_return": None,
            "directional_hit_rate": None,
            "avg_adverse_move": None,
            "worst_adverse_move": None,
            "path_utility": None,
        }
    positive = frame["score"] > threshold
    frame["directional_return"] = np.where(positive, frame["return"], -frame["return"])
    frame["adverse_move"] = np.where(positive, frame["worst"], -frame["best"])
    average_return = float(frame["directional_return"].mean())
    average_adverse = float(frame["adverse_move"].mean())
    return {
        "directional_n": int(len(frame)),
        "avg_directional_return": average_return,
        "directional_hit_rate": float((frame["directional_return"] > 0).mean() * 100.0),
        "avg_adverse_move": average_adverse,
        "worst_adverse_move": float(frame["adverse_move"].min()),
        "path_utility": average_return + 0.35 * average_adverse,
    }


def model_summary_rows(frame: pd.DataFrame) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for market, market_frame in frame.groupby("market"):
        for horizon in ("1w", "4w", "13w", "26w"):
            returns = pd.to_numeric(market_frame[f"forward_return_{horizon}"], errors="coerce")
            worst_path = pd.to_numeric(market_frame[f"forward_worst_path_return_{horizon}"], errors="coerce")
            best_path = pd.to_numeric(market_frame[f"forward_best_path_return_{horizon}"], errors="coerce")
            lags = HORIZON_LAGS[horizon]
            for model, score_col in MODEL_COLUMNS.items():
                if score_col not in market_frame.columns:
                    scores = pd.Series(np.nan, index=market_frame.index, dtype="float64")
                else:
                    scores = pd.to_numeric(market_frame[score_col], errors="coerce")
                paired = pd.DataFrame({"score": scores, "return": returns}).dropna()
                threshold = threshold_for_model(model)
                positive = paired.loc[paired["score"] > threshold, "return"]
                negative = paired.loc[paired["score"] < -threshold, "return"]
                neutral = paired.loc[paired["score"].abs() <= threshold, "return"]
                continuous_hac = hac_slope_stats(scores, returns, lags)

                directional_indicator = pd.Series(np.nan, index=market_frame.index, dtype="float64")
                directional_indicator.loc[scores > threshold] = 1.0
                directional_indicator.loc[scores < -threshold] = 0.0
                edge_hac = hac_slope_stats(directional_indicator, returns, lags)
                stability = chronological_stability(market_frame["report_date"], scores, returns)
                accuracy_n, accuracy = drift_adjusted_accuracy(
                    market_frame["report_date"], scores, returns, threshold
                )
                path = directional_path_metrics(scores, returns, worst_path, best_path, threshold)
                rows.append({
                    "market": market,
                    "horizon": horizon,
                    "model": model,
                    "observations": int(len(paired)),
                    "pearson_r": float(paired["score"].corr(paired["return"])) if len(paired) >= 3 else None,
                    "spearman_r": float(paired["score"].corr(paired["return"], method="spearman")) if len(paired) >= 3 else None,
                    "hac_lags": lags,
                    "score_slope_pp_per_unit": continuous_hac["slope"],
                    "score_hac_t": continuous_hac["hac_t"],
                    "score_hac_p": continuous_hac["hac_p"],
                    "positive_n": int(len(positive)),
                    "positive_avg_return": float(positive.mean()) if len(positive) else None,
                    "negative_n": int(len(negative)),
                    "negative_avg_return": float(negative.mean()) if len(negative) else None,
                    "neutral_n": int(len(neutral)),
                    "neutral_avg_return": float(neutral.mean()) if len(neutral) else None,
                    "positive_minus_negative": float(positive.mean() - negative.mean()) if len(positive) and len(negative) else None,
                    "edge_hac_t": edge_hac["hac_t"],
                    "edge_hac_p": edge_hac["hac_p"],
                    "directional_coverage_pct": float((len(positive) + len(negative)) / len(paired) * 100.0) if len(paired) else None,
                    "drift_adjusted_n": accuracy_n,
                    "drift_adjusted_accuracy_pct": accuracy,
                    "stability_subperiods": stability["subperiods"],
                    "subperiod_sign_agreement_pct": stability["sign_agreement_pct"],
                    "subperiod_min_abs_spearman": stability["min_abs_spearman"],
                    **path,
                    "status": "exploratory_release_aligned_hac",
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
            model: sign_bucket(
                market_frame[column] if column in market_frame.columns else pd.Series(np.nan, index=market_frame.index),
                threshold_for_model(model),
            )
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
