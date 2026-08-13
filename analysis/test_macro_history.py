#!/usr/bin/env python3
"""Regression tests for canonical macro-history contracts."""
from __future__ import annotations

import json
import sys
import tempfile
import types
from pathlib import Path

import pandas as pd

import macro_liquidity_expansion_v12 as macro_v12
import refresh_macro_history as macro


def test_merge_preserves_last_good_history() -> None:
    old = [
        {"date": "2026-08-10", "value": 1.0},
        {"date": "2026-08-11", "value": 2.0},
    ]
    new = [
        {"date": "2026-08-11", "value": 2.5},
        {"date": "2026-08-12", "value": 3.0},
    ]
    merged = macro.merge_series_records(old, new)
    assert merged == [
        {"date": "2026-08-10", "value": 1.0},
        {"date": "2026-08-11", "value": 2.5},
        {"date": "2026-08-12", "value": 3.0},
    ]


def test_market_close_enters_next_business_day() -> None:
    frame = pd.DataFrame(
        {"date": pd.to_datetime(["2026-08-07", "2026-08-10"]), "sp500": [100.0, 101.0]}
    )
    shifted = macro.shift_available_dates(frame, "sp500")
    assert shifted["date"].dt.strftime("%Y-%m-%d").tolist() == [
        "2026-08-10",
        "2026-08-11",
    ]


def test_forward_treasury_amount_requires_auction_to_have_occurred() -> None:
    original = macro.dashboard.load_treasury_issuance_frame

    def fake_loader(*_args, **_kwargs):
        return pd.DataFrame(
            {
                "date": pd.to_datetime(["2026-08-14", "2026-08-17"]),
                "auction_date": ["2026-08-11", "2026-08-14"],
                "amount_bn": [50.0, 75.0],
            }
        )

    macro.dashboard.load_treasury_issuance_frame = fake_loader
    try:
        frame = pd.DataFrame({"date": pd.to_datetime(["2026-08-12", "2026-08-13"])})
        out = macro.apply_safe_forward_treasury_supply(frame)
    finally:
        macro.dashboard.load_treasury_issuance_frame = original

    # 8/12 can use the 8/14 issue because its auction happened 8/11.
    # It cannot use the 8/17 issue because that auction has not happened yet.
    assert out["treasury_issuance_next_7d"].tolist() == [50.0, 50.0]


def test_history_validation_rejects_future_rows() -> None:
    today = pd.Timestamp.now(tz="UTC").normalize().tz_localize(None)
    frame = pd.DataFrame(
        {
            "date": [today + pd.Timedelta(days=1)],
            "liquidity_score": [50.0],
            "regime_label": ["Neutral"],
            "net_liquidity": [1.0],
            "bank_reserves": [1.0],
            "hy_oas": [1.0],
            "sp500": [1.0],
            "nasdaq": [1.0],
        }
    )
    try:
        macro.validate_history(frame)
    except AssertionError as exc:
        assert "future" in str(exc)
    else:
        raise AssertionError("future history row should fail validation")


def test_v12_rejects_regressed_canonical_history() -> None:
    original_paths = (
        macro_v12.CANONICAL_MACRO_HISTORY,
        macro_v12.CANONICAL_MACRO_LATEST,
        macro_v12.CANONICAL_MACRO_PROVENANCE,
    )
    original_restore = macro_v12.restore_canonical_from_gh_pages
    original_refresh_module = sys.modules.get("refresh_macro_history")

    with tempfile.TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        macro_v12.CANONICAL_MACRO_HISTORY = root / "macro_history.csv"
        macro_v12.CANONICAL_MACRO_LATEST = root / "macro_history_latest.json"
        macro_v12.CANONICAL_MACRO_PROVENANCE = root / "macro_history_provenance.json"
        macro_v12.restore_canonical_from_gh_pages = lambda: {"restored": []}

        macro_v12.CANONICAL_MACRO_HISTORY.write_text(
            "date,liquidity_score\n2026-08-12,55\n",
            encoding="utf-8",
        )
        macro_v12.CANONICAL_MACRO_LATEST.write_text(
            json.dumps(
                {
                    "generated_at_utc": "before",
                    "lookahead_safe": True,
                    "status": "fresh",
                    "latest": {"date": "2026-08-12", "liquidity_score": 55},
                }
            ),
            encoding="utf-8",
        )
        macro_v12.CANONICAL_MACRO_PROVENANCE.write_text(
            json.dumps({"end_date": "2026-08-12"}),
            encoding="utf-8",
        )

        fake_refresh = types.SimpleNamespace()

        def regress_history() -> None:
            macro_v12.CANONICAL_MACRO_HISTORY.write_text(
                "date,liquidity_score\n2026-08-10,40\n",
                encoding="utf-8",
            )
            macro_v12.CANONICAL_MACRO_LATEST.write_text(
                json.dumps(
                    {
                        "generated_at_utc": "after",
                        "lookahead_safe": True,
                        "status": "fresh",
                        "latest": {"date": "2026-08-10", "liquidity_score": 40},
                    }
                ),
                encoding="utf-8",
            )
            macro_v12.CANONICAL_MACRO_PROVENANCE.write_text(
                json.dumps({"end_date": "2026-08-10"}),
                encoding="utf-8",
            )

        fake_refresh.main = regress_history
        sys.modules["refresh_macro_history"] = fake_refresh
        try:
            result = macro_v12.refresh_canonical_macro_history()
            restored = json.loads(
                macro_v12.CANONICAL_MACRO_LATEST.read_text(encoding="utf-8")
            )
        finally:
            (
                macro_v12.CANONICAL_MACRO_HISTORY,
                macro_v12.CANONICAL_MACRO_LATEST,
                macro_v12.CANONICAL_MACRO_PROVENANCE,
            ) = original_paths
            macro_v12.restore_canonical_from_gh_pages = original_restore
            if original_refresh_module is None:
                sys.modules.pop("refresh_macro_history", None)
            else:
                sys.modules["refresh_macro_history"] = original_refresh_module

    assert result["status"] == "cached_fallback"
    assert restored["latest"]["date"] == "2026-08-12"
    assert "regressed latest date" in str(result.get("error") or "")


def main() -> None:
    test_merge_preserves_last_good_history()
    test_market_close_enters_next_business_day()
    test_forward_treasury_amount_requires_auction_to_have_occurred()
    test_history_validation_rejects_future_rows()
    test_v12_rejects_regressed_canonical_history()
    print("canonical macro history tests PASS")


if __name__ == "__main__":
    main()
