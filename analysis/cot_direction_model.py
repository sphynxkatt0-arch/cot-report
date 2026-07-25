#!/usr/bin/env python3
"""Transparent, release-aligned COT direction model for equity indices.

Legacy Non-commercial positioning determines structural direction. TFF data may
strengthen or weaken conviction but cannot reverse the structural sign. Asset
Manager positioning and macro conditions modify position size. Price action
controls execution.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd


DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent / "config" / "cot_direction_model_v1.json"


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, float(value)))


def finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if np.isfinite(number) else None


def load_config(path: Path | str = DEFAULT_CONFIG_PATH) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def scheduled_release_date(report_date: str | date | pd.Timestamp) -> date:
    """Return the first Friday on or after the COT as-of date."""
    day = pd.Timestamp(report_date).date()
    return day + timedelta(days=(4 - day.weekday()) % 7)


def percentile_rank_prior(history: Iterable[Any], value: Any, minimum: int = 26) -> float | None:
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


def structural_score_from_percentile(percentile: float | None, config: dict[str, Any]) -> float | None:
    """Contrarian equity-index score: low NC percentile is bullish."""
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
        return clamp((low_neutral - p) / max(low_neutral - full_low, 1.0), 0.0, 1.0)
    return -clamp((p - high_neutral) / max(full_high - high_neutral, 1.0), 0.0, 1.0)


def tactical_modifier(
    structural_score: float | None,
    other_reportable_trend13_rank: float | None,
    nonreportable_trend13_rank: float | None,
    noncommercial_flow4_rank: float | None,
    config: dict[str, Any],
) -> tuple[float, list[dict[str, Any]]]:
    """Return a capped conviction modifier, never a standalone direction."""
    if structural_score is None or abs(structural_score) < 1e-12:
        return 0.0, []
    cfg = config["tactical"]
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
    # High OR and small-trader 13w accumulation has historically been a contrarian warning.
    raw += add(
        "Other Reportables 13w trend",
        other_reportable_trend13_rank,
        float(cfg["other_reportable_trend13_weight"]),
        invert=True,
    )
    raw += add(
        "Nonreportable 13w trend",
        nonreportable_trend13_rank,
        float(cfg["nonreportable_trend13_weight"]),
        invert=True,
    )
    raw += add(
        "Non-commercial 4w flow alignment",
        noncommercial_flow4_rank,
        float(cfg["noncommercial_flow4_alignment_weight"]),
        invert=False,
    )
    cap = float(cfg["modifier_cap"])
    return clamp(raw, -cap, cap), components


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
    p = float(percentile)
    if p <= float(cfg["normal_max_percentile"]):
        return 1.0, "Normal"
    if p <= float(cfg["warning_max_percentile"]):
        return float(cfg["warning_multiplier"]), "Elevated"
    return float(cfg["extreme_multiplier"]), "High"


def macro_multiplier(score: float | None, config: dict[str, Any]) -> tuple[float, str]:
    if score is None:
        return 1.0, "Unavailable"
    cfg = config["macro_size"]
    s = float(score)
    if s >= float(cfg["strong_risk_on_min"]):
        return float(cfg["strong_risk_on_multiplier"]), "Strong supportive"
    if s >= float(cfg["supportive_min"]):
        return float(cfg["supportive_multiplier"]), "Supportive"
    if s >= float(cfg["neutral_min"]):
        return float(cfg["neutral_multiplier"]), "Neutral"
    if s >= float(cfg["defensive_min"]):
        return float(cfg["defensive_multiplier"]), "Defensive"
    return float(cfg["risk_off_multiplier"]), "Risk-off"


def execution_state(
    market: str,
    structural_score: float | None,
    signal_price: float | None,
    latest_price: float | None,
    config: dict[str, Any],
) -> tuple[str, float, float | None]:
    if structural_score is None or abs(structural_score) < 1e-12:
        return "No structural signal", 0.0, None
    if signal_price is None or latest_price is None or signal_price == 0:
        return "Unavailable", 0.0, None
    change_pct = (float(latest_price) / float(signal_price) - 1.0) * 100.0
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
    has_macro: bool,
    has_price: bool,
    release_date_source: str,
    config: dict[str, Any],
) -> float:
    cfg = config["confidence"]
    base = float(cfg["nq_structural_base"] if market == "nq" else cfg["sp500_structural_base"])
    magnitude = abs(float(structural_score or 0.0))
    score = base * (0.55 + 0.45 * magnitude)
    if not has_tff:
        score -= float(cfg["missing_tff_penalty"])
    if not has_macro:
        score -= float(cfg["missing_macro_penalty"])
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
    if adjusted_cot_score is None or abs(adjusted_cot_score) < 0.25:
        return "No COT Trade"
    side = "Long" if adjusted_cot_score > 0 else "Short"
    if macro_override:
        return "Hedge / Risk Override"
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
    macro_score_value: float | None,
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
    macro_mult, macro_state = macro_multiplier(macro_score_value, cfg)
    execution, execution_mult, price_change = execution_state(
        market, adjusted, signal_price, latest_price, cfg
    )
    exposure = abs(float(adjusted or 0.0)) * am_mult * macro_mult * execution_mult
    confidence = confidence_score(
        market,
        structural,
        has_tff=asset_manager_percentile_value is not None or other_reportable_trend13_rank is not None,
        has_macro=macro_score_value is not None,
        has_price=signal_price is not None and latest_price is not None,
        release_date_source=release_date_source,
        config=cfg,
    )
    action = final_action(adjusted, execution, exposure, confidence, macro_override, cfg)
    reasons = [
        f"Legacy Non-commercial percentile {noncommercial_percentile:.1f}%" if noncommercial_percentile is not None else "Legacy Non-commercial percentile unavailable",
        f"Tactical modifier {tactical:+.2f}",
        f"Asset Manager crowding {am_state}; size x{am_mult:.2f}",
        f"Macro {macro_state}; size x{macro_mult:.2f}",
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
        macro_score=round(macro_score_value, 2) if macro_score_value is not None else None,
        macro_state=macro_state,
        macro_multiplier=round(macro_mult, 3),
        macro_override=bool(macro_override),
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
