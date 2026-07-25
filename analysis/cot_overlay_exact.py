#!/usr/bin/env python3
"""
cot_overlay_exact.py

Accurate continuous weekly COT/FRED overlay using ONLY the official CFTC
"Consolidated" rows, not the E-mini/Micro/component rows.

Markets:
  NQ:     NASDAQ-100 Consolidated - CHICAGO MERCANTILE EXCHANGE
          CFTC code 20974+
          FRED NASDAQ100

  SP500:  S&P 500 Consolidated - CHICAGO MERCANTILE EXCHANGE
          CFTC code 13874+
          FRED SP500

  VIX:    VIX FUTURES - CBOE FUTURES EXCHANGE
          CFTC code 1170E1
          FRED VIXCLS

Install:
  pip install pandas matplotlib requests

Run:
  python cot_overlay_exact.py --market both --start 2016
  python cot_overlay_exact.py --market nq --start 2016
  python cot_overlay_exact.py --market sp500 --start 2016

Output folder:
  cot_exact_output/
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
class PositionCategory:
    key: str
    label: str
    long_candidates: list[str]
    short_candidates: list[str]


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
}


POSITION_CATEGORIES = [
    PositionCategory(
        key="asset_mgr",
        label="Asset Manager",
        long_candidates=["Asset_Mgr_Positions_Long_All"],
        short_candidates=["Asset_Mgr_Positions_Short_All"],
    ),
    PositionCategory(
        key="dealer",
        label="Dealer/Intermediary",
        long_candidates=["Dealer_Positions_Long_All"],
        short_candidates=["Dealer_Positions_Short_All"],
    ),
    PositionCategory(
        key="lev_money",
        label="Leveraged Funds",
        long_candidates=["Lev_Money_Positions_Long_All"],
        short_candidates=["Lev_Money_Positions_Short_All"],
    ),
    PositionCategory(
        key="other_reportable",
        label="Other Reportables",
        long_candidates=["Other_Rept_Positions_Long_All", "Other_Reportables_Positions_Long_All"],
        short_candidates=["Other_Rept_Positions_Short_All", "Other_Reportables_Positions_Short_All"],
    ),
    PositionCategory(
        key="non_reportable",
        label="Non-Reportable",
        long_candidates=["NonRept_Positions_Long_All", "Non_Rept_Positions_Long_All"],
        short_candidates=["NonRept_Positions_Short_All", "Non_Rept_Positions_Short_All"],
    ),
]

CATEGORY_LABELS = {cat.key: cat.label for cat in POSITION_CATEGORIES}
FORWARD_WINDOWS = [1, 2, 3, 4, 13, 26, 52]
NEXT_WEEKDAYS = [
    ("monday", 0),
    ("tuesday", 1),
    ("wednesday", 2),
    ("thursday", 3),
    ("friday", 4),
]
CURRENT_TFF_FUTURES_URL = "https://www.cftc.gov/dea/newcot/FinFutWk.txt"


def fetch_url(url: str, timeout: int = 60) -> bytes:
    headers = {"User-Agent": "Mozilla/5.0 COT overlay exact script"}
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


def load_cftc_tff_year(year: int) -> pd.DataFrame:
    url = f"https://www.cftc.gov/files/dea/history/fut_fin_txt_{year}.zip"
    raw = fetch_url(url)
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        names = [n for n in z.namelist() if not n.endswith("/")]
        if not names:
            raise RuntimeError(f"No file inside {url}")
        with z.open(names[0]) as f:
            return normalize_columns(pd.read_csv(f, low_memory=False))


def load_cftc_current_tff(columns: list[str]) -> pd.DataFrame:
    raw = fetch_url(CURRENT_TFF_FUTURES_URL)
    current = pd.read_csv(io.BytesIO(raw), header=None, names=columns, low_memory=False)
    return normalize_columns(current)


def load_cftc_tff_range(start_year: int, end_year: int) -> pd.DataFrame:
    frames = []
    for y in range(start_year, end_year + 1):
        try:
            frames.append(load_cftc_tff_year(y))
            print(f"Loaded CFTC TFF Futures Only {y}")
        except Exception as e:
            print(f"WARNING: skipped {y}: {e}", file=sys.stderr)
    if not frames:
        raise RuntimeError("No CFTC data loaded.")
    if start_year <= datetime.now(UTC).year <= end_year:
        try:
            frames.append(load_cftc_current_tff(list(frames[0].columns)))
            print("Loaded current CFTC TFF Futures Only weekly top-up")
        except Exception as e:
            print(f"WARNING: skipped current weekly TFF top-up: {e}", file=sys.stderr)
    return pd.concat(frames, ignore_index=True)


def parse_cftc_date(s: pd.Series, date_col: str) -> pd.Series:
    if "YYMMDD" in date_col.upper():
        return pd.to_datetime(s.astype(str).str.zfill(6), format="%y%m%d", errors="coerce")
    return pd.to_datetime(s, errors="coerce")


def filter_exact_consolidated(df: pd.DataFrame, cfg: MarketConfig) -> pd.DataFrame:
    contract_col = find_col(df, ["Market_and_Exchange_Names"])
    code_col = find_col(df, ["CFTC_Contract_Market_Code"])
    date_col = find_col(df, ["Report_Date_as_YYYY_MM_DD", "Report_Date_as_YYYY-MM-DD", "As_of_Date_In_Form_YYMMDD"])
    oi_col = find_col(df, ["Open_Interest_All"])

    contract = df[contract_col].astype(str).str.strip()
    code = df[code_col].astype(str).str.strip()

    # IMPORTANT: exact consolidated row only.
    # This avoids accidentally summing: Consolidated + E-mini + Micro + dividend/TR rows.
    mask = contract.eq(cfg.exact_contract_name) & code.eq(cfg.cftc_code)

    out = df.loc[mask, [date_col, contract_col, code_col, oi_col]].copy()
    if out.empty:
        # Useful debugging if CFTC changes formatting.
        possible = df.loc[code.eq(cfg.cftc_code), [date_col, contract_col, code_col]].drop_duplicates().head(30)
        raise RuntimeError(
            f"No exact rows found for {cfg.exact_contract_name} / {cfg.cftc_code}.\n"
            f"Rows with matching code sample:\n{possible.to_string(index=False)}"
        )

    out["date"] = parse_cftc_date(out[date_col], date_col)
    out["open_interest"] = pd.to_numeric(out[oi_col], errors="coerce")
    out["contract"] = out[contract_col].astype(str)

    available_categories: list[str] = []
    for cat in POSITION_CATEGORIES:
        try:
            long_col = find_col(df, cat.long_candidates)
            short_col = find_col(df, cat.short_candidates)
        except KeyError:
            print(f"WARNING: missing columns for {cat.label} positions. Skipping.", file=sys.stderr)
            continue
        out[f"{cat.key}_long"] = pd.to_numeric(df.loc[mask, long_col], errors="coerce")
        out[f"{cat.key}_short"] = pd.to_numeric(df.loc[mask, short_col], errors="coerce")
        out[f"{cat.key}_net"] = out[f"{cat.key}_long"] - out[f"{cat.key}_short"]
        out[f"{cat.key}_net_oi_pct"] = out[f"{cat.key}_net"] / out["open_interest"] * 100.0
        out[f"{cat.key}_short_oi_pct"] = out[f"{cat.key}_short"] / out["open_interest"] * 100.0
        available_categories.append(cat.key)

    if not available_categories:
        raise RuntimeError("No position categories found in CFTC data.")

    out = out.dropna(subset=["date", "open_interest"])
    out = out.sort_values("date").drop_duplicates("date", keep="last")

    columns = ["date", "contract", "open_interest"]
    for key in available_categories:
        columns.extend([
            f"{key}_long",
            f"{key}_short",
            f"{key}_net",
            f"{key}_net_oi_pct",
            f"{key}_short_oi_pct",
        ])

    return out[columns]


def _clean_fred_col(name: str) -> str:
    return name.strip().lstrip("\ufeff")


def _read_fred_csv(path: Path, series_id: str) -> pd.DataFrame:
    px = pd.read_csv(path)
    px.columns = [_clean_fred_col(c) for c in px.columns]
    cols_lower = {c.lower(): c for c in px.columns}
    date_col = cols_lower.get("date") or cols_lower.get("observation_date")
    if not date_col:
        raise KeyError(f"DATE column not found in {path}. Columns: {list(px.columns)[:10]}")

    value_col = series_id if series_id in px.columns else cols_lower.get(series_id.lower())
    if not value_col:
        value_candidates = [c for c in px.columns if c != date_col]
        if not value_candidates:
            raise KeyError(f"Value column not found in {path}. Columns: {list(px.columns)[:10]}")
        value_col = value_candidates[0]

    px["date"] = pd.to_datetime(px[date_col], errors="coerce")
    px["price"] = pd.to_numeric(px[value_col].replace(".", np.nan), errors="coerce")
    return px[["date", "price"]].dropna().sort_values("date")


def _find_local_fred_csv(series_id: str) -> Path | None:
    candidates: list[Path] = []
    for base in [Path.cwd(), Path(__file__).resolve().parent, Path(__file__).resolve().parent.parent]:
        data_dir = base / "data"
        if not data_dir.is_dir():
            continue
        candidates.extend(sorted(data_dir.glob(f"{series_id}*.csv")))
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def load_fred(series_id: str) -> pd.DataFrame:
    local_path = _find_local_fred_csv(series_id)
    if local_path:
        print(f"Using local FRED file: {local_path}")
        return _read_fred_csv(local_path, series_id)
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
    raw = fetch_url(url)
    return _read_fred_csv(io.BytesIO(raw), series_id)


def merge_with_price(cot: pd.DataFrame, fred: pd.DataFrame) -> pd.DataFrame:
    # COT positions are Tuesday. If FRED lacks that exact date due to holiday, use previous available close.
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

    return out


def detect_categories(df: pd.DataFrame) -> list[str]:
    suffix = "_net_oi_pct"
    return sorted({c[:-len(suffix)] for c in df.columns if c.endswith(suffix)})


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


def resolve_position_key(df: pd.DataFrame) -> str:
    if "asset_mgr_net_oi_pct" in df.columns:
        return "asset_mgr"
    categories = detect_categories(df)
    if not categories:
        raise RuntimeError("No position categories available for plotting.")
    return categories[0]


def add_returns_and_corr_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["price_return_1w"] = out["price"].pct_change()
    for key in detect_categories(out):
        out[f"{key}_net_oi_pct_change"] = out[f"{key}_net_oi_pct"].diff()
        out[f"{key}_net_change"] = out[f"{key}_net"].diff()
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

    for key in detect_categories(df):
        label = resolve_position_label(key).lower()
        net_pct_change_col = f"{key}_net_oi_pct_change"
        net_change_col = f"{key}_net_change"
        rows.append({
            "category": key,
            "relationship": f"weekly change in {label} net/OI pct vs weekly price return",
            "position_metric": net_pct_change_col,
            "pearson_r": df[net_pct_change_col].corr(df["price_return_1w"]),
            "observations": int(df[[net_pct_change_col, "price_return_1w"]].dropna().shape[0]),
        })
        for return_col, return_label in next_week_return_metrics:
            if return_col in df.columns:
                rows.append({
                    "category": key,
                    "relationship": f"weekly change in {label} net/OI pct vs {return_label}",
                    "position_metric": net_pct_change_col,
                    "return_metric": return_col,
                    "pearson_r": df[net_pct_change_col].corr(df[return_col]),
                    "observations": int(df[[net_pct_change_col, return_col]].dropna().shape[0]),
                })
        rows.append({
            "category": key,
            "relationship": f"weekly change in {label} net contracts vs weekly price return",
            "position_metric": net_change_col,
            "pearson_r": df[net_change_col].corr(df["price_return_1w"]),
            "observations": int(df[[net_change_col, "price_return_1w"]].dropna().shape[0]),
        })
        for return_col, return_label in next_week_return_metrics:
            if return_col in df.columns:
                rows.append({
                    "category": key,
                    "relationship": f"weekly change in {label} net contracts vs {return_label}",
                    "position_metric": net_change_col,
                    "return_metric": return_col,
                    "pearson_r": df[net_change_col].corr(df[return_col]),
                    "observations": int(df[[net_change_col, return_col]].dropna().shape[0]),
                })
        for return_col, return_label in next_week_return_metrics:
            if return_col not in df.columns:
                continue
            for metric_col, metric_label in [
                (f"{key}_net_oi_pct", f"{label} net/OI pct"),
                (f"{key}_net", f"{label} net contracts"),
                (f"{key}_short_oi_pct", f"{label} short/OI pct"),
            ]:
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
            net_pct_col = f"{key}_net_oi_pct"
            net_col = f"{key}_net"
            rows.append({
                "category": key,
                "relationship": f"{label} net/OI pct vs forward {w}w price return",
                "position_metric": net_pct_col,
                "return_metric": fcol,
                "pearson_r": df[net_pct_col].corr(df[fcol]),
                "observations": int(df[[net_pct_col, fcol]].dropna().shape[0]),
            })
            rows.append({
                "category": key,
                "relationship": f"{label} net contracts vs forward {w}w price return",
                "position_metric": net_col,
                "return_metric": fcol,
                "pearson_r": df[net_col].corr(df[fcol]),
                "observations": int(df[[net_col, fcol]].dropna().shape[0]),
            })
    return pd.DataFrame(rows)


def make_overlay(
    df: pd.DataFrame,
    cfg: MarketConfig,
    outdir: Path,
    start: int,
    end: int,
    position_key: str | None = None,
) -> Path | None:
    if plt is None:
        print("WARNING: matplotlib is not installed; skipping exact overlay PNG.", file=sys.stderr)
        return None
    color_pos = "#1f77b4"
    color_price = "#d62728"

    pos_key = position_key or resolve_position_key(df)
    pos_label = resolve_position_label(pos_key)
    pos_col = f"{pos_key}_net_oi_pct"

    fig, ax1 = plt.subplots(figsize=(15, 8))
    l1, = ax1.plot(df["date"], df[pos_col], color=color_pos, linewidth=1.8,
                   label=f"{pos_label} net / OI (%)")
    ax1.set_ylabel(f"{pos_label} net / OI (%)", color=color_pos)
    ax1.tick_params(axis="y", labelcolor=color_pos)
    ax1.axhline(0, color="gray", linestyle="--", linewidth=0.9)
    ax1.set_xlabel("Date")

    ax2 = ax1.twinx()
    l2, = ax2.plot(df["date"], df["price"], color=color_price, linestyle="--", linewidth=1.6,
                   label=cfg.price_label)
    ax2.set_ylabel(cfg.price_label, color=color_price)
    ax2.tick_params(axis="y", labelcolor=color_price)

    high = df.loc[df[pos_col].idxmax()]
    low = df.loc[df[pos_col].idxmin()]
    latest = df.iloc[-1]
    for label, r, offset in [
        ("Highest net/OI", high, (8, 12)),
        ("Lowest net/OI", low, (8, -34)),
        ("Latest", latest, (-115, 12)),
    ]:
        ax1.scatter([r["date"]], [r[pos_col]], color=color_pos, s=55, zorder=5)
        ax1.annotate(
            f"{label}\n{r['date'].date()}\n{r[pos_col]:.2f}%",
            xy=(r["date"], r[pos_col]),
            xytext=offset,
            textcoords="offset points",
            fontsize=8,
            bbox=dict(boxstyle="round,pad=0.25", fc="white", ec="0.7", alpha=0.92),
            arrowprops=dict(arrowstyle="->", lw=0.7, color="gray"),
        )

    fig.legend([l1, l2], [l1.get_label(), l2.get_label()], loc="upper left", bbox_to_anchor=(0.08, 0.91))
    ax1.set_title(f"{cfg.exact_contract_name}: Exact Consolidated COT vs Price ({start}-{end})")
    fig.tight_layout()

    path = outdir / f"{cfg.key}_exact_consolidated_overlay_{start}_{end}.png"
    fig.savefig(path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    return path


def make_rebased(
    df: pd.DataFrame,
    cfg: MarketConfig,
    outdir: Path,
    start: int,
    end: int,
    position_key: str | None = None,
) -> Path | None:
    if plt is None:
        print("WARNING: matplotlib is not installed; skipping exact rebased PNG.", file=sys.stderr)
        return None
    pos_key = position_key or resolve_position_key(df)
    pos_label = resolve_position_label(pos_key)
    pos_col = f"{pos_key}_net_oi_pct"
    d = df.copy()
    d["position_rebased"] = d[pos_col] / d[pos_col].iloc[0] * 100
    d["price_rebased"] = d["price"] / d["price"].iloc[0] * 100

    fig, ax = plt.subplots(figsize=(15, 8))
    ax.plot(d["date"], d["position_rebased"], color="#1f77b4", linewidth=1.8,
            label=f"{pos_label} net/OI rebased")
    ax.plot(d["date"], d["price_rebased"], color="#d62728", linestyle="--", linewidth=1.6, label=f"{cfg.price_label} rebased")
    ax.set_xlabel("Date")
    ax.set_ylabel("Rebased index, first valid date = 100")
    ax.set_title(f"{cfg.exact_contract_name}: Rebased Shape Overlay ({start}-{end})")
    ax.legend(loc="upper left")
    fig.tight_layout()

    path = outdir / f"{cfg.key}_exact_consolidated_rebased_{start}_{end}.png"
    fig.savefig(path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    return path


def run_market(cfg: MarketConfig, start: int, end: int, outdir: Path, raw: pd.DataFrame | None = None) -> dict:
    print(f"\n=== {cfg.exact_contract_name} ===")
    cftc = raw if raw is not None else load_cftc_tff_range(start, end)
    cot = filter_exact_consolidated(cftc, cfg)
    source_latest_date = cot["date"].max()
    fred = load_fred(cfg.fred_series)
    df = merge_with_price(cot, fred)
    df = add_next_weekday_returns(df, fred)
    df = add_returns_and_corr_columns(df)
    categories = detect_categories(df)
    df = add_notional_columns(df, cfg, categories)
    position_key = resolve_position_key(df)

    outdir.mkdir(parents=True, exist_ok=True)
    data_path = outdir / f"{cfg.key}_exact_consolidated_data_{start}_{end}.csv"
    corr_path = outdir / f"{cfg.key}_exact_consolidated_correlations_{start}_{end}.csv"
    extremes_path = outdir / f"{cfg.key}_exact_consolidated_extremes_{start}_{end}.csv"

    df.to_csv(data_path, index=False)
    corr = build_correlations(df)
    corr.to_csv(corr_path, index=False)

    extremes_rows = []
    for key in categories:
        net_pct_col = f"{key}_net_oi_pct"
        short_pct_col = f"{key}_short_oi_pct"
        if df[net_pct_col].dropna().empty:
            continue
        extremes_rows.append({
            "category": key,
            "extreme": "highest_net_oi_pct",
            **df.loc[df[net_pct_col].idxmax()].to_dict(),
        })
        extremes_rows.append({
            "category": key,
            "extreme": "lowest_net_oi_pct",
            **df.loc[df[net_pct_col].idxmin()].to_dict(),
        })
        if short_pct_col in df.columns and not df[short_pct_col].dropna().empty:
            extremes_rows.append({
                "category": key,
                "extreme": "highest_short_oi_pct",
                **df.loc[df[short_pct_col].idxmax()].to_dict(),
            })
        extremes_rows.append({
            "category": key,
            "extreme": "latest",
            **df.iloc[-1].to_dict(),
        })

    extremes = pd.DataFrame(extremes_rows)
    extremes.to_csv(extremes_path, index=False)

    overlay_path = make_overlay(df, cfg, outdir, start, end, position_key=position_key)
    rebased_path = make_rebased(df, cfg, outdir, start, end, position_key=position_key)

    latest = df.iloc[-1]
    if latest["date"] < source_latest_date:
        raise RuntimeError(
            f"Generated {cfg.key} TFF data is stale: output latest "
            f"{latest['date'].date()} but CFTC source latest is {source_latest_date.date()}."
        )
    print("\nLatest exact consolidated row:")
    print(f"date: {latest['date'].date()}")
    print(f"CFTC source latest date: {source_latest_date.date()}")
    print(f"open_interest: {latest['open_interest']:,.0f}")
    for key in categories:
        label = resolve_position_label(key)
        print(f"{label} long: {latest[f'{key}_long']:,.0f}")
        print(f"{label} short: {latest[f'{key}_short']:,.0f}")
        print(f"{label} net: {latest[f'{key}_net']:,.0f}")
        print(f"{label} net/OI: {latest[f'{key}_net_oi_pct']:.2f}%")

    print("\nCorrelation table:")
    print(corr.to_string(index=False, float_format=lambda x: f"{x:.4f}"))

    print("\nSaved:")
    if overlay_path:
        print(overlay_path)
    if rebased_path:
        print(rebased_path)
    print(data_path)
    print(corr_path)
    print(extremes_path)

    return {
        "market": cfg.key,
        "latest_date": latest["date"],
        "source_latest_date": source_latest_date,
        "latest_price": latest["price"],
        "latest_open_interest": latest["open_interest"],
        "latest_asset_mgr_net": latest["asset_mgr_net"],
        "latest_asset_mgr_net_oi_pct": latest["asset_mgr_net_oi_pct"],
        "highest_date": df.loc[df["asset_mgr_net_oi_pct"].idxmax(), "date"],
        "highest_asset_mgr_net_oi_pct": df["asset_mgr_net_oi_pct"].max(),
        "lowest_date": df.loc[df["asset_mgr_net_oi_pct"].idxmin(), "date"],
        "lowest_asset_mgr_net_oi_pct": df["asset_mgr_net_oi_pct"].min(),
        "data_csv": str(data_path),
        "correlations_csv": str(corr_path),
        "extremes_csv": str(extremes_path),
        "overlay_png": str(overlay_path) if overlay_path else "",
        "rebased_png": str(rebased_path) if rebased_path else "",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--market", choices=["nq", "sp500", "vix", "both"], default="both")
    parser.add_argument("--start", type=int, default=2016)
    parser.add_argument("--end", type=int, default=datetime.now(UTC).year)
    parser.add_argument("--outdir", default="cot_exact_output")
    args = parser.parse_args()

    outdir = Path(args.outdir)
    keys = list(MARKETS) if args.market == "both" else [args.market]
    raw = load_cftc_tff_range(args.start, args.end) if len(keys) > 1 else None
    summaries = []
    for key in keys:
        summaries.append(run_market(MARKETS[key], args.start, args.end, outdir, raw=raw))

    pd.DataFrame(summaries).to_csv(outdir / f"cot_exact_summary_{args.start}_{args.end}.csv", index=False)
    print(f"\nSaved summary: {outdir / f'cot_exact_summary_{args.start}_{args.end}.csv'}")


if __name__ == "__main__":
    main()
