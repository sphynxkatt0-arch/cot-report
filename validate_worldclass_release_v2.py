#!/usr/bin/env python3
"""Release-corrected production validator facade.

Preserves the mature payload/macro/performance checks from
validate_worldclass_release.py while replacing its superseded report+3 and
post-warmup sample-count assumptions. Regime research must also expose
conservative independence diagnostics so overlapping forward windows and
contiguous regime runs are never presented as independent evidence.
"""
from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

import validate_worldclass_release as legacy
from cftc_release_calendar import federal_holiday_observed_dates, release_date, release_record

SIGNAL_FLOORS = {
    ("nq", "tff"): 300,
    ("nq", "legacy"): 300,
    ("sp500", "tff"): 300,
    ("sp500", "legacy"): 300,
    ("gold", "disaggregated"): 300,
    ("silver", "disaggregated"): 300,
}


def expected_as_of_for_week(any_day: date) -> date:
    monday = any_day - timedelta(days=any_day.weekday())
    tuesday = monday + timedelta(days=1)
    holidays: dict[date, Any] = {}
    for year in {tuesday.year - 1, tuesday.year, tuesday.year + 1}:
        holidays.update(federal_holiday_observed_dates(year))
    return monday if tuesday in holidays else tuesday


def expected_cot_report(now: datetime) -> date:
    """Latest normal weekly as-of date whose canonical release is already public."""
    current = now.astimezone(UTC)
    for weeks_back in range(0, 12):
        anchor = current.date() - timedelta(days=7 * weeks_back)
        report = expected_as_of_for_week(anchor)
        record = release_record(report)
        available = datetime.fromisoformat(
            str(record["availability_at_utc"]).replace("Z", "+00:00")
        ).astimezone(UTC)
        if available <= current:
            return report
    raise AssertionError("could not resolve expected CFTC report in prior 12 weeks")


def validate_regime_independence(
    market: str,
    dataset: str,
    payload: dict[str, Any],
) -> None:
    families = payload.get("families") or {}
    assert all(key in families for key in ("cot", "macro", "combined")), (
        f"{market}/{dataset}: model families missing"
    )
    for family_name, family in families.items():
        if not isinstance(family, dict):
            continue
        episode_n = family.get("regime_episode_n")
        assert episode_n is not None and int(episode_n) >= 0, (
            f"{market}/{dataset}/{family_name}: regime_episode_n missing"
        )
        effective_map = family.get("effective_n") or {}
        non_overlap_map = family.get("non_overlapping_sample_n") or {}
        horizons = family.get("horizons") or {}
        assert horizons, f"{market}/{dataset}/{family_name}: horizon summaries missing"
        for horizon, summary in horizons.items():
            observations = int(summary.get("observations") or 0)
            effective_n = summary.get("effective_n")
            non_overlapping_n = summary.get("non_overlapping_n")
            horizon_episode_n = summary.get("regime_episode_n")
            assert effective_n is not None, (
                f"{market}/{dataset}/{family_name}/{horizon}: effective_n missing"
            )
            assert non_overlapping_n is not None, (
                f"{market}/{dataset}/{family_name}/{horizon}: non_overlapping_n missing"
            )
            assert horizon_episode_n is not None, (
                f"{market}/{dataset}/{family_name}/{horizon}: regime_episode_n missing"
            )
            effective_value = int(effective_n)
            non_overlap_value = int(non_overlapping_n)
            episode_value = int(horizon_episode_n)
            assert 0 <= effective_value <= non_overlap_value <= observations, (
                f"{market}/{dataset}/{family_name}/{horizon}: invalid effective/non-overlap N"
            )
            assert effective_value <= episode_value, (
                f"{market}/{dataset}/{family_name}/{horizon}: effective_n exceeds regime episodes"
            )
            assert int(effective_map.get(horizon, -1)) == effective_value, (
                f"{market}/{dataset}/{family_name}/{horizon}: family effective_n mismatch"
            )
            assert int(non_overlap_map.get(horizon, -1)) == non_overlap_value, (
                f"{market}/{dataset}/{family_name}/{horizon}: family non-overlap N mismatch"
            )


def validate_backtests(backtest: dict[str, Any], regime: dict[str, Any]) -> None:
    assert backtest.get("research_generation") == "release-corrected-v2", (
        "standard backtest is not release-corrected v2"
    )
    assert regime.get("research_generation") == "release-corrected-v2", (
        "regime backtest is not release-corrected v2"
    )
    assert backtest.get("markets"), "standard backtest has no markets"
    assert regime.get("markets"), "regime backtest has no markets"
    assert regime.get("macro_vintage_safe") is False, (
        "regime backtest top-level macro vintage safety overstated"
    )
    legacy.validate_model_identity(backtest, "standard backtest")
    legacy.validate_model_identity(regime, "regime backtest")

    for market, market_payload in backtest["markets"].items():
        for dataset, payload in (market_payload.get("datasets") or {}).items():
            method = payload.get("methodology") or {}
            assert method.get("lookahead_safe") is True, (
                f"{market}/{dataset}: COT backtest not lookahead-safe"
            )
            assert method.get("release_calendar_aware") is True, (
                f"{market}/{dataset}: release calendar not enforced"
            )
            legacy.validate_model_identity(payload, f"{market}/{dataset} COT backtest")
            current = payload.get("current") or {}
            score = current.get("score")
            assert score is None or 0 <= float(score) <= 100, (
                f"{market}/{dataset}: score out of bounds"
            )
            report = current.get("report_date")
            release = current.get("release_target_date")
            if report and release:
                assert release == release_date(report).isoformat(), (
                    f"{market}/{dataset}: canonical release mismatch"
                )

    for key, floor in SIGNAL_FLOORS.items():
        market, dataset = key
        payload = (
            (((backtest.get("markets") or {}).get(market) or {}).get("datasets") or {})
            .get(dataset)
        )
        assert isinstance(payload, dict), f"{market}/{dataset}: historical research missing"
        count = int(payload.get("historical_signal_count") or 0)
        assert count >= floor, (
            f"{market}/{dataset}: historical signal count {count} below v2 floor {floor}"
        )

    for market, market_payload in regime["markets"].items():
        for dataset, payload in (market_payload.get("datasets") or {}).items():
            method = payload.get("methodology") or {}
            assert method.get("lookahead_safe_cot") is True, (
                f"{market}/{dataset}: regime COT timing unsafe"
            )
            assert method.get("release_calendar_aware") is True, (
                f"{market}/{dataset}: regime release calendar missing"
            )
            assert method.get("macro_vintage_safe") is False, (
                f"{market}/{dataset}: macro vintage safety overstated"
            )
            assert method.get("sample_independence_policy"), (
                f"{market}/{dataset}: sample independence policy missing"
            )
            legacy.validate_model_identity(payload, f"{market}/{dataset} regime backtest")
            current = payload.get("current") or {}
            report = current.get("report_date")
            release = current.get("release_target_date")
            if report and release:
                assert release == release_date(report).isoformat(), (
                    f"{market}/{dataset}: regime canonical release mismatch"
                )
            for field in ("cot_score", "macro_score"):
                value = current.get(field)
                assert value is None or 0 <= float(value) <= 100, (
                    f"{market}/{dataset}: {field} out of bounds"
                )
            validate_regime_independence(market, dataset, payload)


def main() -> None:
    old_expected = legacy.expected_cot_report
    old_backtests = legacy.validate_backtests
    legacy.expected_cot_report = expected_cot_report
    legacy.validate_backtests = validate_backtests
    try:
        legacy.main()
    finally:
        legacy.expected_cot_report = old_expected
        legacy.validate_backtests = old_backtests


if __name__ == "__main__":
    main()
