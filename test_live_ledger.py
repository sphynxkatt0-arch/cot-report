#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import UTC, date, datetime, timedelta
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
    entry_relative_path,
    forecast_relative_path,
    outcome_relative_path,
    sha256_file,
    validate_forecast,
    validate_ledger,
    validate_manifest_chain,
    within_forecast_window,
    write_immutable_forecast,
)
from settle_live_signals import settle


class LiveLedgerTests(unittest.TestCase):
    model_hash = "a" * 64
    horizon_steps = {"1w": 5, "2w": 10, "4w": 20, "13w": 65, "26w": 130}

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
            "avg_drawdown_pct": -1.8,
            "max_drawdown_pct": -4.2,
            "baseline_return_pct": 0.55,
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
            horizon_steps=self.horizon_steps,
            input_manifest_hash="b" * 64,
            input_artifacts={"worldclass/base.json": "c" * 64},
            research_artifact_hash="d" * 64,
            research_artifacts={"worldclass/regime_backtest.json": "e" * 64},
        )
        return forecast

    def price_source(self, count: int, *, start: date = date(2026, 8, 17)) -> dict:
        rows = []
        day = start
        i = 0
        while len(rows) < count:
            if day.weekday() < 5:
                rows.append({"date": day.isoformat(), "price": 100.0 + i})
                i += 1
            day += timedelta(days=1)
        return {
            "nq": {
                "records": rows,
                "price_source": "synthetic-test",
                "price_source_timestamp": "2026-09-01T22:00:00Z",
            }
        }

    def materialize_forecast(self, root: Path, forecast: dict) -> Path:
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
        applied = apply_forecasts(staging, ledger_root, metadata)
        self.assertEqual(applied["new_count"], 1)
        appended = append_manifest(ledger_root, metadata, "f" * 40)
        self.assertEqual(appended["created"], 1)
        return ledger_root

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

    def test_forecast_contract_has_no_realized_price_and_freezes_horizon_definition(self) -> None:
        forecast = self.fixture_forecast()
        validate_forecast(forecast)
        self.assertEqual(forecast["created_at_utc"], "2026-08-14T19:35:00Z")
        self.assertNotIn("entry_price", forecast)
        self.assertEqual(forecast["probability_positive_4w"], 0.625)
        self.assertEqual(forecast["historical_horizons"]["4w"]["trading_closes"], 20)
        self.assertEqual(forecast["historical_drawdown_expectancy"], -1.8)
        self.assertEqual(forecast["historical_worst_drawdown"], -4.2)
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
            ledger_root = self.materialize_forecast(root, forecast)
            state = validate_manifest_chain(ledger_root)
            self.assertEqual(state["forecast_count"], 1)
            self.assertEqual(state["manifest_count"], 1)

            path = ledger_root / forecast_relative_path(forecast)
            path.write_bytes(path.read_bytes() + b" ")
            with self.assertRaises(LedgerError):
                validate_manifest_chain(ledger_root)

    def test_settlement_is_incremental_and_never_rewrites_matured_horizon(self) -> None:
        forecast = self.fixture_forecast()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ledger_root = self.materialize_forecast(root, forecast)
            signal_id = forecast["signal_id"]

            first = settle(
                ledger_root=ledger_root,
                price_sources=self.price_source(7),
                settled_at_utc=datetime(2026, 8, 25, 22, 0, tzinfo=UTC),
            )
            self.assertEqual(first["created_entry_count"], 1)
            self.assertEqual(first["created_outcome_count"], 1)
            entry = json.loads((ledger_root / entry_relative_path(signal_id)).read_text())
            self.assertEqual(entry["entry_date"], "2026-08-17")
            one_week = ledger_root / outcome_relative_path(signal_id, "1w")
            two_week = ledger_root / outcome_relative_path(signal_id, "2w")
            self.assertTrue(one_week.exists())
            self.assertFalse(two_week.exists())
            one_week_bytes = one_week.read_bytes()
            state = validate_ledger(ledger_root)
            self.assertEqual(state["entry_count"], 1)
            self.assertEqual(state["outcome_count"], 1)

            second = settle(
                ledger_root=ledger_root,
                price_sources=self.price_source(12),
                settled_at_utc=datetime(2026, 9, 1, 22, 0, tzinfo=UTC),
            )
            self.assertEqual(second["created_entry_count"], 0)
            self.assertEqual(second["created_outcome_count"], 1)
            self.assertTrue(two_week.exists())
            self.assertEqual(one_week.read_bytes(), one_week_bytes)
            state = validate_ledger(ledger_root)
            self.assertEqual(state["outcome_count"], 2)

            rerun = settle(
                ledger_root=ledger_root,
                price_sources=self.price_source(12),
                settled_at_utc=datetime(2026, 9, 2, 22, 0, tzinfo=UTC),
            )
            self.assertEqual(rerun["created_entry_count"], 0)
            self.assertEqual(rerun["created_outcome_count"], 0)
            self.assertEqual(one_week.read_bytes(), one_week_bytes)

    def test_settlement_does_not_create_horizon_before_trading_closes_mature(self) -> None:
        forecast = self.fixture_forecast()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ledger_root = self.materialize_forecast(root, forecast)
            signal_id = forecast["signal_id"]
            result = settle(
                ledger_root=ledger_root,
                price_sources=self.price_source(5),
                settled_at_utc=datetime(2026, 8, 21, 22, 0, tzinfo=UTC),
            )
            self.assertEqual(result["created_entry_count"], 1)
            self.assertEqual(result["created_outcome_count"], 0)
            self.assertFalse((ledger_root / outcome_relative_path(signal_id, "1w")).exists())
            validate_ledger(ledger_root)

    def test_outcome_tampering_fails_ledger_validation(self) -> None:
        forecast = self.fixture_forecast()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ledger_root = self.materialize_forecast(root, forecast)
            signal_id = forecast["signal_id"]
            settle(
                ledger_root=ledger_root,
                price_sources=self.price_source(7),
                settled_at_utc=datetime(2026, 8, 25, 22, 0, tzinfo=UTC),
            )
            outcome_path = ledger_root / outcome_relative_path(signal_id, "1w")
            outcome = json.loads(outcome_path.read_text())
            outcome["realized_return_pct"] += 1.0
            outcome_path.write_bytes(canonical_json_bytes(outcome))
            with self.assertRaises(LedgerError):
                validate_ledger(ledger_root)


if __name__ == "__main__":
    unittest.main()
