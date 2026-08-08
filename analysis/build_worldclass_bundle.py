#!/usr/bin/env python3
"""Extract a lightweight runtime bundle from the generated research dashboard.

The legacy dashboard is intentionally retained as the calculation/rendering
artifact, but the v2 front-end should not download and parse several megabytes
of HTML just to get its data.  This script extracts only the JSON payloads v2
needs and trims wide time-series rows to the fields rendered by the UI.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "interactive_cot_dashboard.html"
OUT_DIR = ROOT / "worldclass"
OUT = OUT_DIR / "base.json"

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
            records = payload.get("records") or []
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


def compact_prices(data: Any) -> Any:
    if not isinstance(data, dict):
        return data
    out: dict[str, Any] = {}
    for market, payload in data.items():
        if isinstance(payload, dict):
            rows = payload.get("records") or []
            out[market] = {
                "label": payload.get("label"),
                "records": [
                    {"date": row.get("date"), "price": row.get("price")}
                    for row in rows
                    if isinstance(row, dict) and row.get("date") and row.get("price") is not None
                ],
            }
        elif isinstance(payload, list):
            out[market] = [
                {"date": row.get("date"), "price": row.get("price")}
                for row in payload
                if isinstance(row, dict) and row.get("date") and row.get("price") is not None
            ]
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
    payload = {
        "COT_DATA": compact_cot(raw.get("COT_DATA")),
        "PRICE_DATA": compact_prices(raw.get("PRICE_DATA")),
        "FACTOR_DATA": compact_timeseries_tree(raw.get("FACTOR_DATA")),
        "LIQUIDITY_DATA": compact_timeseries_tree(raw.get("LIQUIDITY_DATA")),
        "MACRO_MONITOR": compact_timeseries_tree(raw.get("MACRO_MONITOR")),
        "MACRO_LENS": compact_timeseries_tree(raw.get("MACRO_LENS")),
        "METADATA": raw.get("METADATA") or {},
    }
    payload["bundle_meta"] = {
        "source_html_bytes": SOURCE.stat().st_size,
    }
    return payload


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    payload = build()
    temporary = OUT.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    temporary.replace(OUT)
    payload["bundle_meta"]["bundle_bytes"] = OUT.stat().st_size
    # Re-write once so the size metadata is also present in the file.
    OUT.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    ratio = OUT.stat().st_size / max(SOURCE.stat().st_size, 1)
    print(f"Saved {OUT} ({OUT.stat().st_size:,} bytes, {ratio:.1%} of source HTML)")


if __name__ == "__main__":
    main()
