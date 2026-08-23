#!/usr/bin/env python3
"""Adapt macro dashboard data into governed context for the COT decision system.

The macro layer is deliberately separated from the directional COT thesis:

* COT supplies the directional thesis.
* Price supplies execution confirmation/invalidation.
* Macro supplies context and an advisory risk-budget view only.

The aggregate macro score uses one canonical weighting pass: Plumbing 48%,
Transmission 42%, Supply 10%. Missing or stale inputs reduce availability and
shrink the observed aggregate toward neutral rather than allowing a partial
subset of factors to masquerade as a fully informed score.
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
NEUTRAL_SCORE = 50.0

# These factor weights are the canonical production weights. Their sums are the
# component weights: Plumbing 48, Transmission 42, Supply 10. Do not apply a
# second component-weight normalization pass after these weights are used.
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
COMPONENT_WEIGHTS = {
    "plumbing": sum(PLUMBING_FACTORS.values()),
    "transmission": sum(TRANSMISSION_FACTORS.values()),
    "supply": sum(SUPPLY_FACTORS.values()),
}

if COMPONENT_WEIGHTS != {"plumbing": 48.0, "transmission": 42.0, "supply": 10.0}:
    raise RuntimeError(f"Unexpected canonical macro weights: {COMPONENT_WEIGHTS}")
if abs(sum(ALL_FACTOR_WEIGHTS.values()) - 100.0) > 1e-9:
    raise RuntimeError("Canonical macro factor weights must sum to 100")

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
    macro_observed_score: float | None
    liquidity_plumbing_score: float | None
    market_transmission_score: float | None
    supply_pressure_score: float | None
    availability_ratio: float
    availability_confidence: float
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
    macro_context: dict[str, Any]
    macro_risk_budget: dict[str, Any]
    macro_directional_edges: list[dict[str, Any]]
    source: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number else None


def clamp_score(value: float) -> float:
    return max(0.0, min(100.0, float(value)))


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
    """Return the observed weighted score and the weight actually available.

    This function intentionally normalizes only across the available factor
    weights supplied to it. The production aggregate then applies missing-data
    shrinkage exactly once using the fraction of the canonical 100 weight that
    was available.
    """
    numerator = 0.0
    available_weight = 0.0
    for key, weight in factors.items():
        if eligible is not None and key not in eligible:
            continue
        value = finite(latest.get(key))
        if value is None:
            continue
        numerator += clamp_score(value) * weight
        available_weight += weight
    if available_weight <= 0:
        return None, 0.0
    return clamp_score(numerator / available_weight), available_weight


def shrink_toward_neutral(
    observed_score: float | None,
    availability_confidence: float,
) -> float | None:
    """Shrink incomplete evidence toward 50 using the governed formula."""
    if observed_score is None:
        return None
    confidence = max(0.0, min(1.0, float(availability_confidence)))
    effective_score = NEUTRAL_SCORE + confidence * (float(observed_score) - NEUTRAL_SCORE)
    return clamp_score(effective_score)


def component_effective_score(
    observed_score: float | None,
    available_weight: float,
    canonical_weight: float,
) -> float | None:
    confidence = available_weight / canonical_weight if canonical_weight > 0 else 0.0
    return shrink_toward_neutral(observed_score, confidence)


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


def edge_label(score: float | None) -> str:
    if score is None:
        return "unavailable"
    if score >= 55:
        return "supportive"
    if score <= 45:
        return "defensive"
    return "neutral"


def directional_edges(
    plumbing: float | None,
    transmission: float | None,
    supply: float | None,
) -> list[dict[str, Any]]:
    rows = (
        ("Liquidity plumbing", "plumbing", plumbing, COMPONENT_WEIGHTS["plumbing"]),
        ("Market transmission", "transmission", transmission, COMPONENT_WEIGHTS["transmission"]),
        ("Treasury supply", "supply", supply, COMPONENT_WEIGHTS["supply"]),
    )
    return [
        {
            "label": label,
            "component": component,
            "score": round(score, 2) if score is not None else None,
            "context": edge_label(score),
            "canonical_weight_pct": weight,
            "production_directional_weight": 0.0,
            "evidence_status": "context_only_not_vintage_safe",
        }
        for label, component, score, weight in rows
    ]


def risk_budget_payload(
    *,
    score: float | None,
    availability: float,
    hard_override: bool,
    reliable: bool,
) -> dict[str, Any]:
    """Describe macro risk context without silently resizing the COT thesis."""
    if hard_override:
        state = "hard_override"
    elif not reliable:
        state = "insufficient_fresh_data"
    else:
        state = edge_label(score)
    return {
        "state": state,
        "context_score": round(score, 2) if score is not None else None,
        "availability_confidence": round(availability, 4),
        "production_macro_multiplier": 1.0,
        "production_directional_weight": 0.0,
        "hard_override": bool(hard_override),
        "advisory_only": True,
        "evidence_status": "calendar_aligned_not_vintage_safe",
        "policy": "Macro does not resize or reverse COT direction; independent hard overrides remain active.",
    }


def unavailable_context(source: str) -> MacroDirectionContext:
    total_weight = sum(ALL_FACTOR_WEIGHTS.values())
    macro_context = {
        "effective_score": None,
        "observed_score": None,
        "availability_confidence": 0.0,
        "regime": "Unavailable",
        "canonical_weights_pct": COMPONENT_WEIGHTS.copy(),
        "evidence_status": "unavailable",
    }
    return MacroDirectionContext(
        macro_regime_score=None,
        macro_observed_score=None,
        liquidity_plumbing_score=None,
        market_transmission_score=None,
        supply_pressure_score=None,
        availability_ratio=0.0,
        availability_confidence=0.0,
        available_weight=0.0,
        total_weight=total_weight,
        reliable_for_action=False,
        regime_label="Unavailable",
        hard_override=False,
        hard_override_suppressed_by_freshness=False,
        severe_alert_count=0,
        severe_alerts=[],
        stale_factors=[],
        missing_factors=list(ALL_FACTOR_WEIGHTS),
        macro_context=macro_context,
        macro_risk_budget=risk_budget_payload(
            score=None,
            availability=0.0,
            hard_override=False,
            reliable=False,
        ),
        macro_directional_edges=directional_edges(None, None, None),
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

    plumbing_observed, plumbing_weight = weighted_available_score(latest, PLUMBING_FACTORS, eligible)
    transmission_observed, transmission_weight = weighted_available_score(latest, TRANSMISSION_FACTORS, eligible)
    supply_observed, supply_weight = weighted_available_score(latest, SUPPLY_FACTORS, eligible)

    plumbing = component_effective_score(
        plumbing_observed,
        plumbing_weight,
        COMPONENT_WEIGHTS["plumbing"],
    )
    transmission = component_effective_score(
        transmission_observed,
        transmission_weight,
        COMPONENT_WEIGHTS["transmission"],
    )
    supply = component_effective_score(
        supply_observed,
        supply_weight,
        COMPONENT_WEIGHTS["supply"],
    )

    # Single canonical aggregate pass. The original factor weights already sum
    # to 48/42/10 by component, so there must be no second component weighting.
    observed_score, available_weight = weighted_available_score(latest, ALL_FACTOR_WEIGHTS, eligible)
    total_weight = sum(ALL_FACTOR_WEIGHTS.values())
    availability = available_weight / total_weight if total_weight else 0.0
    macro_score = shrink_toward_neutral(observed_score, availability)

    severe = [
        str(row.get("label") or "Unnamed severe alert")
        for row in alerts
        if row.get("triggered") and str(row.get("severity") or "").lower() == "red"
    ]
    reliable = availability >= MINIMUM_RELIABLE_AVAILABILITY
    raw_override = len(severe) >= 2
    hard_override = raw_override and reliable
    label = regime_label(macro_score)

    macro_context = {
        "effective_score": round(macro_score, 2) if macro_score is not None else None,
        "observed_score": round(observed_score, 2) if observed_score is not None else None,
        "availability_confidence": round(availability, 4),
        "regime": label,
        "canonical_weights_pct": COMPONENT_WEIGHTS.copy(),
        "components": {
            "plumbing": round(plumbing, 2) if plumbing is not None else None,
            "transmission": round(transmission, 2) if transmission is not None else None,
            "supply": round(supply, 2) if supply is not None else None,
        },
        "reliable_for_action": reliable,
        "evidence_status": "calendar_aligned_not_vintage_safe",
    }

    return MacroDirectionContext(
        macro_regime_score=round(macro_score, 2) if macro_score is not None else None,
        macro_observed_score=round(observed_score, 2) if observed_score is not None else None,
        liquidity_plumbing_score=round(plumbing, 2) if plumbing is not None else None,
        market_transmission_score=round(transmission, 2) if transmission is not None else None,
        supply_pressure_score=round(supply, 2) if supply is not None else None,
        availability_ratio=round(availability, 4),
        availability_confidence=round(availability, 4),
        available_weight=round(available_weight, 2),
        total_weight=round(total_weight, 2),
        reliable_for_action=reliable,
        regime_label=label,
        hard_override=hard_override,
        hard_override_suppressed_by_freshness=raw_override and not reliable,
        severe_alert_count=len(severe),
        severe_alerts=severe,
        stale_factors=stale_factors,
        missing_factors=missing_factors,
        macro_context=macro_context,
        macro_risk_budget=risk_budget_payload(
            score=macro_score,
            availability=availability,
            hard_override=hard_override,
            reliable=reliable,
        ),
        macro_directional_edges=directional_edges(plumbing, transmission, supply),
        source="interactive_cot_dashboard.MACRO_MONITOR+METADATA",
    )
