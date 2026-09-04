#!/usr/bin/env python3
"""Adapter bridging Macro Monitor data into the COT directional model."""

from __future__ import annotations

import json
import math
import re
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
DEFAULT_DASHBOARD = ROOT / "interactive_cot_dashboard.html"
MACRO_VINTAGE_SAFE = False
MINIMUM_RELIABLE_AVAILABILITY = 0.50

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

GROUP_WEIGHTS = {
    "plumbing": 48.0,
    "transmission": 42.0,
    "supply": 10.0,
}

TOTAL_WEIGHT = sum(ALL_FACTOR_WEIGHTS.values())

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
    macro_context: dict[str, Any]
    macro_risk_budget: dict[str, Any]
    macro_directional_edges: dict[str, Any]
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
        num = float(value)
    except (TypeError, ValueError):
        return None
    return num if math.isfinite(num) else None


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


def extract_js_object(source: str, variable: str) -> dict[str, Any] | None:
    """Read a JSON object assigned as `const NAME = <json>;` or `var NAME = <json>;` in HTML."""
    start = -1
    for prefix in (f"const {variable} = ", f"var {variable} = ", f"let {variable} = "):
        pos = source.find(prefix)
        if pos >= 0:
            start = pos + len(prefix)
            break
    if start < 0:
        return None
    index = start
    depth = 0
    in_string = False
    escaped = False
    for cursor in range(index, len(source)):
        char = source[cursor]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char in "[{":
            depth += 1
        elif char in "]}":
            depth -= 1
            if depth < 0:
                return None
        elif char == ";" and depth == 0:
            try:
                parsed = json.loads(source[index:cursor])
            except json.JSONDecodeError:
                return None
            return parsed if isinstance(parsed, dict) else None
    return None


def weighted_available_score(
    latest: dict[str, Any],
    weights: dict[str, float],
    eligible_factors: set[str] | None = None,
) -> tuple[float | None, float]:
    total_w = 0.0
    accum = 0.0
    for factor, weight in weights.items():
        if eligible_factors is not None and factor not in eligible_factors:
            continue
        val = finite(latest.get(factor))
        if val is None:
            continue
        accum += val * float(weight)
        total_w += float(weight)
    if total_w <= 1e-9:
        return None, 0.0
    return clamp_score(accum / total_w), total_w


def shrink_toward_neutral(
    observed_score: float | None,
    availability_confidence: float,
) -> float | None:
    if observed_score is None:
        return None
    confidence = max(0.0, min(1.0, float(availability_confidence)))
    return clamp_score(50.0 + confidence * (float(observed_score) - 50.0))


def regime_label(score: float | None) -> str:
    if score is None:
        return "Unavailable"
    s = clamp_score(score)
    if s >= 70.0:
        return "Strong supportive"
    if s >= 55.0:
        return "Supportive"
    if s >= 45.0:
        return "Neutral"
    if s >= 30.0:
        return "Defensive"
    return "Risk-off"


def risk_budget_payload(
    *,
    hard_override: bool,
    raw_override: bool,
    reliable: bool,
    severe_alerts: list[str],
) -> dict[str, Any]:
    if hard_override:
        return {
            "status": "HARD_OVERRIDE",
            "multiplier": 0.0,
            "exposure_cap": 0.0,
            "hard_override_applied": True,
            "raw_override": raw_override,
            "reliable": reliable,
            "severe_alert_count": len(severe_alerts),
            "severe_alerts": severe_alerts,
            "aggregate_score_sizing_weight": 0.0,
        }
    if not reliable:
        return {
            "status": "DEGRADED_AVAILABILITY",
            "multiplier": 1.0,
            "exposure_cap": 1.0,
            "hard_override_applied": False,
            "raw_override": raw_override,
            "reliable": False,
            "severe_alert_count": len(severe_alerts),
            "severe_alerts": severe_alerts,
            "aggregate_score_sizing_weight": 0.0,
        }
    return {
        "status": "NEUTRAL",
        "multiplier": 1.0,
        "exposure_cap": 1.0,
        "hard_override_applied": False,
        "raw_override": raw_override,
        "reliable": True,
        "severe_alert_count": len(severe_alerts),
        "severe_alerts": severe_alerts,
        "aggregate_score_sizing_weight": 0.0,
    }


def directional_edges_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "RESEARCH_ONLY_NOT_VINTAGE_SAFE",
        "macro_vintage_safe": MACRO_VINTAGE_SAFE,
        "aggregate_score_directional_weight": 0.0,
        "production_weight": 0.0,
        "active_edges": [],
        "evidence_status": "CALENDAR_ALIGNED_NOT_VINTAGE_SAFE",
    }


def score_block(
    latest: dict[str, Any],
    weights: dict[str, float],
    eligible: set[str] | None = None,
) -> dict[str, Any]:
    observed, available_w = weighted_available_score(latest, weights, eligible)
    total_w = sum(weights.values())
    availability = available_w / total_w if total_w else 0.0
    effective = shrink_toward_neutral(observed, availability)
    return {
        "observed_score": round(observed, 2) if observed is not None else None,
        "effective_score": round(effective, 2) if effective is not None else None,
        "availability_ratio": round(availability, 4),
        "available_weight": round(available_w, 2),
        "total_weight": round(total_w, 2),
        "weights": weights,
    }


def unavailable_context(source: str) -> MacroDirectionContext:
    risk_budget = risk_budget_payload(
        hard_override=False,
        raw_override=False,
        reliable=False,
        severe_alerts=[],
    )
    directional_edges = directional_edges_payload({})
    macro_context = {
        "observed_score": None,
        "effective_score": None,
        "regime_label": "Unavailable",
        "availability_ratio": 0.0,
        "available_weight": 0.0,
        "total_weight": TOTAL_WEIGHT,
        "reliable": False,
        "macro_vintage_safe": MACRO_VINTAGE_SAFE,
        "canonical_group_weights": GROUP_WEIGHTS,
        "canonical_factor_weights": ALL_FACTOR_WEIGHTS,
        "missing_factors": list(ALL_FACTOR_WEIGHTS),
        "stale_factors": [],
        "components": {
            "plumbing": score_block({}, PLUMBING_FACTORS, set()),
            "transmission": score_block({}, TRANSMISSION_FACTORS, set()),
            "supply": score_block({}, SUPPLY_FACTORS, set()),
        },
        "source": source,
    }
    return MacroDirectionContext(
        macro_context=macro_context,
        macro_risk_budget=risk_budget,
        macro_directional_edges=directional_edges,
        macro_regime_score=None,
        liquidity_plumbing_score=None,
        market_transmission_score=None,
        supply_pressure_score=None,
        availability_ratio=0.0,
        available_weight=0.0,
        total_weight=TOTAL_WEIGHT,
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

    observed_score, available_weight = weighted_available_score(
        latest, ALL_FACTOR_WEIGHTS, eligible
    )
    availability = available_weight / TOTAL_WEIGHT if TOTAL_WEIGHT else 0.0
    effective_score = shrink_toward_neutral(observed_score, availability)

    plumbing = score_block(latest, PLUMBING_FACTORS, eligible)
    transmission = score_block(latest, TRANSMISSION_FACTORS, eligible)
    supply = score_block(latest, SUPPLY_FACTORS, eligible)

    severe = [
        str(row.get("label") or "Unnamed severe alert")
        for row in alerts
        if row.get("triggered") and str(row.get("severity") or "").lower() == "red"
    ]
    reliable = availability >= MINIMUM_RELIABLE_AVAILABILITY
    raw_override = len(severe) >= 2
    hard_override = raw_override and reliable

    context_source = "interactive_cot_dashboard.MACRO_MONITOR+METADATA"
    macro_context = {
        "observed_score": round(observed_score, 2) if observed_score is not None else None,
        "effective_score": round(effective_score, 2) if effective_score is not None else None,
        "regime_label": regime_label(effective_score),
        "availability_ratio": round(availability, 4),
        "available_weight": round(available_weight, 2),
        "total_weight": round(TOTAL_WEIGHT, 2),
        "reliable": reliable,
        "macro_vintage_safe": MACRO_VINTAGE_SAFE,
        "canonical_group_weights": GROUP_WEIGHTS,
        "canonical_factor_weights": ALL_FACTOR_WEIGHTS,
        "components": {
            "plumbing": plumbing,
            "transmission": transmission,
            "supply": supply,
        },
        "missing_factors": missing_factors,
        "stale_factors": stale_factors,
        "source": context_source,
    }
    risk_budget = risk_budget_payload(
        hard_override=hard_override,
        raw_override=raw_override,
        reliable=reliable,
        severe_alerts=severe,
    )
    directional_edges = directional_edges_payload(payload)

    return MacroDirectionContext(
        macro_context=macro_context,
        macro_risk_budget=risk_budget,
        macro_directional_edges=directional_edges,
        macro_regime_score=round(effective_score, 2) if effective_score is not None else None,
        liquidity_plumbing_score=plumbing["effective_score"],
        market_transmission_score=transmission["effective_score"],
        supply_pressure_score=supply["effective_score"],
        availability_ratio=round(availability, 4),
        available_weight=round(available_weight, 2),
        total_weight=round(TOTAL_WEIGHT, 2),
        reliable_for_action=reliable,
        regime_label=regime_label(effective_score),
        hard_override=hard_override,
        hard_override_suppressed_by_freshness=raw_override and not reliable,
        severe_alert_count=len(severe),
        severe_alerts=severe,
        stale_factors=stale_factors,
        missing_factors=missing_factors,
        source=context_source,
    )
