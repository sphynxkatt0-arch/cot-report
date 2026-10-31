#!/usr/bin/env python3
"""
cot_legacy_correlations.py

Legacy COT category correlation study for the same exact consolidated
NASDAQ-100, S&P 500, and VIX rows used by cot_overlay_exact.py.

This script uses the official CFTC Legacy Futures Only historical files:
  https://www.cftc.gov/files/dea/history/deacotYYYY.zip

Legacy categories:
  - Noncommercial
  - Commercial
  - Total Reportable
  - Nonreportable

Run:
  py cot_legacy_correlations.py --market both --start 2016
  py cot_legacy_correlations.py --market nq --start 2016
  py cot_legacy_correlations.py --market sp500 --start 2016
  py cot_legacy_correlations.py --market vix --start 2016

Output folder:
  cot_legacy_output/
"""

from __future__ import annotations

import argparse
import io
import re
import sys
import urllib.request
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

try:
    import matplotlib.pyplot as plt
except ModuleNotFoundError:
    plt = None

try:
    import requests
except ModuleNotFoundError:
    requests = None


@dataclass(frozen=True)
class MarketConfig:
    key: str
    cftc_code: str
    exact_contract_name: str
    fred_series: str
    price_label: str
    contract_multiplier: float
    contract_unit: str


@dataclass(frozen=True)
class LegacyCategory:
    key: str
    label: str
    long_candidates: list[str]
    short_candidates: list[str]
    spreading_candidates: list[str] | None = None


MARKETS = {
    "nq": MarketConfig(
        key="nq",
        cftc_code="20974+",
        exact_contract_name="NASDAQ-100 Consolidated - CHICAGO MERCANTILE EXCHANGE",
        fred_series="NASDAQ100",
        price_label="NASDAQ-100 close / PA",
        contract_multiplier=20.0,
        contract_unit="NASDAQ-100 Index x $20",
    ),
    "sp500": MarketConfig(
        key="sp500",
        cftc_code="13874+",
        exact_contract_name="S&P 500 Consolidated - CHICAGO MERCANTILE EXCHANGE",
        fred_series="SP500",
        price_label="S&P 500 close / PA",
        contract_multiplier=50.0,
        contract_unit="S&P 500 Index x $50",
    ),
    "vix": MarketConfig(
        key="vix",
        cftc_code="1170E1",
        exact_contract_name="VIX FUTURES - CBOE FUTURES EXCHANGE",
        fred_series="VIXCLS",
        price_label="VIX close / FRED",
        contract_multiplier=1000.0,
        contract_unit="$1,000 x VIX Index",
    ),
    "rty": MarketConfig(
        key="rty",
        cftc_code="239742",
        exact_contract_name="RUSSELL E-MINI - CHICAGO MERCANTILE EXCHANGE",
        fred_series="RUT",
        price_label="Russell 2000 close / Yahoo",
        contract_multiplier=50.0,
        contract_unit="Russell 2000 Index x $50",
    ),
    "dow": MarketConfig(
        key="dow",
        cftc_code="12460+",
        exact_contract_name="DJIA Consolidated - CHICAGO BOARD OF TRADE",
        fred_series="DJIA",
        price_label="DJIA close / Yahoo",
        contract_multiplier=5.0,
        contract_unit="DJIA x $5",
    ),
    "gold": MarketConfig(
        key="gold",
        cftc_code="088691",
        exact_contract_name="GOLD - COMMODITY EXCHANGE INC.",
        fred_series="GOLD",
        price_label="Gold close / Yahoo GC=F",
        contract_multiplier=100.0,
        contract_unit="100 troy oz",
    ),
}


LEGACY_CATEGORIES = [
    LegacyCategory(
        key="noncommercial",
        label="Noncommercial",
        long_candidates=["Noncommercial Positions-Long (All)"],
        short_candidates=["Noncommercial Positions-Short (All)"],
        spreading_candidates=["Noncommercial Positions-Spreading (All)"],
    ),
    LegacyCategory(
        key="commercial",
        label="Commercial",
        long_candidates=["Commercial Positions-Long (All)"],
        short_candidates=["Commercial Positions-Short (All)"],
    ),
    LegacyCategory(
        key="total_reportable",
        label="Total Reportable",
        long_candidates=["Total Reportable Positions-Long (All)", " Total Reportable Positions-Long (All)"],
        short_candidates=["Total Reportable Positions-Short (All)"],
    ),
    LegacyCategory(
        key="nonreportable",
        label="Nonreportable",
        long_candidates=["Nonreportable Positions-Long (All)"],
        short_candidates=["Nonreportable Positions-Short (All)"],
    ),
]

CATEGORY_LABELS = {cat.key: cat.label for cat in LEGACY_CATEGORIES}
FORWARD_WINDOWS = [1, 2, 3, 4, 13, 26, 52]
NEXT_WEEK_TARGET = "next_week_mon_fri_return"
CURRENT_LEGACY_FUTURES_URL = "https://www.cftc.gov/dea/newcot/deafut.txt"
NEXT_WEEKDAYS = [
    ("monday", 0),
    ("tuesday", 1),
    ("wednesday", 2),
    ("thursday", 3),
    ("friday", 4),
]


def fetch_url(url: str, timeout: int = 60) -> bytes:
    headers = {"User-Agent": "Mozilla/5.0 COT legacy correlation script"}
    if requests is not None:
        r = requests.get(url, timeout=timeout, headers=headers)
        r.raise_for_status()
        return r.content
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read()


def normalize_colname(c: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]+", "_", c.strip()).strip("_")


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [normalize_colname(c) for c in df.columns]
    return df


def find_col(df: pd.DataFrame, candidates: list[str]) -> str:
    cols = {c.lower(): c for c in df.columns}
    for cand in candidates:
        key = normalize_colname(cand).lower()
        if key in cols:
            return cols[key]
    raise KeyError(f"Could not find any of {candidates}. Available columns sample: {list(df.columns)[:40]}")


def load_cftc_legacy_year(year: int) -> pd.DataFrame:
    url = f"https://www.cftc.gov/files/dea/history/deacot{year}.zip"
    raw = fetch_url(url)
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        names = [n for n in z.namelist() if not n.endswith("/")]
        if not names:
            raise RuntimeError(f"No file inside {url}")
        with z.open(names[0]) as f:
            return normalize_columns(pd.read_csv(f, low_memory=False))


def load_cftc_current_legacy(columns: list[str]) -> pd.DataFrame:
    raw = fetch_url(CURRENT_LEGACY_FUTURES_URL)
    current = pd.read_csv(io.BytesIO(raw), header=None, names=columns, low_memory=False)
    return normalize_columns(current)


def load_cftc_legacy_range(start_year: int, end_year: int) -> pd.DataFrame:
    frames = []
    for y in range(start_year, end_year + 1):
        try:
            frames.append(load_cftc_legacy_year(y))
            print(f"Loaded CFTC Legacy Futures Only {y}")
        except Exception as e:
            print(f"WARNING: skipped {y}: {e}", file=sys.stderr)
    if not frames:
        raise RuntimeError("No CFTC legacy data loaded.")
    if start_year <= datetime.now(UTC).year <= end_year:
        try:
            frames.append(load_cftc_current_legacy(list(frames[0].columns)))
            print("Loaded current CFTC Legacy Futures Only weekly top-up")
        except Exception as e:
            print(f"WARNING: skipped current weekly legacy top-up: {e}", file=sys.stderr)
    return pd.concat(frames, ignore_index=True)


def parse_cftc_date(s: pd.Series, date_col: str) -> pd.Series:
    if "YYMMDD" in date_col.upper():
        return pd.to_datetime(s.astype(str).str.zfill(6), format="%y%m%d", errors="coerce")
    return pd.to_datetime(s, errors="coerce")


def filter_exact_legacy(df: pd.DataFrame, cfg: MarketConfig) -> pd.DataFrame:
    contract_col = find_col(df, ["Market and Exchange Names"])
    code_col = find_col(df, ["CFTC Contract Market Code"])
    date_col = find_col(df, ["As of Date in Form YYYY-MM-DD", "As of Date in Form YYMMDD"])
    oi_col = find_col(df, ["Open Interest (All)"])

    contract = df[contract_col].astype(str).str.strip()
    code = df[code_col].astype(str).str.strip()
    mask = contract.eq(cfg.exact_contract_name) & code.eq(cfg.cftc_code)

    out = df.loc[mask, [date_col, contract_col, code_col, oi_col]].copy()
    if out.empty:
        possible = df.loc[code.eq(cfg.cftc_code), [date_col, contract_col, code_col]].drop_duplicates().head(30)
        raise RuntimeError(
            f"No exact legacy rows found for {cfg.exact_contract_name} / {cfg.cftc_code}.\n"
            f"Rows with matching code sample:\n{possible.to_string(index=False)}"
        )

    out["date"] = parse_cftc_date(out[date_col], date_col)
    out["contract"] = out[contract_col].astype(str)
    out["open_interest"] = pd.to_numeric(out[oi_col], errors="coerce")

    available_categories: list[str] = []
    for cat in LEGACY_CATEGORIES:
        try:
            long_col = find_col(df, cat.long_candidates)
            short_col = find_col(df, cat.short_candidates)
        except KeyError:
            print(f"WARNING: missing columns for {cat.label}. Skipping.", file=sys.stderr)
            continue

        out[f"{cat.key}_long"] = pd.to_numeric(df.loc[mask, long_col], errors="coerce")
        out[f"{cat.key}_short"] = pd.to_numeric(df.loc[mask, short_col], errors="coerce")
        out[f"{cat.key}_net"] = out[f"{cat.key}_long"] - out[f"{cat.key}_short"]
        out[f"{cat.key}_net_oi_pct"] = out[f"{cat.key}_net"] / out["open_interest"] * 100.0
        out[f"{cat.key}_long_oi_pct"] = out[f"{cat.key}_long"] / out["open_interest"] * 100.0
        out[f"{cat.key}_short_oi_pct"] = out[f"{cat.key}_short"] / out["open_interest"] * 100.0

        if cat.spreading_candidates:
            try:
                spread_col = find_col(df, cat.spreading_candidates)
                out[f"{cat.key}_spreading"] = pd.to_numeric(df.loc[mask, spread_col], errors="coerce")
                out[f"{cat.key}_spreading_oi_pct"] = out[f"{cat.key}_spreading"] / out["open_interest"] * 100.0
            except KeyError:
                pass

        available_categories.append(cat.key)

    if not available_categories:
        raise RuntimeError("No legacy position categories found in CFTC data.")

    out = out.dropna(subset=["date", "open_interest"])
    out = out.sort_values("date").drop_duplicates("date", keep="last")

    columns = ["date", "contract", "open_interest"]
    for key in available_categories:
        columns.extend([
            f"{key}_long",
            f"{key}_short",
            f"{key}_net",
            f"{key}_net_oi_pct",
            f"{key}_long_oi_pct",
            f"{key}_short_oi_pct",
        ])
        if f"{key}_spreading" in out.columns:
            columns.extend([f"{key}_spreading", f"{key}_spreading_oi_pct"])
    return out[columns]


def _clean_fred_col(name: str) -> str:
    return name.strip().lstrip("\ufeff")


def _read_fred_csv(path_or_buffer, series_id: str) -> pd.DataFrame:
    px = pd.read_csv(path_or_buffer)
    px.columns = [_clean_fred_col(c) for c in px.columns]
    cols_lower = {c.lower(): c for c in px.columns}
    date_col = cols_lower.get("date") or cols_lower.get("observation_date")
    if not date_col:
        raise KeyError(f"DATE column not found. Columns: {list(px.columns)[:10]}")

    value_col = series_id if series_id in px.columns else cols_lower.get(series_id.lower())
    if not value_col:
        value_candidates = [c for c in px.columns if c != date_col]
        if not value_candidates:
            raise KeyError(f"Value column not found. Columns: {list(px.columns)[:10]}")
        value_col = value_candidates[0]

    px["date"] = pd.to_datetime(px[date_col], errors="coerce")
    px["price"] = pd.to_numeric(px[value_col].replace(".", np.nan), errors="coerce")
    return px[["date", "price"]].dropna().sort_values("date")


def _find_local_fred_csv(series_id: str) -> Path | None:
    candidates: list[Path] = []
    search_roots = [Path.cwd(), Path(__file__).resolve().parent, Path(__file__).resolve().parent.parent]
    for base in search_roots:
        data_dir = base / "data"
        if data_dir.is_dir():
            candidates.extend(sorted(data_dir.glob(f"{series_id}*.csv")))
    return max(candidates, key=lambda p: p.stat().st_mtime) if candidates else None


# Maps fred_series IDs that have no FRED equivalent to Yahoo Finance symbols.
YAHOO_PRICE_SERIES: dict[str, str] = {
    "RUT": "^RUT",
    "DJIA": "^DJI",
    "GOLD": "GC=F",
}


def _fetch_yahoo_price(yahoo_symbol: str) -> pd.DataFrame:
    """Fetch daily close prices from Yahoo Finance (best-effort, no retries)."""
    import urllib.parse as _uparse
    import json as _json
    encoded = _uparse.quote(yahoo_symbol, safe="")
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{encoded}?range=15y&interval=1d"
    headers = {"User-Agent": "Mozilla/5.0 COT legacy script"}
    if requests is not None:
        r = requests.get(url, timeout=30, headers=headers)
        r.raise_for_status()
        raw = r.content
    else:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read()
    payload = _json.loads(raw)
    result = (payload.get("chart", {}).get("result") or [None])[0]
    if not result:
        raise RuntimeError(f"Yahoo Finance returned no data for {yahoo_symbol}.")
    timestamps = result.get("timestamp") or []
    closes = ((result.get("indicators") or {}).get("quote") or [{}])[0].get("close") or []
    rows = []
    for ts, close in zip(timestamps, closes):
        if close is None:
            continue
        rows.append((datetime.fromtimestamp(int(ts), UTC).date().isoformat(), float(close)))
    if not rows:
        raise RuntimeError(f"Yahoo Finance returned no usable closes for {yahoo_symbol}.")
    df = pd.DataFrame(rows, columns=["date", "price"])
    df["date"] = pd.to_datetime(df["date"])
    return df.dropna().sort_values("date")


def load_fred(series_id: str) -> pd.DataFrame:
    # For markets not on FRED, fetch from Yahoo Finance with a local CSV cache.
    if series_id in YAHOO_PRICE_SERIES:
        yahoo_symbol = YAHOO_PRICE_SERIES[series_id]
        local_path = _find_local_fred_csv(series_id)
        if local_path:
            print(f"Refreshing Yahoo price cache: {local_path}")
            try:
                fresh = _fetch_yahoo_price(yahoo_symbol)
                fresh.rename(columns={"price": series_id}, inplace=True)
                fresh.rename(columns={"date": "observation_date"}, inplace=True)
                fresh.to_csv(local_path, index=False)
                return _read_fred_csv(local_path, series_id)
            except Exception as exc:
                print(f"WARNING: Yahoo refresh failed ({exc}); using cached file.", file=sys.stderr)
                return _read_fred_csv(local_path, series_id)
        print(f"Fetching Yahoo Finance price for {series_id} ({yahoo_symbol}) …")
        df = _fetch_yahoo_price(yahoo_symbol)
        for base in [Path.cwd(), Path(__file__).resolve().parent, Path(__file__).resolve().parent.parent]:
            data_dir = base / "data"
            if data_dir.is_dir():
                dest = data_dir / f"{series_id}.csv"
                out = df.copy().rename(columns={"price": series_id, "date": "observation_date"})
                out.to_csv(dest, index=False)
                print(f"Cached price data → {dest}")
                break
        return df
    local_path = _find_local_fred_csv(series_id)
    if local_path:
        print(f"Using local FRED file: {local_path}")
        return _read_fred_csv(local_path, series_id)
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
    raw = fetch_url(url)
    return _read_fred_csv(io.BytesIO(raw), series_id)


def merge_with_price(cot: pd.DataFrame, fred: pd.DataFrame) -> pd.DataFrame:
    out = pd.merge_asof(cot.sort_values("date"), fred.sort_values("date"), on="date", direction="backward")
    return out.dropna(subset=["price"]).sort_values("date").reset_index(drop=True)


def add_next_weekday_returns(df: pd.DataFrame, fred: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    prices = fred.dropna(subset=["date", "price"]).sort_values("date").reset_index(drop=True)
    price_dates = prices["date"].to_numpy()
    price_values = prices["price"].to_numpy(dtype=float)

    monday_targets = out["date"] + pd.to_timedelta(7 - out["date"].dt.weekday, unit="D")

    for weekday_name, offset in NEXT_WEEKDAYS:
        target = monday_targets + pd.Timedelta(days=offset)
        idx = np.searchsorted(price_dates, target.to_numpy(), side="left")
        valid = (idx >= 0) & (idx < len(prices))
        positions = np.flatnonzero(valid)

        out[f"next_week_{weekday_name}_target"] = target
        out[f"next_week_{weekday_name}_date"] = pd.NaT
        out[f"next_week_{weekday_name}_price"] = np.nan
        if len(positions):
            out.loc[positions, f"next_week_{weekday_name}_date"] = prices.iloc[idx[positions]]["date"].to_numpy()
            out.loc[positions, f"next_week_{weekday_name}_price"] = price_values[idx[positions]]
        out[f"next_week_{weekday_name}_return"] = out[f"next_week_{weekday_name}_price"] / out["price"] - 1

    for i, (weekday_name, _) in enumerate(NEXT_WEEKDAYS):
        prev_price = out["price"] if i == 0 else out[f"next_week_{NEXT_WEEKDAYS[i - 1][0]}_price"]
        out[f"next_week_{weekday_name}_daily_return"] = out[f"next_week_{weekday_name}_price"] / prev_price - 1

    out[NEXT_WEEK_TARGET] = out["next_week_friday_price"] / out["next_week_monday_price"] - 1
    return out


def detect_categories(df: pd.DataFrame) -> list[str]:
    suffix = "_net_oi_pct"
    order = [cat.key for cat in LEGACY_CATEGORIES]
    found = {c[:-len(suffix)] for c in df.columns if c.endswith(suffix)}
    return [key for key in order if key in found]


def add_notional_columns(df: pd.DataFrame, cfg: MarketConfig, categories: list[str]) -> pd.DataFrame:
    out = df.copy()
    out["contract_multiplier"] = float(cfg.contract_multiplier)
    out["contract_unit"] = cfg.contract_unit
    out["contract_notional_usd"] = pd.to_numeric(out["price"], errors="coerce") * cfg.contract_multiplier
    for key in categories:
        for side in ("long", "short", "net"):
            out[f"{key}_{side}_notional_usd"] = (
                pd.to_numeric(out[f"{key}_{side}"], errors="coerce") * out["contract_notional_usd"]
            )
        out[f"{key}_net_flow_1w_notional_usd"] = (
            pd.to_numeric(out[f"{key}_net"], errors="coerce").diff() * out["contract_notional_usd"]
        )
        out[f"{key}_net_flow_4w_notional_usd"] = (
            pd.to_numeric(out[f"{key}_net"], errors="coerce").diff(4) * out["contract_notional_usd"]
        )
    return out


def resolve_position_label(key: str) -> str:
    return CATEGORY_LABELS.get(key, key.replace("_", " ").title())


def add_returns_and_corr_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["price_return_1w"] = out["price"].pct_change()
    for key in detect_categories(out):
        out[f"{key}_net_oi_pct_change"] = out[f"{key}_net_oi_pct"].diff()
        out[f"{key}_net_change"] = out[f"{key}_net"].diff()
        out[f"{key}_long_oi_pct_change"] = out[f"{key}_long_oi_pct"].diff()
        out[f"{key}_short_oi_pct_change"] = out[f"{key}_short_oi_pct"].diff()
    for w in FORWARD_WINDOWS:
        out[f"forward_return_{w}w"] = out["price"].shift(-w) / out["price"] - 1
    return out


def build_correlations(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    next_week_return_metrics = []
    for weekday_name, _ in NEXT_WEEKDAYS:
        next_week_return_metrics.append((
            f"next_week_{weekday_name}_return",
            f"next {weekday_name} close return",
        ))
        next_week_return_metrics.append((
            f"next_week_{weekday_name}_daily_return",
            f"next {weekday_name} single-day return",
        ))
    if NEXT_WEEK_TARGET in df.columns:
        next_week_return_metrics.append((NEXT_WEEK_TARGET, "next week Monday-Friday return"))

    for key in detect_categories(df):
        label = resolve_position_label(key).lower()
        weekly_metrics = [
            (f"{key}_net_oi_pct_change", f"weekly change in {label} net/OI pct vs weekly price return"),
            (f"{key}_net_change", f"weekly change in {label} net contracts vs weekly price return"),
            (f"{key}_long_oi_pct_change", f"weekly change in {label} long/OI pct vs weekly price return"),
            (f"{key}_short_oi_pct_change", f"weekly change in {label} short/OI pct vs weekly price return"),
        ]
        for metric_col, relationship in weekly_metrics:
            rows.append({
                "category": key,
                "relationship": relationship,
                "position_metric": metric_col,
                "pearson_r": df[metric_col].corr(df["price_return_1w"]),
                "observations": int(df[[metric_col, "price_return_1w"]].dropna().shape[0]),
            })
            for return_col, return_label in next_week_return_metrics:
                if return_col not in df.columns:
                    continue
                rows.append({
                    "category": key,
                    "relationship": relationship.replace("weekly price return", return_label),
                    "position_metric": metric_col,
                    "return_metric": return_col,
                    "pearson_r": df[metric_col].corr(df[return_col]),
                    "observations": int(df[[metric_col, return_col]].dropna().shape[0]),
                })

        level_metrics = [
            (f"{key}_net_oi_pct", f"{label} net/OI pct"),
            (f"{key}_net", f"{label} net contracts"),
            (f"{key}_long_oi_pct", f"{label} long/OI pct"),
            (f"{key}_short_oi_pct", f"{label} short/OI pct"),
        ]
        for return_col, return_label in next_week_return_metrics:
            if return_col not in df.columns:
                continue
            for metric_col, metric_label in level_metrics:
                rows.append({
                    "category": key,
                    "relationship": f"{metric_label} vs {return_label}",
                    "position_metric": metric_col,
                    "return_metric": return_col,
                    "pearson_r": df[metric_col].corr(df[return_col]),
                    "observations": int(df[[metric_col, return_col]].dropna().shape[0]),
                })
        for w in FORWARD_WINDOWS:
            fcol = f"forward_return_{w}w"
            for metric_col, metric_label in level_metrics:
                rows.append({
                    "category": key,
                    "relationship": f"{metric_label} vs forward {w}w price return",
                    "position_metric": metric_col,
                    "return_metric": fcol,
                    "pearson_r": df[metric_col].corr(df[fcol]),
                    "observations": int(df[[metric_col, fcol]].dropna().shape[0]),
                })
    return pd.DataFrame(rows)


def make_net_overlay(df: pd.DataFrame, cfg: MarketConfig, outdir: Path, start: int, end: int) -> Path | None:
    if plt is None:
        print("WARNING: matplotlib is not installed; skipping legacy overlay PNG.", file=sys.stderr)
        return None
    fig, ax1 = plt.subplots(figsize=(15, 8))
    colors = {
        "noncommercial": "#1f77b4",
        "commercial": "#2ca02c",
        "total_reportable": "#9467bd",
        "nonreportable": "#ff7f0e",
    }

    lines = []
    labels = []
    for key in detect_categories(df):
        col = f"{key}_net_oi_pct"
        line, = ax1.plot(df["date"], df[col], linewidth=1.5, color=colors.get(key), label=f"{resolve_position_label(key)} net/OI")
        lines.append(line)
        labels.append(line.get_label())
    ax1.axhline(0, color="gray", linestyle="--", linewidth=0.9)
    ax1.set_xlabel("Date")
    ax1.set_ylabel("Legacy category net / open interest (%)")

    ax2 = ax1.twinx()
    price_line, = ax2.plot(df["date"], df["price"], color="#d62728", linestyle="--", linewidth=1.4, label=cfg.price_label)
    ax2.set_ylabel(cfg.price_label, color="#d62728")
    ax2.tick_params(axis="y", labelcolor="#d62728")
    lines.append(price_line)
    labels.append(price_line.get_label())

    ax1.set_title(f"{cfg.exact_contract_name}: Legacy COT Net/OI vs Price ({start}-{end})")
    fig.legend(lines, labels, loc="upper left", bbox_to_anchor=(0.08, 0.91), ncols=2)
    fig.tight_layout()

    path = outdir / f"{cfg.key}_legacy_net_oi_overlay_{start}_{end}.png"
    fig.savefig(str(path.resolve()), dpi=200, bbox_inches="tight")
    plt.close(fig)
    return path


def make_corr_heatmap(corr: pd.DataFrame, cfg: MarketConfig, outdir: Path, start: int, end: int) -> Path | None:
    if plt is None:
        print("WARNING: matplotlib is not installed; skipping legacy heatmap PNG.", file=sys.stderr)
        return None
    forward = corr[
        corr["relationship"].str.contains("net/OI pct vs forward", regex=False)
        & corr["position_metric"].str.endswith("_net_oi_pct")
    ].copy()
    forward["window"] = forward["relationship"].str.extract(r"forward (\d+w)")
    pivot = forward.pivot(index="category", columns="window", values="pearson_r")
    pivot = pivot.reindex([key for key in [cat.key for cat in LEGACY_CATEGORIES] if key in pivot.index])
    pivot = pivot[[f"{w}w" for w in FORWARD_WINDOWS if f"{w}w" in pivot.columns]]

    fig, ax = plt.subplots(figsize=(10, 4.8))
    im = ax.imshow(pivot.to_numpy(dtype=float), cmap="RdBu_r", vmin=-1, vmax=1, aspect="auto")
    ax.set_xticks(range(len(pivot.columns)), pivot.columns)
    ax.set_yticks(range(len(pivot.index)), [resolve_position_label(k) for k in pivot.index])
    ax.set_title(f"{cfg.key.upper()} legacy net/OI correlation with forward returns ({start}-{end})")
    for i in range(pivot.shape[0]):
        for j in range(pivot.shape[1]):
            val = pivot.iloc[i, j]
            if pd.notna(val):
                ax.text(j, i, f"{val:.2f}", ha="center", va="center", color="black", fontsize=9)
    fig.colorbar(im, ax=ax, label="Pearson r")
    fig.tight_layout()

    path = outdir / f"{cfg.key}_legacy_forward_corr_heatmap_{start}_{end}.png"
    fig.savefig(str(path.resolve()), dpi=200, bbox_inches="tight")
    plt.close(fig)
    return path


def build_extremes(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for key in detect_categories(df):
        for metric in ["net_oi_pct", "long_oi_pct", "short_oi_pct"]:
            col = f"{key}_{metric}"
            if col not in df.columns or df[col].dropna().empty:
                continue
            rows.append({"category": key, "extreme": f"highest_{metric}", **df.loc[df[col].idxmax()].to_dict()})
            rows.append({"category": key, "extreme": f"lowest_{metric}", **df.loc[df[col].idxmin()].to_dict()})
        rows.append({"category": key, "extreme": "latest", **df.iloc[-1].to_dict()})
    return pd.DataFrame(rows)


def run_market(cfg: MarketConfig, start: int, end: int, outdir: Path, raw: pd.DataFrame | None = None) -> dict:
    print(f"\n=== {cfg.exact_contract_name} ===")
    cftc = raw if raw is not None else load_cftc_legacy_range(start, end)
    cot = filter_exact_legacy(cftc, cfg)
    source_latest_date = cot["date"].max()
    fred = load_fred(cfg.fred_series)
    df = merge_with_price(cot, fred)
    df = add_next_weekday_returns(df, fred)
    df = add_returns_and_corr_columns(df)
    categories = detect_categories(df)
    df = add_notional_columns(df, cfg, categories)

    outdir.mkdir(parents=True, exist_ok=True)
    data_path = outdir / f"{cfg.key}_legacy_data_{start}_{end}.csv"
    corr_path = outdir / f"{cfg.key}_legacy_correlations_{start}_{end}.csv"
    extremes_path = outdir / f"{cfg.key}_legacy_extremes_{start}_{end}.csv"

    df.to_csv(data_path, index=False)
    corr = build_correlations(df)
    corr.to_csv(corr_path, index=False)
    build_extremes(df).to_csv(extremes_path, index=False)

    overlay_path = make_net_overlay(df, cfg, outdir, start, end)
    heatmap_path = make_corr_heatmap(corr, cfg, outdir, start, end)

    latest = df.iloc[-1]
    if latest["date"] < source_latest_date:
        raise RuntimeError(
            f"Generated {cfg.key} legacy data is stale: output latest "
            f"{latest['date'].date()} but CFTC source latest is {source_latest_date.date()}."
        )
    print("\nLatest exact legacy row:")
    print(f"date: {latest['date'].date()}")
    print(f"CFTC source latest date: {source_latest_date.date()}")
    print(f"price: {latest['price']:,.2f}")
    print(f"open_interest: {latest['open_interest']:,.0f}")
    for key in categories:
        label = resolve_position_label(key)
        print(f"{label} net: {latest[f'{key}_net']:,.0f} ({latest[f'{key}_net_oi_pct']:.2f}% of OI)")

    strongest = corr.dropna(subset=["pearson_r"]).copy()
    strongest["abs_pearson_r"] = strongest["pearson_r"].abs()
    strongest = strongest.sort_values("abs_pearson_r", ascending=False).head(12)
    print("\nStrongest absolute correlations:")
    print(strongest.drop(columns=["abs_pearson_r"]).to_string(index=False, float_format=lambda x: f"{x:.4f}"))

    print("\nSaved:")
    print(data_path)
    print(corr_path)
    print(extremes_path)
    if overlay_path:
        print(overlay_path)
    if heatmap_path:
        print(heatmap_path)

    return {
        "market": cfg.key,
        "latest_date": latest["date"],
        "source_latest_date": source_latest_date,
        "latest_price": latest["price"],
        "latest_open_interest": latest["open_interest"],
        "latest_noncommercial_net_oi_pct": latest.get("noncommercial_net_oi_pct"),
        "latest_commercial_net_oi_pct": latest.get("commercial_net_oi_pct"),
        "latest_nonreportable_net_oi_pct": latest.get("nonreportable_net_oi_pct"),
        "data_csv": str(data_path),
        "correlations_csv": str(corr_path),
        "extremes_csv": str(extremes_path),
        "overlay_png": str(overlay_path) if overlay_path else "",
        "heatmap_png": str(heatmap_path) if heatmap_path else "",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--market", choices=["nq", "sp500", "vix", "rty", "dow", "gold", "all"], default="all")
    parser.add_argument("--start", type=int, default=2016)
    parser.add_argument("--end", type=int, default=datetime.now(UTC).year)
    parser.add_argument("--outdir", default="cot_legacy_output")
    args = parser.parse_args()

    outdir = Path(args.outdir)
    keys = list(MARKETS) if args.market == "all" else [args.market]
    raw = load_cftc_legacy_range(args.start, args.end) if len(keys) > 1 else None
    summaries = [run_market(MARKETS[key], args.start, args.end, outdir, raw=raw) for key in keys]
    summary_path = outdir / f"cot_legacy_summary_{args.start}_{args.end}.csv"
    pd.DataFrame(summaries).to_csv(summary_path, index=False)
    print(f"\nSaved summary: {summary_path}")


if __name__ == "__main__":
    main()
