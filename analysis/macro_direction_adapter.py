#!/usr/bin/env python3
"""Adapt the existing macro dashboard payload into directional-model sub-scores.

This module does not replace the macro engine. It separates the existing broad
score into liquidity plumbing, market transmission, and supply/event pressure
for clearer position-sizing decisions. Missing factors reduce availability
instead of being silently interpreted as neutral evidence.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

from build_directional_cot_report import extract_js_object

ROOT = Path(__file__).resolve().parent
DEFAULT_DASHBOARD = ROOT / "interactive_cot_dashboard.html"

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
SUPPLY_FACTORS = {
    "score_treasury_supply": 10.0,
}
ALL_FACTOR_WEIGHTS = {
    **PLUMBING_FACTORS,
    **TRANSMISSION_FACTORS,
    **SUPPLY_FACTORS,
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
    regime_label: str
    hard_override: bool
    severe_alert_count: int
    severe_alerts: list[str]
    source: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number else None


def weighted_available_score(latest: dict[str, Any], factors: dict[str, float]) -> tuple[float | None, float]:
    numerator = 0.0
    available_weight = 0.0
    for key, weight in factors.items():
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


def load_macro_direction_context(path: Path = DEFAULT_DASHBOARD) -> MacroDirectionContext:
    if not path.exists():
        return MacroDirectionContext(
            macro_regime_score=None,
            liquidity_plumbing_score=None,
            market_transmission_score=None,
            supply_pressure_score=None,
            availability_ratio=0.0,
            available_weight=0.0,
            total_weight=sum(ALL_FACTOR_WEIGHTS.values()),
            regime_label="Unavailable",
            hard_override=False,
            severe_alert_count=0,
            severe_alerts=[],
            source="macro_dashboard_missing",
        )

    source = path.read_text(encoding="utf-8", errors="replace")
    payload = extract_js_object(source, "MACRO_MONITOR") or {}
    latest = payload.get("latest") or {}
    alerts = payload.get("alerts") or []

    plumbing, plumbing_weight = weighted_available_score(latest, PLUMBING_FACTORS)
    transmission, transmission_weight = weighted_available_score(latest, TRANSMISSION_FACTORS)
    supply, supply_weight = weighted_available_score(latest, SUPPLY_FACTORS)

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

    return MacroDirectionContext(
        macro_regime_score=round(macro_score, 2) if macro_score is not None else None,
        liquidity_plumbing_score=round(plumbing, 2) if plumbing is not None else None,
        market_transmission_score=round(transmission, 2) if transmission is not None else None,
        supply_pressure_score=round(supply, 2) if supply is not None else None,
        availability_ratio=round(availability, 4),
        available_weight=round(available_weight, 2),
        total_weight=round(total_weight, 2),
        regime_label=regime_label(macro_score),
        hard_override=len(severe) >= 2,
        severe_alert_count=len(severe),
        severe_alerts=severe,
        source="interactive_cot_dashboard.MACRO_MONITOR",
    )
