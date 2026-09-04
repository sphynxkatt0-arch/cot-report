#!/usr/bin/env python3
"""Transparent, release-aligned COT direction model for equity indices."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd

DEFAULT_CONFIG_PATH = (
    Path(__file__).resolve().parent / "config" / "cot_direction_model_v1.json"
)


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, float(value)))


def finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if np.isfinite(number) else None


def validate_config(config: dict[str, Any]) -> None:
    required = {
        "schema_version",
        "model_version",
        "minimum_history_weeks",
        "structural",
        "tactical",
        "asset_manager_size",
        "macro_size",
        "execution",
        "confidence",
    }
    missing = sorted(required - set(config))
    if missing:
        raise ValueError(f"Direction model config missing sections: {missing}")
    if int(config["minimum_history_weeks"]) < 26:
        raise ValueError("minimum_history_weeks must be at least 26")

    structural = config["structural"]
    full_low = float(structural["full_strength_percentile_low"])
    neutral_low = float(structural["neutral_percentile_low"])
    neutral_high = float(structural["neutral_percentile_high"])
    full_high = float(structural["full_strength_percentile_high"])
    if not 0 <= full_low < neutral_low < neutral_high < full_high <= 100:
        raise ValueError("Structural percentile thresholds must be strictly ordered inside 0..100")

    tactical = config["tactical"]
    minimum_structural = float(tactical["minimum_structural_magnitude"])
    cap = float(tactical["modifier_cap"])
    weights = [
        float(tactical["other_reportable_trend13_weight"]),
        float(tactical["nonreportable_trend13_weight"]),
        float(tactical["noncommercial_flow4_alignment_weight"]),
    ]
    if not 0 <= minimum_structural <= 1:
        raise ValueError("minimum_structural_magnitude must be inside 0..1")
    if not 0 <= cap <= 1:
        raise ValueError("modifier_cap must be inside 0..1")
    if any(weight < 0 for weight in weights):
        raise ValueError("Tactical weights cannot be negative")

    am = config["asset_manager_size"]
    if not 0 <= float(am["normal_max_percentile"]) <= float(am["warning_max_percentile"]) <= 100:
        raise ValueError("Asset Manager percentile thresholds are invalid")
    for key in ("warning_multiplier", "extreme_multiplier"):
        if not 0 <= float(am[key]) <= 1.25:
            raise ValueError(f"{key} must be inside 0..1.25")

    macro = config["macro_size"]
    thresholds = [
        float(macro["strong_risk_on_min"]),
        float(macro["supportive_min"]),
        float(macro["neutral_min"]),
        float(macro["defensive_min"]),
    ]
    if thresholds != sorted(thresholds, reverse=True):
        raise ValueError("Macro regime thresholds must be descending")

    execution = config["execution"]
    if float(execution["waiting_band_pct"]) < 0:
        raise ValueError("waiting_band_pct cannot be negative")
    for key in ("sp500_invalidation_pct", "nq_invalidation_pct"):
        if float(execution[key]) <= 0:
            raise ValueError(f"{key} must be positive")
    for key in (
        "confirmed_multiplier",
        "waiting_multiplier",
        "contradicted_multiplier",
        "invalidated_multiplier",
    ):
        if not 0 <= float(execution[key]) <= 1.25:
            raise ValueError(f"{key} must be inside 0..1.25")

    confidence = config["confidence"]
    for key in ("nq_structural_base", "sp500_structural_base", "minimum_actionable"):
        if not 0 <= float(confidence[key]) <= 1:
            raise ValueError(f"{key} must be inside 0..1")


def load_config(path: Path | str = DEFAULT_CONFIG_PATH) -> dict[str, Any]:
    config = json.loads(Path(path).read_text(encoding="utf-8"))
    validate_config(config)
    return config


def scheduled_release_date(report_date: str | date | pd.Timestamp) -> date:
    day = pd.Timestamp(report_date).date()
    return day + timedelta(days=(4 - day.weekday()) % 7)


def percentile_rank_prior(
    history: Iterable[Any], value: Any, minimum: int = 26
) -> float | None:
    clean = pd.to_numeric(pd.Series(list(history), dtype="object"), errors="coerce").dropna()
    current = finite(value)
    if current is None or len(clean) < minimum:
        return None
    less = float((clean < current).sum())
    equal = float((clean == current).sum())
    return 100.0 * (less + 0.5 * equal) / len(clean)


def rank_score(percentile: float | None) -> float | None:
    if percentile is None:
        return None
    return clamp(float(percentile) / 50.0 - 1.0, -1.0, 1.0)


def structural_score_from_percentile(
    percentile: float | None, config: dict[str, Any]
) -> float | None:
    if percentile is None:
        return None
    cfg = config["structural"]
    p = clamp(float(percentile), 0.0, 100.0)
    low_neutral = float(cfg["neutral_percentile_low"])
    high_neutral = float(cfg["neutral_percentile_high"])
    full_low = float(cfg["full_strength_percentile_low"])
    full_high = float(cfg["full_strength_percentile_high"])
    if low_neutral <= p <= high_neutral:
        return 0.0
    if p < low_neutral:
        return clamp((low_neutral - p) / (low_neutral - full_low), 0.0, 1.0)
    return -clamp((p - high_neutral) / (full_high - high_neutral), 0.0, 1.0)


def tactical_modifier(
    structural_score: float | None,
    other_reportable_trend13_rank: float | None,
    nonreportable_trend13_rank: float | None,
    noncommercial_flow4_rank: float | None,
    config: dict[str, Any],
) -> tuple[float, list[dict[str, Any]]]:
    if structural_score is None:
        return 0.0, []
    cfg = config["tactical"]
    minimum = float(cfg["minimum_structural_magnitude"])
    if abs(structural_score) < minimum:
        return 0.0, []
    structural_sign = 1.0 if structural_score > 0 else -1.0
    components: list[dict[str, Any]] = []

    def add(label: str, value: float | None, weight: float, invert: bool = False) -> float:
        if value is None:
            return 0.0
        normalized = clamp(float(value), -1.0, 1.0)
        directional_signal = -normalized if invert else normalized
        support = structural_sign * directional_signal
        contribution = float(weight) * support
        components.append({
            "label": label,
            "rank_score": round(normalized, 3),
            "support": round(support, 3),
            "contribution": round(contribution, 3),
        })
        return contribution

    raw = 0.0
    raw += add("Other Reportables 13w trend", other_reportable_trend13_rank, float(cfg["other_reportable_trend13_weight"]), invert=True)
    raw += add("Nonreportable 13w trend", nonreportable_trend13_rank, float(cfg["nonreportable_trend13_weight"]), invert=True)
    raw += add("Non-commercial 4w flow alignment", noncommercial_flow4_rank, float(cfg["noncommercial_flow4_alignment_weight"]))
    return clamp(raw, -float(cfg["modifier_cap"]), float(cfg["modifier_cap"])), components


def preserve_structural_sign(structural_score: float | None, modifier: float) -> float | None:
    if structural_score is None:
        return None
    if abs(structural_score) < 1e-12:
        return 0.0
    sign = 1.0 if structural_score > 0 else -1.0
    magnitude = clamp(abs(structural_score) + float(modifier), 0.01, 1.0)
    return sign * magnitude


def asset_manager_multiplier(percentile: float | None, config: dict[str, Any]) -> tuple[float, str]:
    if percentile is None:
        return 1.0, "Unavailable"
    cfg = config["asset_manager_size"]
    p = clamp(float(percentile), 0.0, 100.0)
    if p <= float(cfg["normal_max_percentile"]):
        return 1.0, "Normal"
    if p <= float(cfg["warning_max_percentile"]):
        return float(cfg["warning_multiplier"]), "Elevated"
    return float(cfg["extreme_multiplier"]), "High"


def macro_state_label(score: float | None, config: dict[str, Any]) -> str:
    if score is None:
        return "Unavailable"
    cfg = config["macro_size"]
    s = clamp(float(score), 0.0, 100.0)
    if s >= float(cfg["strong_risk_on_min"]):
        return "Strong supportive"
    if s >= float(cfg["supportive_min"]):
        return "Supportive"
    if s >= float(cfg["neutral_min"]):
        return "Neutral"
    if s >= float(cfg["defensive_min"]):
        return "Defensive"
    return "Risk-off"


def macro_multiplier(score: float | None, config: dict[str, Any]) -> tuple[float, str]:
    return 1.0, macro_state_label(score, config)


def execution_state(
    market: str,
    structural_score: float | None,
    signal_price: float | None,
    latest_price: float | None,
    config: dict[str, Any],
) -> tuple[str, float, float | None]:
    if structural_score is None or abs(structural_score) < 1e-12:
        return "No structural signal", 0.0, None
    signal = finite(signal_price)
    latest = finite(latest_price)
    if signal is None or latest is None or signal <= 0 or latest <= 0:
        return "Unavailable", 0.0, None
    change_pct = (latest / signal - 1.0) * 100.0
    signed_change = change_pct if structural_score > 0 else -change_pct
    cfg = config["execution"]
    invalidation = float(cfg["nq_invalidation_pct"] if market == "nq" else cfg["sp500_invalidation_pct"])
    waiting_band = float(cfg["waiting_band_pct"])
    if signed_change <= -invalidation:
        return "Invalidated", float(cfg["invalidated_multiplier"]), change_pct
    if signed_change > waiting_band:
        return "Confirmed", float(cfg["confirmed_multiplier"]), change_pct
    if signed_change < -waiting_band:
        return "Contradicted", float(cfg["contradicted_multiplier"]), change_pct
    return "Waiting", float(cfg["waiting_multiplier"]), change_pct


def confidence_score(
    market: str,
    structural_score: float | None,
    has_tff: bool,
    has_price: bool,
    release_date_source: str,
    config: dict[str, Any],
    has_macro: bool | None = None,
) -> float:
    cfg = config["confidence"]
    base = float(cfg["nq_structural_base"] if market == "nq" else cfg["sp500_structural_base"])
    magnitude = abs(float(structural_score or 0.0))
    score = base * (0.55 + 0.45 * magnitude)
    if not has_tff:
        score -= float(cfg["missing_tff_penalty"])
    if not has_price:
        score -= float(cfg["missing_price_penalty"])
    if release_date_source != "actual":
        score -= float(cfg["scheduled_release_assumption_penalty"])
    return clamp(score, 0.0, 1.0)


def confidence_label(value: float) -> str:
    if value >= 0.75:
        return "High"
    if value >= 0.55:
        return "Medium"
    if value >= 0.40:
        return "Low"
    return "Weak"


def final_action(
    adjusted_cot_score: float | None,
    execution: str,
    final_exposure: float,
    confidence: float,
    macro_override: bool,
    config: dict[str, Any],
) -> str:
    if macro_override:
        return "Hedge / Risk Override"
    if adjusted_cot_score is None or abs(adjusted_cot_score) < 0.25:
        return "No COT Trade"
    side = "Long" if adjusted_cot_score > 0 else "Short"
    if execution in {"Invalidated", "Unavailable"}:
        return "No Trade"
    if execution in {"Waiting", "Contradicted"}:
        return f"Wait for {side}"
    if confidence < float(config["confidence"]["minimum_actionable"]):
        return f"Wait for {side}"
    if final_exposure >= 0.65:
        return f"Strong {side}"
    if final_exposure >= 0.20:
        return f"{side} — Reduced Size"
    return f"Wait for {side}"


@dataclass
class DirectionDecision:
    model_version: str
    market: str
    report_date: str
    scheduled_release_date: str
    actual_release_date: str
    release_date_source: str
    signal_price_date: str | None
    latest_price_date: str | None
    structural_bias: str
    structural_score: float | None
    noncommercial_percentile: float | None
    tactical_modifier: float
    adjusted_cot_score: float | None
    asset_manager_percentile: float | None
    asset_manager_state: str
    asset_manager_multiplier: float
    macro_score: float | None
    macro_state: str
    macro_multiplier: float
    macro_directional_weight: float
    macro_risk_budget_multiplier: float
    macro_risk_budget_state: str
    macro_directional_edges_status: str
    macro_override: bool
    execution_state: str
    price_change_since_release_pct: float | None
    execution_multiplier: float
    exposure_multiplier: float
    confidence_score: float
    confidence_label: str
    final_action: str
    reasons: list[str]
    tactical_components: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def structural_bias_label(score: float | None) -> str:
    if score is None:
        return "Unavailable"
    if score >= 0.70:
        return "Strong bullish"
    if score >= 0.25:
        return "Bullish"
    if score <= -0.70:
        return "Strong bearish"
    if score <= -0.25:
        return "Bearish"
    return "Neutral"


def _macro_context_score(
    macro_context: dict[str, Any] | None,
    fallback: float | None,
) -> float | None:
    if isinstance(macro_context, dict):
        for key in ("effective_score", "observed_score", "macro_regime_score"):
            value = finite(macro_context.get(key))
            if value is not None:
                return clamp(value, 0.0, 100.0)
    value = finite(fallback)
    return clamp(value, 0.0, 100.0) if value is not None else None


def _macro_risk_budget(
    macro_risk_budget: dict[str, Any] | None,
    macro_override: bool,
) -> tuple[float, str, bool]:
    budget = macro_risk_budget if isinstance(macro_risk_budget, dict) else {}
    multiplier = finite(budget.get("multiplier"))
    if multiplier is None:
        multiplier = 1.0
    multiplier = clamp(multiplier, 0.0, 1.25)
    cap = finite(budget.get("exposure_cap"))
    if cap is not None:
        multiplier = min(multiplier, clamp(cap, 0.0, 1.25))
    state = str(budget.get("status") or "NEUTRAL")
    override = bool(macro_override or budget.get("hard_override_applied"))
    if override:
        multiplier = 0.0
        if state == "NEUTRAL":
            state = "HARD_OVERRIDE"
    return multiplier, state, override


def build_decision(
    *,
    market: str,
    report_date: str,
    actual_release_date: str,
    release_date_source: str,
    signal_price_date: str | None,
    latest_price_date: str | None,
    signal_price: float | None,
    latest_price: float | None,
    noncommercial_percentile: float | None,
    other_reportable_trend13_rank: float | None,
    nonreportable_trend13_rank: float | None,
    noncommercial_flow4_rank: float | None,
    asset_manager_percentile_value: float | None,
    macro_context: dict[str, Any] | None = None,
    macro_risk_budget: dict[str, Any] | None = None,
    macro_directional_edges: dict[str, Any] | None = None,
    macro_score_value: float | None = None,
    macro_override: bool = False,
    config: dict[str, Any] | None = None,
) -> DirectionDecision:
    cfg = config or load_config()
    structural = structural_score_from_percentile(noncommercial_percentile, cfg)
    tactical, components = tactical_modifier(
        structural,
        other_reportable_trend13_rank,
        nonreportable_trend13_rank,
        noncommercial_flow4_rank,
        cfg,
    )
    adjusted = preserve_structural_sign(structural, tactical)
    am_mult, am_state = asset_manager_multiplier(asset_manager_percentile_value, cfg)

    context_score = _macro_context_score(macro_context, macro_score_value)
    macro_mult, macro_state = macro_multiplier(context_score, cfg)
    risk_mult, risk_state, effective_override = _macro_risk_budget(macro_risk_budget, macro_override)
    edges = macro_directional_edges if isinstance(macro_directional_edges, dict) else {}
    edges_status = str(edges.get("status") or "RESEARCH_ONLY_NOT_VINTAGE_SAFE")

    execution, execution_mult, price_change = execution_state(
        market, adjusted, signal_price, latest_price, cfg
    )
    exposure = clamp(
        abs(float(adjusted or 0.0)) * am_mult * risk_mult * execution_mult,
        0.0,
        1.25,
    )
    confidence = confidence_score(
        market,
        structural,
        has_tff=any(
            value is not None
            for value in (
                asset_manager_percentile_value,
                other_reportable_trend13_rank,
                nonreportable_trend13_rank,
            )
        ),
        has_price=finite(signal_price) is not None and finite(latest_price) is not None,
        release_date_source=release_date_source,
        config=cfg,
    )
    action = final_action(
        adjusted, execution, exposure, confidence, effective_override, cfg
    )

    tactical_reason = (
        f"Tactical modifier {tactical:+.2f}"
        if components
        else "Tactical layer inactive because Legacy structure is neutral/weak or TFF inputs are unavailable"
    )
    reasons = [
        f"Legacy Non-commercial percentile {noncommercial_percentile:.1f}%"
        if noncommercial_percentile is not None
        else "Legacy Non-commercial percentile unavailable",
        tactical_reason,
        f"Asset Manager crowding {am_state}; COT-side size x{am_mult:.2f}",
        f"Macro context {macro_state}; aggregate directional weight 0.00 and multiplier x{macro_mult:.2f}",
        f"Macro risk budget {risk_state}; exposure cap x{risk_mult:.2f}",
        f"Macro directional edges {edges_status}; production weight 0.00",
        f"Price execution {execution}",
    ]

    return DirectionDecision(
        model_version=str(cfg["model_version"]),
        market=market,
        report_date=report_date,
        scheduled_release_date=scheduled_release_date(report_date).isoformat(),
        actual_release_date=actual_release_date,
        release_date_source=release_date_source,
        signal_price_date=signal_price_date,
        latest_price_date=latest_price_date,
        structural_bias=structural_bias_label(structural),
        structural_score=round(structural, 4) if structural is not None else None,
        noncommercial_percentile=round(noncommercial_percentile, 2) if noncommercial_percentile is not None else None,
        tactical_modifier=round(tactical, 4),
        adjusted_cot_score=round(adjusted, 4) if adjusted is not None else None,
        asset_manager_percentile=round(asset_manager_percentile_value, 2) if asset_manager_percentile_value is not None else None,
        asset_manager_state=am_state,
        asset_manager_multiplier=round(am_mult, 3),
        macro_score=round(context_score, 2) if context_score is not None else None,
        macro_state=macro_state,
        macro_multiplier=1.0,
        macro_directional_weight=0.0,
        macro_risk_budget_multiplier=round(risk_mult, 3),
        macro_risk_budget_state=risk_state,
        macro_directional_edges_status=edges_status,
        macro_override=effective_override,
        execution_state=execution,
        price_change_since_release_pct=round(price_change, 3) if price_change is not None else None,
        execution_multiplier=round(execution_mult, 3),
        exposure_multiplier=round(exposure, 3),
        confidence_score=round(confidence, 3),
        confidence_label=confidence_label(confidence),
        final_action=action,
        reasons=reasons,
        tactical_components=components,
    )
