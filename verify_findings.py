#!/usr/bin/env python3
"""
Verify dashboard research constants against exact consolidated COT outputs.

Run:
  py verify_findings.py

The script recomputes:
  - same-week dNet/OI vs weekly return correlations
  - net/OI vs forward return correlations
  - top/bottom 10% bucket average forward returns
  - latest net/OI and percentile ranks
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / "config" / "research_findings.json"
DATA_DIR = ROOT / "cot_exact_output"
CATEGORIES = ("asset_mgr", "dealer", "lev_money", "other_reportable", "non_reportable")
FORWARD_WINDOWS = (1, 4, 13, 26, 52)
EXTREME_WINDOWS = (13, 26, 52)


def load_config() -> dict[str, Any]:
    return json.loads(CONFIG.read_text(encoding="utf-8"))


def latest_data_file(market: str) -> Path:
    matches = sorted(DATA_DIR.glob(f"{market}_exact_consolidated_data_*.csv"), key=lambda p: p.stat().st_mtime)
    if not matches:
        raise FileNotFoundError(f"No exact consolidated data file found for {market} in {DATA_DIR}")
    return matches[-1]


def prepare_data(market: str) -> pd.DataFrame:
    df = pd.read_csv(latest_data_file(market))
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.sort_values("date").reset_index(drop=True)
    df["price_return_1w"] = df["price"].pct_change()
    for category in CATEGORIES:
        df[f"{category}_net_oi_pct_change"] = df[f"{category}_net_oi_pct"].diff()
    for weeks in FORWARD_WINDOWS:
        df[f"forward_return_{weeks}w"] = df["price"].shift(-weeks) / df["price"] - 1
    return df


def percentile_rank(series: pd.Series) -> float:
    return float(series.rank(method="average", pct=True).iloc[-1] * 100)


def bucket_average(df: pd.DataFrame, category: str, side: str, weeks: int) -> float:
    series = df[f"{category}_net_oi_pct"]
    threshold = series.quantile(0.9 if side == "top" else 0.1)
    bucket = df[series >= threshold] if side == "top" else df[series <= threshold]
    return float(bucket[f"forward_return_{weeks}w"].mean() * 100)


def check_close(
    failures: list[str],
    label: str,
    actual: float,
    expected: float,
    tolerance: float,
) -> None:
    if pd.isna(actual) or abs(actual - expected) > tolerance:
        failures.append(f"{label}: expected {expected:.6f}, actual {actual:.6f}, tolerance {tolerance}")


def verify_market(market: str, expected: dict[str, Any], args: argparse.Namespace) -> list[str]:
    failures: list[str] = []
    df = prepare_data(market)

    for category, expected_value in expected["same_week"].items():
        actual = df[f"{category}_net_oi_pct_change"].corr(df["price_return_1w"])
        check_close(failures, f"{market} same_week {category}", actual, expected_value, args.corr_tol)

    for category, values in expected["forward"].items():
        for window_label, expected_value in values.items():
            weeks = int(window_label.removesuffix("w"))
            actual = df[f"{category}_net_oi_pct"].corr(df[f"forward_return_{weeks}w"])
            check_close(failures, f"{market} forward {category} {window_label}", actual, expected_value, args.corr_tol)

    for group_name in ("best", "worst"):
        for row in expected.get("extremes", {}).get(group_name, []):
            category = row["category"]
            side = row["side"]
            for weeks in EXTREME_WINDOWS:
                actual = bucket_average(df, category, side, weeks)
                check_close(
                    failures,
                    f"{market} extreme {row['signal']} {weeks}w",
                    actual,
                    row[f"{weeks}w"],
                    args.return_tol,
                )

    latest = df.iloc[-1]
    for category, values in expected.get("current", {}).items():
        actual_net = float(latest[f"{category}_net_oi_pct"])
        actual_pct = percentile_rank(df[f"{category}_net_oi_pct"])
        check_close(failures, f"{market} current net/OI {category}", actual_net, values["net_oi_pct"], args.current_net_tol)
        check_close(failures, f"{market} current percentile {category}", actual_pct, values["percentile"], args.percentile_tol)

    print(f"{market}: checked through {df['date'].iloc[-1].date()} ({len(df)} rows)")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corr-tol", type=float, default=0.001)
    parser.add_argument("--return-tol", type=float, default=0.01)
    parser.add_argument("--current-net-tol", type=float, default=0.01)
    parser.add_argument("--percentile-tol", type=float, default=0.1)
    args = parser.parse_args()

    config = load_config()
    failures: list[str] = []
    for market, expected in config.items():
        failures.extend(verify_market(market, expected, args))

    if failures:
        print("\nVerification failed:")
        for failure in failures:
            print(f"FAIL {failure}")
        return 1

    print("\nVerification passed: research_findings.json matches current exact consolidated outputs.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
