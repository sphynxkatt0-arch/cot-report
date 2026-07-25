#!/usr/bin/env python3
"""Validate raw COT and cleaned price inputs before running the directional model."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from build_directional_cot_report import MARKETS, latest_file, read_position_file, read_prices
from cot_direction_model import load_config

ROOT = Path(__file__).resolve().parent
EXPECTED_CONTRACTS = {
    "sp500": "S&P 500 Consolidated - CHICAGO MERCANTILE EXCHANGE",
    "nq": "NASDAQ-100 Consolidated - CHICAGO MERCANTILE EXCHANGE",
}
LEGACY_REQUIRED = {
    "date",
    "open_interest",
    "noncommercial_long",
    "noncommercial_short",
    "noncommercial_net",
    "noncommercial_net_oi_pct",
}
TFF_REQUIRED = {
    "date",
    "open_interest",
    "asset_mgr_long",
    "asset_mgr_short",
    "asset_mgr_net_oi_pct",
    "other_reportable_net_oi_pct",
    "non_reportable_net_oi_pct",
}


def read_raw_position_file(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path)
    frame.columns = [str(column).strip().lstrip("\ufeff") for column in frame.columns]
    if "date" in frame.columns:
        frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    return frame


def ensure_columns(frame: pd.DataFrame, required: set[str], label: str, failures: list[str]) -> None:
    missing = sorted(required - set(frame.columns))
    if missing:
        failures.append(f"{label}: missing columns {missing}")


def validate_frame(
    frame: pd.DataFrame,
    *,
    label: str,
    required: set[str],
    expected_contract: str,
    minimum_rows: int,
    failures: list[str],
) -> None:
    ensure_columns(frame, required, label, failures)
    if len(frame) < minimum_rows:
        failures.append(f"{label}: only {len(frame)} rows; need at least {minimum_rows}")
    if "date" in frame.columns:
        if frame["date"].isna().any():
            failures.append(f"{label}: contains invalid dates")
        valid_dates = frame["date"].dropna()
        if valid_dates.duplicated().any():
            failures.append(f"{label}: contains duplicate report dates")
        if not valid_dates.is_monotonic_increasing:
            failures.append(f"{label}: dates are not sorted")
    if "contract" in frame.columns:
        contracts = sorted(str(value).strip() for value in frame["contract"].dropna().unique())
        if contracts != [expected_contract]:
            failures.append(f"{label}: expected exact contract {expected_contract!r}, found {contracts[:5]!r}")
    else:
        failures.append(f"{label}: missing contract identity column")
    if "open_interest" in frame.columns:
        oi = pd.to_numeric(frame["open_interest"], errors="coerce")
        if oi.isna().any() or (oi <= 0).any():
            failures.append(f"{label}: open interest contains missing or non-positive values")
    if not frame.empty:
        latest = frame.iloc[-1]
        for column in required - {"date"}:
            if column in frame.columns and pd.isna(latest[column]):
                failures.append(f"{label}: latest row has missing {column}")


def validate_price_frame(
    prices: pd.DataFrame,
    *,
    label: str,
    minimum_rows: int,
    failures: list[str],
) -> None:
    if len(prices) < minimum_rows:
        failures.append(f"{label}: only {len(prices)} price rows; need at least {minimum_rows}")
    if prices["date"].duplicated().any():
        failures.append(f"{label}: duplicate price dates")
    if not prices["date"].is_monotonic_increasing:
        failures.append(f"{label}: price dates are not sorted")
    values = pd.to_numeric(prices["price"], errors="coerce")
    if values.isna().any() or (values <= 0).any():
        failures.append(f"{label}: prices contain missing or non-positive values")


def validate_market(market: str, config: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    meta = MARKETS[market]
    legacy_path = latest_file(meta["legacy_glob"])
    tff_path = latest_file(meta["tff_glob"])
    legacy_raw = read_raw_position_file(legacy_path)
    tff_raw = read_raw_position_file(tff_path)
    legacy = read_position_file(legacy_path)
    tff = read_position_file(tff_path)
    prices = read_prices(meta["price_path"], meta["price_col"])
    minimum = int(config["minimum_history_weeks"]) + 13
    expected = EXPECTED_CONTRACTS[market]

    validate_frame(
        legacy_raw,
        label=f"{market} Legacy raw",
        required=LEGACY_REQUIRED,
        expected_contract=expected,
        minimum_rows=minimum,
        failures=failures,
    )
    validate_frame(
        tff_raw,
        label=f"{market} TFF raw",
        required=TFF_REQUIRED,
        expected_contract=expected,
        minimum_rows=minimum,
        failures=failures,
    )
    validate_price_frame(prices, label=f"{market} price", minimum_rows=260, failures=failures)

    if not legacy.empty and not tff.empty:
        legacy_latest = legacy["date"].iloc[-1]
        tff_latest = tff["date"].iloc[-1]
        if legacy_latest != tff_latest:
            failures.append(
                f"{market}: Legacy latest {legacy_latest.date()} does not match TFF latest {tff_latest.date()}"
            )
        common = set(legacy["date"]).intersection(set(tff["date"]))
        if len(common) < minimum:
            failures.append(f"{market}: only {len(common)} common Legacy/TFF dates; need at least {minimum}")
        if not prices.empty and prices["date"].iloc[-1] < min(legacy_latest, tff_latest):
            failures.append(
                f"{market}: latest price {prices['date'].iloc[-1].date()} predates COT row {min(legacy_latest, tff_latest).date()}"
            )
    return failures


def main() -> None:
    config = load_config(ROOT / "config" / "cot_direction_model_v1.json")
    failures: list[str] = []
    for market in ("sp500", "nq"):
        failures.extend(validate_market(market, config))
    dashboard = ROOT / "interactive_cot_dashboard.html"
    if not dashboard.exists():
        failures.append("interactive_cot_dashboard.html is missing; macro context cannot be loaded")
    if failures:
        raise RuntimeError("Directional input validation failed:\n- " + "\n- ".join(failures))
    print("Directional input validation passed.")


if __name__ == "__main__":
    main()
