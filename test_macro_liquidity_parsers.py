#!/usr/bin/env python3
"""Offline regression tests for macro-liquidity source parsing contracts."""
from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import patch

import macro_liquidity_expansion as macro
from treasury_cash_flow_extension import operating_cash_result


def test_series_points_bare_timeseries() -> None:
    payload = [["2026-08-05", 3.62], ["2026-08-06", None], ["2026-08-07", 3.64]]
    assert macro.series_points(payload, "REPO-DVP_AR_OO-P") == [
        ("2026-08-05", 3.62),
        ("2026-08-07", 3.64),
    ]


def test_series_points_casefolded_full_payload() -> None:
    payload = {
        "REPO-TRI_AR_OO-P": {
            "timeseries": {
                "aggregation": [["2026-08-05", 3.61], ["2026-08-06", 3.63]],
                "disclosure_edits": [],
            }
        }
    }
    assert macro.series_points(payload, "repo-tri_ar_oo-p") == [
        ("2026-08-05", 3.61),
        ("2026-08-06", 3.63),
    ]


def test_fetch_indicator_scales_raw_dollars() -> None:
    spec = {
        "key": "dealer_treasury_fails",
        "label": "Dealer Treasury settlement fails",
        "dataset": "nypd",
        "unit": "USD mn",
        "scale_divisor": 1_000_000,
        "preferred_mnemonics": ["NYPD-PD_AFtD_T-A"],
        "stale_after_days": 12,
        "short_observations": 1,
        "medium_observations": 2,
        "history_days": 30,
    }
    raw = [
        ["2026-08-05", 100_000_000_000],
        ["2026-08-06", 103_000_000_000],
        ["2026-08-07", 105_000_000_000],
    ]
    with patch.object(macro, "request_json", return_value=raw):
        result = macro.fetch_indicator(spec, now=datetime(2026, 8, 8, tzinfo=UTC))
    assert result.status == "fresh"
    assert result.latest_value == 105_000.0
    assert result.change_short == 2_000.0
    assert result.unit == "USD mn"


def test_tga_closing_balance_wins_regardless_of_row_order() -> None:
    rows = [
        {
            "record_date": "2026-08-06",
            "account_type": "Treasury General Account (TGA) Closing Balance",
            "open_today_bal": "920000",
        },
        {
            "record_date": "2026-08-06",
            "account_type": "Treasury General Account (TGA) Opening Balance",
            "open_today_bal": "880000",
        },
        {
            "record_date": "2026-08-07",
            "account_type": "Treasury General Account (TGA) Opening Balance",
            "open_today_bal": "910000",
        },
        {
            "record_date": "2026-08-07",
            "account_type": "Treasury General Account (TGA) Closing Balance",
            "open_today_bal": "940000",
        },
    ]
    result, context = operating_cash_result(rows, datetime(2026, 8, 8, tzinfo=UTC))
    assert result.status == "fresh"
    assert context["latest_operating_cash_bn"] == 940.0
    assert context["operating_cash_change_5d_bn"] == 20.0


def main() -> None:
    tests = [
        test_series_points_bare_timeseries,
        test_series_points_casefolded_full_payload,
        test_fetch_indicator_scales_raw_dollars,
        test_tga_closing_balance_wins_regardless_of_row_order,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"Macro parser regression suite PASS ({len(tests)} tests)")


if __name__ == "__main__":
    main()
