#!/usr/bin/env python3
"""Enrich canonical multi-market COT history with release-time macro/price context."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from build_directional_cot_report import MARKETS, extract_js_object, read_prices
from build_directional_cot_system import HISTORY_OUT
from cot_direction_model import asset_manager_multiplier, clamp, load_config, macro_multiplier

ROOT = Path(__file__).resolve().parent
DASHBOARD = ROOT / "interactive_cot_dashboard.html"
WAITING_BAND_PCT = 0.25


def finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number else None


def load_macro_records(path: Path = DASHBOARD) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Missing macro dashboard {path}")
    payload = extract_js_object(path.read_text(encoding="utf-8", errors="replace"), "MACRO_MONITOR") or {}
    rows = payload.get("records") or []
    if not rows:
        raise ValueError("MACRO_MONITOR has no historical records")
    frame = pd.DataFrame(rows)
    required = {"date", "liquidity_score", "net_liquidity_4w_change", "bank_reserves_4w_change", "sofr_iorb_spread", "hy_oas_4w_change"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise KeyError(f"Historical macro records missing {missing}")
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    for column in frame.columns:
        if column not in {"date", "regime_label"}:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame.dropna(subset=["date"]).sort_values("date").drop_duplicates("date", keep="last")


def historical_red_alert_count(current: pd.Series, previous: pd.Series | None) -> tuple[int, list[str]]:
    alerts: list[str] = []
    net_liquidity = finite(current.get("net_liquidity_4w_change"))
    reserves = finite(current.get("bank_reserves_4w_change"))
    repo = finite(current.get("sofr_iorb_spread"))
    credit = finite(current.get("hy_oas_4w_change"))
    score = finite(current.get("liquidity_score"))
    previous_score = finite(previous.get("liquidity_score")) if previous is not None else None
    if net_liquidity is not None and net_liquidity < -150:
        alerts.append("Net liquidity drawdown")
    if reserves is not None and reserves < -200:
        alerts.append("Reserve drain")
    if repo is not None and repo > 0.10:
        alerts.append("Repo funding pressure")
    if credit is not None and credit > 0.50:
        alerts.append("HY spread widening")
    if score is not None and previous_score is not None and previous_score >= 45 and score < 45:
        alerts.append("Score crossed below 45")
    return len(alerts), alerts


def price_trend_at_signal(prices: pd.DataFrame, signal_date: pd.Timestamp, periods: int = 20) -> float | None:
    eligible = prices.loc[prices["date"] <= signal_date].copy()
    if len(eligible) <= periods:
        return None
    latest = float(eligible.iloc[-1]["price"])
    prior = float(eligible.iloc[-1 - periods]["price"])
    return (latest / prior - 1.0) * 100.0 if latest > 0 and prior > 0 else None


def historical_price_multiplier(adjusted_score: float | None, trend_20d_pct: float | None, market: str, config: dict[str, Any]) -> tuple[float, str]:
    if adjusted_score is None or abs(adjusted_score) < 0.25:
        return 0.0, "No structural signal"
    if trend_20d_pct is None:
        return 0.0, "Unavailable"
    sign = 1.0 if adjusted_score > 0 else -1.0
    signed_trend = sign * trend_20d_pct
    invalidation = float(MARKETS[market].get("invalidation_pct") or config["execution"]["sp500_invalidation_pct"])
    if signed_trend <= -invalidation:
        return 0.0, "Invalidated"
    if signed_trend > WAITING_BAND_PCT:
        return 1.0, "Trend confirmed"
    if signed_trend < -WAITING_BAND_PCT:
        return 0.25, "Trend contradicted"
    return 0.50, "Trend waiting"


def align_macro(history: pd.DataFrame, macro: pd.DataFrame) -> pd.DataFrame:
    left = history.copy()
    left["signal_price_date"] = pd.to_datetime(left["signal_price_date"], errors="coerce")
    right = macro.copy().rename(columns={"date": "historical_macro_date"})
    aligned = pd.merge_asof(
        left.sort_values("signal_price_date"),
        right.sort_values("historical_macro_date"),
        left_on="signal_price_date",
        right_on="historical_macro_date",
        direction="backward",
        suffixes=("", "_macro"),
    )
    return aligned.sort_values(["market", "report_date"]).reset_index(drop=True)


def enrich_history(history: pd.DataFrame, macro: pd.DataFrame, config: dict[str, Any]) -> pd.DataFrame:
    aligned = align_macro(history, macro)
    price_frames = {market: read_prices(meta["price_path"], meta["price_col"]) for market, meta in MARKETS.items()}
    macro_sorted = macro.reset_index(drop=True)
    macro_index_by_date = {pd.Timestamp(value): index for index, value in enumerate(macro_sorted["date"])}
    rows: list[dict[str, Any]] = []
    for _, raw in aligned.iterrows():
        row = raw.to_dict()
        market = str(row["market"])
        adjusted = finite(row.get("adjusted_cot_score"))
        crowding_percentile = finite(row.get("asset_manager_percentile"))
        macro_score = finite(row.get("liquidity_score"))
        signal_date = pd.to_datetime(row.get("signal_price_date"), errors="coerce")
        trend_20d = price_trend_at_signal(price_frames[market], pd.Timestamp(signal_date)) if pd.notna(signal_date) else None
        crowding_mult, crowding_state = asset_manager_multiplier(crowding_percentile, config)
        macro_mult, macro_state = macro_multiplier(macro_score, config)
        price_mult, price_state = historical_price_multiplier(adjusted, trend_20d, market, config)

        macro_date = pd.to_datetime(row.get("historical_macro_date"), errors="coerce")
        current_macro: pd.Series | None = None
        previous_macro: pd.Series | None = None
        if pd.notna(macro_date):
            macro_position = macro_index_by_date.get(pd.Timestamp(macro_date))
            if macro_position is not None:
                current_macro = macro_sorted.iloc[macro_position]
                previous_macro = macro_sorted.iloc[macro_position - 1] if macro_position >= 1 else None
        red_count, red_alerts = historical_red_alert_count(current_macro, previous_macro) if current_macro is not None else (0, [])
        hard_override = red_count >= 2
        if adjusted is None or abs(adjusted) < 0.25 or macro_score is None or trend_20d is None:
            full_score = None
        elif hard_override:
            full_score = 0.0
        else:
            full_score = clamp(adjusted * crowding_mult * macro_mult * price_mult, -1.25, 1.25)

        row.update({
            "historical_macro_score": macro_score,
            "historical_macro_state": macro_state,
            "historical_macro_multiplier": macro_mult,
            "historical_asset_manager_state": crowding_state,
            "historical_asset_manager_multiplier": crowding_mult,
            "historical_conviction_group_label": MARKETS[market]["conviction_group_label"],
            "historical_price_trend_20d_pct": trend_20d,
            "historical_price_state": price_state,
            "historical_price_multiplier": price_mult,
            "historical_red_alert_count": red_count,
            "historical_red_alerts": " | ".join(red_alerts),
            "historical_macro_override": hard_override,
            "release_decision_score": full_score,
            "release_decision_definition": "Friday COT + crowding size + as-of macro + 20d trend; no future post-release confirmation",
        })
        rows.append(row)
    return pd.DataFrame(rows)


def main() -> None:
    if not HISTORY_OUT.exists():
        raise FileNotFoundError(f"Missing {HISTORY_OUT}; run rebuild_directional_history.py first")
    history = pd.read_csv(HISTORY_OUT)
    config = load_config(ROOT / "config" / "cot_direction_model_v1.json")
    enrich_history(history, load_macro_records(), config).to_csv(HISTORY_OUT, index=False)
    print(f"Enriched {HISTORY_OUT} with historical macro and price context")


if __name__ == "__main__":
    main()
