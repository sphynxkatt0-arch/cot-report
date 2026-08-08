#!/usr/bin/env python3
"""Extract a lightweight runtime bundle from the generated research dashboard.

The legacy dashboard is intentionally retained as the calculation/rendering
artifact, but the v2 front-end should not download and parse several megabytes
of HTML just to get its data. This script extracts only the JSON payloads v2
needs, trims wide time-series rows to rendered fields, and keeps the initial
browser history intentionally bounded. Full research/backtest history remains
in the canonical research artifact and derived backtest files.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import model_spec as model_cfg

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "interactive_cot_dashboard.html"
OUT_DIR = ROOT / "worldclass"
OUT = OUT_DIR / "base.json"
MODEL_OUT = OUT_DIR / "model-spec.json"

# Six years comfortably covers the dashboard's 3-year positioning percentile
# use case while avoiding a multi-megabyte first-load COT payload. Long-history
# evidence remains available in the separate walk-forward backtest artifacts.
BROWSER_COT_WEEKS = 312
RECENT_DAILY_PRICE_DAYS = 183

CONSTANTS = (
    "COT_DATA",
    "PRICE_DATA",
    "FACTOR_DATA",
    "LIQUIDITY_DATA",
    "MACRO_MONITOR",
    "MACRO_LENS",
    "METADATA",
)

COT_SUFFIXES = (
    "_long",
    "_short",
    "_net",
    "_net_oi_pct",
    "_short_oi_pct",
)

MACRO_FIELDS = {
    "date",
    "liquidity_score",
    "macro_score",
    "unified_score",
    "score",
    "net_liquidity",
    "net_liquidity_4w_change",
    "bank_reserves",
    "bank_reserves_4w_change",
    "sofr",
    "iorb",
    "sofr_iorb_spread",
    "sofr_iorb_spread_4w_change",
    "real_yield_10y",
    "real_yield_4w_change",
    "hy_oas",
    "hy_oas_4w_change",
    "dollar_index",
    "dollar_4w_change",
    "vix",
}


def atomic_write_json(path: Path, payload: Any) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    temporary.replace(path)


def extract_json_constant(text: str, name: str) -> Any:
    marker = f"const {name} = "
    start = text.find(marker)
    if start < 0:
        return {}
    cursor = start + len(marker)
    while cursor < len(text) and text[cursor].isspace():
        cursor += 1
    json_start = cursor
    depth = 0
    started = False
    in_string = False
    escaped = False
    while cursor < len(text):
        char = text[cursor]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
        else:
            if char == '"':
                in_string = True
            elif char in "[{":
                depth += 1
                started = True
            elif char in "]}":
                depth -= 1
                if started and depth == 0:
                    return json.loads(text[json_start : cursor + 1])
        cursor += 1
    raise ValueError(f"Could not find the end of embedded JSON constant {name}")


def compact_cot(data: Any) -> Any:
    if not isinstance(data, dict):
        return data
    out: dict[str, Any] = {}
    for dataset, markets in data.items():
        if not isinstance(markets, dict):
            continue
        out[dataset] = {}
        for market, payload in markets.items():
            if not isinstance(payload, dict):
                out[dataset][market] = payload
                continue
            records = (payload.get("records") or [])[-BROWSER_COT_WEEKS:]
            compact_rows = []
            for row in records:
                if not isinstance(row, dict):
                    continue
                compact = {
                    key: value
                    for key, value in row.items()
                    if key in {"date", "price", "open_interest", "contract"}
                    or key.endswith(COT_SUFFIXES)
                }
                compact_rows.append(compact)
            out[dataset][market] = {
                "label": payload.get("label"),
                "categories": payload.get("categories") or {},
                "records": compact_rows,
            }
    return out


def parse_day(value: Any) -> date | None:
    text = str(value or "")[:10]
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def compact_price_rows(rows: Any) -> list[dict[str, Any]]:
    if not isinstance(rows, list):
        return []
    valid = [
        {"date": str(row.get("date"))[:10], "price": row.get("price")}
        for row in rows
        if isinstance(row, dict) and row.get("date") and row.get("price") is not None and parse_day(row.get("date"))
    ]
    if not valid:
        return []
    valid.sort(key=lambda row: row["date"])
    latest = parse_day(valid[-1]["date"])
    if latest is None:
        return valid
    daily_cutoff = latest - timedelta(days=RECENT_DAILY_PRICE_DAYS)
    weekly: dict[tuple[int, int], dict[str, Any]] = {}
    recent: list[dict[str, Any]] = []
    for row in valid:
        day = parse_day(row["date"])
        if day is None:
            continue
        if day >= daily_cutoff:
            recent.append(row)
            continue
        iso = day.isocalendar()
        weekly[(iso.year, iso.week)] = row
    combined = [*weekly.values(), *recent]
    combined.sort(key=lambda row: row["date"])
    return combined


def compact_prices(data: Any) -> Any:
    if not isinstance(data, dict):
        return data
    out: dict[str, Any] = {}
    for market, payload in data.items():
        if isinstance(payload, dict):
            out[market] = {
                "label": payload.get("label"),
                "records": compact_price_rows(payload.get("records") or []),
            }
        elif isinstance(payload, list):
            out[market] = compact_price_rows(payload)
    return out


def compact_timeseries_tree(node: Any, depth: int = 0) -> Any:
    if depth > 8:
        return None
    if isinstance(node, list):
        if node and all(isinstance(item, dict) for item in node[: min(len(node), 5)]):
            has_dates = any(item.get("date") for item in node[: min(len(node), 20)])
            if has_dates:
                rows = []
                for item in node:
                    compact = {key: item.get(key) for key in MACRO_FIELDS if key in item}
                    # Factor payloads often use a generic value key.
                    for key in ("value", "label", "source"):
                        if key in item:
                            compact[key] = item.get(key)
                    if compact.get("date"):
                        rows.append(compact)
                return rows
        return [value for item in node if (value := compact_timeseries_tree(item, depth + 1)) not in (None, {}, [])]
    if isinstance(node, dict):
        out: dict[str, Any] = {}
        for key, value in node.items():
            if isinstance(value, (dict, list)):
                compact = compact_timeseries_tree(value, depth + 1)
                if compact not in (None, {}, []):
                    out[key] = compact
            elif key in MACRO_FIELDS or key in {"label", "source", "unit", "generated_at", "generated_at_utc"}:
                out[key] = value
        return out
    return None


def build() -> dict[str, Any]:
    if not SOURCE.exists():
        raise FileNotFoundError(f"Missing {SOURCE}; build the interactive dashboard first")
    source_text = SOURCE.read_text(encoding="utf-8")
    raw = {name: extract_json_constant(source_text, name) for name in CONSTANTS}
    spec = model_cfg.load_model_spec()
    model_meta = model_cfg.runtime_metadata(spec)
    payload = {
        "COT_DATA": compact_cot(raw.get("COT_DATA")),
        "PRICE_DATA": compact_prices(raw.get("PRICE_DATA")),
        "FACTOR_DATA": compact_timeseries_tree(raw.get("FACTOR_DATA")),
        # LIQUIDITY_DATA is a legacy duplicate and is not consumed by the v2
        # runtime. Bootstrap synthesizes an empty constant when it is omitted.
        "MACRO_MONITOR": compact_timeseries_tree(raw.get("MACRO_MONITOR")),
        "MACRO_LENS": compact_timeseries_tree(raw.get("MACRO_LENS")),
        "METADATA": raw.get("METADATA") or {},
        "MODEL_SPEC": model_meta,
    }
    payload["bundle_meta"] = {
        "source_html_bytes": SOURCE.stat().st_size,
        "cot_history_weeks": BROWSER_COT_WEEKS,
        "recent_daily_price_days": RECENT_DAILY_PRICE_DAYS,
        "older_price_sampling": "weekly-last-observation",
        "full_history_location": "research source + backtest artifacts",
        "model_version": model_meta["model_version"],
        "model_spec_hash": model_meta["model_spec_hash"],
    }
    return payload


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    payload = build()
    atomic_write_json(MODEL_OUT, payload["MODEL_SPEC"])
    atomic_write_json(OUT, payload)
    payload["bundle_meta"]["bundle_bytes"] = OUT.stat().st_size
    # Re-write once so the size metadata is also present in the file.
    atomic_write_json(OUT, payload)
    ratio = OUT.stat().st_size / max(SOURCE.stat().st_size, 1)
    print(f"Saved {OUT} ({OUT.stat().st_size:,} bytes, {ratio:.1%} of source HTML)")
    print(f"Saved {MODEL_OUT} (model {payload['MODEL_SPEC']['model_version']} · {payload['MODEL_SPEC']['model_spec_hash']})")


if __name__ == "__main__":
    main()
