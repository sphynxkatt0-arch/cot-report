#!/usr/bin/env python3
"""Refresh Russell 2000, Dow Jones, and Gold COT/price inputs.

This supplements the existing SP500/NQ dashboard refresh. It downloads daily
Yahoo price history, exact CFTC futures-only rows, and writes a machine-readable
contract-integrity manifest consumed by validation.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

import cot_disaggregated_correlations as disaggregated
import cot_legacy_correlations as legacy
import cot_overlay_exact as tff
from cot_market_registry import MARKETS

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parent
MANIFEST = ROOT / "model_output" / "cot_market_refresh_manifest.json"
EXTENDED_MARKETS = ("russell2000", "dow", "gold")


def fetch_url_json(url: str, timeout: int = 30) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 COT market updater"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def existing_series(dest: Path, series_id: str) -> dict[str, str]:
    rows: dict[str, str] = {}
    if not dest.exists():
        return rows
    with dest.open("r", newline="", encoding="utf-8-sig", errors="replace") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            return rows
        date_col = "observation_date" if "observation_date" in reader.fieldnames else "date"
        value_col = series_id if series_id in reader.fieldnames else next(
            (field for field in reader.fieldnames if field != date_col), None
        )
        if value_col is None:
            return rows
        for row in reader:
            day = str(row.get(date_col) or "").strip()
            value = str(row.get(value_col) or "").strip()
            if day and value and value != ".":
                rows[day] = value
    return rows


def write_price_series(dest: Path, series_id: str, symbol: str) -> None:
    encoded = urllib.parse.quote(symbol, safe="")
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{encoded}?range=max&interval=1d"
    result = (fetch_url_json(url).get("chart", {}).get("result") or [None])[0]
    if not result or len(result.get("timestamp") or []) < 260:
        url_10y = f"https://query1.finance.yahoo.com/v8/finance/chart/{encoded}?range=10y&interval=1d"
        res_10y = (fetch_url_json(url_10y).get("chart", {}).get("result") or [None])[0]
        if res_10y and len(res_10y.get("timestamp") or []) > len(result.get("timestamp") or [] if result else []):
            result = res_10y
    if not result:
        raise RuntimeError(f"Yahoo returned no data for {symbol}")
    timestamps = result.get("timestamp") or []
    quote = ((result.get("indicators") or {}).get("quote") or [{}])[0]
    closes = quote.get("close") or []
    merged = existing_series(dest, series_id)
    for timestamp, close_value in zip(timestamps, closes):
        if close_value is None:
            continue
        day = datetime.fromtimestamp(int(timestamp), UTC).date().isoformat()
        merged[day] = f"{float(close_value):.6f}"
    meta = result.get("meta") or {}
    if meta.get("regularMarketPrice") is not None and meta.get("regularMarketTime") is not None:
        day = datetime.fromtimestamp(int(meta["regularMarketTime"]), UTC).date().isoformat()
        merged[day] = f"{float(meta['regularMarketPrice']):.6f}"
    if not merged:
        raise RuntimeError(f"Yahoo returned no usable prices for {symbol}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["observation_date", series_id])
        writer.writerows(sorted(merged.items()))
    print(f"Updated {series_id} from Yahoo {symbol}: {dest}")


def tff_config(market: str) -> tff.MarketConfig:
    meta = MARKETS[market]
    return tff.MarketConfig(
        key=market,
        cftc_code=str(meta["secondary_cftc_code"]),
        exact_contract_name=str(meta["secondary_contract_name"]),
        fred_series=str(meta["price_col"]),
        price_label=f"{meta['label']} close",
        contract_multiplier=float(meta["contract_multiplier"]),
        contract_unit=str(meta["contract_unit"]),
    )


def legacy_config(market: str) -> legacy.MarketConfig:
    meta = MARKETS[market]
    return legacy.MarketConfig(
        key=market,
        cftc_code=str(meta["legacy_cftc_code"]),
        exact_contract_name=str(meta["legacy_contract_name"]),
        fred_series=str(meta["price_col"]),
        price_label=f"{meta['label']} close",
        contract_multiplier=float(meta["contract_multiplier"]),
        contract_unit=str(meta["contract_unit"]),
    )


def serializable_summary(summary: dict[str, Any]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for key, value in summary.items():
        if isinstance(value, pd.Timestamp):
            output[key] = value.isoformat()
        elif hasattr(value, "item"):
            try:
                output[key] = value.item()
            except Exception:
                output[key] = str(value)
        else:
            output[key] = value
    return output


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=int, default=2016)
    parser.add_argument("--end", type=int, default=datetime.now(UTC).year)
    args = parser.parse_args()

    for market in EXTENDED_MARKETS:
        meta = MARKETS[market]
        try:
            write_price_series(Path(meta["price_path"]), str(meta["price_col"]), str(meta["price_symbol"]))
        except Exception as exc:
            if Path(meta["price_path"]).exists():
                print(f"WARNING: {market} price refresh failed; using cached file: {exc}", file=sys.stderr)
            else:
                raise

    tff_raw = tff.load_cftc_tff_range(args.start, args.end)
    legacy_raw = legacy.load_cftc_legacy_range(args.start, args.end)
    disaggregated_raw = disaggregated.load_cftc_disaggregated_range(args.start, args.end)
    summaries: list[dict[str, Any]] = []

    for market in ("russell2000", "dow"):
        summaries.append({"report": "tff", **serializable_summary(tff.run_market(tff_config(market), args.start, args.end, ROOT / "cot_exact_output", raw=tff_raw))})
        summaries.append({"report": "legacy", **serializable_summary(legacy.run_market(legacy_config(market), args.start, args.end, ROOT / "cot_legacy_output", raw=legacy_raw))})

    summaries.append({"report": "legacy", **serializable_summary(legacy.run_market(legacy_config("gold"), args.start, args.end, ROOT / "cot_legacy_output", raw=legacy_raw))})
    summaries.append(serializable_summary(disaggregated.run_market(disaggregated.gold_config(), args.start, args.end, ROOT / "cot_disaggregated_output", raw=disaggregated_raw)))

    manifest_markets: list[dict[str, Any]] = []
    for market in EXTENDED_MARKETS:
        meta = MARKETS[market]
        market_rows = [row for row in summaries if row.get("market") == market]
        manifest_markets.append({
            "market": market,
            "label": meta["label"],
            "secondary_report": meta["secondary_kind"],
            "selection_mode": meta["contract_selection_mode"],
            "selection_note": meta["contract_selection_note"],
            "legacy_contract_name": meta["legacy_contract_name"],
            "legacy_cftc_code": meta["legacy_cftc_code"],
            "secondary_contract_name": meta["secondary_contract_name"],
            "secondary_cftc_code": meta["secondary_cftc_code"],
            "price_series": meta["price_col"],
            "price_symbol": meta["price_symbol"],
            "outputs": market_rows,
        })
    payload = {
        "schema_version": 1,
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "start_year": args.start,
        "end_year": args.end,
        "markets": manifest_markets,
    }
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote contract-integrity manifest: {MANIFEST}")


if __name__ == "__main__":
    main()
