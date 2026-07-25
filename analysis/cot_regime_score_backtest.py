#!/usr/bin/env python3
"""
Walk-forward backtest for the COT regime-score rules.

The backtest intentionally uses only TFF Detailed COT rules from
config/regime_rules.json. COT rows are Tuesday "as of" observations, but signals
are shifted to the first available market close on or after the Friday release
date.
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from datetime import UTC, datetime

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parent
CONFIG = ROOT / "config" / "regime_rules.json"
DATA_DIR = ROOT / "cot_exact_output"
OUT_DIR = ROOT / "cot_regime_backtest_output"
DATASET_LABEL = "TFF Detailed"

CATEGORIES = ("asset_mgr", "dealer", "lev_money", "other_reportable", "non_reportable")
MARKETS = {
    "sp500": {
        "label": "S&P 500",
        "price_file": PROJECT / "data" / "SP500.csv",
        "price_col": "SP500",
        "cot_glob": "sp500_exact_consolidated_data_*.csv",
    },
    "nq": {
        "label": "NASDAQ-100",
        "price_file": PROJECT / "data" / "NASDAQ100.csv",
        "price_col": "NASDAQ100",
        "cot_glob": "nq_exact_consolidated_data_*.csv",
    },
}
HORIZONS = {
    "1d": 1,
    "2d": 2,
    "3d": 3,
    "1w": 5,
    "2w": 10,
    "4w": 20,
    "13w": 65,
    "26w": 130,
    "52w": 260,
}


@dataclass(frozen=True)
class HorizonResult:
    future_date: pd.Timestamp | None
    future_price: float | None
    return_pct: float | None
    drawdown_pct: float | None


def latest_file(pattern: str) -> Path:
    matches = sorted(DATA_DIR.glob(pattern), key=lambda p: p.stat().st_mtime)
    if not matches:
        raise FileNotFoundError(f"No COT files match {DATA_DIR / pattern}")
    return matches[-1]


def load_rules() -> dict[str, list[dict[str, Any]]]:
    payload = json.loads(CONFIG.read_text(encoding="utf-8"))
    return {
        market: [rule for rule in rules if (rule.get("source") or "cot") == "cot"]
        for market, rules in payload.items()
    }


def load_cot(market: str) -> pd.DataFrame:
    path = latest_file(str(MARKETS[market]["cot_glob"]))
    df = pd.read_csv(path)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)
    required = [f"{category}_net_oi_pct" for category in CATEGORIES]
    missing = [col for col in required if col not in df.columns]
    if missing:
        raise KeyError(f"{path} is missing required columns: {missing}")
    return df


def load_prices(market: str) -> pd.DataFrame:
    cfg = MARKETS[market]
    df = pd.read_csv(cfg["price_file"])
    df.columns = [col.strip().lstrip("\ufeff") for col in df.columns]
    date_col = "observation_date" if "observation_date" in df.columns else "date"
    value_col = cfg["price_col"] if cfg["price_col"] in df.columns else [c for c in df.columns if c != date_col][0]
    out = pd.DataFrame(
        {
            "date": pd.to_datetime(df[date_col], errors="coerce"),
            "price": pd.to_numeric(df[value_col].replace(".", pd.NA), errors="coerce"),
        }
    ).dropna()
    return out.sort_values("date").reset_index(drop=True)


def percentile_rank(history: pd.Series, value: float) -> float | None:
    clean = pd.to_numeric(history, errors="coerce").dropna().sort_values()
    if clean.empty or not math.isfinite(value):
        return None
    less = int((clean < value).sum())
    equal = int((clean == value).sum())
    avg_rank = ((less + 1) + (less + max(equal, 1))) / 2
    return float(avg_rank / len(clean) * 100)


def triggered(rule: dict[str, Any], percentile: float | None) -> bool:
    if percentile is None or not math.isfinite(percentile):
        return False
    threshold = float(rule["threshold"])
    if rule["side"] == "high":
        return percentile >= threshold
    return percentile <= threshold


def score_regime(
    market: str,
    cot: pd.DataFrame,
    index: int,
    rules: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    row = cot.iloc[index]
    history = cot.iloc[: index + 1]
    score = 0.0
    trigger_rows: list[dict[str, Any]] = []
    out: dict[str, Any] = {}

    for category in CATEGORIES:
        value = float(row[f"{category}_net_oi_pct"])
        pct = percentile_rank(history[f"{category}_net_oi_pct"], value)
        contribution = 0.0
        active: list[str] = []
        for rule in rules.get(market, []):
            if rule["key"] != category:
                continue
            if triggered(rule, pct):
                weight = float(rule.get("weight", 0.0))
                contribution += weight
                trigger_rows.append(
                    {
                        "key": category,
                        "percentile": pct,
                        "weight": weight,
                        "reason": rule.get("reason", ""),
                        "role": rule.get("role", ""),
                        "side": rule.get("side", ""),
                        "threshold": rule.get("threshold"),
                    }
                )
                active.append(f"{rule.get('reason', category)} ({weight:+.2f})")
        score += contribution
        out[f"{category}_net_oi_pct"] = round(value, 6)
        out[f"{category}_percentile"] = round(pct, 6) if pct is not None else None
        out[f"{category}_score"] = round(contribution, 6)
        out[f"{category}_triggers"] = "; ".join(active)

    out["score"] = round(score, 6)
    out["bucket"] = regime_bucket(score)
    out["trigger_count"] = len(trigger_rows)
    out["high_conviction_triggers"] = sum(1 for hit in trigger_rows if abs(float(hit["weight"])) >= 1.0)
    out["trigger_detail"] = "; ".join(
        f"{hit['key']} {hit['percentile']:.1f}% {hit['weight']:+.2f} {hit['reason']}"
        for hit in trigger_rows
    )
    return out


def regime_bucket(score: float) -> str:
    if score >= 2:
        return "Risk-On"
    if score <= -2:
        return "Caution"
    return "Mixed"


def score_sign_bucket(score: float) -> str:
    if score > 0:
        return "Positive"
    if score < 0:
        return "Negative"
    return "Zero"


def score_intensity_bucket(score: float) -> str:
    if score >= 3:
        return "Extreme Positive"
    if score >= 2:
        return "Risk-On"
    if score > 0:
        return "Mild Positive"
    if score == 0:
        return "Zero"
    if score > -2:
        return "Mild Negative"
    if score > -3:
        return "Caution"
    return "Extreme Negative"


def first_price_on_or_after(prices: pd.DataFrame, target: pd.Timestamp) -> int | None:
    dates = prices["date"].to_numpy(dtype="datetime64[ns]")
    index = int(np.searchsorted(dates, np.datetime64(target), side="left"))
    if index >= len(prices):
        return None
    return index


def horizon_return(prices: pd.DataFrame, start_index: int, steps: int) -> HorizonResult:
    end = start_index + steps
    if end >= len(prices):
        return HorizonResult(None, None, None, None)
    start_price = float(prices.iloc[start_index]["price"])
    future_price = float(prices.iloc[end]["price"])
    if not math.isfinite(start_price) or not math.isfinite(future_price) or start_price == 0:
        return HorizonResult(None, None, None, None)
    window = pd.to_numeric(prices.iloc[start_index : end + 1]["price"], errors="coerce").dropna()
    drawdown = float(window.min() / start_price - 1) * 100 if not window.empty else None
    return HorizonResult(
        future_date=prices.iloc[end]["date"],
        future_price=future_price,
        return_pct=float(future_price / start_price - 1) * 100,
        drawdown_pct=drawdown,
    )


def build_histories(min_lookback: int, rules: dict[str, list[dict[str, Any]]]) -> tuple[pd.DataFrame, pd.DataFrame]:
    history_rows: list[dict[str, Any]] = []
    forward_rows: list[dict[str, Any]] = []

    for market in MARKETS:
        cot = load_cot(market)
        prices = load_prices(market)
        for index in range(len(cot)):
            if index + 1 < min_lookback:
                continue
            report_date = cot.iloc[index]["date"]
            release_target = report_date + pd.Timedelta(days=3)
            price_index = first_price_on_or_after(prices, release_target)
            if price_index is None:
                continue

            score = score_regime(market, cot, index, rules)
            signal_date = prices.iloc[price_index]["date"]
            signal_price = float(prices.iloc[price_index]["price"])
            base = {
                "market": market,
                "market_label": MARKETS[market]["label"],
                "report_date": report_date.date().isoformat(),
                "release_target_date": release_target.date().isoformat(),
                "signal_date": signal_date.date().isoformat(),
                "signal_price": round(signal_price, 6),
                "lookback_weeks": index + 1,
                **score,
            }
            history_rows.append(base)

            for label, steps in HORIZONS.items():
                result = horizon_return(prices, price_index, steps)
                forward_rows.append(
                    {
                        "market": market,
                        "market_label": MARKETS[market]["label"],
                        "report_date": base["report_date"],
                        "release_target_date": base["release_target_date"],
                        "signal_date": base["signal_date"],
                        "signal_price": base["signal_price"],
                        "horizon": label,
                        "horizon_trading_days": steps,
                        "future_date": result.future_date.date().isoformat() if result.future_date is not None else None,
                        "future_price": round(result.future_price, 6) if result.future_price is not None else None,
                        "forward_return_pct": round(result.return_pct, 6) if result.return_pct is not None else None,
                        "drawdown_pct": round(result.drawdown_pct, 6) if result.drawdown_pct is not None else None,
                        "score": base["score"],
                        "regime_bucket": base["bucket"],
                        "score_sign": score_sign_bucket(base["score"]),
                        "score_intensity": score_intensity_bucket(base["score"]),
                        "trigger_count": base["trigger_count"],
                        "high_conviction_triggers": base["high_conviction_triggers"],
                    }
                )

    return pd.DataFrame(history_rows), pd.DataFrame(forward_rows)


def normal_approx_p_value(t_stat: float | None) -> float | None:
    if t_stat is None or not math.isfinite(t_stat):
        return None
    return float(math.erfc(abs(t_stat) / math.sqrt(2)))


def welch_t_stat(left: pd.Series, right: pd.Series) -> float | None:
    left = pd.to_numeric(left, errors="coerce").dropna()
    right = pd.to_numeric(right, errors="coerce").dropna()
    if len(left) < 2 or len(right) < 2:
        return None
    denom = left.var(ddof=1) / len(left) + right.var(ddof=1) / len(right)
    if denom <= 0 or not math.isfinite(denom):
        return None
    return float((left.mean() - right.mean()) / math.sqrt(denom))


def metric_row(
    market: str,
    horizon: str,
    bucket_type: str,
    bucket: str,
    group: pd.DataFrame,
    universe: pd.DataFrame,
) -> dict[str, Any]:
    returns = pd.to_numeric(group["forward_return_pct"], errors="coerce").dropna()
    drawdowns = pd.to_numeric(group["drawdown_pct"], errors="coerce").dropna()
    all_returns = pd.to_numeric(universe["forward_return_pct"], errors="coerce").dropna()
    rest = universe.loc[~universe.index.isin(group.index), "forward_return_pct"]
    avg_return = float(returns.mean()) if len(returns) else None
    volatility = float(returns.std(ddof=1)) if len(returns) > 1 else None
    t_stat = welch_t_stat(returns, rest)
    unconditional = float(all_returns.mean()) if len(all_returns) else None
    return {
        "market": market,
        "market_label": MARKETS[market]["label"],
        "horizon": horizon,
        "bucket_type": bucket_type,
        "bucket": bucket,
        "observations": int(len(returns)),
        "avg_return_pct": round(avg_return, 6) if avg_return is not None else None,
        "median_return_pct": round(float(returns.median()), 6) if len(returns) else None,
        "hit_rate_pct": round(float((returns > 0).mean() * 100), 6) if len(returns) else None,
        "avg_drawdown_pct": round(float(drawdowns.mean()), 6) if len(drawdowns) else None,
        "worst_drawdown_pct": round(float(drawdowns.min()), 6) if len(drawdowns) else None,
        "volatility_pct": round(volatility, 6) if volatility is not None else None,
        "sharpe_like": round(avg_return / volatility, 6) if avg_return is not None and volatility and volatility > 0 else None,
        "unconditional_avg_return_pct": round(unconditional, 6) if unconditional is not None else None,
        "diff_vs_unconditional_pct": round(avg_return - unconditional, 6)
        if avg_return is not None and unconditional is not None
        else None,
        "welch_t_stat_vs_rest": round(t_stat, 6) if t_stat is not None else None,
        "approx_p_value_vs_rest": round(normal_approx_p_value(t_stat), 6)
        if t_stat is not None
        else None,
    }


def build_bucket_summary(forward: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    bucket_specs = (
        ("regime", "regime_bucket"),
        ("score_sign", "score_sign"),
        ("score_intensity", "score_intensity"),
    )
    clean = forward.dropna(subset=["forward_return_pct"]).copy()
    for (market, horizon), universe in clean.groupby(["market", "horizon"], sort=False):
        for bucket_type, column in bucket_specs:
            for bucket, group in universe.groupby(column, sort=False):
                rows.append(metric_row(str(market), str(horizon), bucket_type, str(bucket), group, universe))
    return pd.DataFrame(rows)


def correlation(x: pd.Series, y: pd.Series) -> float | None:
    data = pd.DataFrame({"x": x, "y": y}).dropna()
    if len(data) < 3 or data["x"].nunique() < 2 or data["y"].nunique() < 2:
        return None
    return float(data["x"].corr(data["y"]))


def horizon_hac_lags(horizon: str) -> int:
    """Use enough Newey-West lags to cover overlapping weekly signal windows."""
    trading_days = int(HORIZONS[horizon])
    return max(1, int(math.ceil(trading_days / 5)) - 1)


def newey_west_slope_stats(
    y: pd.Series,
    x: pd.Series,
    lags: int,
) -> tuple[float | None, float | None, float | None]:
    """Return OLS slope, HAC t-statistic, and normal-approximation p-value."""
    data = pd.DataFrame({"y": y, "x": x}).dropna()
    if len(data) < max(12, lags + 4) or data["x"].nunique() < 2:
        return None, None, None

    y_values = data["y"].to_numpy(dtype=float)
    x_values = data["x"].to_numpy(dtype=float)
    design = np.column_stack([np.ones(len(data)), x_values])
    xtx_inv = np.linalg.pinv(design.T @ design)
    beta = xtx_inv @ design.T @ y_values
    residuals = y_values - design @ beta

    meat = np.zeros((2, 2), dtype=float)
    for index in range(len(data)):
        row = design[index][:, None]
        meat += residuals[index] ** 2 * (row @ row.T)

    usable_lags = min(max(int(lags), 0), len(data) - 2)
    for lag in range(1, usable_lags + 1):
        weight = 1.0 - lag / (usable_lags + 1.0)
        for index in range(lag, len(data)):
            current = design[index][:, None]
            prior = design[index - lag][:, None]
            covariance_term = residuals[index] * residuals[index - lag]
            meat += weight * covariance_term * (current @ prior.T + prior @ current.T)

    covariance = xtx_inv @ meat @ xtx_inv
    if len(data) > 2:
        covariance *= len(data) / (len(data) - 2)
    variance = float(covariance[1, 1])
    slope = float(beta[1])
    if variance <= 0 or not math.isfinite(variance):
        return slope, None, None
    t_stat = slope / math.sqrt(variance)
    return slope, float(t_stat), normal_approx_p_value(float(t_stat))


def drift_adjusted_accuracy(group: pd.DataFrame, min_history: int = 52) -> tuple[int, float | None]:
    """Measure whether score sign predicts above/below the prior expanding return drift."""
    ordered = group.sort_values("signal_date").copy()
    returns = pd.to_numeric(ordered["forward_return_pct"], errors="coerce")
    scores = pd.to_numeric(ordered["score"], errors="coerce")
    prior_drift = returns.expanding(min_periods=min_history).mean().shift(1)
    excess = returns - prior_drift
    valid = returns.notna() & scores.notna() & scores.ne(0) & prior_drift.notna() & excess.ne(0)
    if not valid.any():
        return 0, None
    correct = np.sign(scores[valid]) == np.sign(excess[valid])
    return int(valid.sum()), float(correct.mean() * 100.0)


def predictivity_grade(
    risk_caution_diff: float | None,
    risk_caution_p: float | None,
    min_bucket_n: int,
    score_corr: float | None,
    score_p: float | None,
) -> str:
    if min_bucket_n < 20 or risk_caution_diff is None:
        return "Insufficient"
    if risk_caution_diff < 0 and risk_caution_p is not None and risk_caution_p <= 0.10:
        return "Contradictory"
    if risk_caution_diff > 0 and risk_caution_p is not None and risk_caution_p <= 0.05:
        return "Supported"
    if risk_caution_diff > 0 and risk_caution_p is not None and risk_caution_p <= 0.10:
        return "Tentative"
    if score_corr is not None and score_corr > 0 and score_p is not None and score_p <= 0.10:
        return "Weak"
    return "Unclear"


def permutation_p_value(scores: np.ndarray, returns: np.ndarray, observed: float, rng: np.random.Generator, n: int) -> float | None:
    if not math.isfinite(observed) or len(scores) < 5 or n <= 0:
        return None
    extreme = 0
    for _ in range(n):
        permuted = rng.permutation(returns)
        value = np.corrcoef(scores, permuted)[0, 1]
        if math.isfinite(value) and abs(value) >= abs(observed):
            extreme += 1
    return float((extreme + 1) / (n + 1))


def bootstrap_mean_diff(
    left: np.ndarray,
    right: np.ndarray,
    rng: np.random.Generator,
    n: int,
) -> tuple[float | None, float | None]:
    if len(left) < 2 or len(right) < 2 or n <= 0:
        return None, None
    values = []
    for _ in range(n):
        l = rng.choice(left, size=len(left), replace=True)
        r = rng.choice(right, size=len(right), replace=True)
        values.append(float(np.mean(l) - np.mean(r)))
    return float(np.percentile(values, 2.5)), float(np.percentile(values, 97.5))


def build_predictivity_summary(forward: pd.DataFrame, permutations: int, seed: int) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    clean = forward.dropna(subset=["forward_return_pct", "score"]).copy()
    rng = np.random.default_rng(seed)

    for (market, horizon), group in clean.groupby(["market", "horizon"], sort=False):
        group = group.sort_values("signal_date").copy()
        returns = pd.to_numeric(group["forward_return_pct"], errors="coerce")
        scores = pd.to_numeric(group["score"], errors="coerce")
        corr = correlation(scores, returns)
        pos = group.loc[group["score"] > 0, "forward_return_pct"].dropna().to_numpy(dtype=float)
        neg = group.loc[group["score"] < 0, "forward_return_pct"].dropna().to_numpy(dtype=float)
        risk_on = group.loc[group["score"] >= 2, "forward_return_pct"].dropna().to_numpy(dtype=float)
        caution = group.loc[group["score"] <= -2, "forward_return_pct"].dropna().to_numpy(dtype=float)
        extreme = group.loc[group["score"].abs() >= 3, "forward_return_pct"].dropna()
        mild = group.loc[(group["score"].abs() > 0) & (group["score"].abs() < 2), "forward_return_pct"].dropna()
        score_values = scores.to_numpy(dtype=float)
        return_values = returns.to_numpy(dtype=float)
        pos_neg_diff = float(np.mean(pos) - np.mean(neg)) if len(pos) and len(neg) else None
        risk_caution_diff = float(np.mean(risk_on) - np.mean(caution)) if len(risk_on) and len(caution) else None
        ci_low, ci_high = bootstrap_mean_diff(pos, neg, rng, permutations)
        hac_lags = horizon_hac_lags(str(horizon))
        score_slope, score_hac_t, score_hac_p = newey_west_slope_stats(returns, scores, hac_lags)
        directional = group.loc[(group["score"] >= 2) | (group["score"] <= -2)].copy()
        directional_indicator = (pd.to_numeric(directional["score"], errors="coerce") >= 2).astype(float)
        _, risk_caution_hac_t, risk_caution_hac_p = newey_west_slope_stats(
            pd.to_numeric(directional["forward_return_pct"], errors="coerce"),
            directional_indicator,
            hac_lags,
        )
        accuracy_n, accuracy_pct = drift_adjusted_accuracy(group)
        min_bucket_n = min(len(risk_on), len(caution))
        grade = predictivity_grade(
            risk_caution_diff,
            risk_caution_hac_p,
            min_bucket_n,
            corr,
            score_hac_p,
        )
        rows.append(
            {
                "market": market,
                "market_label": MARKETS[str(market)]["label"],
                "horizon": horizon,
                "observations": int(len(group)),
                "score_return_corr": round(corr, 6) if corr is not None else None,
                "score_return_ols_slope": round(score_slope, 6) if score_slope is not None else None,
                "score_return_hac_t": round(score_hac_t, 6) if score_hac_t is not None else None,
                "score_return_hac_p_value": round(score_hac_p, 6) if score_hac_p is not None else None,
                "hac_lags": int(hac_lags),
                "corr_permutation_p_value": round(
                    permutation_p_value(score_values, return_values, corr, rng, permutations), 6
                )
                if corr is not None
                else None,
                "positive_score_observations": int(len(pos)),
                "negative_score_observations": int(len(neg)),
                "positive_minus_negative_avg_return_pct": round(pos_neg_diff, 6) if pos_neg_diff is not None else None,
                "positive_minus_negative_welch_t": round(welch_t_stat(pd.Series(pos), pd.Series(neg)), 6)
                if len(pos) and len(neg)
                else None,
                "positive_minus_negative_bootstrap_ci_low_pct": round(ci_low, 6) if ci_low is not None else None,
                "positive_minus_negative_bootstrap_ci_high_pct": round(ci_high, 6) if ci_high is not None else None,
                "risk_on_observations": int(len(risk_on)),
                "caution_observations": int(len(caution)),
                "risk_on_minus_caution_avg_return_pct": round(risk_caution_diff, 6)
                if risk_caution_diff is not None
                else None,
                "risk_on_minus_caution_welch_t": round(welch_t_stat(pd.Series(risk_on), pd.Series(caution)), 6)
                if len(risk_on) and len(caution)
                else None,
                "risk_on_minus_caution_hac_t": round(risk_caution_hac_t, 6)
                if risk_caution_hac_t is not None
                else None,
                "risk_on_minus_caution_hac_p_value": round(risk_caution_hac_p, 6)
                if risk_caution_hac_p is not None
                else None,
                "minimum_directional_bucket_observations": int(min_bucket_n),
                "drift_adjusted_observations": int(accuracy_n),
                "drift_adjusted_accuracy_pct": round(accuracy_pct, 6) if accuracy_pct is not None else None,
                "evidence_grade": grade,
                "extreme_score_observations": int(len(extreme)),
                "mild_score_observations": int(len(mild)),
                "extreme_avg_abs_return_pct": round(float(extreme.abs().mean()), 6) if len(extreme) else None,
                "mild_avg_abs_return_pct": round(float(mild.abs().mean()), 6) if len(mild) else None,
                "extreme_minus_mild_abs_return_pct": round(float(extreme.abs().mean() - mild.abs().mean()), 6)
                if len(extreme) and len(mild)
                else None,
            }
        )
    return pd.DataFrame(rows)


def write_outputs(history: pd.DataFrame, forward: pd.DataFrame, bucket: pd.DataFrame, predictivity: pd.DataFrame) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    history.to_csv(OUT_DIR / "regime_score_history.csv", index=False)
    forward.to_csv(OUT_DIR / "regime_forward_returns.csv", index=False)
    bucket.to_csv(OUT_DIR / "regime_bucket_summary.csv", index=False)
    predictivity.to_csv(OUT_DIR / "regime_predictivity_summary.csv", index=False)


def markdown_table(headers: list[str], rows: list[list[Any]]) -> str:
    def cell(value: Any) -> str:
        if value is None or (isinstance(value, float) and math.isnan(value)):
            return "n/a"
        return str(value).replace("|", "\\|")
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    lines.extend("| " + " | ".join(cell(value) for value in row) + " |" for row in rows)
    return "\n".join(lines)


def write_analysis_report(history: pd.DataFrame, bucket: pd.DataFrame, predictivity: pd.DataFrame) -> None:
    generated = datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
    current_rows: list[list[Any]] = []
    cutoff_rows: list[list[Any]] = []
    for market, rows in history.groupby("market", sort=False):
        latest = rows.sort_values("report_date").iloc[-1]
        prices = load_prices(str(market))
        cutoff_rows.append([
            MARKETS[str(market)]["label"],
            pd.to_datetime(rows["report_date"]).max().date(),
            pd.to_datetime(rows["signal_date"]).max().date(),
            prices["date"].max().date(),
            len(rows),
        ])
        current_rows.append([
            MARKETS[str(market)]["label"],
            pd.to_datetime(latest["report_date"]).date(),
            pd.to_datetime(latest["signal_date"]).date(),
            f"{float(latest['score']):+.2f}",
            latest["bucket"],
            latest.get("trigger_detail") or "No active extreme trigger",
        ])

    bucket_view = bucket[
        bucket["bucket_type"].eq("regime") & bucket["horizon"].isin(["4w", "13w", "26w"])
    ].copy()
    bucket_rows = [[
        row.market_label,
        row.horizon,
        row.bucket,
        int(row.observations),
        f"{float(row.avg_return_pct):+.2f}%" if pd.notna(row.avg_return_pct) else "n/a",
        f"{float(row.hit_rate_pct):.1f}%" if pd.notna(row.hit_rate_pct) else "n/a",
        f"{float(row.avg_drawdown_pct):+.2f}%" if pd.notna(row.avg_drawdown_pct) else "n/a",
    ] for row in bucket_view.itertuples(index=False)]

    pred_view = predictivity[predictivity["horizon"].isin(["4w", "13w", "26w"])]
    pred_rows = [[
        row.market_label,
        row.horizon,
        int(row.observations),
        f"{float(row.score_return_corr):+.3f}" if pd.notna(row.score_return_corr) else "n/a",
        f"{float(row.score_return_hac_p_value):.3f}" if pd.notna(row.score_return_hac_p_value) else "n/a",
        f"{float(row.risk_on_minus_caution_avg_return_pct):+.2f}%" if pd.notna(row.risk_on_minus_caution_avg_return_pct) else "n/a",
        f"{float(row.risk_on_minus_caution_hac_p_value):.3f}" if pd.notna(row.risk_on_minus_caution_hac_p_value) else "n/a",
        f"{float(row.drift_adjusted_accuracy_pct):.1f}%" if pd.notna(row.drift_adjusted_accuracy_pct) else "n/a",
        row.evidence_grade,
    ] for row in pred_view.itertuples(index=False)]

    report = f"""# COT Regime Score Backtest Report

Generated: {generated}

This report is regenerated from the same current {DATASET_LABEL} inputs used by the dashboard. COT observations are Tuesday report dates; signals start at the first available close on or after Friday publication.

## Data Cutoffs

{markdown_table(["Market", "Latest COT report", "Latest signal close", "Latest price", "Scored rows"], cutoff_rows)}

## Current Tradable COT Signals

{markdown_table(["Market", "Report date", "Signal date", "Score", "Bucket", "Active triggers"], current_rows)}

## Forward Returns by Regime Bucket

{markdown_table(["Market", "Horizon", "Bucket", "N", "Average return", "Hit rate", "Average drawdown"], bucket_rows)}

## Predictivity Diagnostics

{markdown_table(["Market", "Horizon", "N", "Score/return r", "HAC p", "Risk-On minus Caution", "Edge HAC p", "Drift-adjusted accuracy", "Evidence"], pred_rows)}

## Interpretation

- Risk-On means the configured COT extremes historically aligned with better forward reward/risk; it is not a guaranteed long signal.
- Caution is primarily an exposure and position-sizing warning, not an automatic short.
- Mixed means the active COT extremes conflict or lack enough conviction for a directional call.
- The backtest is COT-only. Price, volatility, and the unified macro-liquidity score are excluded from the regime score.
- `Supported` requires a positive Risk-On-minus-Caution edge with an overlap-adjusted HAC p-value at or below 0.05 and at least 20 observations in the smaller directional bucket.
- Drift-adjusted accuracy asks whether the score sign predicted a return above or below the prior expanding average, rather than rewarding the model for the equity market's long-run positive drift.

## Caveats

1. The expanding-percentile warmup requires at least 104 prior weekly reports.
2. Equity-index drift can keep average returns positive even in Caution buckets.
3. Long-horizon observations overlap. The main evidence table therefore uses Newey-West HAC statistics with lags tied to the forecast horizon; conventional permutation and Welch statistics remain in the CSV only as secondary diagnostics.
4. Publication timing is approximated using the first available market close on or after Friday release.
5. Latest rows may lack longer-horizon returns until enough future price history exists.
6. Percentile ranks are walk-forward, but the rule thresholds and weights are fixed researcher choices rather than rules selected in a sealed out-of-sample training process.
"""
    (OUT_DIR / "regime_analysis_report.md").write_text(report, encoding="utf-8")


def print_result_summary(history: pd.DataFrame, bucket: pd.DataFrame, predictivity: pd.DataFrame) -> None:
    print(f"Scored {len(history)} walk-forward COT observations.")
    for market, rows in history.groupby("market", sort=False):
        latest = rows.iloc[-1]
        print(
            f"{MARKETS[str(market)]['label']}: latest {latest['report_date']} signal {latest['signal_date']} "
            f"score {latest['score']:+.2f} ({latest['bucket']}); observations {len(rows)}"
        )
    print("\nRegime bucket summary, 4w horizon:")
    view = bucket[(bucket["bucket_type"] == "regime") & (bucket["horizon"] == "4w")]
    if not view.empty:
        cols = ["market", "bucket", "observations", "avg_return_pct", "hit_rate_pct", "diff_vs_unconditional_pct", "welch_t_stat_vs_rest"]
        print(view[cols].to_string(index=False))
    print("\nScore/return correlation summary, 4w horizon:")
    view = predictivity[predictivity["horizon"] == "4w"]
    if not view.empty:
        cols = ["market", "observations", "score_return_corr", "score_return_hac_p_value", "risk_on_minus_caution_avg_return_pct", "risk_on_minus_caution_hac_p_value", "drift_adjusted_accuracy_pct", "evidence_grade"]
        print(view[cols].to_string(index=False))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--min-lookback", type=int, default=104)
    parser.add_argument("--permutations", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()

    rules = load_rules()
    history, forward = build_histories(args.min_lookback, rules)
    bucket = build_bucket_summary(forward)
    predictivity = build_predictivity_summary(forward, args.permutations, args.seed)
    write_outputs(history, forward, bucket, predictivity)
    write_analysis_report(history, bucket, predictivity)
    print_result_summary(history, bucket, predictivity)
    print(f"\nSaved outputs to {OUT_DIR}")


if __name__ == "__main__":
    main()
