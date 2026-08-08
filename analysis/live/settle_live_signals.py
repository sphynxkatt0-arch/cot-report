#!/usr/bin/env python3
"""Settle prospective forecast entries and matured horizons without rewriting history."""
from __future__ import annotations

import argparse
import json
import sys
from bisect import bisect_left
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ledger import (
    HORIZONS,
    LedgerError,
    atomic_write_json,
    canonical_json_bytes,
    finite,
    forecast_files,
    iso_utc,
    parse_iso_day,
    parse_utc,
    sha256_file,
    validate_forecast,
)

ANALYSIS = Path(__file__).resolve().parents[1]
if str(ANALYSIS) not in sys.path:
    sys.path.insert(0, str(ANALYSIS))

from build_worldclass_bundle import extract_json_constant  # noqa: E402

INTERACTIVE = ANALYSIS / "interactive_cot_dashboard.html"
METALS = ANALYSIS / "worldclass" / "metals.json"


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise LedgerError(f"missing required JSON: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise LedgerError(f"JSON root must be an object: {path}")
    return payload


def normalize_price_rows(rows: Any) -> list[dict[str, Any]]:
    if isinstance(rows, dict):
        rows = rows.get("records") or []
    if not isinstance(rows, list):
        return []
    deduped: dict[str, float] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            day = parse_iso_day(row.get("date")).isoformat()
        except LedgerError:
            continue
        price = finite(row.get("price"))
        if price is None or price <= 0:
            continue
        deduped[day] = price
    return [{"date": day, "price": deduped[day]} for day in sorted(deduped)]


def load_price_sources(
    interactive_path: Path = INTERACTIVE,
    metals_path: Path = METALS,
) -> dict[str, dict[str, Any]]:
    if not interactive_path.exists():
        raise LedgerError(f"interactive price source missing: {interactive_path}")
    text = interactive_path.read_text(encoding="utf-8")
    price_data = extract_json_constant(text, "PRICE_DATA") or {}
    metadata = extract_json_constant(text, "METADATA") or {}
    index_timestamp = str(metadata.get("generated_at_utc") or metadata.get("generated_at") or "") or None

    sources: dict[str, dict[str, Any]] = {}
    if isinstance(price_data, dict):
        for market, payload in price_data.items():
            rows = normalize_price_rows(payload)
            if rows:
                sources[market] = {
                    "records": rows,
                    "price_source": "interactive_cot_dashboard.PRICE_DATA",
                    "price_source_timestamp": index_timestamp,
                }

    if metals_path.exists():
        metals = load_json(metals_path)
        metal_timestamp = str(metals.get("generated_at_utc") or metals.get("generated_at") or "") or None
        for market, payload in (metals.get("prices") or {}).items():
            rows = normalize_price_rows(payload)
            if rows:
                sources[market] = {
                    "records": rows,
                    "price_source": "worldclass/metals.json",
                    "price_source_timestamp": metal_timestamp,
                }
    return sources


def first_index_on_or_after(prices: list[dict[str, Any]], target: str) -> int | None:
    dates = [row["date"] for row in prices]
    index = bisect_left(dates, target)
    return index if index < len(prices) else None


def entry_relative_path(signal_id: str) -> Path:
    return Path("live") / "entries" / f"{signal_id}.json"


def outcome_relative_path(signal_id: str, horizon: str) -> Path:
    if horizon not in HORIZONS:
        raise LedgerError(f"unsupported horizon: {horizon}")
    return Path("live") / "outcomes" / signal_id / f"{horizon}.json"


def write_immutable_json(path: Path, payload: dict[str, Any]) -> str:
    data = canonical_json_bytes(payload)
    if path.exists():
        if path.read_bytes() != data:
            raise LedgerError(f"immutable settlement artifact collision: {path}")
        return "unchanged"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return "created"


def load_existing(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise LedgerError(f"settlement artifact root must be object: {path}")
    return payload


def build_entry(
    forecast: dict[str, Any],
    forecast_hash: str,
    prices: list[dict[str, Any]],
    *,
    price_source: str,
    price_source_timestamp: str | None,
    settled_at_utc: datetime,
) -> tuple[dict[str, Any] | None, int | None]:
    target = str(forecast["release_target_date"])
    entry_index = first_index_on_or_after(prices, target)
    if entry_index is None:
        return None, None
    row = prices[entry_index]
    entry = {
        "schema_version": 1,
        "signal_id": forecast["signal_id"],
        "forecast_hash": forecast_hash,
        "market": forecast["market"],
        "release_target_date": target,
        "entry_date": row["date"],
        "entry_price": row["price"],
        "price_source": price_source,
        "price_source_timestamp": price_source_timestamp,
        "settled_at_utc": iso_utc(settled_at_utc),
    }
    return entry, entry_index


def locate_entry_index(prices: list[dict[str, Any]], entry: dict[str, Any]) -> int:
    dates = [row["date"] for row in prices]
    index = bisect_left(dates, str(entry.get("entry_date") or ""))
    if index >= len(prices) or prices[index]["date"] != entry.get("entry_date"):
        raise LedgerError(f"entry date {entry.get('entry_date')} no longer exists in current price source")
    source_price = finite(prices[index].get("price"))
    entry_price = finite(entry.get("entry_price"))
    if source_price is None or entry_price is None:
        raise LedgerError("entry/current price source contains a non-finite price")
    return index


def build_outcome(
    forecast: dict[str, Any],
    forecast_hash: str,
    entry: dict[str, Any],
    prices: list[dict[str, Any]],
    entry_index: int,
    horizon: str,
    *,
    price_source: str,
    price_source_timestamp: str | None,
    settled_at_utc: datetime,
) -> dict[str, Any] | None:
    horizon_meta = (forecast.get("historical_horizons") or {}).get(horizon) or {}
    steps = int(horizon_meta.get("trading_closes") or 0)
    if steps <= 0:
        raise LedgerError(f"forecast {forecast['signal_id']} has no frozen trading-close definition for {horizon}")
    exit_index = entry_index + steps
    if exit_index >= len(prices):
        return None

    entry_price = finite(entry.get("entry_price"))
    exit_price = finite(prices[exit_index].get("price"))
    if entry_price is None or entry_price <= 0 or exit_price is None:
        raise LedgerError("cannot settle horizon with invalid entry/exit price")
    window = [finite(row.get("price")) for row in prices[entry_index : exit_index + 1]]
    if any(value is None for value in window):
        raise LedgerError("non-finite price inside settlement window")
    clean_window = [float(value) for value in window if value is not None]
    realized = (exit_price / entry_price - 1.0) * 100.0
    mae = (min(clean_window) / entry_price - 1.0) * 100.0
    mfe = (max(clean_window) / entry_price - 1.0) * 100.0
    predicted = finite(horizon_meta.get("expected_return_pct"))
    probability = finite(horizon_meta.get("probability_positive"))
    forecast_error = realized - predicted if predicted is not None else None
    direction_correct = None
    if predicted is not None and abs(predicted) > 1e-12:
        direction_correct = bool(realized > 0) if predicted > 0 else bool(realized < 0)

    return {
        "schema_version": 1,
        "signal_id": forecast["signal_id"],
        "forecast_hash": forecast_hash,
        "horizon": horizon,
        "trading_closes": steps,
        "entry_date": entry["entry_date"],
        "entry_price": entry_price,
        "exit_date": prices[exit_index]["date"],
        "exit_price": exit_price,
        "realized_return_pct": round(realized, 8),
        "max_adverse_excursion_pct": round(mae, 8),
        "max_favorable_excursion_pct": round(mfe, 8),
        "predicted_return_pct": predicted,
        "forecast_error_pct": round(forecast_error, 8) if forecast_error is not None else None,
        "predicted_probability_positive": probability,
        "direction_correct": direction_correct,
        "settled_at_utc": iso_utc(settled_at_utc),
        "price_source": price_source,
        "price_source_timestamp": price_source_timestamp,
    }


def settle(
    *,
    ledger_root: Path,
    price_sources: dict[str, dict[str, Any]],
    settled_at_utc: datetime,
    metadata_out: Path | None = None,
) -> dict[str, Any]:
    created_entries: list[str] = []
    created_outcomes: list[str] = []
    open_entries: list[str] = []
    open_horizons: list[str] = []

    for forecast_path in forecast_files(ledger_root):
        forecast = load_json(forecast_path)
        validate_forecast(forecast)
        signal_id = forecast["signal_id"]
        market = str(forecast.get("market") or "")
        source = price_sources.get(market)
        if not source:
            open_entries.append(signal_id)
            continue
        prices = source.get("records") or []
        if not prices:
            open_entries.append(signal_id)
            continue
        forecast_hash = sha256_file(forecast_path)
        entry_path = ledger_root / entry_relative_path(signal_id)
        entry = load_existing(entry_path)

        if entry is None:
            candidate, entry_index = build_entry(
                forecast,
                forecast_hash,
                prices,
                price_source=str(source.get("price_source") or "unknown"),
                price_source_timestamp=source.get("price_source_timestamp"),
                settled_at_utc=settled_at_utc,
            )
            if candidate is None or entry_index is None:
                open_entries.append(signal_id)
                continue
            write_immutable_json(entry_path, candidate)
            entry = candidate
            created_entries.append(str(entry_relative_path(signal_id)).replace("\\", "/"))
        else:
            entry_index = locate_entry_index(prices, entry)

        for horizon in HORIZONS:
            outcome_path = ledger_root / outcome_relative_path(signal_id, horizon)
            if outcome_path.exists():
                continue
            outcome = build_outcome(
                forecast,
                forecast_hash,
                entry,
                prices,
                entry_index,
                horizon,
                price_source=str(source.get("price_source") or "unknown"),
                price_source_timestamp=source.get("price_source_timestamp"),
                settled_at_utc=settled_at_utc,
            )
            if outcome is None:
                open_horizons.append(f"{signal_id}:{horizon}")
                continue
            write_immutable_json(outcome_path, outcome)
            created_outcomes.append(str(outcome_relative_path(signal_id, horizon)).replace("\\", "/"))

    result = {
        "schema_version": 1,
        "settled_at_utc": iso_utc(settled_at_utc),
        "created_entries": sorted(created_entries),
        "created_outcomes": sorted(created_outcomes),
        "created_entry_count": len(created_entries),
        "created_outcome_count": len(created_outcomes),
        "open_entry_count": len(set(open_entries)),
        "open_horizon_count": len(set(open_horizons)),
    }
    if metadata_out is not None:
        atomic_write_json(metadata_out, result)
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ledger-root", type=Path, required=True)
    parser.add_argument("--interactive", type=Path, default=INTERACTIVE)
    parser.add_argument("--metals", type=Path, default=METALS)
    parser.add_argument("--metadata-out", type=Path)
    parser.add_argument("--now-utc", help="Override settlement time for deterministic tests")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    now = parse_utc(args.now_utc) if args.now_utc else datetime.now(UTC)
    sources = load_price_sources(args.interactive, args.metals)
    result = settle(
        ledger_root=args.ledger_root,
        price_sources=sources,
        settled_at_utc=now,
        metadata_out=args.metadata_out,
    )
    print(
        f"Live settlement complete · entries={result['created_entry_count']} · "
        f"outcomes={result['created_outcome_count']} · open_horizons={result['open_horizon_count']}"
    )


if __name__ == "__main__":
    main()
