#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

ANALYSIS = Path(__file__).resolve().parent
LIVE = ANALYSIS / "live"
if str(LIVE) not in sys.path:
    sys.path.insert(0, str(LIVE))

from append_ledger_manifest import append as append_manifest
from apply_live_forecasts import apply as apply_forecasts
from generate_live_forecasts import build_forecast
from ledger import (
    HORIZONS,
    LedgerError,
    atomic_write_json,
    canonical_json_bytes,
    deterministic_signal_id,
    forecast_relative_path,
    sha256_file,
    validate_forecast,
    validate_manifest_chain,
    within_forecast_window,
    write_immutable_forecast,
)


class LiveLedgerTests(unittest.TestCase):
    model_hash = "a" * 64

    def fixture_forecast(self) -> dict:
        current = {
            "report_date": "2026-08-11",
            "release_target_date": "2026-08-14",
            "cot_score": 64.25,
            "cot_score_delta_4w": 4.5,
            "extreme_count": 2,
            "macro_score": 57.0,
            "cot_state": "bullish",
            "macro_state": "neutral",
            "transmission_state": "supportive",
            "combined_state": "bullish COT / neutral macro",
        }
        horizon_template = {
            "mean_return_pct": 1.25,
            "median_return_pct": 0.9,
            "hit_rate_pct": 62.5,
            "max_drawdown_pct": -4.2,
            "observations": 40,
            "confidence": "High",
        }
        family = {
            "sample_size": 40,
            "horizons": {key: dict(horizon_template) for key in HORIZONS},
        }
        forecast = build_forecast(
            market="nq",
            dataset="tff",
            family="combined",
            dataset_payload={"current": current},
            family_payload=family,
            model_version="1.0.0",
            model_spec_hash=self.model_hash,
            input_manifest_hash="b" * 64,
            input_artifacts={"worldclass/base.json": "c" * 64},
            research_artifact_hash="d" * 64,
            research_artifacts={"worldclass/regime_backtest.json": "e" * 64},
        )
        return forecast

    def test_signal_id_is_deterministic_and_versioned(self) -> None:
        args = ("2026-08-11", "nq", "tff", "combined", "1.0.0", self.model_hash)
        first = deterministic_signal_id(*args)
        second = deterministic_signal_id(*args)
        changed = deterministic_signal_id("2026-08-11", "nq", "tff", "combined", "1.0.1", self.model_hash)
        self.assertEqual(first, second)
        self.assertNotEqual(first, changed)
        self.assertEqual(len(first), 64)

    def test_release_window_is_dst_safe_and_rejects_retroactive_generation(self) -> None:
        self.assertTrue(within_forecast_window(datetime(2026, 8, 14, 19, 35, tzinfo=UTC), "2026-08-14"))
        self.assertFalse(within_forecast_window(datetime(2026, 8, 16, 12, 0, tzinfo=UTC), "2026-08-14"))
        # Stockholm is CET in December, so 21:35 local is 20:35 UTC.
        self.assertTrue(within_forecast_window(datetime(2026, 12, 11, 20, 35, tzinfo=UTC), "2026-12-11"))

    def test_forecast_contract_has_no_realized_price_and_is_stable(self) -> None:
        forecast = self.fixture_forecast()
        validate_forecast(forecast)
        self.assertEqual(forecast["created_at_utc"], "2026-08-14T19:35:00Z")
        self.assertNotIn("entry_price", forecast)
        self.assertEqual(forecast["probability_positive_4w"], 0.625)
        self.assertEqual(canonical_json_bytes(forecast), canonical_json_bytes(json.loads(canonical_json_bytes(forecast))))

    def test_apply_is_idempotent_and_refuses_forecast_overwrite(self) -> None:
        forecast = self.fixture_forecast()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            staging = root / "staging"
            ledger_root = root / "ledger"
            relative = forecast_relative_path(forecast)
            staged = staging / relative
            write_immutable_forecast(staged, forecast)
            plan = {
                "model_version": forecast["model_version"],
                "model_spec_hash": forecast["model_spec_hash"],
                "forecasts": [{
                    "signal_id": forecast["signal_id"],
                    "relative_path": str(relative).replace("\\", "/"),
                    "forecast_hash": sha256_file(staged),
                    "created_at_utc": forecast["created_at_utc"],
                }],
            }
            atomic_write_json(staging / "plan.json", plan)
            metadata = root / "append.json"
            first = apply_forecasts(staging, ledger_root, metadata)
            self.assertEqual(first["new_count"], 1)
            frozen = (ledger_root / relative).read_bytes()

            second = apply_forecasts(staging, ledger_root, metadata)
            self.assertEqual(second["new_count"], 0)
            self.assertEqual(second["unchanged_count"], 1)
            self.assertEqual((ledger_root / relative).read_bytes(), frozen)

            changed = dict(forecast)
            changed["cot_score"] = 63.0
            staged.write_bytes(canonical_json_bytes(changed))
            plan["forecasts"][0]["forecast_hash"] = sha256_file(staged)
            atomic_write_json(staging / "plan.json", plan)
            with self.assertRaises(LedgerError):
                apply_forecasts(staging, ledger_root, metadata)
            self.assertEqual((ledger_root / relative).read_bytes(), frozen)

    def test_manifest_chain_detects_tampering(self) -> None:
        forecast = self.fixture_forecast()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            staging = root / "staging"
            ledger_root = root / "ledger"
            relative = forecast_relative_path(forecast)
            staged = staging / relative
            write_immutable_forecast(staged, forecast)
            atomic_write_json(staging / "plan.json", {
                "model_version": forecast["model_version"],
                "model_spec_hash": forecast["model_spec_hash"],
                "forecasts": [{
                    "signal_id": forecast["signal_id"],
                    "relative_path": str(relative).replace("\\", "/"),
                    "forecast_hash": sha256_file(staged),
                    "created_at_utc": forecast["created_at_utc"],
                }],
            })
            metadata = root / "append.json"
            apply_forecasts(staging, ledger_root, metadata)
            appended = append_manifest(ledger_root, metadata, "f" * 40)
            self.assertEqual(appended["created"], 1)
            state = validate_manifest_chain(ledger_root)
            self.assertEqual(state["forecast_count"], 1)
            self.assertEqual(state["manifest_count"], 1)

            path = ledger_root / relative
            path.write_bytes(path.read_bytes() + b" ")
            with self.assertRaises(LedgerError):
                validate_manifest_chain(ledger_root)


if __name__ == "__main__":
    unittest.main()
