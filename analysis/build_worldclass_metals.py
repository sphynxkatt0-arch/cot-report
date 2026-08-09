#!/usr/bin/env python3
"""Build presentation and research Gold/Silver COT datasets.

Physical commodities use the CFTC Disaggregated Futures Only taxonomy. The
public browser artifact is compact, while `worldclass/research/metals-full.json`
retains the complete normalized COT history plus daily prices for lookahead-safe
research. The research file is never requested by the dashboard runtime.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import urllib.parse
import urllib.request
from bisect import bisect_right
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
OUT_DIR = ROOT / "worldclass"
OUT = OUT_DIR / "metals.json"
RESEARCH_OUT = OUT_DIR / "research" / "metals-full.json"

CFTC_DATASET = "72hh-3qpy"
CFTC_API = f"https://publicreporting.cftc.gov/resource/{CFTC_DATASET}.json"
START_DATE = "2016-01-01T00:00:00.000"
BROWSER_COT_WEEKS = 312

MARKETS = {
    "gold": {
        "label": "Gold",
        "code": "088691",
        "contract": "GOLD - COMMODITY EXCHANGE INC.",
        "symbol": "GC=F",
        "multiplier": 100.0,
        "unit": "100 troy oz",
    },
    "silver": {
        "label": "Silver",
        "code": "084691",
        "contract": "SILVER - COMMODITY EXCHANGE INC.",
        "symbol": "SI=F",
        "multiplier": 5000.0,
        "unit": "5,000 troy oz",
    },
}

CATEGORIES = {
    "producer_merchant": {
        "label": "Producer / Merchant / Processor / User",
        "long": ("prod_merc_positions_long", "prod_merc_positions_long_all"),
        "short": ("prod_merc_positions_short", "prod_merc_positions_short_all"),
    },
    "swap_dealer": {
        "label": "Swap Dealers",
        "long": ("swap_positions_long_all", "swap_positions_long"),
        "short": ("swap__positions_short_all", "swap_positions_short_all", "swap_positions_short"),
    },
    "managed_money": {
        "label": "Managed Money",
        "long": ("m_money_positions_long_all", "m_money_positions_long"),
        "short": ("m_money_positions_short_all", "m_money_positions_short"),
    },
    "other_reportable": {
        "label": "Other Reportables",
        "long": ("other_rept_positions_long", "other_rept_positions_long_all"),
        "short": ("other_rept_positions_short", "other_rept_positions_short_all"),
    },
    "non_reportable": {
        "label": "Non-reportable",
        "long": ("nonrept_positions_long_all", "nonrept_positions_long"),
        "short": ("nonrept_positions_short_all", "nonrept_positions_short"),
    },
}


def fetch_json(url: str, timeout: int = 45) -> Any:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 COT Macro Monitor",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def first_number(row: dict[str, Any], candidates: tuple[str, ...]) -> float | None:
    for key in candidates:
        value = finite(row.get(key))
        if value is not None:
            return value
    return None


def clean_date(value: Any) -> str:
    text = str(value or "").strip()
    return text[:10] if len(text) >= 10 else text


def fetch_cftc_rows(code: str) -> list[dict[str, Any]]:
    params = {
        "$limit": "5000",
        "$order": "report_date_as_yyyy_mm_dd ASC",
        "$where": (
            f"cftc_contract_market_code='{code}' "
            f"AND report_date_as_yyyy_mm_dd >= '{START_DATE}'"
        ),
    }
    url = f"{CFTC_API}?{urllib.parse.urlencode(params)}"
    payload = fetch_json(url)
    if not isinstance(payload, list):
        raise RuntimeError(f"Unexpected CFTC payload for contract {code}")
    rows = [row for row in payload if isinstance(row, dict)]
    if not rows:
        raise RuntimeError(f"CFTC returned no rows for contract {code}")
    return rows


def fetch_yahoo_prices(symbol: str) -> list[dict[str, Any]]:
    encoded = urllib.parse.quote(symbol, safe="")
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{encoded}"
        "?range=15y&interval=1d&events=history"
    )
    payload = fetch_json(url)
    result = ((payload.get("chart") or {}).get("result") or [None])[0]
    if not result:
        raise RuntimeError(f"Yahoo returned no chart data for {symbol}")
    timestamps = result.get("timestamp") or []
    closes = (((result.get("indicators") or {}).get("quote") or [{}])[0].get("close") or [])
    by_date: dict[str, float] = {}
    for timestamp, close in zip(timestamps, closes):
        price = finite(close)
        if price is None:
            continue
        day = datetime.fromtimestamp(int(timestamp), UTC).date().isoformat()
        by_date[day] = price
    if not by_date:
        raise RuntimeError(f"Yahoo returned no usable close values for {symbol}")
    return [{"date": day, "price": round(price, 6)} for day, price in sorted(by_date.items())]


def price_at_or_before(prices: list[dict[str, Any]], day: str) -> float | None:
    dates = [row["date"] for row in prices]
    index = bisect_right(dates, day) - 1
    if index < 0:
        return None
    return finite(prices[index].get("price"))


def normalize_market_rows(
    raw_rows: list[dict[str, Any]],
    prices: list[dict[str, Any]],
    market: str,
) -> list[dict[str, Any]]:
    cfg = MARKETS[market]
    normalized: list[dict[str, Any]] = []
    for row in raw_rows:
        day = clean_date(row.get("report_date_as_yyyy_mm_dd"))
        open_interest = finite(row.get("open_interest_all"))
        if not day or open_interest is None or open_interest <= 0:
            continue

        item: dict[str, Any] = {
            "date": day,
            "contract": str(row.get("market_and_exchange_names") or cfg["contract"]).strip(),
            "open_interest": round(open_interest, 6),
            "price": price_at_or_before(prices, day),
        }
        complete_categories = 0
        for key, cat in CATEGORIES.items():
            long_value = first_number(row, cat["long"])
            short_value = first_number(row, cat["short"])
            if long_value is None or short_value is None:
                continue
            complete_categories += 1
            net = long_value - short_value
            item[f"{key}_long"] = round(long_value, 6)
            item[f"{key}_short"] = round(short_value, 6)
            item[f"{key}_net"] = round(net, 6)
            item[f"{key}_net_oi_pct"] = round(net / open_interest * 100.0, 6)
            item[f"{key}_short_oi_pct"] = round(short_value / open_interest * 100.0, 6)

        if complete_categories >= 4:
            normalized.append(item)

    deduped = {row["date"]: row for row in normalized}
    rows = [deduped[key] for key in sorted(deduped)]
    if len(rows) < 100:
        raise RuntimeError(f"Only {len(rows)} usable CFTC rows were built for {market}")
    return rows


def compact_runtime_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return rows[-BROWSER_COT_WEEKS:]


def aligned_runtime_prices(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {"date": row["date"], "price": row["price"]}
        for row in rows
        if finite(row.get("price")) is not None
    ]


def payload_shell(markets: dict[str, Any], prices: dict[str, Any], generated_at: str) -> dict[str, Any]:
    return {
        "dataset": "disaggregated",
        "dataset_label": "CFTC Disaggregated Futures Only",
        "generated_at_utc": generated_at,
        "source": {
            "name": "CFTC Public Reporting — Disaggregated Futures Only",
            "dataset_id": CFTC_DATASET,
            "price_source": "Yahoo Finance daily futures close",
        },
        "markets": markets,
        "prices": prices,
    }


def runtime_from_research(research: dict[str, Any]) -> dict[str, Any]:
    runtime_markets: dict[str, Any] = {}
    runtime_prices: dict[str, Any] = {}
    source_counts: dict[str, int] = {}
    for market, cfg in MARKETS.items():
        source_market = (research.get("markets") or {}).get(market) or {}
        full_rows = source_market.get("records") or []
        if len(full_rows) < BROWSER_COT_WEEKS:
            raise RuntimeError(f"{market}: full research source has only {len(full_rows)} COT rows")
        rows = compact_runtime_rows(full_rows)
        source_counts[market] = len(full_rows)
        runtime_markets[market] = {
            **{key: value for key, value in source_market.items() if key != "records"},
            "records": rows,
            "latest_date": rows[-1]["date"],
        }
        runtime_prices[market] = {
            "label": cfg["label"],
            "symbol": cfg["symbol"],
            "records": aligned_runtime_prices(rows),
        }

    runtime = payload_shell(
        runtime_markets,
        runtime_prices,
        str(research.get("generated_at_utc") or datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")),
    )
    runtime["runtime_contract"] = {
        "history_window_weeks": BROWSER_COT_WEEKS,
        "price_frequency": "COT-aligned weekly close",
        "full_history_research_separate": True,
        "research_source": "worldclass/research/metals-full.json",
        "source_cot_rows": source_counts,
    }
    return runtime


def build_payloads() -> tuple[dict[str, Any], dict[str, Any]]:
    research_markets: dict[str, Any] = {}
    research_prices: dict[str, Any] = {}
    source_counts: dict[str, int] = {}
    generated_at = datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")

    for market, cfg in MARKETS.items():
        print(f"Fetching {cfg['label']} prices...", flush=True)
        prices = fetch_yahoo_prices(cfg["symbol"])
        print(f"Fetching {cfg['label']} CFTC disaggregated rows...", flush=True)
        raw = fetch_cftc_rows(cfg["code"])
        full_rows = normalize_market_rows(raw, prices, market)
        source_counts[market] = len(full_rows)
        research_markets[market] = {
            "label": f"{cfg['label']} CFTC Disaggregated Futures Only",
            "categories": {key: value["label"] for key, value in CATEGORIES.items()},
            "records": full_rows,
            "contract_spec": {
                "cftc_code": cfg["code"],
                "contract": cfg["contract"],
                "multiplier": cfg["multiplier"],
                "unit": cfg["unit"],
            },
            "latest_date": full_rows[-1]["date"],
        }
        research_prices[market] = {
            "label": cfg["label"],
            "symbol": cfg["symbol"],
            "records": prices,
        }
        print(f"  {cfg['label']}: {len(full_rows)} full-history COT rows through {full_rows[-1]['date']}")

    research = payload_shell(research_markets, research_prices, generated_at)
    research["research_contract"] = {
        "full_history": True,
        "daily_price_history": True,
        "browser_loaded": False,
        "source_cot_rows": source_counts,
    }
    return runtime_from_research(research), research


def build_payload() -> dict[str, Any]:
    runtime, _ = build_payloads()
    return runtime


def atomic_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".write.tmp")
    temporary.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    temporary.replace(path)


def compact_saved_research() -> None:
    if not RESEARCH_OUT.exists():
        raise FileNotFoundError(f"Missing persistent full-history metals source: {RESEARCH_OUT}")
    research = json.loads(RESEARCH_OUT.read_text(encoding="utf-8"))
    runtime = runtime_from_research(research)
    atomic_write(OUT, runtime)
    print(f"Compacted persistent research source into browser runtime {OUT}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--compact-from-research",
        action="store_true",
        help="Rebuild only the compact browser payload from the persistent full-history research source.",
    )
    args = parser.parse_args()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    if args.compact_from_research:
        compact_saved_research()
        return

    try:
        runtime, research = build_payloads()
    except Exception as exc:
        if OUT.exists() and RESEARCH_OUT.exists():
            print(
                f"WARNING: metals refresh failed ({exc}). Keeping cached browser and full-history research payloads.",
                file=sys.stderr,
            )
            return
        raise

    atomic_write(RESEARCH_OUT, research)
    atomic_write(OUT, runtime)
    print(f"Saved persistent full-history research source {RESEARCH_OUT}")
    print(f"Saved compact browser runtime {OUT}")


if __name__ == "__main__":
    main()
