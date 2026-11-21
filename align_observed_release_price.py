#!/usr/bin/env python3
"""Correct signal-price alignment for delayed CFTC reports.

Scheduled reports are assumed public at 15:30 New York time and may use Friday's
close. For a delayed report, the local first-observed timestamp is used. When it
falls after 16:00 New York time, the first eligible daily close is the next
available trading-day close.
"""

from __future__ import annotations

import json
from datetime import time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

from build_directional_cot_report import MARKETS, price_at_or_after, read_prices
from build_directional_cot_system import OUT_DIR, write_csv

ROOT = Path(__file__).resolve().parent
DECISION_JSON = OUT_DIR / "cot_direction_latest.json"
DECISION_CSV = OUT_DIR / "cot_direction_latest.csv"
NEW_YORK = ZoneInfo("America/New_York")
CASH_CLOSE = time(16, 0)


def observed_signal_target(first_observed_utc: str) -> str:
    observed = pd.Timestamp(first_observed_utc)
    if observed.tzinfo is None:
        observed = observed.tz_localize("UTC")
    local = observed.tz_convert(NEW_YORK)
    target = local.date()
    if local.time() > CASH_CLOSE:
        target += timedelta(days=1)
    return target.isoformat()


def align_decisions(decisions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for raw in decisions:
        row = dict(raw)
        if row.get("release_date_source") != "first_observed_delayed" or not row.get("first_observed_utc"):
            output.append(row)
            continue
        market = str(row["market"])
        target = observed_signal_target(str(row["first_observed_utc"]))
        meta = MARKETS[market]
        prices = read_prices(meta["price_path"], meta["price_col"])
        signal_date, signal_price = price_at_or_after(prices, pd.Timestamp(target))
        if signal_date is None or signal_price in (None, 0):
            row["signal_price_date"] = None
            row["signal_price"] = None
            row["price_change_since_release_pct"] = None
            row["new_signal_available"] = False
            row["final_action"] = "Wait — Delayed Release Price Unavailable"
        else:
            latest_price = float(row.get("latest_price")) if row.get("latest_price") is not None else None
            row["observed_release_date"] = str(row["first_observed_utc"])[:10]
            row["effective_signal_target_date"] = target
            row["signal_price_date"] = signal_date
            row["signal_price"] = signal_price
            row["price_change_since_release_pct"] = (
                round((latest_price / signal_price - 1.0) * 100.0, 4)
                if latest_price is not None and signal_price
                else None
            )
            reasons = list(row.get("reasons") or [])
            reasons.append(
                f"Delayed release first observed {row['first_observed_utc']}; execution price aligned to {signal_date} close"
            )
            row["reasons"] = reasons
        output.append(row)
    return output


def main() -> None:
    try:
        decisions = json.loads(DECISION_JSON.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Cannot read {DECISION_JSON}: {exc}") from exc
    if not isinstance(decisions, list) or not decisions:
        raise ValueError("Directional decision JSON is empty")
    aligned = align_decisions(decisions)
    DECISION_JSON.write_text(json.dumps(aligned, indent=2) + "\n", encoding="utf-8")
    write_csv(DECISION_CSV, aligned)
    print("Observed delayed-release price alignment completed.")


if __name__ == "__main__":
    main()
