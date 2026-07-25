#!/usr/bin/env python3
"""Adapt the existing macro dashboard payload into directional-model sub-scores.

This module does not replace the macro engine. It separates the existing broad
score into liquidity plumbing, market transmission, and supply/event pressure.
Missing or stale factors reduce availability instead of being silently treated
as neutral evidence.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from build_directional_cot_report import extract_js_object

ROOT = Path(__file__).resolve().parent
DEFAULT_DASHBOARD = ROOT / "interactive_cot_dashboard.html"
MINIMUM_RELIABLE_AVAILABILITY = 0.60

PLUMBING_FACTORS = {
    "score_net_liquidity": 26.0,
    "score_bank_reserves": 10.0,
    "score_repo_spread": 8.0,
    "score_slr_load": 4.0,
}
TRANSMISSION_FACTORS = {
    "score_real_yield": 14.0,
    "score_credit": 14.0,
    "score_dollar": 8.0,
    "score_vix": 6.0,
}
SUPPLY_FACTORS = {"score_treasury_supply": 10.0}
ALL_FACTOR_WEIGHTS = {**PLUMBING_FACTORS, **TRANSMISSION_FACTORS, **SUPPLY_FACTORS}

FACTOR_SOURCE_DATES = {
    "score_net_liquidity": (
        ("liquidity_latest", "fed_balance_sheet", 12),
        ("liquidity_latest", "reverse_repo", 5),
        ("liquidity_latest", "treasury_cash", 12),
    ),
    "score_bank_reserves": (("liquidity_latest", "bank_reserves", 12),),
    "score_repo_spread": (
        ("funding_latest", "sofr", 5),
        ("funding_latest", "iorb", 5),
    ),
    "score_slr_load": (("liquidity_latest", "bank_treasury_agency", 12),),
    "score_real_yield": (("factor_latest", "real_yield_10y", 5),),
    "score_credit": (("factor_latest", "hy_oas", 5),),
    "score_dollar": (("factor_latest", "dollar_index", 5),),
    "score_vix": (("factor_latest", "fred_vix", 5),),
    "score_treasury_supply": (("generated_at_utc", "", 2),),
}


@dataclass
class MacroDirectionContext:
    macro_regime_score: float | None
    liquidity_plumbing_score: float | None
    market_transmission_score: float | None
    supply_pressure_score: float | None
    availability_ratio: float
    available_weight: float
    total_weight: float
    reliable_for_action: bool
    regime_label: str
    hard_override: bool
    hard_override_suppressed_by_freshness: bool
    severe_alert_count: int
    severe_alerts: list[str]
    stale_factors: list[str]
    missing_factors: list[str]
    source: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number else None


def parse_timestamp(value: Any) -> pd.Timestamp | None:
    if value in {None, ""}:
        return None
    parsed = pd.to_datetime(value, errors="coerce", utc=True)
    return None if pd.isna(parsed) else pd.Timestamp(parsed)


def metadata_date(metadata: dict[str, Any], section: str, key: str) -> pd.Timestamp | None:
    if section == "generated_at_utc":
        return parse_timestamp(metadata.get("generated_at_utc"))
    payload = metadata.get(section) or {}
    return parse_timestamp(payload.get(key))


def factor_freshness(
    factor: str,
    metadata: dict[str, Any],
    *,
    now: datetime | pd.Timestamp | None = None,
) -> tuple[bool, list[str]]:
    current = pd.Timestamp(now if now is not None else datetime.now(UTC))
    if current.tzinfo is None:
        current = current.tz_localize("UTC")
    else:
        current = current.tz_convert("UTC")
    failures: list[str] = []
    for section, key, maximum_age_days in FACTOR_SOURCE_DATES.get(factor, ()):
        observed = metadata_date(metadata, section, key)
        label = f"{section}.{key}" if key else section
        if observed is None:
            failures.append(f"{label} missing")
            continue
        age_days = (current - observed).total_seconds() / 86400.0
        if age_days > maximum_age_days:
            failures.append(f"{label} stale {age_days:.1f}d>{maximum_age_days}d")
    return not failures, failures


def weighted_available_score(
    latest: dict[str, Any],
    factors: dict[str, float],
    eligible: set[str] | None = None,
) -> tuple[float | None, float]:
    numerator = 0.0
    available_weight = 0.0
    for key, weight in factors.items():
        if eligible is not None and key not in eligible:
            continue
        value = finite(latest.get(key))
        if value is None:
            continue
        numerator += value * weight
        available_weight += weight
    if available_weight <= 0:
        return None, 0.0
    return max(0.0, min(100.0, numerator / available_weight)), available_weight


def regime_label(score: float | None) -> str:
    if score is None:
        return "Unavailable"
    if score >= 70:
        return "Strong supportive"
    if score >= 55:
        return "Supportive"
    if score >= 45:
        return "Neutral"
    if score >= 30:
        return "Defensive"
    return "Risk-off"


def unavailable_context(source: str) -> MacroDirectionContext:
    return MacroDirectionContext(
        macro_regime_score=None,
        liquidity_plumbing_score=None,
        market_transmission_score=None,
        supply_pressure_score=None,
        availability_ratio=0.0,
        available_weight=0.0,
        total_weight=sum(ALL_FACTOR_WEIGHTS.values()),
        reliable_for_action=False,
        regime_label="Unavailable",
        hard_override=False,
        hard_override_suppressed_by_freshness=False,
        severe_alert_count=0,
        severe_alerts=[],
        stale_factors=[],
        missing_factors=list(ALL_FACTOR_WEIGHTS),
        source=source,
    )


def load_macro_direction_context(
    path: Path = DEFAULT_DASHBOARD,
    *,
    now: datetime | pd.Timestamp | None = None,
) -> MacroDirectionContext:
    if not path.exists():
        return unavailable_context("macro_dashboard_missing")

    source_text = path.read_text(encoding="utf-8", errors="replace")
    payload = extract_js_object(source_text, "MACRO_MONITOR") or {}
    metadata = extract_js_object(source_text, "METADATA") or {}
    latest = payload.get("latest") or {}
    alerts = payload.get("alerts") or []
    if not latest:
        return unavailable_context("macro_payload_missing")

    eligible: set[str] = set()
    stale_factors: list[str] = []
    missing_factors: list[str] = []
    for factor in ALL_FACTOR_WEIGHTS:
        if finite(latest.get(factor)) is None:
            missing_factors.append(factor)
            continue
        fresh, failures = factor_freshness(factor, metadata, now=now)
        if fresh:
            eligible.add(factor)
        else:
            stale_factors.append(f"{factor}: " + "; ".join(failures))

    plumbing, plumbing_weight = weighted_available_score(latest, PLUMBING_FACTORS, eligible)
    transmission, transmission_weight = weighted_available_score(latest, TRANSMISSION_FACTORS, eligible)
    supply, supply_weight = weighted_available_score(latest, SUPPLY_FACTORS, eligible)

    component_values: list[tuple[float, float]] = []
    if plumbing is not None:
        component_values.append((plumbing, 45.0))
    if transmission is not None:
        component_values.append((transmission, 40.0))
    if supply is not None:
        component_values.append((supply, 15.0))
    macro_score = None
    if component_values:
        denominator = sum(weight for _, weight in component_values)
        macro_score = sum(value * weight for value, weight in component_values) / denominator
        macro_score = max(0.0, min(100.0, macro_score))

    severe = [
        str(row.get("label") or "Unnamed severe alert")
        for row in alerts
        if row.get("triggered") and str(row.get("severity") or "").lower() == "red"
    ]
    available_weight = plumbing_weight + transmission_weight + supply_weight
    total_weight = sum(ALL_FACTOR_WEIGHTS.values())
    availability = available_weight / total_weight if total_weight else 0.0
    reliable = availability >= MINIMUM_RELIABLE_AVAILABILITY
    raw_override = len(severe) >= 2

    return MacroDirectionContext(
        macro_regime_score=round(macro_score, 2) if macro_score is not None else None,
        liquidity_plumbing_score=round(plumbing, 2) if plumbing is not None else None,
        market_transmission_score=round(transmission, 2) if transmission is not None else None,
        supply_pressure_score=round(supply, 2) if supply is not None else None,
        availability_ratio=round(availability, 4),
        available_weight=round(available_weight, 2),
        total_weight=round(total_weight, 2),
        reliable_for_action=reliable,
        regime_label=regime_label(macro_score),
        hard_override=raw_override and reliable,
        hard_override_suppressed_by_freshness=raw_override and not reliable,
        severe_alert_count=len(severe),
        severe_alerts=severe,
        stale_factors=stale_factors,
        missing_factors=missing_factors,
        source="interactive_cot_dashboard.MACRO_MONITOR+METADATA",
    )
