#!/usr/bin/env python3
"""Refresh public macro inputs and persist a lookahead-safe canonical history.

This module deliberately does not change the governed COT model.  It refreshes
the macro source caches, preserves last-good observations when a source is
temporarily unavailable, applies conservative availability lags, and writes a
historical macro artifact that can be consumed without scraping generated HTML.
"""
from __future__ import annotations

import csv
import json
import math
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

import build_interactive_cot_dashboard as dashboard

OUT_DIR = dashboard.ROOT / "model_output"
HISTORY_OUT = OUT_DIR / "macro_history.csv"
LATEST_OUT = OUT_DIR / "macro_history_latest.json"
PROVENANCE_OUT = OUT_DIR / "macro_history_provenance.json"

# Availability is intentionally conservative at business-day granularity.
# The history is designed for post-close / COT-release research, not intraday
# timestamp reconstruction.
AVAILABILITY_LAG_BUSINESS_DAYS: dict[str, int] = {
    "walcl": 1,                    # Wed H.4.1 observation -> Thu publication
    "tga": 1,                      # H.4.1 weekly Treasury cash
    "rrp": 0,                      # operation result is public the same day
    "bank_reserves": 1,            # H.4.1
    "bank_treasury_agency": 2,     # H.8 is released after the observation date
    "bank_assets": 2,              # H.8 is released after the observation date
    "sofr": 1,                     # prior-day NY Fed/OFR rate
    "effr": 1,                     # prior-day NY Fed/OFR rate
    "iorb": 0,                     # administered rate is known when effective
    "real_yield_10y": 1,           # end-of-day market/yield observation
    "real_yield_5y": 1,
    "nominal_yield_10y": 1,
    "nominal_yield_2y": 1,
    "nominal_yield_3m": 1,
    "nominal_yield_30y": 1,
    "hy_oas": 1,                   # end-of-day credit observation
    "ig_oas": 1,
    "dollar_index": 1,             # daily market/index observation
    "vix": 1,
    "sp500": 1,
    "nasdaq": 1,
}

FRESHNESS_DAYS = {
    "daily": 5,
    "weekly": 14,
    "monthly": 45,
}


def finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def existing_series_path(series_id: str) -> Path:
    exact = dashboard.PROJECT / "data" / f"{series_id}.csv"
    if exact.exists():
        return exact
    matches = sorted(
        (dashboard.PROJECT / "data").glob(f"{series_id}*.csv"),
        key=lambda path: path.stat().st_mtime,
    )
    return matches[-1] if matches else exact


def load_series_records(path: Path, series_id: str) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        rows = dashboard.load_price(path, series_id)
    except Exception:
        return []
    clean: dict[str, float] = {}
    for row in rows:
        stamp = str(row.get("date") or "")[:10]
        value = finite(row.get("price"))
        if stamp and value is not None:
            clean[stamp] = value
    return [{"date": stamp, "value": value} for stamp, value in sorted(clean.items())]


def write_series_records(path: Path, series_id: str, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{series_id}.", suffix=".csv", dir=path.parent)
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        with tmp.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["observation_date", series_id])
            for row in rows:
                writer.writerow([row["date"], row["value"]])
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


def merge_series_records(*groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, float] = {}
    for rows in groups:
        for row in rows:
            stamp = str(row.get("date") or "")[:10]
            value = finite(row.get("value"))
            if stamp and value is not None:
                merged[stamp] = value
    return [{"date": stamp, "value": value} for stamp, value in sorted(merged.items())]


def series_columns() -> dict[str, dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}
    for column, spec in dashboard.MACRO_SERIES.items():
        series_id = str(spec["fred_id"])
        entry = by_id.setdefault(
            series_id,
            {
                "series_id": series_id,
                "columns": [],
                "frequency": str(spec.get("frequency") or "daily"),
                "source": str(spec.get("source") or series_id),
                "required": False,
            },
        )
        entry["columns"].append(column)
        entry["required"] = bool(entry["required"] or spec.get("required", True))
    return by_id


def fetch_series_to_file(series_id: str, destination: Path) -> str:
    """Fetch from the repo's primary adapters, keeping market indices on FRED."""
    if series_id in {"SP500", "NASDAQ100", "VIXCLS"}:
        # The legacy dashboard refresh path routes these IDs through Yahoo.
        # Canonical macro history uses FRED directly so provenance stays on a
        # public macro-data source rather than a presentation fallback.
        if dashboard.requests is None:
            raise RuntimeError("requests is required for canonical FRED market-series refresh")
        api_key = dashboard.load_fred_api_key()
        if api_key:
            ok = dashboard.fetch_fred_api_csv(series_id, destination, timeout=45)
            if ok:
                return "FRED API"
        url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
        response = dashboard.requests.get(
            url,
            timeout=45,
            headers={"User-Agent": "Mozilla/5.0 COT canonical macro history"},
        )
        response.raise_for_status()
        destination.write_bytes(response.content)
        return "FRED graph CSV"

    dashboard.fetch_fred_csv(series_id, destination, timeout=45)
    if series_id in dashboard.TREASURY_XML_SERIES:
        return "U.S. Treasury XML (FRED fallback available)"
    if series_id in {"SOFR", "EFFR"}:
        return "OFR STFM"
    if series_id in {"IORB", "USGSEC", "BANKASSETS"}:
        return "Federal Reserve DDP"
    return "FRED"


def refresh_source(series_id: str, meta: dict[str, Any]) -> dict[str, Any]:
    destination = existing_series_path(series_id)
    old_rows = load_series_records(destination, series_id)
    fetched_rows: list[dict[str, Any]] = []
    error: str | None = None
    fetch_route: str | None = None

    tmp_dir = destination.parent
    tmp_dir.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".fetch-{series_id}.", suffix=".csv", dir=tmp_dir)
    os.close(fd)
    tmp_path = Path(tmp_name)
    try:
        try:
            # Fetch into a temporary file so a transient endpoint failure can
            # never destroy the last-good repository cache.
            fetch_route = fetch_series_to_file(series_id, tmp_path)
            fetched_rows = load_series_records(tmp_path, series_id)
            if not fetched_rows:
                raise RuntimeError("source returned no usable observations")
        except Exception as exc:
            error = str(exc)[:500]

        if fetched_rows:
            merged = merge_series_records(old_rows, fetched_rows)
            write_series_records(destination, series_id, merged)
            active_rows = merged
            fetch_status = "refreshed"
        else:
            active_rows = old_rows
            fetch_status = "cached_fallback" if old_rows else "missing"

        latest_date = active_rows[-1]["date"] if active_rows else None
        age_days = None
        if latest_date:
            age_days = max(0, (datetime.now(UTC).date() - pd.Timestamp(latest_date).date()).days)
        threshold = FRESHNESS_DAYS.get(str(meta.get("frequency") or "daily"), 14)
        if not active_rows:
            freshness = "missing"
        elif age_days is not None and age_days <= threshold:
            freshness = "fresh"
        else:
            freshness = "stale"

        return {
            "series_id": series_id,
            "columns": list(meta["columns"]),
            "source": meta["source"],
            "frequency": meta["frequency"],
            "required": bool(meta["required"]),
            "path": str(destination.relative_to(dashboard.PROJECT)),
            "fetch_status": fetch_status,
            "fetch_route": fetch_route,
            "freshness": freshness,
            "rows": len(active_rows),
            "latest_observation_date": latest_date,
            "age_days": age_days,
            "error": error,
        }
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


def shift_available_dates(frame: pd.DataFrame, column: str) -> pd.DataFrame:
    if frame.empty:
        return frame
    lag = int(AVAILABILITY_LAG_BUSINESS_DAYS.get(column, 0))
    if lag <= 0:
        return frame
    out = frame.copy()
    out["date"] = pd.to_datetime(out["date"], errors="coerce").map(
        lambda stamp: pd.Timestamp(
            dashboard.add_business_days(stamp.date(), lag)
        )
        if pd.notna(stamp)
        else pd.NaT
    )
    return out.dropna(subset=["date"]).sort_values("date").drop_duplicates("date", keep="last").reset_index(drop=True)


def apply_safe_forward_treasury_supply(frame: pd.DataFrame) -> pd.DataFrame:
    """Replace ex-post next-7d offering amounts with an auction-date-safe series."""
    if frame.empty:
        return frame
    out = frame.copy()
    start = pd.to_datetime(out["date"].min()) - pd.Timedelta(days=35)
    end = pd.to_datetime(out["date"].max()) + pd.Timedelta(days=35)
    treasury = dashboard.load_treasury_issuance_frame(start, end)
    if treasury.empty:
        out["treasury_issuance_next_7d"] = pd.NA
        return out

    treasury = treasury.copy()
    treasury["date"] = pd.to_datetime(treasury["date"], errors="coerce")
    treasury["auction_date"] = pd.to_datetime(treasury.get("auction_date"), errors="coerce")
    treasury["amount_bn"] = pd.to_numeric(treasury["amount_bn"], errors="coerce")
    treasury = treasury.dropna(subset=["date", "auction_date", "amount_bn"])

    values: list[float] = []
    for current in pd.to_datetime(out["date"], errors="coerce"):
        if pd.isna(current):
            values.append(float("nan"))
            continue
        # Offering amount is admitted only once the auction has occurred.
        # This is stricter than using today's knowledge of the future issue
        # calendar and prevents historical rows from seeing ex-post amounts.
        mask = (
            (treasury["date"] > current)
            & (treasury["date"] <= current + pd.Timedelta(days=7))
            & (treasury["auction_date"] <= current)
        )
        values.append(round(float(treasury.loc[mask, "amount_bn"].sum()), 3))
    out["treasury_issuance_next_7d"] = values
    return out


def build_lookahead_safe_history() -> pd.DataFrame:
    original_loader = dashboard.load_macro_series

    def safe_loader(column: str, spec: dict[str, Any]) -> pd.DataFrame:
        return shift_available_dates(original_loader(column, spec), column)

    dashboard.load_macro_series = safe_loader
    try:
        # Retirement-flow fields are presentation/confirmation context and are
        # intentionally excluded here because their publication timestamps are
        # not yet audited to the same day-level availability contract.
        raw = dashboard.build_macro_base_frame(pd.DataFrame())
    finally:
        dashboard.load_macro_series = original_loader

    raw = apply_safe_forward_treasury_supply(raw)
    scored = dashboard.score_macro_frame(raw)
    if scored.empty:
        return scored

    score_columns = [str(item["score_col"]) for item in dashboard.MACRO_SCORE_FACTORS]
    extras = ["score_market_trend", "score_retirement_proxy"]
    columns: list[str] = []
    for column in [*dashboard.MACRO_COLUMNS, *score_columns, *extras]:
        if column in scored.columns and column not in columns:
            columns.append(column)
    export = scored[columns].copy()
    export["date"] = pd.to_datetime(export["date"], errors="coerce")
    export = export.dropna(subset=["date"]).sort_values("date").drop_duplicates("date", keep="last")
    today = pd.Timestamp(datetime.now(UTC).date())
    export = export.loc[export["date"] <= today].reset_index(drop=True)
    return export


def scalar_json(value: Any) -> Any:
    if value is None or value is pd.NA:
        return None
    if isinstance(value, (bool, str)):
        return value
    if isinstance(value, pd.Timestamp):
        return value.strftime("%Y-%m-%d")
    if pd.isna(value):
        return None
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, float):
        return round(value, 6)
    return value


def row_to_json(row: pd.Series) -> dict[str, Any]:
    return {str(key): scalar_json(value) for key, value in row.items()}


def write_history(frame: pd.DataFrame, source_status: list[dict[str, Any]], generated_at: datetime) -> dict[str, Any]:
    if frame.empty:
        raise RuntimeError("canonical macro history is empty after refresh")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    export = frame.copy()
    export["date"] = pd.to_datetime(export["date"], errors="coerce").dt.strftime("%Y-%m-%d")
    fd, tmp_name = tempfile.mkstemp(prefix=".macro-history.", suffix=".csv", dir=OUT_DIR)
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        export.to_csv(tmp, index=False)
        os.replace(tmp, HISTORY_OUT)
    finally:
        if tmp.exists():
            tmp.unlink()

    latest = row_to_json(frame.iloc[-1])
    future_targets = [
        column
        for column in frame.columns
        if "_forward_" in column
    ]
    required_missing = [
        row["series_id"]
        for row in source_status
        if row["required"] and row["freshness"] == "missing"
    ]
    stale_required = [
        row["series_id"]
        for row in source_status
        if row["required"] and row["freshness"] == "stale"
    ]
    status = "error" if required_missing else "warning" if stale_required else "fresh"

    provenance = {
        "schema_version": 1,
        "generated_at_utc": generated_at.isoformat(),
        "artifact": str(HISTORY_OUT.relative_to(dashboard.ROOT)),
        "role": "historical macro context only; does not create or reverse governed COT direction",
        "lookahead_safe": True,
        "availability_granularity": "business-day",
        "availability_policy": {
            "series_lag_business_days": AVAILABILITY_LAG_BUSINESS_DAYS,
            "market_close_policy": "daily market, yield, credit and volatility observations enter on the next business day",
            "weekly_policy": "H.4.1 observations enter one business day later; H.8 observations enter two business days later",
            "funding_policy": "SOFR/EFFR enter one business day later; IORB enters on its effective date",
            "treasury_forward_supply_policy": "future issue amounts enter only when auction_date <= historical row date",
            "retirement_flow_policy": "excluded from canonical score history until publication timestamps are audited",
        },
        "future_outcome_columns": future_targets,
        "future_outcome_policy": "forward-return columns are validation targets only and are never predictor inputs",
        "rows": int(len(frame)),
        "start_date": latest.get("date") if len(frame) == 1 else pd.Timestamp(frame.iloc[0]["date"]).strftime("%Y-%m-%d"),
        "end_date": latest.get("date"),
        "source_status": source_status,
        "required_missing": required_missing,
        "required_stale": stale_required,
        "status": status,
    }
    PROVENANCE_OUT.write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")
    LATEST_OUT.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "generated_at_utc": generated_at.isoformat(),
                "lookahead_safe": True,
                "status": status,
                "latest": latest,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return provenance


def validate_history(frame: pd.DataFrame) -> None:
    if frame.empty:
        raise AssertionError("macro history must not be empty")
    dates = pd.to_datetime(frame["date"], errors="coerce")
    if dates.isna().any():
        raise AssertionError("macro history contains invalid dates")
    if not dates.is_monotonic_increasing:
        raise AssertionError("macro history dates must be sorted")
    if dates.duplicated().any():
        raise AssertionError("macro history dates must be unique")
    if dates.max().date() > datetime.now(UTC).date():
        raise AssertionError("macro history contains a future observed row")
    for column in ("liquidity_score", "regime_label", "net_liquidity", "bank_reserves", "hy_oas", "sp500", "nasdaq"):
        if column not in frame.columns:
            raise AssertionError(f"macro history missing required column {column}")


def main() -> None:
    generated_at = datetime.now(UTC)
    statuses = [
        refresh_source(series_id, meta)
        for series_id, meta in series_columns().items()
    ]
    history = build_lookahead_safe_history()
    validate_history(history)
    provenance = write_history(history, statuses, generated_at)
    print(f"Wrote {HISTORY_OUT}")
    print(f"Wrote {LATEST_OUT}")
    print(f"Wrote {PROVENANCE_OUT}")
    print(
        "Macro history "
        f"{provenance['start_date']} -> {provenance['end_date']} "
        f"({provenance['rows']} rows, status={provenance['status']})"
    )
    for row in statuses:
        print(
            f"{row['series_id']}: {row['fetch_status']} / {row['freshness']} "
            f"latest={row['latest_observation_date'] or 'n/a'}"
        )


if __name__ == "__main__":
    main()
