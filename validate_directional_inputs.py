#!/usr/bin/env python3
"""Validate raw COT, price, contract identity, and baseline-model inputs."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from build_directional_cot_report import latest_file, read_position_file, read_prices
from cot_direction_model import load_config
from cot_market_registry import BASELINE_MARKETS, DIRECTIONAL_MARKETS, MARKETS

ROOT = Path(__file__).resolve().parent
LEGACY_REQUIRED = {"date", "open_interest", "noncommercial_long", "noncommercial_short", "noncommercial_net", "noncommercial_net_oi_pct"}
TFF_REQUIRED = {"date", "open_interest", "asset_mgr_long", "asset_mgr_short", "asset_mgr_net_oi_pct", "other_reportable_net_oi_pct", "non_reportable_net_oi_pct"}
DISAGGREGATED_REQUIRED = {"date", "open_interest", "managed_money_long", "managed_money_short", "managed_money_net_oi_pct", "other_reportable_net_oi_pct", "non_reportable_net_oi_pct"}
BASELINE_HISTORIES = {
    "old TFF regime": ROOT / "cot_regime_backtest_output" / "regime_score_history.csv",
    "old Legacy regime": ROOT / "cot_legacy_regime_backtest_output" / "regime_score_history.csv",
}
MANIFEST = ROOT / "model_output" / "cot_market_refresh_manifest.json"


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


def validate_price_frame(prices: pd.DataFrame, *, label: str, minimum_rows: int, failures: list[str]) -> None:
    if len(prices) < minimum_rows:
        failures.append(f"{label}: only {len(prices)} price rows; need at least {minimum_rows}")
    if prices["date"].duplicated().any():
        failures.append(f"{label}: duplicate price dates")
    if not prices["date"].is_monotonic_increasing:
        failures.append(f"{label}: price dates are not sorted")
    values = pd.to_numeric(prices["price"], errors="coerce")
    if values.isna().any() or (values <= 0).any():
        failures.append(f"{label}: prices contain missing or non-positive values")


def validate_baseline_history(path: Path, *, label: str, expected_latest: dict[str, pd.Timestamp], minimum_rows: int, failures: list[str]) -> None:
    if not path.exists():
        failures.append(f"{label}: missing {path}")
        return
    frame = pd.read_csv(path)
    required = {"market", "report_date", "release_target_date", "signal_date", "score", "bucket"}
    missing = sorted(required - set(frame.columns))
    if missing:
        failures.append(f"{label}: missing columns {missing}")
        return
    frame["report_date"] = pd.to_datetime(frame["report_date"], errors="coerce")
    frame["release_target_date"] = pd.to_datetime(frame["release_target_date"], errors="coerce")
    frame["signal_date"] = pd.to_datetime(frame["signal_date"], errors="coerce")
    if frame[["report_date", "release_target_date", "signal_date"]].isna().any().any():
        failures.append(f"{label}: contains invalid timing dates")
    if frame.duplicated(["market", "report_date"]).any():
        failures.append(f"{label}: contains duplicate market/report rows")
    if (frame["release_target_date"] < frame["report_date"]).any():
        failures.append(f"{label}: release target predates report date")
    if (frame["signal_date"] < frame["release_target_date"]).any():
        failures.append(f"{label}: signal date predates release target")
    for market, expected in expected_latest.items():
        subset = frame.loc[frame["market"] == market].sort_values("report_date")
        if len(subset) < minimum_rows:
            failures.append(f"{label} {market}: only {len(subset)} rows; need at least {minimum_rows}")
            continue
        actual = subset["report_date"].iloc[-1]
        if actual != expected:
            failures.append(f"{label} {market}: latest report {actual.date()} does not match COT {expected.date()}")
        if pd.to_numeric(subset["score"], errors="coerce").isna().any():
            failures.append(f"{label} {market}: score contains missing/non-numeric values")


def validate_market(market: str, config: dict[str, Any]) -> tuple[list[str], pd.Timestamp | None]:
    failures: list[str] = []
    meta = MARKETS[market]
    legacy_path = latest_file(str(meta["legacy_glob"]))
    secondary_path = latest_file(str(meta["secondary_glob"]))
    legacy_raw = read_raw_position_file(legacy_path)
    secondary_raw = read_raw_position_file(secondary_path)
    legacy = read_position_file(legacy_path)
    secondary = read_position_file(secondary_path)
    prices = read_prices(Path(meta["price_path"]), str(meta["price_col"]))
    minimum = int(config["minimum_history_weeks"]) + 13

    validate_frame(
        legacy_raw,
        label=f"{market} Legacy raw",
        required=LEGACY_REQUIRED,
        expected_contract=str(meta["legacy_contract_name"]),
        minimum_rows=minimum,
        failures=failures,
    )
    secondary_required = TFF_REQUIRED if meta["secondary_kind"] == "tff" else DISAGGREGATED_REQUIRED
    validate_frame(
        secondary_raw,
        label=f"{market} {meta['secondary_label']} raw",
        required=secondary_required,
        expected_contract=str(meta["secondary_contract_name"]),
        minimum_rows=minimum,
        failures=failures,
    )
    validate_price_frame(prices, label=f"{market} price", minimum_rows=260, failures=failures)

    latest_common: pd.Timestamp | None = None
    if not legacy.empty and not secondary.empty:
        legacy_latest, secondary_latest = legacy["date"].iloc[-1], secondary["date"].iloc[-1]
        if legacy_latest != secondary_latest:
            failures.append(f"{market}: Legacy latest {legacy_latest.date()} does not match {meta['secondary_label']} latest {secondary_latest.date()}")
        else:
            latest_common = pd.Timestamp(legacy_latest)
        common = set(legacy["date"]).intersection(set(secondary["date"]))
        if len(common) < minimum:
            failures.append(f"{market}: only {len(common)} common Legacy/{meta['secondary_label']} dates; need at least {minimum}")
        if not prices.empty and prices["date"].iloc[-1] < min(legacy_latest, secondary_latest):
            failures.append(f"{market}: latest price {prices['date'].iloc[-1].date()} predates COT row {min(legacy_latest, secondary_latest).date()}")
    return failures, latest_common


def validate_manifest(failures: list[str]) -> None:
    if not MANIFEST.exists():
        failures.append(f"missing extended-market contract manifest {MANIFEST}")
        return
    try:
        payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        failures.append(f"cannot read extended-market contract manifest: {exc}")
        return
    rows = {str(row.get("market")): row for row in payload.get("markets") or [] if isinstance(row, dict)}
    for market in ("russell2000", "dow", "gold"):
        meta = MARKETS[market]
        row = rows.get(market)
        if row is None:
            failures.append(f"contract manifest missing {market}")
            continue
        for field, expected in (
            ("legacy_cftc_code", meta["legacy_cftc_code"]),
            ("secondary_cftc_code", meta["secondary_cftc_code"]),
            ("legacy_contract_name", meta["legacy_contract_name"]),
            ("secondary_contract_name", meta["secondary_contract_name"]),
            ("selection_mode", meta["contract_selection_mode"]),
        ):
            if str(row.get(field)) != str(expected):
                failures.append(f"contract manifest {market}: {field}={row.get(field)!r}, expected {expected!r}")


def main() -> None:
    config = load_config(ROOT / "config" / "cot_direction_model_v1.json")
    failures: list[str] = []
    latest_dates: dict[str, pd.Timestamp] = {}
    for market in DIRECTIONAL_MARKETS:
        market_failures, latest = validate_market(market, config)
        failures.extend(market_failures)
        if latest is not None:
            latest_dates[market] = latest

    baseline_minimum = max(20, int(config["minimum_history_weeks"]) // 2)
    baseline_latest = {market: latest_dates[market] for market in BASELINE_MARKETS if market in latest_dates}
    if set(baseline_latest) == set(BASELINE_MARKETS):
        for label, path in BASELINE_HISTORIES.items():
            validate_baseline_history(path, label=label, expected_latest=baseline_latest, minimum_rows=baseline_minimum, failures=failures)

    validate_manifest(failures)
    if not (ROOT / "interactive_cot_dashboard.html").exists():
        failures.append("interactive_cot_dashboard.html is missing; macro context cannot be loaded")
    if failures:
        raise RuntimeError("Directional input validation failed:\n- " + "\n- ".join(failures))
    print("Directional input validation passed for all five markets.")


if __name__ == "__main__":
    main()
