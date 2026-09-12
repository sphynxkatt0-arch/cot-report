from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
ANALYSIS = ROOT / "analysis"
DATA = ROOT / "data"
OUTDIR = ANALYSIS / "cot_cross_market_predictivity_output"

MARKETS = ("sp500", "nq", "vix")
TARGETS = {
    "sp500": {"label": "S&P 500", "price_file": DATA / "SP500.csv", "price_col": "SP500"},
    "nq": {"label": "NASDAQ-100", "price_file": DATA / "NASDAQ100.csv", "price_col": "NASDAQ100"},
}
HORIZONS = (1, 4, 13, 26)

DATASETS = {
    "tff": {
        "label": "TFF Detailed",
        "dir": ANALYSIS / "cot_exact_output",
        "file": lambda market: f"{market}_exact_consolidated_data_2016_2026.csv",
        "categories": {
            "dealer": "Dealer / Intermediary",
            "asset_mgr": "Asset Manager / Institutional",
            "lev_money": "Leveraged Funds",
            "other_reportable": "Other Reportables",
            "non_reportable": "Non-reportable",
        },
    },
    "legacy": {
        "label": "Legacy",
        "dir": ANALYSIS / "cot_legacy_output",
        "file": lambda market: f"{market}_legacy_data_2016_2026.csv",
        # Match the dashboard cross-market panel. Total Reportable is an aggregate.
        "categories": {
            "noncommercial": "Noncommercial",
            "commercial": "Commercial",
            "nonreportable": "Nonreportable",
        },
    },
}

DIRECTIONAL_EXCLUDED_CATEGORIES = {
    "tff": {"dealer"},
    "legacy": set(),
}

SIGNALS = {
    "net_z": "risk_net_bn_z",
    "flow1_z": "risk_flow1_bn_z",
    "flow4_z": "risk_flow4_bn_z",
    "trend13_z": "risk_trend13_bn_z",
    "trend26_z": "risk_trend26_bn_z",
    "net_raw_bn": "risk_net_bn",
    "trend13_raw_bn": "risk_trend13_bn",
    "trend26_raw_bn": "risk_trend26_bn",
}

NET_POSITION_SOURCES = {
    "combined": {
        "label": "Combined SP+NQ-VIX",
        "column": "risk_net_bn",
        "kind": "combined",
        "interpretation": "positive = equity risk-on net long; negative = equity risk-on net short",
    },
    "sp500": {
        "label": "S&P 500 only",
        "column": "sp500_risk_net_bn",
        "kind": "single",
        "interpretation": "positive = net long S&P 500; negative = net short S&P 500",
    },
    "nq": {
        "label": "NASDAQ-100 only",
        "column": "nq_risk_net_bn",
        "kind": "single",
        "interpretation": "positive = net long NASDAQ-100; negative = net short NASDAQ-100",
    },
    "vix_inverse": {
        "label": "VIX only, inverted",
        "column": "vix_inverse_risk_net_bn",
        "kind": "single",
        "interpretation": "positive = net short VIX / hedge selling; negative = net long VIX / hedge buying",
    },
}


def normal_approx_p_value(t_stat: float | None) -> float | None:
    if t_stat is None or not math.isfinite(t_stat):
        return None
    return float(math.erfc(abs(t_stat) / math.sqrt(2)))


def horizon_hac_lags(weeks: int) -> int:
    """Use enough Newey-West lags to cover overlapping weekly signal windows."""
    return max(1, int(math.ceil((weeks * 5) / 5)) - 1)


def newey_west_slope_stats(
    y: pd.Series,
    x: pd.Series,
    lags: int,
    min_unique_x: int = 5,
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


def expanding_z(series: pd.Series, min_periods: int = 52) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    mean = values.expanding(min_periods=min_periods).mean()
    std = values.expanding(min_periods=min_periods).std().replace(0, np.nan)
    return (values - mean) / std


def load_cot_dataset(dataset_key: str) -> dict[str, pd.DataFrame]:
    cfg = DATASETS[dataset_key]
    data: dict[str, pd.DataFrame] = {}
    for market in MARKETS:
        path = cfg["dir"] / cfg["file"](market)
        df = pd.read_csv(path, parse_dates=["date"])
        data[market] = df.sort_values("date").drop_duplicates("date", keep="last")
    return data


def load_price_series(target: str) -> pd.DataFrame:
    cfg = TARGETS[target]
    df = pd.read_csv(cfg["price_file"], parse_dates=["observation_date"])
    df = df.rename(columns={"observation_date": "date", cfg["price_col"]: "price"})
    df["price"] = pd.to_numeric(df["price"], errors="coerce")
    return df.dropna(subset=["date", "price"]).sort_values("date").reset_index(drop=True)


PRICE_CACHE = {target: load_price_series(target) for target in TARGETS}


def forward_drawdown_pct(signal_dates: pd.Series, target: str, weeks: int) -> pd.Series:
    prices = PRICE_CACHE[target]
    dates = prices["date"].to_numpy(dtype="datetime64[ns]")
    values = prices["price"].to_numpy(dtype=float)
    out: list[float | None] = []
    steps = weeks * 5

    for signal_date in pd.to_datetime(signal_dates):
        idx = int(np.searchsorted(dates, np.datetime64(signal_date), side="left"))
        if idx >= len(values) or not math.isfinite(values[idx]) or values[idx] <= 0:
            out.append(None)
            continue
        end = min(idx + steps, len(values) - 1)
        if end <= idx:
            out.append(None)
            continue
        window = values[idx : end + 1]
        window = window[np.isfinite(window)]
        if len(window) == 0:
            out.append(None)
            continue
        out.append(float((np.min(window) / values[idx] - 1.0) * 100.0))
    return pd.Series(out, index=signal_dates.index)


def build_signal_frame(dataset_key: str, category: str) -> pd.DataFrame:
    data = load_cot_dataset(dataset_key)
    common_dates = set(data["sp500"]["date"]) & set(data["nq"]["date"]) & set(data["vix"]["date"])
    dates = sorted(common_dates)
    frame = pd.DataFrame({"date": dates})

    for market in MARKETS:
        df = data[market].set_index("date").reindex(dates)
        frame[f"{market}_net"] = pd.to_numeric(df[f"{category}_net_notional_usd"], errors="coerce").to_numpy()
        frame[f"{market}_flow1"] = pd.to_numeric(
            df[f"{category}_net_flow_1w_notional_usd"],
            errors="coerce",
        ).to_numpy()
        frame[f"{market}_flow4"] = pd.to_numeric(
            df[f"{category}_net_flow_4w_notional_usd"],
            errors="coerce",
        ).to_numpy()

    frame["sp500_risk_net_bn"] = frame["sp500_net"] / 1e9
    frame["nq_risk_net_bn"] = frame["nq_net"] / 1e9
    frame["vix_inverse_risk_net_bn"] = -frame["vix_net"] / 1e9
    frame["risk_net_bn"] = (frame["sp500_net"] + frame["nq_net"] - frame["vix_net"]) / 1e9
    frame["risk_flow1_bn"] = (frame["sp500_flow1"] + frame["nq_flow1"] - frame["vix_flow1"]) / 1e9
    frame["risk_flow4_bn"] = (frame["sp500_flow4"] + frame["nq_flow4"] - frame["vix_flow4"]) / 1e9
    frame["risk_trend13_bn"] = frame["risk_net_bn"] - frame["risk_net_bn"].shift(13)
    frame["risk_trend26_bn"] = frame["risk_net_bn"] - frame["risk_net_bn"].shift(26)

    for column in ("risk_net_bn", "risk_flow1_bn", "risk_flow4_bn", "risk_trend13_bn", "risk_trend26_bn"):
        frame[f"{column}_z"] = expanding_z(frame[column])

    for target in TARGETS:
        df = data[target].set_index("date").reindex(dates)
        for weeks in HORIZONS:
            frame[f"{target}_fwd_{weeks}w"] = (
                pd.to_numeric(df[f"forward_return_{weeks}w"], errors="coerce").to_numpy() * 100.0
            )
            frame[f"{target}_drawdown_{weeks}w"] = forward_drawdown_pct(frame["date"], target, weeks)

    return frame


def corr_safe(x: pd.Series, y: pd.Series, method: str = "pearson") -> float | None:
    data = pd.DataFrame({"x": x, "y": y}).replace([np.inf, -np.inf], np.nan).dropna()
    if len(data) < 30 or data["x"].nunique() < 5 or data["y"].nunique() < 5:
        return None
    if method == "spearman":
        return float(data["x"].rank(method="average").corr(data["y"].rank(method="average")))
    return float(data["x"].corr(data["y"]))


def bucket_stats(df: pd.DataFrame, signal: str, return_col: str, drawdown_col: str) -> dict[str, Any] | None:
    data = df[[signal, return_col, drawdown_col]].replace([np.inf, -np.inf], np.nan).dropna(subset=[signal, return_col])
    if len(data) < 60 or data[signal].nunique() < 10:
        return None
    low, high = data[signal].quantile([0.3, 0.7])
    bottom = data.loc[data[signal] <= low]
    top = data.loc[data[signal] >= high]
    if len(bottom) < 20 or len(top) < 20:
        return None

    return {
        "n": int(len(data)),
        "top_n": int(len(top)),
        "bottom_n": int(len(bottom)),
        "top_avg": float(top[return_col].mean()),
        "bottom_avg": float(bottom[return_col].mean()),
        "top_minus_bottom": float(top[return_col].mean() - bottom[return_col].mean()),
        "top_hit": float((top[return_col] > 0).mean() * 100.0),
        "bottom_hit": float((bottom[return_col] > 0).mean() * 100.0),
        "top_avg_drawdown": float(top[drawdown_col].mean()) if top[drawdown_col].notna().any() else None,
        "bottom_avg_drawdown": float(bottom[drawdown_col].mean()) if bottom[drawdown_col].notna().any() else None,
    }


def evidence_label(row: pd.Series) -> str:
    edge = abs(float(row.get("bucket_top_minus_bottom") or 0.0))
    p_value = row.get("hac_p")
    if pd.notna(p_value) and p_value <= 0.05 and edge >= 2.0:
        return "supported"
    if pd.notna(p_value) and p_value <= 0.10 and edge >= 1.0:
        return "tentative"
    if (pd.notna(p_value) and p_value <= 0.20) or edge >= 1.5:
        return "weak/mixed"
    return "none"


def directional_evidence_label(row: pd.Series) -> str:
    edge = abs(float(row.get("side_edge_pp") or 0.0))
    p_value = row.get("hac_p")
    if pd.notna(p_value) and p_value <= 0.05 and edge >= 2.0:
        return "supported"
    if pd.notna(p_value) and p_value <= 0.10 and edge >= 1.0:
        return "tentative"
    if (pd.notna(p_value) and p_value <= 0.20) or edge >= 1.5:
        return "weak/mixed"
    return "none"


def direction_side_stats(
    frame: pd.DataFrame,
    signal_col: str,
    return_col: str,
    drawdown_col: str,
    weeks: int,
) -> dict[str, Any] | None:
    data = frame[[signal_col, return_col, drawdown_col]].replace([np.inf, -np.inf], np.nan).dropna(
        subset=[signal_col, return_col]
    )
    data = data.loc[data[signal_col] != 0].copy()
    if len(data) < 60 or data[signal_col].nunique() < 5:
        return None

    positive = data.loc[data[signal_col] > 0]
    negative = data.loc[data[signal_col] < 0]
    if len(positive) < 20 or len(negative) < 20:
        return None

    side_dummy = (data[signal_col] > 0).astype(float)
    slope, hac_t, hac_p = newey_west_slope_stats(
        data[return_col],
        side_dummy,
        horizon_hac_lags(weeks),
        min_unique_x=2,
    )
    positive_avg = float(positive[return_col].mean())
    negative_avg = float(negative[return_col].mean())
    positive_drawdown = float(positive[drawdown_col].mean()) if positive[drawdown_col].notna().any() else None
    negative_drawdown = float(negative[drawdown_col].mean()) if negative[drawdown_col].notna().any() else None
    side_edge = positive_avg - negative_avg

    return {
        "n": int(len(data)),
        "positive_n": int(len(positive)),
        "negative_n": int(len(negative)),
        "positive_avg_return": positive_avg,
        "negative_avg_return": negative_avg,
        "side_edge_pp": float(side_edge),
        "positive_hit_rate": float((positive[return_col] > 0).mean() * 100.0),
        "negative_hit_rate": float((negative[return_col] > 0).mean() * 100.0),
        "positive_avg_drawdown": positive_drawdown,
        "negative_avg_drawdown": negative_drawdown,
        "hac_t": hac_t,
        "hac_p": hac_p,
        "better_side": "positive" if side_edge > 0 else "negative" if side_edge < 0 else "flat",
        "abs_side_edge_pp": abs(float(side_edge)),
    }


def compare_combined_vs_single(side_tests: pd.DataFrame) -> pd.DataFrame:
    if side_tests.empty:
        return pd.DataFrame()

    rows: list[dict[str, Any]] = []
    group_cols = ["dataset", "dataset_label", "player", "player_key", "target", "horizon"]
    for keys, group in side_tests.groupby(group_cols, dropna=False):
        group_map = {str(row["source"]): row for _, row in group.iterrows()}
        combined = group_map.get("combined")
        singles = [row for source, row in group_map.items() if source != "combined"]
        if combined is None or not singles:
            continue

        best_single = max(singles, key=lambda row: float(row.get("abs_side_edge_pp") or 0.0))
        combined_abs = float(combined.get("abs_side_edge_pp") or 0.0)
        best_abs = float(best_single.get("abs_side_edge_pp") or 0.0)
        edge_gap = combined_abs - best_abs
        if abs(edge_gap) < 0.25:
            winner = "tie"
        elif edge_gap > 0:
            winner = "combined"
        else:
            winner = "single"

        rows.append(
            {
                "dataset": keys[0],
                "dataset_label": keys[1],
                "player": keys[2],
                "player_key": keys[3],
                "target": keys[4],
                "horizon": keys[5],
                "winner": winner,
                "combined_source_label": combined.get("source_label"),
                "combined_better_side": combined.get("better_side"),
                "combined_side_edge_pp": combined.get("side_edge_pp"),
                "combined_abs_side_edge_pp": combined_abs,
                "combined_hac_p": combined.get("hac_p"),
                "combined_evidence": combined.get("evidence"),
                "best_single_source": best_single.get("source"),
                "best_single_source_label": best_single.get("source_label"),
                "best_single_better_side": best_single.get("better_side"),
                "best_single_side_edge_pp": best_single.get("side_edge_pp"),
                "best_single_abs_side_edge_pp": best_abs,
                "best_single_hac_p": best_single.get("hac_p"),
                "best_single_evidence": best_single.get("evidence"),
                "combined_minus_best_single_abs_edge_pp": edge_gap,
                "combined_positive_avg_return": combined.get("positive_avg_return"),
                "combined_negative_avg_return": combined.get("negative_avg_return"),
                "best_single_positive_avg_return": best_single.get("positive_avg_return"),
                "best_single_negative_avg_return": best_single.get("negative_avg_return"),
            }
        )

    result = pd.DataFrame(rows)
    if result.empty:
        return result
    result["winner_rank"] = result["winner"].map({"combined": 0, "single": 1, "tie": 2}).fillna(3)
    result["strongest_abs_edge_pp"] = result[
        ["combined_abs_side_edge_pp", "best_single_abs_side_edge_pp"]
    ].max(axis=1)
    return result


def build_predictivity() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    rows: list[dict[str, Any]] = []
    side_rows: list[dict[str, Any]] = []
    latest_rows: list[dict[str, Any]] = []

    for dataset_key, cfg in DATASETS.items():
        for category, player_label in cfg["categories"].items():
            frame = build_signal_frame(dataset_key, category)
            latest = frame.dropna(subset=["risk_net_bn"]).iloc[-1]
            latest_rows.append(
                {
                    "dataset": dataset_key,
                    "player": player_label,
                    "date": latest["date"].date().isoformat(),
                    "risk_net_bn": latest["risk_net_bn"],
                    "risk_net_z": latest["risk_net_bn_z"],
                    "risk_trend13_bn": latest["risk_trend13_bn"],
                    "risk_trend13_z": latest["risk_trend13_bn_z"],
                    "risk_trend26_bn": latest["risk_trend26_bn"],
                    "risk_trend26_z": latest["risk_trend26_bn_z"],
                }
            )

            for signal_label, signal_col in SIGNALS.items():
                for target, target_cfg in TARGETS.items():
                    for weeks in HORIZONS:
                        return_col = f"{target}_fwd_{weeks}w"
                        drawdown_col = f"{target}_drawdown_{weeks}w"
                        data = frame[[signal_col, return_col]].replace([np.inf, -np.inf], np.nan).dropna()
                        if len(data) < 60:
                            continue
                        slope, hac_t, hac_p = newey_west_slope_stats(
                            data[return_col],
                            data[signal_col],
                            horizon_hac_lags(weeks),
                        )
                        stats = bucket_stats(frame, signal_col, return_col, drawdown_col) or {}
                        rows.append(
                            {
                                "dataset": dataset_key,
                                "dataset_label": cfg["label"],
                                "player": player_label,
                                "player_key": category,
                                "signal": signal_label,
                                "target": target_cfg["label"],
                                "horizon": f"{weeks}w",
                                "n": int(len(data)),
                                "pearson_r": corr_safe(data[signal_col], data[return_col], "pearson"),
                                "spearman_r": corr_safe(data[signal_col], data[return_col], "spearman"),
                                "slope_pp_per_unit": slope,
                                "hac_t": hac_t,
                                "hac_p": hac_p,
                                **{f"bucket_{key}": value for key, value in stats.items()},
                            }
                        )

            if category not in DIRECTIONAL_EXCLUDED_CATEGORIES.get(dataset_key, set()):
                for target, target_cfg in TARGETS.items():
                    for weeks in HORIZONS:
                        return_col = f"{target}_fwd_{weeks}w"
                        drawdown_col = f"{target}_drawdown_{weeks}w"
                        for source_key, source_cfg in NET_POSITION_SOURCES.items():
                            side_stats = direction_side_stats(
                                frame,
                                str(source_cfg["column"]),
                                return_col,
                                drawdown_col,
                                weeks,
                            )
                            if not side_stats:
                                continue
                            side_rows.append(
                                {
                                    "dataset": dataset_key,
                                    "dataset_label": cfg["label"],
                                    "player": player_label,
                                    "player_key": category,
                                    "source": source_key,
                                    "source_label": source_cfg["label"],
                                    "source_kind": source_cfg["kind"],
                                    "source_interpretation": source_cfg["interpretation"],
                                    "target": target_cfg["label"],
                                    "horizon": f"{weeks}w",
                                    **side_stats,
                                }
                            )

    summary = pd.DataFrame(rows)
    summary["abs_spearman"] = summary["spearman_r"].abs()
    summary["top_minus_bottom_abs"] = summary["bucket_top_minus_bottom"].abs()
    summary["evidence"] = summary.apply(evidence_label, axis=1)
    latest_signals = pd.DataFrame(latest_rows)
    side_tests = pd.DataFrame(side_rows)
    if not side_tests.empty:
        side_tests["evidence"] = side_tests.apply(directional_evidence_label, axis=1)
    combined_vs_single = compare_combined_vs_single(side_tests)
    return summary, latest_signals, side_tests, combined_vs_single


def main() -> None:
    OUTDIR.mkdir(exist_ok=True)
    summary, latest_signals, side_tests, combined_vs_single = build_predictivity()
    summary_path = OUTDIR / "risk_exposure_predictivity_summary.csv"
    latest_path = OUTDIR / "latest_risk_exposure_signals.csv"
    top_path = OUTDIR / "risk_exposure_predictivity_top_findings.csv"
    side_path = OUTDIR / "net_position_side_predictivity.csv"
    comparison_path = OUTDIR / "net_position_combined_vs_single_summary.csv"
    comparison_top_path = OUTDIR / "net_position_combined_vs_single_top_findings.csv"

    summary.to_csv(summary_path, index=False)
    latest_signals.to_csv(latest_path, index=False)
    side_tests.to_csv(side_path, index=False)
    combined_vs_single.to_csv(comparison_path, index=False)
    rank = {"supported": 0, "tentative": 1, "weak/mixed": 2, "none": 3}
    filtered = summary[summary["signal"].isin(["net_z", "trend13_z", "trend26_z", "flow1_z", "flow4_z"])].copy()
    filtered["evidence_rank"] = filtered["evidence"].map(rank)
    top = filtered.sort_values(
        ["evidence_rank", "hac_p", "top_minus_bottom_abs"],
        ascending=[True, True, False],
    ).head(50)
    top.to_csv(top_path, index=False)
    if not combined_vs_single.empty:
        comparison_top = combined_vs_single.sort_values(
            ["winner_rank", "strongest_abs_edge_pp", "combined_minus_best_single_abs_edge_pp"],
            ascending=[True, False, False],
        ).head(50)
    else:
        comparison_top = combined_vs_single
    comparison_top.to_csv(comparison_top_path, index=False)

    print(f"Saved {summary_path}")
    print(f"Saved {latest_path}")
    print(f"Saved {top_path}")
    print(f"Saved {side_path}")
    print(f"Saved {comparison_path}")
    print(f"Saved {comparison_top_path}")
    print("")
    cols = [
        "dataset",
        "player",
        "signal",
        "target",
        "horizon",
        "n",
        "spearman_r",
        "hac_t",
        "hac_p",
        "bucket_top_avg",
        "bucket_bottom_avg",
        "bucket_top_minus_bottom",
        "evidence",
    ]
    print(top[cols].head(20).to_string(index=False, float_format=lambda value: f"{value:.3f}"))
    if not comparison_top.empty:
        print("")
        comparison_cols = [
            "dataset",
            "player",
            "target",
            "horizon",
            "winner",
            "combined_abs_side_edge_pp",
            "best_single_source_label",
            "best_single_abs_side_edge_pp",
            "combined_minus_best_single_abs_edge_pp",
            "combined_hac_p",
            "best_single_hac_p",
        ]
        print(
            comparison_top[comparison_cols]
            .head(20)
            .to_string(index=False, float_format=lambda value: f"{value:.3f}")
        )


if __name__ == "__main__":
    main()
