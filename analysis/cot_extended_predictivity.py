#!/usr/bin/env python3
"""Extensive, release-aligned COT participant predictivity backtest.

This analysis is designed to answer three practical questions:
1. Which Legacy and TFF participant signals have repeatable predictive value?
2. Does the edge survive chronological out-of-sample and regime-stability checks?
3. Do Asset Manager, Other Reportable, and Nonreportable signals add value around
   a Legacy Non-Commercial anchor?

Methodological safeguards:
- Tuesday COT observations become tradable on the first market close on/after
  the normal Friday publication date.
- All z-scores and percentiles are computed from prior observations only.
- Overlapping-return inference uses Newey-West HAC standard errors.
- Benjamini-Hochberg false-discovery-rate adjustments are reported.
- Chronological out-of-sample, subperiod, and rolling-window stability are tested.
- A purged expanding walk-forward ridge model only trains on outcomes that would
  have been known by each prediction date.
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
ANALYSIS = ROOT / "analysis"
DATA = ROOT / "data"
OUTDIR = ANALYSIS / "cot_extended_predictivity_output"

MARKETS: dict[str, dict[str, Any]] = {
    "sp500": {
        "label": "S&P 500",
        "price_file": DATA / "SP500.csv",
        "price_col": "SP500",
    },
    "nq": {
        "label": "NASDAQ-100",
        "price_file": DATA / "NASDAQ100.csv",
        "price_col": "NASDAQ100",
    },
}

DATASETS: dict[str, dict[str, Any]] = {
    "tff": {
        "label": "TFF Detailed",
        "directory": ANALYSIS / "cot_exact_output",
        "glob": lambda market: f"{market}_exact_consolidated_data_*.csv",
        "categories": {
            "asset_mgr": "Asset Manager / Institutional",
            "dealer": "Dealer / Intermediary",
            "lev_money": "Leveraged Funds",
            "other_reportable": "Other Reportables",
            "non_reportable": "Nonreportable",
        },
    },
    "legacy": {
        "label": "Legacy",
        "directory": ANALYSIS / "cot_legacy_output",
        "glob": lambda market: f"{market}_legacy_data_*.csv",
        "categories": {
            "noncommercial": "Non-Commercial",
            "commercial": "Commercial",
            "nonreportable": "Nonreportable",
        },
    },
}

HORIZONS: dict[str, int] = {
    "1d": 1,
    "3d": 3,
    "1w": 5,
    "2w": 10,
    "3w": 15,
    "4w": 20,
    "8w": 40,
    "13w": 65,
    "26w": 130,
    "52w": 260,
}

RIDGE_HORIZONS = ("1w", "2w", "4w", "13w", "26w")
CHANGE_LOOKBACKS = (1, 4, 13, 26)
TAIL_QUANTILES = (0.10, 0.20)

SELECTED_PARTICIPANT_SIGNALS = (
    "net_oi_pct_z",
    "net_notional_bn_z",
    "short_oi_pct_z",
    "net_oi_change_1w_z",
    "net_oi_change_4w_z",
    "net_oi_change_13w_z",
    "net_oi_change_26w_z",
    "net_notional_change_1w_z",
    "net_notional_change_4w_z",
    "net_notional_change_13w_z",
    "net_notional_change_26w_z",
    "notional_flow_accel_4w_z",
    "oi_flow_accel_4w_z",
)

SELECTED_DIVERGENCE_SIGNALS = (
    "net_oi_pct_divergence_z",
    "net_notional_bn_divergence_z",
    "net_oi_change_13w_divergence_z",
    "net_notional_change_13w_divergence_z",
)

ERA_SPECS = (
    ("2018-2019", "2018-01-01", "2019-12-31"),
    ("2020-2021", "2020-01-01", "2021-12-31"),
    ("2022-2023", "2022-01-01", "2023-12-31"),
    ("2024+", "2024-01-01", "2099-12-31"),
)


@dataclass(frozen=True)
class Outcome:
    future_date: pd.Timestamp | None
    future_price: float | None
    return_pct: float | None
    drawdown_pct: float | None
    runup_pct: float | None


def latest_file(directory: Path, pattern: str) -> Path:
    matches = sorted(directory.glob(pattern), key=lambda path: path.stat().st_mtime)
    if not matches:
        raise FileNotFoundError(f"No files match {directory / pattern}")
    return matches[-1]


def load_prices(market: str) -> pd.DataFrame:
    cfg = MARKETS[market]
    df = pd.read_csv(cfg["price_file"])
    df.columns = [str(column).strip().lstrip("\ufeff") for column in df.columns]
    date_col = "observation_date" if "observation_date" in df.columns else "date"
    value_col = cfg["price_col"] if cfg["price_col"] in df.columns else next(
        column for column in df.columns if column != date_col
    )
    out = pd.DataFrame(
        {
            "date": pd.to_datetime(df[date_col], errors="coerce"),
            "price": pd.to_numeric(df[value_col].replace(".", pd.NA), errors="coerce"),
        }
    ).dropna(subset=["date", "price"])
    return out.sort_values("date").drop_duplicates("date", keep="last").reset_index(drop=True)


def load_cot(dataset: str, market: str) -> tuple[pd.DataFrame, Path]:
    cfg = DATASETS[dataset]
    path = latest_file(cfg["directory"], cfg["glob"](market))
    df = pd.read_csv(path)
    df.columns = [str(column).strip().lstrip("\ufeff") for column in df.columns]
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"]).sort_values("date").drop_duplicates("date", keep="last")
    return df.reset_index(drop=True), path


def first_price_on_or_after(prices: pd.DataFrame, target: pd.Timestamp) -> int | None:
    dates = prices["date"].to_numpy(dtype="datetime64[ns]")
    index = int(np.searchsorted(dates, np.datetime64(target), side="left"))
    return None if index >= len(prices) else index


def horizon_outcome(prices: pd.DataFrame, start_index: int, steps: int) -> Outcome:
    end_index = start_index + steps
    if end_index >= len(prices):
        return Outcome(None, None, None, None, None)
    start_price = float(prices.iloc[start_index]["price"])
    future_price = float(prices.iloc[end_index]["price"])
    if not math.isfinite(start_price) or not math.isfinite(future_price) or start_price <= 0:
        return Outcome(None, None, None, None, None)
    window = pd.to_numeric(prices.iloc[start_index : end_index + 1]["price"], errors="coerce").dropna()
    if window.empty:
        return Outcome(None, None, None, None, None)
    return Outcome(
        future_date=pd.Timestamp(prices.iloc[end_index]["date"]),
        future_price=future_price,
        return_pct=float((future_price / start_price - 1.0) * 100.0),
        drawdown_pct=float((window.min() / start_price - 1.0) * 100.0),
        runup_pct=float((window.max() / start_price - 1.0) * 100.0),
    )


def build_outcomes(market: str, report_dates: pd.Series) -> pd.DataFrame:
    prices = load_prices(market)
    rows: list[dict[str, Any]] = []
    for report_date in pd.to_datetime(report_dates):
        release_target = report_date + pd.Timedelta(days=3)
        start_index = first_price_on_or_after(prices, release_target)
        if start_index is None:
            continue
        signal_date = pd.Timestamp(prices.iloc[start_index]["date"])
        signal_price = float(prices.iloc[start_index]["price"])
        base: dict[str, Any] = {
            "report_date": report_date,
            "release_target_date": release_target,
            "signal_date": signal_date,
            "signal_price": signal_price,
        }
        for label, steps in HORIZONS.items():
            outcome = horizon_outcome(prices, start_index, steps)
            base[f"future_date_{label}"] = outcome.future_date
            base[f"forward_return_{label}"] = outcome.return_pct
            base[f"drawdown_{label}"] = outcome.drawdown_pct
            base[f"runup_{label}"] = outcome.runup_pct
        rows.append(base)
    return pd.DataFrame(rows)


def numeric(df: pd.DataFrame, column: str, default: float | None = None) -> pd.Series:
    if column not in df.columns:
        if default is None:
            return pd.Series(np.nan, index=df.index, dtype=float)
        return pd.Series(default, index=df.index, dtype=float)
    return pd.to_numeric(df[column], errors="coerce")


def prior_expanding_z(series: pd.Series, min_history: int) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    mean = values.expanding(min_periods=min_history).mean().shift(1)
    std = values.expanding(min_periods=min_history).std(ddof=1).shift(1).replace(0, np.nan)
    return (values - mean) / std


def prior_expanding_percentile(series: pd.Series, min_history: int) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    output = pd.Series(np.nan, index=values.index, dtype=float)
    for index in range(len(values)):
        value = values.iloc[index]
        if not math.isfinite(value):
            continue
        history = values.iloc[:index].dropna()
        if len(history) < min_history:
            continue
        less = int((history < value).sum())
        equal = int((history == value).sum())
        output.iloc[index] = 100.0 * (less + 0.5 * equal) / len(history)
    return output


def build_raw_category_signals(df: pd.DataFrame, category: str) -> pd.DataFrame:
    open_interest = numeric(df, "open_interest")
    long_contracts = numeric(df, f"{category}_long")
    short_contracts = numeric(df, f"{category}_short")
    net_contracts = numeric(df, f"{category}_net")
    net_oi_pct = numeric(df, f"{category}_net_oi_pct")
    long_oi_pct = numeric(df, f"{category}_long_oi_pct")
    short_oi_pct = numeric(df, f"{category}_short_oi_pct")
    if long_oi_pct.isna().all():
        long_oi_pct = long_contracts.div(open_interest.replace(0, np.nan)).mul(100.0)
    if short_oi_pct.isna().all():
        short_oi_pct = short_contracts.div(open_interest.replace(0, np.nan)).mul(100.0)
    net_notional_bn = numeric(df, f"{category}_net_notional_usd") / 1e9

    out = pd.DataFrame(
        {
            "report_date": pd.to_datetime(df["date"], errors="coerce"),
            "net_contracts": net_contracts,
            "net_oi_pct": net_oi_pct,
            "long_oi_pct": long_oi_pct,
            "short_oi_pct": short_oi_pct,
            "net_notional_bn": net_notional_bn,
        }
    )

    for lookback in CHANGE_LOOKBACKS:
        out[f"net_oi_change_{lookback}w"] = out["net_oi_pct"].diff(lookback)
        out[f"net_contract_change_{lookback}w"] = out["net_contracts"].diff(lookback)
        out[f"net_notional_change_{lookback}w"] = out["net_notional_bn"].diff(lookback)
    for lookback in (1, 4, 13, 26):
        out[f"long_oi_change_{lookback}w"] = out["long_oi_pct"].diff(lookback)
        out[f"short_oi_change_{lookback}w"] = out["short_oi_pct"].diff(lookback)

    out["notional_flow_accel_4w"] = (
        out["net_notional_change_1w"] - out["net_notional_change_4w"] / 4.0
    )
    out["notional_flow_accel_13w"] = (
        out["net_notional_change_4w"] / 4.0 - out["net_notional_change_13w"] / 13.0
    )
    out["oi_flow_accel_4w"] = out["net_oi_change_1w"] - out["net_oi_change_4w"] / 4.0
    out["oi_flow_accel_13w"] = out["net_oi_change_4w"] / 4.0 - out["net_oi_change_13w"] / 13.0
    return out


def standardize_signal_frame(raw: pd.DataFrame, min_history: int) -> pd.DataFrame:
    out = raw[["report_date"]].copy()
    raw_columns = [column for column in raw.columns if column != "report_date"]
    for column in raw_columns:
        out[f"{column}_z"] = prior_expanding_z(raw[column], min_history)
    for column in ("net_oi_pct", "net_notional_bn", "short_oi_pct", "long_oi_pct"):
        out[f"{column}_pctile"] = prior_expanding_percentile(raw[column], min_history)
    return out


def build_all_signal_frames(min_history: int) -> tuple[dict[tuple[str, str, str], pd.DataFrame], list[dict[str, Any]]]:
    frames: dict[tuple[str, str, str], pd.DataFrame] = {}
    source_rows: list[dict[str, Any]] = []
    for dataset, dataset_cfg in DATASETS.items():
        for market in MARKETS:
            cot, path = load_cot(dataset, market)
            source_rows.append(
                {
                    "dataset": dataset,
                    "dataset_label": dataset_cfg["label"],
                    "market": market,
                    "market_label": MARKETS[market]["label"],
                    "path": str(path.relative_to(ROOT)),
                    "rows": int(len(cot)),
                    "first_date": cot["date"].min().date().isoformat(),
                    "last_date": cot["date"].max().date().isoformat(),
                }
            )
            for category, label in dataset_cfg["categories"].items():
                raw = build_raw_category_signals(cot, category)
                standardized = standardize_signal_frame(raw, min_history)
                standardized.attrs.update(
                    dataset=dataset,
                    dataset_label=dataset_cfg["label"],
                    market=market,
                    market_label=MARKETS[market]["label"],
                    category=category,
                    category_label=label,
                )
                frames[(dataset, market, category)] = standardized
    return frames, source_rows


def build_divergence_frames(
    frames: dict[tuple[str, str, str], pd.DataFrame], min_history: int
) -> dict[tuple[str, str, str], pd.DataFrame]:
    specs = {
        "tff": (
            ("asset_mgr_minus_lev_money", "Asset Manager minus Leveraged Funds", "asset_mgr", "lev_money"),
            ("asset_mgr_minus_nonreportable", "Asset Manager minus Nonreportable", "asset_mgr", "non_reportable"),
            ("other_minus_nonreportable", "Other Reportables minus Nonreportable", "other_reportable", "non_reportable"),
        ),
        "legacy": (
            ("noncommercial_minus_nonreportable", "Non-Commercial minus Nonreportable", "noncommercial", "nonreportable"),
            ("commercial_minus_noncommercial", "Commercial minus Non-Commercial", "commercial", "noncommercial"),
        ),
    }
    result: dict[tuple[str, str, str], pd.DataFrame] = {}
    raw_suffixes = (
        "net_oi_pct_z",
        "net_notional_bn_z",
        "net_oi_change_4w_z",
        "net_oi_change_13w_z",
        "net_oi_change_26w_z",
        "net_notional_change_4w_z",
        "net_notional_change_13w_z",
        "net_notional_change_26w_z",
    )
    for dataset, dataset_specs in specs.items():
        for market in MARKETS:
            for key, label, left_category, right_category in dataset_specs:
                left = frames[(dataset, market, left_category)]
                right = frames[(dataset, market, right_category)]
                merged = left[["report_date", *[c for c in raw_suffixes if c in left.columns]]].merge(
                    right[["report_date", *[c for c in raw_suffixes if c in right.columns]]],
                    on="report_date",
                    suffixes=("_left", "_right"),
                    how="inner",
                )
                out = merged[["report_date"]].copy()
                for suffix in raw_suffixes:
                    left_col = f"{suffix}_left"
                    right_col = f"{suffix}_right"
                    if left_col in merged and right_col in merged:
                        difference = merged[left_col] - merged[right_col]
                        out[f"{suffix.removesuffix('_z')}_divergence_z"] = prior_expanding_z(
                            difference, max(52, min_history // 2)
                        )
                out.attrs.update(
                    dataset=dataset,
                    dataset_label=DATASETS[dataset]["label"],
                    market=market,
                    market_label=MARKETS[market]["label"],
                    category=key,
                    category_label=label,
                    signal_family="divergence",
                )
                result[(dataset, market, key)] = out
    return result


def normal_approx_p_value(t_stat: float | None) -> float | None:
    if t_stat is None or not math.isfinite(t_stat):
        return None
    return float(math.erfc(abs(t_stat) / math.sqrt(2.0)))


def horizon_hac_lags(horizon: str) -> int:
    return max(1, int(math.ceil(HORIZONS[horizon] / 5.0)) - 1)


def newey_west_slope_stats(
    y: pd.Series, x: pd.Series, lags: int, min_unique_x: int = 5
) -> tuple[float | None, float | None, float | None]:
    data = pd.DataFrame({"y": y, "x": x}).replace([np.inf, -np.inf], np.nan).dropna()
    if len(data) < max(30, lags + 8) or data["x"].nunique() < min_unique_x:
        return None, None, None
    y_values = data["y"].to_numpy(dtype=float)
    x_values = data["x"].to_numpy(dtype=float)
    design = np.column_stack([np.ones(len(data)), x_values])
    xtx_inv = np.linalg.pinv(design.T @ design)
    beta = xtx_inv @ design.T @ y_values
    residuals = y_values - design @ beta
    scores = design * residuals[:, None]
    meat = scores.T @ scores
    usable_lags = min(max(int(lags), 0), len(data) - 2)
    for lag in range(1, usable_lags + 1):
        weight = 1.0 - lag / (usable_lags + 1.0)
        gamma = scores[lag:].T @ scores[:-lag]
        meat += weight * (gamma + gamma.T)
    covariance = xtx_inv @ meat @ xtx_inv
    if len(data) > 2:
        covariance *= len(data) / (len(data) - 2)
    slope = float(beta[1])
    variance = float(covariance[1, 1])
    if variance <= 0 or not math.isfinite(variance):
        return slope, None, None
    t_stat = slope / math.sqrt(variance)
    return slope, float(t_stat), normal_approx_p_value(float(t_stat))


def corr_safe(x: pd.Series, y: pd.Series, method: str = "pearson") -> float | None:
    data = pd.DataFrame({"x": x, "y": y}).replace([np.inf, -np.inf], np.nan).dropna()
    if len(data) < 30 or data["x"].nunique() < 5 or data["y"].nunique() < 5:
        return None
    if method == "spearman":
        return float(data["x"].rank(method="average").corr(data["y"].rank(method="average")))
    return float(data["x"].corr(data["y"]))


def tail_stats(data: pd.DataFrame, quantile: float, horizon: str) -> dict[str, Any]:
    if len(data) < 80:
        return {}
    low_threshold = float(data["signal"].quantile(quantile))
    high_threshold = float(data["signal"].quantile(1.0 - quantile))
    bottom = data.loc[data["signal"] <= low_threshold]
    top = data.loc[data["signal"] >= high_threshold]
    if min(len(bottom), len(top)) < 15:
        return {}
    prefix = f"q{int(quantile * 100):02d}"
    return {
        f"{prefix}_low_threshold": low_threshold,
        f"{prefix}_high_threshold": high_threshold,
        f"{prefix}_top_n": int(len(top)),
        f"{prefix}_bottom_n": int(len(bottom)),
        f"{prefix}_top_avg_return": float(top["return"].mean()),
        f"{prefix}_bottom_avg_return": float(bottom["return"].mean()),
        f"{prefix}_top_minus_bottom": float(top["return"].mean() - bottom["return"].mean()),
        f"{prefix}_top_median_return": float(top["return"].median()),
        f"{prefix}_bottom_median_return": float(bottom["return"].median()),
        f"{prefix}_top_hit_rate": float((top["return"] > 0).mean() * 100.0),
        f"{prefix}_bottom_hit_rate": float((bottom["return"] > 0).mean() * 100.0),
        f"{prefix}_top_avg_drawdown": float(top["drawdown"].mean()),
        f"{prefix}_bottom_avg_drawdown": float(bottom["drawdown"].mean()),
        f"{prefix}_top_avg_runup": float(top["runup"].mean()),
        f"{prefix}_bottom_avg_runup": float(bottom["runup"].mean()),
    }


def chronological_oos(data: pd.DataFrame, horizon: str, train_fraction: float = 0.70) -> dict[str, Any]:
    ordered = data.sort_values("signal_date").reset_index(drop=True)
    split = max(120, int(len(ordered) * train_fraction))
    if len(ordered) - split < 40:
        return {}
    train = ordered.iloc[:split]
    test = ordered.iloc[split:]
    train_x = train["signal"].to_numpy(dtype=float)
    train_y = train["return"].to_numpy(dtype=float)
    variance = float(np.var(train_x))
    train_slope = float(np.cov(train_x, train_y, ddof=0)[0, 1] / variance) if variance > 0 else None
    if train_slope is None or train_slope == 0:
        return {}
    orientation = 1.0 if train_slope > 0 else -1.0
    oriented_train = train["signal"] * orientation
    oriented_test = test["signal"] * orientation
    low = float(oriented_train.quantile(0.20))
    high = float(oriented_train.quantile(0.80))
    bottom = test.loc[oriented_test <= low]
    top = test.loc[oriented_test >= high]
    test_spearman = corr_safe(oriented_test, test["return"], "spearman")
    edge = float(top["return"].mean() - bottom["return"].mean()) if len(top) and len(bottom) else None
    return {
        "oos_train_n": int(len(train)),
        "oos_test_n": int(len(test)),
        "oos_train_end": pd.Timestamp(train["signal_date"].max()).date().isoformat(),
        "oos_test_start": pd.Timestamp(test["signal_date"].min()).date().isoformat(),
        "oos_train_slope": train_slope,
        "oos_orientation": orientation,
        "oos_spearman": test_spearman,
        "oos_top_n": int(len(top)),
        "oos_bottom_n": int(len(bottom)),
        "oos_top_avg_return": float(top["return"].mean()) if len(top) else None,
        "oos_bottom_avg_return": float(bottom["return"].mean()) if len(bottom) else None,
        "oos_top_minus_bottom": edge,
        "oos_directional_accuracy": float(
            (np.sign(oriented_test) == np.sign(test["return"] - train["return"].mean())).mean() * 100.0
        ),
    }


def stability_stats(data: pd.DataFrame, full_slope: float | None) -> dict[str, Any]:
    if full_slope is None or full_slope == 0:
        return {}
    expected_sign = np.sign(full_slope)
    era_values: list[float] = []
    output: dict[str, Any] = {}
    dates = pd.to_datetime(data["signal_date"])
    for label, start, end in ERA_SPECS:
        mask = dates.between(pd.Timestamp(start), pd.Timestamp(end))
        group = data.loc[mask]
        value = corr_safe(group["signal"], group["return"], "spearman")
        output[f"era_{label}_n"] = int(len(group))
        output[f"era_{label}_spearman"] = value
        if value is not None and value != 0:
            era_values.append(value)
    output["era_count"] = len(era_values)
    output["era_sign_agreement"] = (
        float(np.mean(np.sign(era_values) == expected_sign)) if era_values else None
    )
    output["era_median_spearman"] = float(np.median(era_values)) if era_values else None

    ordered = data.sort_values("signal_date").reset_index(drop=True)
    rolling_values: list[float] = []
    window = 156
    step = 13
    for end_index in range(window, len(ordered) + 1, step):
        group = ordered.iloc[end_index - window : end_index]
        value = corr_safe(group["signal"], group["return"], "spearman")
        if value is not None and value != 0:
            rolling_values.append(value)
    output["rolling_3y_windows"] = len(rolling_values)
    output["rolling_3y_sign_agreement"] = (
        float(np.mean(np.sign(rolling_values) == expected_sign)) if rolling_values else None
    )
    output["rolling_3y_median_spearman"] = (
        float(np.median(rolling_values)) if rolling_values else None
    )
    output["rolling_3y_min_spearman"] = float(np.min(rolling_values)) if rolling_values else None
    output["rolling_3y_max_spearman"] = float(np.max(rolling_values)) if rolling_values else None
    return output


def benjamini_hochberg(values: pd.Series) -> pd.Series:
    result = pd.Series(np.nan, index=values.index, dtype=float)
    valid = pd.to_numeric(values, errors="coerce").dropna()
    if valid.empty:
        return result
    ordered = valid.sort_values()
    count = len(ordered)
    adjusted = ordered.to_numpy(dtype=float) * count / np.arange(1, count + 1)
    adjusted = np.minimum.accumulate(adjusted[::-1])[::-1]
    adjusted = np.clip(adjusted, 0.0, 1.0)
    result.loc[ordered.index] = adjusted
    return result


def evaluate_signal(
    frame: pd.DataFrame,
    outcomes: pd.DataFrame,
    signal_column: str,
    horizon: str,
) -> dict[str, Any] | None:
    merged = frame[["report_date", signal_column]].merge(outcomes, on="report_date", how="inner")
    data = pd.DataFrame(
        {
            "signal_date": pd.to_datetime(merged["signal_date"], errors="coerce"),
            "signal": pd.to_numeric(merged[signal_column], errors="coerce"),
            "return": pd.to_numeric(merged[f"forward_return_{horizon}"], errors="coerce"),
            "drawdown": pd.to_numeric(merged[f"drawdown_{horizon}"], errors="coerce"),
            "runup": pd.to_numeric(merged[f"runup_{horizon}"], errors="coerce"),
        }
    ).replace([np.inf, -np.inf], np.nan).dropna(subset=["signal_date", "signal", "return"])
    if len(data) < 100 or data["signal"].nunique() < 20:
        return None
    slope, hac_t, hac_p = newey_west_slope_stats(
        data["return"], data["signal"], horizon_hac_lags(horizon)
    )
    row: dict[str, Any] = {
        "horizon": horizon,
        "horizon_trading_days": HORIZONS[horizon],
        "signal": signal_column,
        "n": int(len(data)),
        "first_signal_date": data["signal_date"].min().date().isoformat(),
        "last_signal_date": data["signal_date"].max().date().isoformat(),
        "pearson_r": corr_safe(data["signal"], data["return"], "pearson"),
        "spearman_r": corr_safe(data["signal"], data["return"], "spearman"),
        "slope_pp_per_z": slope,
        "hac_t": hac_t,
        "hac_p": hac_p,
        "avg_return_pct": float(data["return"].mean()),
        "median_return_pct": float(data["return"].median()),
        "hit_rate_pct": float((data["return"] > 0).mean() * 100.0),
        "avg_drawdown_pct": float(data["drawdown"].mean()),
        "avg_runup_pct": float(data["runup"].mean()),
    }
    for quantile in TAIL_QUANTILES:
        row.update(tail_stats(data, quantile, horizon))
    q20_edge = abs(float(row.get("q20_top_minus_bottom") or 0.0))
    if (hac_p is not None and hac_p <= 0.20) or q20_edge >= 1.00:
        row.update(chronological_oos(data, horizon))
    return row


def rebuild_test_data(
    frame: pd.DataFrame,
    outcomes: pd.DataFrame,
    signal_column: str,
    horizon: str,
) -> pd.DataFrame:
    merged = frame[["report_date", signal_column]].merge(outcomes, on="report_date", how="inner")
    return pd.DataFrame(
        {
            "signal_date": pd.to_datetime(merged["signal_date"], errors="coerce"),
            "signal": pd.to_numeric(merged[signal_column], errors="coerce"),
            "return": pd.to_numeric(merged[f"forward_return_{horizon}"], errors="coerce"),
            "drawdown": pd.to_numeric(merged[f"drawdown_{horizon}"], errors="coerce"),
            "runup": pd.to_numeric(merged[f"runup_{horizon}"], errors="coerce"),
        }
    ).replace([np.inf, -np.inf], np.nan).dropna(subset=["signal_date", "signal", "return"])


def add_stability_to_results(
    results: pd.DataFrame,
    frame_lookup: dict[tuple[str, str, str], pd.DataFrame],
    outcomes_by_market: dict[str, pd.DataFrame],
    max_tests: int = 300,
) -> pd.DataFrame:
    if results.empty:
        return results
    candidates = results.loc[
        (pd.to_numeric(results["hac_p"], errors="coerce") <= 0.10)
        & (pd.to_numeric(results["fdr_q_by_horizon"], errors="coerce") <= 0.25)
        & (pd.to_numeric(results["abs_q20_edge"], errors="coerce") >= 0.50)
    ].sort_values(["fdr_q_by_horizon", "hac_p", "abs_q20_edge"], ascending=[True, True, False]).head(max_tests)
    for index, row in candidates.iterrows():
        key = (str(row["dataset"]), str(row["market"]), str(row["category"]))
        frame = frame_lookup[key]
        data = rebuild_test_data(frame, outcomes_by_market[str(row["market"])], str(row["signal"]), str(row["horizon"]))
        stats = stability_stats(data, row.get("slope_pp_per_z"))
        for column, value in stats.items():
            results.loc[index, column] = value
    return results


def classify_evidence(row: pd.Series) -> str:
    p_value = row.get("hac_p")
    q_value = row.get("fdr_q_by_horizon")
    oos_r = row.get("oos_spearman")
    oos_edge = row.get("oos_top_minus_bottom")
    era_agreement = row.get("era_sign_agreement")
    rolling_agreement = row.get("rolling_3y_sign_agreement")
    edge = abs(float(row.get("q20_top_minus_bottom") or 0.0))
    if (
        pd.notna(p_value)
        and p_value <= 0.05
        and pd.notna(q_value)
        and q_value <= 0.10
        and pd.notna(oos_r)
        and oos_r >= 0.05
        and pd.notna(oos_edge)
        and oos_edge > 0
        and pd.notna(era_agreement)
        and era_agreement >= 0.67
        and pd.notna(rolling_agreement)
        and rolling_agreement >= 0.60
        and edge >= 0.75
    ):
        return "robust"
    if (
        pd.notna(p_value)
        and p_value <= 0.10
        and pd.notna(q_value)
        and q_value <= 0.20
        and pd.notna(oos_r)
        and oos_r > 0
        and pd.notna(oos_edge)
        and oos_edge > 0
        and edge >= 0.50
    ):
        return "supported"
    if (pd.notna(p_value) and p_value <= 0.20 and edge >= 0.50) or edge >= 1.50:
        return "tentative"
    return "none"


def run_standalone_tests(
    frames: dict[tuple[str, str, str], pd.DataFrame], min_history: int
) -> tuple[pd.DataFrame, dict[str, pd.DataFrame]]:
    rows: list[dict[str, Any]] = []
    outcomes_by_market: dict[str, pd.DataFrame] = {}
    report_dates_by_market: dict[str, pd.Series] = {}
    for market in MARKETS:
        sample_key = next(key for key in frames if key[1] == market)
        report_dates_by_market[market] = frames[sample_key]["report_date"]
        outcomes_by_market[market] = build_outcomes(market, report_dates_by_market[market])

    for (dataset, market, category), frame in frames.items():
        selected = (
            SELECTED_DIVERGENCE_SIGNALS
            if frame.attrs.get("signal_family") == "divergence"
            else SELECTED_PARTICIPANT_SIGNALS
        )
        signal_columns = [column for column in selected if column in frame.columns]
        for signal_column in signal_columns:
            for horizon in HORIZONS:
                result = evaluate_signal(frame, outcomes_by_market[market], signal_column, horizon)
                if result is None:
                    continue
                result.update(
                    {
                        "dataset": dataset,
                        "dataset_label": frame.attrs.get("dataset_label", DATASETS[dataset]["label"]),
                        "market": market,
                        "market_label": MARKETS[market]["label"],
                        "category": category,
                        "category_label": frame.attrs.get("category_label", category),
                        "signal_family": frame.attrs.get("signal_family", "participant"),
                        "min_history_weeks": min_history,
                    }
                )
                rows.append(result)
    results = pd.DataFrame(rows)
    if results.empty:
        return results, outcomes_by_market
    results["global_fdr_q"] = benjamini_hochberg(results["hac_p"])
    results["fdr_q_by_horizon"] = results.groupby(
        ["market", "horizon"], group_keys=False
    )["hac_p"].apply(benjamini_hochberg)
    results["abs_spearman"] = results["spearman_r"].abs()
    results["abs_q20_edge"] = results["q20_top_minus_bottom"].abs()
    results = add_stability_to_results(results, frames, outcomes_by_market)
    results["evidence"] = results.apply(classify_evidence, axis=1)
    return results, outcomes_by_market


def feature_from(
    frames: dict[tuple[str, str, str], pd.DataFrame],
    dataset: str,
    market: str,
    category: str,
    column: str,
    output_name: str,
) -> pd.DataFrame:
    frame = frames[(dataset, market, category)]
    return frame[["report_date", column]].rename(columns={column: output_name})


def build_composite_frame(
    frames: dict[tuple[str, str, str], pd.DataFrame], market: str
) -> pd.DataFrame:
    parts = [
        feature_from(frames, "legacy", market, "noncommercial", "net_notional_bn_z", "nc_net_z"),
        feature_from(frames, "tff", market, "asset_mgr", "net_oi_pct_z", "am_net_z"),
        feature_from(frames, "tff", market, "asset_mgr", "net_notional_change_4w_z", "am_flow4_z"),
        feature_from(
            frames,
            "tff",
            market,
            "other_reportable",
            "net_oi_change_13w_z",
            "other_trend13_z",
        ),
        feature_from(
            frames,
            "tff",
            market,
            "non_reportable",
            "net_oi_change_13w_z",
            "nonreportable_trend13_z",
        ),
        feature_from(frames, "tff", market, "lev_money", "net_oi_pct_z", "lf_net_z"),
    ]
    merged = parts[0]
    for part in parts[1:]:
        merged = merged.merge(part, on="report_date", how="inner")
    merged["nc_only"] = -merged["nc_net_z"]
    merged["nc_plus_am_crowding"] = -merged["nc_net_z"] - 0.20 * merged["am_net_z"]
    merged["nc_plus_other_trend"] = -merged["nc_net_z"] - 0.30 * merged["other_trend13_z"]
    merged["nc_plus_nonreportable_trend"] = (
        -merged["nc_net_z"] - 0.20 * merged["nonreportable_trend13_z"]
    )
    merged["nc_anchored_full"] = (
        -merged["nc_net_z"]
        - 0.15 * merged["am_net_z"]
        + 0.10 * merged["am_flow4_z"]
        - 0.30 * merged["other_trend13_z"]
        - 0.15 * merged["nonreportable_trend13_z"]
        + 0.10 * merged["lf_net_z"]
    )
    return merged


def run_composite_tests(
    frames: dict[tuple[str, str, str], pd.DataFrame], outcomes_by_market: dict[str, pd.DataFrame]
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    candidates = (
        "nc_only",
        "nc_plus_am_crowding",
        "nc_plus_other_trend",
        "nc_plus_nonreportable_trend",
        "nc_anchored_full",
    )
    for market in MARKETS:
        frame = build_composite_frame(frames, market)
        for candidate in candidates:
            candidate_frame = frame[["report_date", candidate]].rename(columns={candidate: f"{candidate}_z"})
            for horizon in HORIZONS:
                result = evaluate_signal(
                    candidate_frame, outcomes_by_market[market], f"{candidate}_z", horizon
                )
                if result is None:
                    continue
                result.update(
                    {
                        "market": market,
                        "market_label": MARKETS[market]["label"],
                        "candidate": candidate,
                    }
                )
                rows.append(result)
    results = pd.DataFrame(rows)
    if results.empty:
        return results
    results["global_fdr_q"] = benjamini_hochberg(results["hac_p"])
    results["fdr_q_by_horizon"] = results.groupby(
        ["market", "horizon"], group_keys=False
    )["hac_p"].apply(benjamini_hochberg)
    results["abs_spearman"] = results["spearman_r"].abs()
    results["abs_q20_edge"] = results["q20_top_minus_bottom"].abs()
    candidates_for_stability = results.loc[
        (pd.to_numeric(results["hac_p"], errors="coerce") <= 0.10)
        & (pd.to_numeric(results["fdr_q_by_horizon"], errors="coerce") <= 0.25)
        & (pd.to_numeric(results["abs_q20_edge"], errors="coerce") >= 0.50)
    ].head(100)
    composite_cache = {market: build_composite_frame(frames, market) for market in MARKETS}
    for index, row in candidates_for_stability.iterrows():
        market = str(row["market"])
        candidate = str(row["candidate"])
        candidate_frame = composite_cache[market][["report_date", candidate]].rename(columns={candidate: f"{candidate}_z"})
        data = rebuild_test_data(candidate_frame, outcomes_by_market[market], f"{candidate}_z", str(row["horizon"]))
        stats = stability_stats(data, row.get("slope_pp_per_z"))
        for column, value in stats.items():
            results.loc[index, column] = value
    results["evidence"] = results.apply(classify_evidence, axis=1)
    return results


def ridge_fit_predict(x: np.ndarray, y: np.ndarray, x_new: np.ndarray, alpha: float) -> tuple[float, np.ndarray]:
    design = np.column_stack([np.ones(len(x)), x])
    penalty = np.eye(design.shape[1]) * alpha
    penalty[0, 0] = 0.0
    beta = np.linalg.pinv(design.T @ design + penalty) @ design.T @ y
    prediction = float(np.r_[1.0, x_new] @ beta)
    return prediction, beta


def run_purged_walk_forward_models(
    frames: dict[tuple[str, str, str], pd.DataFrame],
    outcomes_by_market: dict[str, pd.DataFrame],
    min_train: int = 156,
    alpha: float = 8.0,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    summary_rows: list[dict[str, Any]] = []
    prediction_rows: list[dict[str, Any]] = []
    feature_columns = (
        "nc_net_z",
        "am_net_z",
        "am_flow4_z",
        "other_trend13_z",
        "nonreportable_trend13_z",
        "lf_net_z",
    )
    for market in MARKETS:
        feature_frame = build_composite_frame(frames, market)
        for horizon in RIDGE_HORIZONS:
            outcome_columns = [
                "report_date",
                "signal_date",
                f"future_date_{horizon}",
                f"forward_return_{horizon}",
            ]
            data = feature_frame[["report_date", *feature_columns]].merge(
                outcomes_by_market[market][outcome_columns], on="report_date", how="inner"
            )
            data = data.rename(
                columns={
                    f"future_date_{horizon}": "future_date",
                    f"forward_return_{horizon}": "target",
                }
            )
            data["signal_date"] = pd.to_datetime(data["signal_date"], errors="coerce")
            data["future_date"] = pd.to_datetime(data["future_date"], errors="coerce")
            data = data.replace([np.inf, -np.inf], np.nan).dropna(
                subset=[*feature_columns, "signal_date", "future_date", "target"]
            ).sort_values("signal_date").reset_index(drop=True)
            local_predictions: list[dict[str, Any]] = []
            for index in range(len(data)):
                current = data.iloc[index]
                train = data.loc[data["future_date"] < current["signal_date"]]
                if len(train) < min_train:
                    continue
                x_train = train[list(feature_columns)].to_numpy(dtype=float)
                y_train = train["target"].to_numpy(dtype=float)
                x_new = current[list(feature_columns)].to_numpy(dtype=float)
                prediction, beta = ridge_fit_predict(x_train, y_train, x_new, alpha)
                drift = float(np.mean(y_train))
                row = {
                    "market": market,
                    "market_label": MARKETS[market]["label"],
                    "horizon": horizon,
                    "report_date": pd.Timestamp(current["report_date"]).date().isoformat(),
                    "signal_date": pd.Timestamp(current["signal_date"]).date().isoformat(),
                    "future_date": pd.Timestamp(current["future_date"]).date().isoformat(),
                    "actual_return": float(current["target"]),
                    "predicted_return": prediction,
                    "train_drift": drift,
                    "predicted_excess": prediction - drift,
                    "actual_excess": float(current["target"] - drift),
                    "train_n": int(len(train)),
                }
                for feature_index, feature in enumerate(feature_columns, start=1):
                    row[f"coef_{feature}"] = float(beta[feature_index])
                    row[feature] = float(current[feature])
                local_predictions.append(row)
                prediction_rows.append(row)
            pred = pd.DataFrame(local_predictions)
            if len(pred) < 40:
                continue
            low, high = pred["predicted_excess"].quantile([0.20, 0.80])
            bottom = pred.loc[pred["predicted_excess"] <= low]
            top = pred.loc[pred["predicted_excess"] >= high]
            row = {
                "market": market,
                "market_label": MARKETS[market]["label"],
                "horizon": horizon,
                "predictions": int(len(pred)),
                "first_prediction": pred["signal_date"].min(),
                "last_prediction": pred["signal_date"].max(),
                "return_correlation": corr_safe(pred["predicted_return"], pred["actual_return"], "pearson"),
                "excess_spearman": corr_safe(pred["predicted_excess"], pred["actual_excess"], "spearman"),
                "drift_adjusted_accuracy_pct": float(
                    (np.sign(pred["predicted_excess"]) == np.sign(pred["actual_excess"])).mean() * 100.0
                ),
                "top_n": int(len(top)),
                "bottom_n": int(len(bottom)),
                "top_avg_return": float(top["actual_return"].mean()),
                "bottom_avg_return": float(bottom["actual_return"].mean()),
                "top_minus_bottom": float(top["actual_return"].mean() - bottom["actual_return"].mean()),
                "top_hit_rate": float((top["actual_return"] > 0).mean() * 100.0),
                "bottom_hit_rate": float((bottom["actual_return"] > 0).mean() * 100.0),
                "ridge_alpha": alpha,
            }
            for feature in feature_columns:
                row[f"median_coef_{feature}"] = float(pred[f"coef_{feature}"].median())
                nonzero = pred[f"coef_{feature}"].replace(0, np.nan).dropna()
                row[f"coef_sign_stability_{feature}"] = (
                    float((np.sign(nonzero) == np.sign(nonzero.median())).mean()) if len(nonzero) else None
                )
            summary_rows.append(row)
    return pd.DataFrame(summary_rows), pd.DataFrame(prediction_rows)


def current_signal_snapshot(
    frames: dict[tuple[str, str, str], pd.DataFrame]
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    selected = (
        "net_oi_pct_z",
        "net_notional_bn_z",
        "net_oi_change_1w_z",
        "net_oi_change_4w_z",
        "net_oi_change_13w_z",
        "net_notional_change_4w_z",
        "net_notional_change_13w_z",
        "net_oi_pct_pctile",
        "net_notional_bn_pctile",
    )
    for (dataset, market, category), frame in frames.items():
        valid = frame.dropna(subset=["report_date"])
        if valid.empty:
            continue
        latest = valid.iloc[-1]
        row = {
            "dataset": dataset,
            "dataset_label": frame.attrs.get("dataset_label", DATASETS[dataset]["label"]),
            "market": market,
            "market_label": MARKETS[market]["label"],
            "category": category,
            "category_label": frame.attrs.get("category_label", category),
            "report_date": pd.Timestamp(latest["report_date"]).date().isoformat(),
        }
        for column in selected:
            if column in latest.index:
                row[column] = latest[column]
        rows.append(row)
    return pd.DataFrame(rows)


def markdown_table(df: pd.DataFrame, columns: Iterable[str], max_rows: int = 20) -> str:
    selected = df.loc[:, [column for column in columns if column in df.columns]].head(max_rows).copy()
    if selected.empty:
        return "_No qualifying rows._"
    for column in selected.columns:
        if pd.api.types.is_float_dtype(selected[column]):
            selected[column] = selected[column].map(
                lambda value: "" if pd.isna(value) else f"{float(value):.3f}"
            )
        else:
            selected[column] = selected[column].fillna("").astype(str)
    header = "| " + " | ".join(selected.columns) + " |"
    separator = "| " + " | ".join(["---"] * len(selected.columns)) + " |"
    rows = ["| " + " | ".join(row) + " |" for row in selected.astype(str).to_numpy().tolist()]
    return "\n".join([header, separator, *rows])


def build_report(
    standalone: pd.DataFrame,
    composites: pd.DataFrame,
    ridge_summary: pd.DataFrame,
    current: pd.DataFrame,
    sources: list[dict[str, Any]],
    min_history: int,
) -> str:
    evidence_rank = {"robust": 0, "supported": 1, "tentative": 2, "none": 3}
    ranked = standalone.copy()
    ranked["evidence_rank"] = ranked["evidence"].map(evidence_rank).fillna(9)
    ranked = ranked.sort_values(
        ["evidence_rank", "fdr_q_by_horizon", "hac_p", "abs_q20_edge"],
        ascending=[True, True, True, False],
    )
    asset_manager = ranked.loc[
        (ranked["dataset"] == "tff") & (ranked["category"] == "asset_mgr")
    ]
    short_term = ranked.loc[ranked["horizon"].isin(["1d", "3d", "1w", "2w", "3w", "4w"])]
    category_best = (
        ranked.sort_values(["evidence_rank", "fdr_q_by_horizon", "abs_q20_edge"], ascending=[True, True, False])
        .groupby(["dataset_label", "market_label", "category_label"], as_index=False)
        .first()
    )
    composite_ranked = composites.copy()
    if not composite_ranked.empty:
        composite_ranked["evidence_rank"] = composite_ranked["evidence"].map(evidence_rank).fillna(9)
        composite_ranked = composite_ranked.sort_values(
            ["evidence_rank", "fdr_q_by_horizon", "hac_p", "abs_q20_edge"],
            ascending=[True, True, True, False],
        )

    lines = [
        "# Extended COT Predictivity Backtest",
        "",
        f"Generated: {datetime.now(UTC).isoformat()}",
        "",
        "## Scope and safeguards",
        "",
        f"- Strict prior-only standardization with a {min_history}-week warmup.",
        "- Signals become tradable on the first market close on or after normal Friday publication.",
        "- Horizons: " + ", ".join(HORIZONS),
        "- HAC inference for overlapping returns, FDR correction, chronological OOS testing, era stability, and rolling three-year stability.",
        "- TFF Nonreportable is treated as a small-trader/retail proxy, not as a verified pure-retail category.",
        "",
        "## Source coverage",
        "",
        markdown_table(pd.DataFrame(sources), ["dataset_label", "market_label", "path", "rows", "first_date", "last_date"], 20),
        "",
        "## Highest-quality standalone findings",
        "",
        markdown_table(
            ranked.loc[ranked["evidence"].isin(["robust", "supported", "tentative"])],
            [
                "evidence",
                "dataset_label",
                "market_label",
                "category_label",
                "signal",
                "horizon",
                "n",
                "spearman_r",
                "hac_p",
                "fdr_q_by_horizon",
                "q20_top_minus_bottom",
                "oos_spearman",
                "oos_top_minus_bottom",
                "era_sign_agreement",
                "rolling_3y_sign_agreement",
            ],
            40,
        ),
        "",
        "## Best short-term signals (1 day to 4 weeks)",
        "",
        markdown_table(
            short_term,
            [
                "evidence",
                "dataset_label",
                "market_label",
                "category_label",
                "signal",
                "horizon",
                "spearman_r",
                "hac_p",
                "fdr_q_by_horizon",
                "q20_top_minus_bottom",
                "oos_spearman",
                "oos_top_minus_bottom",
            ],
            35,
        ),
        "",
        "## Asset Manager / Institutional results",
        "",
        markdown_table(
            asset_manager,
            [
                "evidence",
                "market_label",
                "signal",
                "horizon",
                "spearman_r",
                "hac_p",
                "fdr_q_by_horizon",
                "q20_top_minus_bottom",
                "oos_spearman",
                "oos_top_minus_bottom",
                "era_sign_agreement",
            ],
            30,
        ),
        "",
        "## Best result by participant category",
        "",
        markdown_table(
            category_best,
            [
                "dataset_label",
                "market_label",
                "category_label",
                "evidence",
                "signal",
                "horizon",
                "spearman_r",
                "hac_p",
                "fdr_q_by_horizon",
                "q20_top_minus_bottom",
                "oos_spearman",
            ],
            30,
        ),
        "",
        "## Fixed Non-Commercial-anchored composite tests",
        "",
        markdown_table(
            composite_ranked,
            [
                "evidence",
                "market_label",
                "candidate",
                "horizon",
                "spearman_r",
                "hac_p",
                "fdr_q_by_horizon",
                "q20_top_minus_bottom",
                "oos_spearman",
                "oos_top_minus_bottom",
            ],
            35,
        ),
        "",
        "## Purged expanding walk-forward ridge model",
        "",
        markdown_table(
            ridge_summary.sort_values(["market", "horizon"]) if not ridge_summary.empty else ridge_summary,
            [
                "market_label",
                "horizon",
                "predictions",
                "excess_spearman",
                "drift_adjusted_accuracy_pct",
                "top_minus_bottom",
                "top_hit_rate",
                "bottom_hit_rate",
                "median_coef_nc_net_z",
                "median_coef_am_net_z",
                "median_coef_am_flow4_z",
                "median_coef_other_trend13_z",
                "median_coef_nonreportable_trend13_z",
                "median_coef_lf_net_z",
            ],
            20,
        ),
        "",
        "## Latest standardized participant readings",
        "",
        markdown_table(
            current,
            [
                "report_date",
                "dataset_label",
                "market_label",
                "category_label",
                "net_oi_pct_z",
                "net_notional_bn_z",
                "net_oi_change_4w_z",
                "net_oi_change_13w_z",
                "net_oi_pct_pctile",
            ],
            30,
        ),
        "",
        "## Interpretation rules",
        "",
        "1. A low p-value without FDR survival is exploratory, not decision-grade.",
        "2. A full-sample relationship that fails chronological OOS or regime-stability checks should not receive meaningful model weight.",
        "3. Non-Commercial remains the structural anchor; TFF categories are retained only when they add stable OOS information.",
        "4. Caution signals are primarily exposure and timing controls, not automatic short instructions.",
        "",
        "## Caveats",
        "",
        "- COT is weekly and delayed; even the 1–3 day horizons begin after Friday publication.",
        "- Long-horizon observations overlap, although HAC statistics and purged walk-forward training reduce the main inference problems.",
        "- TFF category classifications can change as trader business models change.",
        "- Nonreportable is a residual below reporting thresholds and cannot be assigned a known retail percentage.",
        "- Composite weights are fixed hypotheses. The ridge model is reported separately and is not allowed to train on unavailable outcomes.",
    ]
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--min-history", type=int, default=104)
    parser.add_argument("--ridge-min-train", type=int, default=156)
    parser.add_argument("--ridge-alpha", type=float, default=8.0)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    OUTDIR.mkdir(parents=True, exist_ok=True)

    participant_frames, sources = build_all_signal_frames(args.min_history)
    divergence_frames = build_divergence_frames(participant_frames, args.min_history)
    all_frames = {**participant_frames, **divergence_frames}

    standalone, outcomes_by_market = run_standalone_tests(all_frames, args.min_history)
    composites = run_composite_tests(participant_frames, outcomes_by_market)
    ridge_summary, ridge_predictions = run_purged_walk_forward_models(
        participant_frames,
        outcomes_by_market,
        min_train=args.ridge_min_train,
        alpha=args.ridge_alpha,
    )
    current = current_signal_snapshot(participant_frames)

    evidence_rank = {"robust": 0, "supported": 1, "tentative": 2, "none": 3}
    top = standalone.copy()
    if not top.empty:
        top["evidence_rank"] = top["evidence"].map(evidence_rank).fillna(9)
        top = top.sort_values(
            ["evidence_rank", "fdr_q_by_horizon", "hac_p", "abs_q20_edge"],
            ascending=[True, True, True, False],
        ).head(250)

    report = build_report(standalone, composites, ridge_summary, current, sources, args.min_history)
    methodology = {
        "generated_at": datetime.now(UTC).isoformat(),
        "min_history_weeks": args.min_history,
        "ridge_min_train": args.ridge_min_train,
        "ridge_alpha": args.ridge_alpha,
        "horizons": HORIZONS,
        "tail_quantiles": TAIL_QUANTILES,
        "release_alignment": "Tuesday report date plus three calendar days, first price close on or after",
        "standardization": "prior-only expanding z-score and percentile",
        "multiple_testing": "Benjamini-Hochberg globally and within market/horizon",
        "oos": "chronological 70/30 split with train-defined orientation and thresholds",
        "walk_forward": "purged expanding ridge; training outcomes must be known before prediction date",
        "source_files": sources,
    }

    standalone.to_csv(OUTDIR / "standalone_signal_results.csv", index=False)
    top.to_csv(OUTDIR / "standalone_top_findings.csv", index=False)
    composites.to_csv(OUTDIR / "fixed_composite_results.csv", index=False)
    ridge_summary.to_csv(OUTDIR / "walk_forward_ridge_summary.csv", index=False)
    ridge_predictions.to_csv(OUTDIR / "walk_forward_ridge_predictions.csv", index=False)
    current.to_csv(OUTDIR / "latest_participant_signals.csv", index=False)
    for market, outcomes in outcomes_by_market.items():
        outcomes.to_csv(OUTDIR / f"{market}_release_aligned_outcomes.csv", index=False)
    (OUTDIR / "extended_backtest_report.md").write_text(report, encoding="utf-8")
    (OUTDIR / "methodology.json").write_text(json.dumps(methodology, indent=2), encoding="utf-8")

    print(f"Saved outputs to {OUTDIR}")
    print(f"Standalone tests: {len(standalone):,}")
    print(f"Composite tests: {len(composites):,}")
    print(f"Walk-forward predictions: {len(ridge_predictions):,}")
    if not top.empty:
        display_columns = [
            "evidence",
            "dataset_label",
            "market_label",
            "category_label",
            "signal",
            "horizon",
            "spearman_r",
            "hac_p",
            "fdr_q_by_horizon",
            "q20_top_minus_bottom",
            "oos_spearman",
            "oos_top_minus_bottom",
        ]
        print(top[display_columns].head(30).to_string(index=False))


if __name__ == "__main__":
    main()
