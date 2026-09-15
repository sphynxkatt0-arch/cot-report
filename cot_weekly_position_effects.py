#!/usr/bin/env python3
"""
Event study for whether weekly COT position increases/decreases lead future returns.

The signal date is the COT "as of" Tuesday. Because those values are normally
published Friday afternoon, actionable returns are measured from the Friday
release close to future closes by trading-day horizon.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import erfc, sqrt
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "analysis" / "cot_position_effects_output"


@dataclass(frozen=True)
class StudyConfig:
    dataset: str
    market: str
    cot_path: Path
    price_path: Path
    price_col: str
    categories: tuple[str, ...]


CONFIGS = [
    StudyConfig(
        dataset="tff_disaggregated",
        market="sp500",
        cot_path=ROOT / "analysis" / "cot_exact_output" / "sp500_exact_consolidated_data_2016_2026.csv",
        price_path=ROOT / "data" / "SP500.csv",
        price_col="SP500",
        categories=("asset_mgr", "dealer", "lev_money", "other_reportable", "non_reportable"),
    ),
    StudyConfig(
        dataset="tff_disaggregated",
        market="nq",
        cot_path=ROOT / "analysis" / "cot_exact_output" / "nq_exact_consolidated_data_2016_2026.csv",
        price_path=ROOT / "data" / "NASDAQ100.csv",
        price_col="NASDAQ100",
        categories=("asset_mgr", "dealer", "lev_money", "other_reportable", "non_reportable"),
    ),
    StudyConfig(
        dataset="legacy",
        market="sp500",
        cot_path=ROOT / "analysis" / "cot_legacy_output" / "sp500_legacy_data_2016_2026.csv",
        price_path=ROOT / "data" / "SP500.csv",
        price_col="SP500",
        categories=("noncommercial", "commercial", "total_reportable", "nonreportable"),
    ),
    StudyConfig(
        dataset="legacy",
        market="nq",
        cot_path=ROOT / "analysis" / "cot_legacy_output" / "nq_legacy_data_2016_2026.csv",
        price_path=ROOT / "data" / "NASDAQ100.csv",
        price_col="NASDAQ100",
        categories=("noncommercial", "commercial", "total_reportable", "nonreportable"),
    ),
]


HORIZONS = (
    ("1d_post_release", 1),
    ("2d_post_release", 2),
    ("3d_post_release", 3),
    ("1w_post_release", 5),
    ("2w_post_release", 10),
    ("4w_post_release", 20),
    ("13w_post_release", 65),
)


def normal_two_sided_p(t_stat: float) -> float:
    if not np.isfinite(t_stat):
        return np.nan
    return erfc(abs(t_stat) / sqrt(2.0))


def load_prices(path: Path, value_col: str) -> pd.DataFrame:
    px = pd.read_csv(path)
    px.columns = [c.strip().lstrip("\ufeff") for c in px.columns]
    px["date"] = pd.to_datetime(px["observation_date"], errors="coerce")
    px["price"] = pd.to_numeric(px[value_col], errors="coerce")
    return px[["date", "price"]].dropna().sort_values("date").reset_index(drop=True)


def add_post_release_returns(cot: pd.DataFrame, prices: pd.DataFrame) -> pd.DataFrame:
    out = cot.copy()
    out["date"] = pd.to_datetime(out["date"], errors="coerce")
    price_dates = prices["date"].to_numpy(dtype="datetime64[ns]")
    price_vals = prices["price"].to_numpy(dtype=float)

    release_friday = out["date"] + pd.to_timedelta((4 - out["date"].dt.weekday) % 7, unit="D")
    release_dates = release_friday.to_numpy(dtype="datetime64[ns]")
    base_idx = np.searchsorted(price_dates, release_dates, side="right") - 1
    valid_base = (base_idx >= 0) & (base_idx < len(price_vals))

    out["release_reference_date"] = pd.NaT
    out["release_reference_price"] = np.nan
    valid_positions = np.flatnonzero(valid_base)
    out.loc[out.index[valid_positions], "release_reference_date"] = pd.to_datetime(price_dates[base_idx[valid_positions]])
    out.loc[out.index[valid_positions], "release_reference_price"] = price_vals[base_idx[valid_positions]]

    for label, trading_days in HORIZONS:
        target_idx = base_idx + trading_days
        valid = valid_base & (target_idx >= 0) & (target_idx < len(price_vals))
        vals = np.full(len(out), np.nan)
        vals[valid] = price_vals[target_idx[valid]] / price_vals[base_idx[valid]] - 1.0
        out[f"return_{label}"] = vals
    return out


def ensure_change_columns(df: pd.DataFrame, categories: tuple[str, ...]) -> pd.DataFrame:
    out = df.copy()
    for cat in categories:
        if f"{cat}_long_oi_pct" not in out and f"{cat}_long" in out:
            out[f"{cat}_long_oi_pct"] = out[f"{cat}_long"] / out["open_interest"] * 100.0
        if f"{cat}_short_oi_pct" not in out and f"{cat}_short" in out:
            out[f"{cat}_short_oi_pct"] = out[f"{cat}_short"] / out["open_interest"] * 100.0

        for metric in ("net_oi_pct", "long_oi_pct", "short_oi_pct"):
            col = f"{cat}_{metric}"
            chg = f"{col}_change"
            if col in out and chg not in out:
                out[chg] = out[col].diff()

        if f"{cat}_net" in out and f"{cat}_net_change" not in out:
            out[f"{cat}_net_change"] = out[f"{cat}_net"].diff()
    return out


def describe_returns(values: pd.Series) -> dict[str, float]:
    clean = pd.to_numeric(values, errors="coerce").dropna()
    if clean.empty:
        return {
            "n": 0,
            "mean_return": np.nan,
            "median_return": np.nan,
            "hit_rate": np.nan,
            "stdev": np.nan,
        }
    return {
        "n": int(clean.shape[0]),
        "mean_return": float(clean.mean()),
        "median_return": float(clean.median()),
        "hit_rate": float((clean > 0).mean()),
        "stdev": float(clean.std(ddof=1)) if clean.shape[0] > 1 else np.nan,
    }


def diff_stats(up: pd.Series, down: pd.Series) -> dict[str, float]:
    up = pd.to_numeric(up, errors="coerce").dropna()
    down = pd.to_numeric(down, errors="coerce").dropna()
    if len(up) < 2 or len(down) < 2:
        return {"mean_diff_up_minus_down": np.nan, "welch_t": np.nan, "normal_p_approx": np.nan}
    diff = float(up.mean() - down.mean())
    se = sqrt(float(up.var(ddof=1) / len(up) + down.var(ddof=1) / len(down)))
    t_stat = diff / se if se else np.nan
    return {
        "mean_diff_up_minus_down": diff,
        "welch_t": float(t_stat),
        "normal_p_approx": normal_two_sided_p(float(t_stat)),
    }


def correlation(x: pd.Series, y: pd.Series) -> tuple[float, int]:
    pair = pd.concat([pd.to_numeric(x, errors="coerce"), pd.to_numeric(y, errors="coerce")], axis=1).dropna()
    if len(pair) < 3:
        return np.nan, len(pair)
    return float(pair.iloc[:, 0].corr(pair.iloc[:, 1])), len(pair)


def build_rows(cfg: StudyConfig) -> tuple[list[dict], list[dict], list[dict]]:
    cot = pd.read_csv(cfg.cot_path)
    prices = load_prices(cfg.price_path, cfg.price_col)
    df = add_post_release_returns(cot, prices)
    df = ensure_change_columns(df, cfg.categories)

    sign_rows: list[dict] = []
    extreme_rows: list[dict] = []
    corr_rows: list[dict] = []

    for cat in cfg.categories:
        for metric in ("net_oi_pct_change", "long_oi_pct_change", "short_oi_pct_change"):
            change_col = f"{cat}_{metric}"
            if change_col not in df:
                continue
            change = pd.to_numeric(df[change_col], errors="coerce")
            up_mask = change > 0
            down_mask = change < 0

            q25 = change.quantile(0.25)
            q75 = change.quantile(0.75)
            strong_up_mask = change >= q75
            strong_down_mask = change <= q25

            for horizon_label, _ in HORIZONS:
                ret_col = f"return_{horizon_label}"
                up_desc = describe_returns(df.loc[up_mask, ret_col])
                down_desc = describe_returns(df.loc[down_mask, ret_col])
                row = {
                    "dataset": cfg.dataset,
                    "market": cfg.market,
                    "category": cat,
                    "position_change_metric": metric,
                    "horizon": horizon_label,
                    **{f"increase_{k}": v for k, v in up_desc.items()},
                    **{f"decrease_{k}": v for k, v in down_desc.items()},
                    **diff_stats(df.loc[up_mask, ret_col], df.loc[down_mask, ret_col]),
                }
                sign_rows.append(row)

                strong_up_desc = describe_returns(df.loc[strong_up_mask, ret_col])
                strong_down_desc = describe_returns(df.loc[strong_down_mask, ret_col])
                extreme_rows.append({
                    "dataset": cfg.dataset,
                    "market": cfg.market,
                    "category": cat,
                    "position_change_metric": metric,
                    "horizon": horizon_label,
                    "bottom_quartile_threshold": float(q25),
                    "top_quartile_threshold": float(q75),
                    **{f"top_quartile_{k}": v for k, v in strong_up_desc.items()},
                    **{f"bottom_quartile_{k}": v for k, v in strong_down_desc.items()},
                    **diff_stats(df.loc[strong_up_mask, ret_col], df.loc[strong_down_mask, ret_col]),
                })

                r, n = correlation(change, df[ret_col])
                corr_rows.append({
                    "dataset": cfg.dataset,
                    "market": cfg.market,
                    "category": cat,
                    "position_change_metric": metric,
                    "horizon": horizon_label,
                    "pearson_r": r,
                    "observations": n,
                })

    enriched_name = f"{cfg.market}_{cfg.dataset}_post_release_data.csv"
    df.to_csv(OUT / enriched_name, index=False)
    return sign_rows, extreme_rows, corr_rows


def add_summary_tables(sign: pd.DataFrame, corr: pd.DataFrame) -> dict[str, pd.DataFrame]:
    net_sign = sign[sign["position_change_metric"].eq("net_oi_pct_change")].copy()
    one_week = net_sign[net_sign["horizon"].eq("1w_post_release")].copy()
    one_week["mean_diff_pct_points"] = one_week["mean_diff_up_minus_down"] * 100.0
    one_week = one_week.sort_values("mean_diff_up_minus_down", key=lambda s: s.abs(), ascending=False)

    net_corr = corr[corr["position_change_metric"].eq("net_oi_pct_change")].copy()
    net_corr["abs_r"] = net_corr["pearson_r"].abs()
    strongest_corr = net_corr.sort_values("abs_r", ascending=False).head(25)

    return {
        "net_1w_sign_effects_ranked.csv": one_week,
        "strongest_net_forward_correlations.csv": strongest_corr,
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    sign_rows: list[dict] = []
    extreme_rows: list[dict] = []
    corr_rows: list[dict] = []
    for cfg in CONFIGS:
        s, e, c = build_rows(cfg)
        sign_rows.extend(s)
        extreme_rows.extend(e)
        corr_rows.extend(c)

    sign = pd.DataFrame(sign_rows)
    extreme = pd.DataFrame(extreme_rows)
    corr = pd.DataFrame(corr_rows)

    sign.to_csv(OUT / "cot_position_increase_decrease_forward_returns.csv", index=False)
    extreme.to_csv(OUT / "cot_position_extreme_quartile_forward_returns.csv", index=False)
    corr.to_csv(OUT / "cot_position_change_forward_correlations.csv", index=False)

    for name, table in add_summary_tables(sign, corr).items():
        table.to_csv(OUT / name, index=False)

    print(f"Wrote analysis outputs to {OUT}")


if __name__ == "__main__":
    main()
