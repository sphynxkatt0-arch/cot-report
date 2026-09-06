#!/usr/bin/env python3
"""Exact CFTC Disaggregated Futures-Only extraction for governed commodities.

Gold uses the exact COMEX Gold row (CFTC code 088691). Micro Gold and every
other metal row are excluded by exact name-and-code matching.
"""
from __future__ import annotations

import argparse
import io
import sys
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from cot_overlay_exact import (
    MarketConfig,
    add_next_weekday_returns,
    add_notional_columns,
    add_returns_and_corr_columns,
    build_correlations,
    detect_categories,
    fetch_url,
    find_col,
    load_fred,
    make_overlay,
    make_rebased,
    merge_with_price,
    normalize_columns,
    parse_cftc_date,
)
from cot_market_registry import MARKETS

CURRENT_DISAGGREGATED_FUTURES_URL = "https://www.cftc.gov/dea/newcot/f_disagg.txt"


@dataclass(frozen=True)
class DisaggregatedCategory:
    key: str
    label: str
    long_candidates: list[str]
    short_candidates: list[str]


CATEGORIES = (
    DisaggregatedCategory(
        "producer_merchant",
        "Producer/Merchant",
        ["Prod_Merc_Positions_Long_All"],
        ["Prod_Merc_Positions_Short_All"],
    ),
    DisaggregatedCategory(
        "swap_dealer",
        "Swap Dealer",
        ["Swap_Positions_Long_All"],
        ["Swap__Positions_Short_All", "Swap_Positions_Short_All"],
    ),
    DisaggregatedCategory(
        "managed_money",
        "Managed Money",
        ["M_Money_Positions_Long_All", "Managed_Money_Positions_Long_All"],
        ["M_Money_Positions_Short_All", "Managed_Money_Positions_Short_All"],
    ),
    DisaggregatedCategory(
        "other_reportable",
        "Other Reportables",
        ["Other_Rept_Positions_Long_All", "Other_Reportables_Positions_Long_All"],
        ["Other_Rept_Positions_Short_All", "Other_Reportables_Positions_Short_All"],
    ),
    DisaggregatedCategory(
        "non_reportable",
        "Nonreportables",
        ["NonRept_Positions_Long_All", "Non_Rept_Positions_Long_All"],
        ["NonRept_Positions_Short_All", "Non_Rept_Positions_Short_All"],
    ),
)


def load_cftc_disaggregated_year(year: int) -> pd.DataFrame:
    url = f"https://www.cftc.gov/files/dea/history/fut_disagg_txt_{year}.zip"
    raw = fetch_url(url)
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        names = [name for name in archive.namelist() if not name.endswith("/")]
        if not names:
            raise RuntimeError(f"No file inside {url}")
        with archive.open(names[0]) as handle:
            return normalize_columns(pd.read_csv(handle, low_memory=False))


def load_cftc_current_disaggregated(columns: list[str]) -> pd.DataFrame:
    raw = fetch_url(CURRENT_DISAGGREGATED_FUTURES_URL)
    current = pd.read_csv(io.BytesIO(raw), header=None, names=columns, low_memory=False)
    return normalize_columns(current)


def load_cftc_disaggregated_range(start_year: int, end_year: int) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for year in range(start_year, end_year + 1):
        try:
            frames.append(load_cftc_disaggregated_year(year))
            print(f"Loaded CFTC Disaggregated Futures Only {year}")
        except Exception as exc:
            print(f"WARNING: skipped Disaggregated {year}: {exc}", file=sys.stderr)
    if not frames:
        raise RuntimeError("No CFTC Disaggregated futures-only data loaded")
    if start_year <= datetime.now(UTC).year <= end_year:
        try:
            frames.append(load_cftc_current_disaggregated(list(frames[0].columns)))
            print("Loaded current CFTC Disaggregated Futures Only weekly top-up")
        except Exception as exc:
            print(f"WARNING: skipped current Disaggregated weekly top-up: {exc}", file=sys.stderr)
    return pd.concat(frames, ignore_index=True)


def filter_exact_disaggregated(df: pd.DataFrame, cfg: MarketConfig) -> pd.DataFrame:
    contract_col = find_col(df, ["Market_and_Exchange_Names"])
    code_col = find_col(df, ["CFTC_Contract_Market_Code"])
    date_col = find_col(df, ["Report_Date_as_YYYY_MM_DD", "Report_Date_as_YYYY-MM-DD", "As_of_Date_In_Form_YYMMDD"])
    oi_col = find_col(df, ["Open_Interest_All"])

    contract = df[contract_col].astype(str).str.strip()
    code = df[code_col].astype(str).str.strip()
    mask = contract.eq(cfg.exact_contract_name) & code.eq(cfg.cftc_code)
    out = df.loc[mask, [date_col, contract_col, code_col, oi_col]].copy()
    if out.empty:
        possible = df.loc[code.eq(cfg.cftc_code), [date_col, contract_col, code_col]].drop_duplicates().head(30)
        raise RuntimeError(
            f"No exact Disaggregated rows found for {cfg.exact_contract_name} / {cfg.cftc_code}.\n"
            f"Rows with matching code sample:\n{possible.to_string(index=False)}"
        )

    out["date"] = parse_cftc_date(out[date_col], date_col)
    out["open_interest"] = pd.to_numeric(out[oi_col], errors="coerce")
    out["contract"] = out[contract_col].astype(str)

    available: list[str] = []
    for category in CATEGORIES:
        try:
            long_col = find_col(df, category.long_candidates)
            short_col = find_col(df, category.short_candidates)
        except KeyError:
            print(f"WARNING: missing {category.label} columns; skipping", file=sys.stderr)
            continue
        out[f"{category.key}_long"] = pd.to_numeric(df.loc[mask, long_col], errors="coerce")
        out[f"{category.key}_short"] = pd.to_numeric(df.loc[mask, short_col], errors="coerce")
        out[f"{category.key}_net"] = out[f"{category.key}_long"] - out[f"{category.key}_short"]
        out[f"{category.key}_net_oi_pct"] = out[f"{category.key}_net"] / out["open_interest"] * 100.0
        out[f"{category.key}_short_oi_pct"] = out[f"{category.key}_short"] / out["open_interest"] * 100.0
        available.append(category.key)

    required = {"managed_money", "other_reportable", "non_reportable"}
    if not required.issubset(available):
        raise RuntimeError(f"Disaggregated extraction missing required categories: {sorted(required - set(available))}")

    out = out.dropna(subset=["date", "open_interest"]).sort_values("date").drop_duplicates("date", keep="last")
    columns = ["date", "contract", "open_interest"]
    for key in available:
        columns.extend([
            f"{key}_long", f"{key}_short", f"{key}_net", f"{key}_net_oi_pct", f"{key}_short_oi_pct",
        ])
    return out[columns]


def build_extremes(df: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict] = []
    for key in detect_categories(df):
        for metric in ("net_oi_pct", "short_oi_pct"):
            column = f"{key}_{metric}"
            if column not in df.columns or df[column].dropna().empty:
                continue
            rows.append({"category": key, "extreme": f"highest_{metric}", **df.loc[df[column].idxmax()].to_dict()})
            rows.append({"category": key, "extreme": f"lowest_{metric}", **df.loc[df[column].idxmin()].to_dict()})
        rows.append({"category": key, "extreme": "latest", **df.iloc[-1].to_dict()})
    return pd.DataFrame(rows)


def run_market(cfg: MarketConfig, start: int, end: int, outdir: Path, raw: pd.DataFrame | None = None) -> dict:
    print(f"\n=== {cfg.exact_contract_name} / Disaggregated ===")
    cftc = raw if raw is not None else load_cftc_disaggregated_range(start, end)
    cot = filter_exact_disaggregated(cftc, cfg)
    source_latest_date = cot["date"].max()
    prices = load_fred(cfg.fred_series)
    frame = merge_with_price(cot, prices)
    frame = add_next_weekday_returns(frame, prices)
    frame = add_returns_and_corr_columns(frame)
    categories = detect_categories(frame)
    frame = add_notional_columns(frame, cfg, categories)

    outdir.mkdir(parents=True, exist_ok=True)
    data_path = outdir / f"{cfg.key}_disaggregated_data_{start}_{end}.csv"
    correlations_path = outdir / f"{cfg.key}_disaggregated_correlations_{start}_{end}.csv"
    extremes_path = outdir / f"{cfg.key}_disaggregated_extremes_{start}_{end}.csv"
    frame.to_csv(data_path, index=False)
    build_correlations(frame).to_csv(correlations_path, index=False)
    build_extremes(frame).to_csv(extremes_path, index=False)
    overlay_path = make_overlay(frame, cfg, outdir, start, end, position_key="managed_money")
    rebased_path = make_rebased(frame, cfg, outdir, start, end, position_key="managed_money")

    latest = frame.iloc[-1]
    if latest["date"] < source_latest_date:
        raise RuntimeError(
            f"Generated {cfg.key} Disaggregated data is stale: output {latest['date'].date()} "
            f"but CFTC source latest is {source_latest_date.date()}"
        )
    return {
        "market": cfg.key,
        "report": "disaggregated",
        "latest_date": latest["date"],
        "source_latest_date": source_latest_date,
        "latest_price": latest["price"],
        "latest_open_interest": latest["open_interest"],
        "latest_managed_money_net_oi_pct": latest["managed_money_net_oi_pct"],
        "data_csv": str(data_path),
        "correlations_csv": str(correlations_path),
        "extremes_csv": str(extremes_path),
        "overlay_png": str(overlay_path) if overlay_path else "",
        "rebased_png": str(rebased_path) if rebased_path else "",
    }


def gold_config() -> MarketConfig:
    meta = MARKETS["gold"]
    return MarketConfig(
        key="gold",
        cftc_code=str(meta["secondary_cftc_code"]),
        exact_contract_name=str(meta["secondary_contract_name"]),
        fred_series=str(meta["price_col"]),
        price_label="Gold futures close",
        contract_multiplier=float(meta["contract_multiplier"]),
        contract_unit=str(meta["contract_unit"]),
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=int, default=2016)
    parser.add_argument("--end", type=int, default=datetime.now(UTC).year)
    parser.add_argument("--outdir", default="cot_disaggregated_output")
    args = parser.parse_args()
    outdir = Path(args.outdir)
    summary = run_market(gold_config(), args.start, args.end, outdir)
    summary_path = outdir / f"cot_disaggregated_summary_{args.start}_{args.end}.csv"
    pd.DataFrame([summary]).to_csv(summary_path, index=False)
    print(f"Saved summary: {summary_path}")


if __name__ == "__main__":
    main()
