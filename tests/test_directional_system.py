from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from build_directional_cot_system import (  # noqa: E402
    build_history_for_market,
    build_latest_market_decision,
    build_validation_summary,
)
from cot_direction_model import load_config  # noqa: E402


class DirectionalSystemTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = load_config(ROOT / "config" / "cot_direction_model_v1.json")
        dates = pd.date_range(end="2026-07-21", periods=150, freq="W-TUE")
        cls.legacy = pd.DataFrame({
            "date": dates,
            "noncommercial_net_oi_pct": np.linspace(25.0, -25.0, len(dates)),
        })
        cls.tff = pd.DataFrame({
            "date": dates,
            "asset_mgr_net_oi_pct": np.linspace(5.0, 30.0, len(dates)),
            "other_reportable_net_oi_pct": np.sin(np.linspace(0, 8, len(dates))) * 12,
            "non_reportable_net_oi_pct": np.cos(np.linspace(0, 7, len(dates))) * 10,
        })
        price_dates = pd.bdate_range(start=dates.min() - pd.Timedelta(days=7), end="2027-03-31")
        cls.prices = pd.DataFrame({
            "date": price_dates,
            "price": np.linspace(1000.0, 1500.0, len(price_dates)),
        })

    def test_history_uses_release_aligned_prices_and_creates_all_horizons(self):
        history = build_history_for_market("nq", self.legacy, self.tff, self.prices, self.config)
        self.assertEqual(len(history), len(self.legacy))
        actionable = [row for row in history if row["adjusted_cot_score"] is not None]
        self.assertGreater(len(actionable), 10)
        latest = actionable[-1]
        self.assertGreaterEqual(latest["signal_price_date"], latest["scheduled_release_date"])
        self.assertIn("forward_return_1w", latest)
        self.assertIn("forward_return_26w", latest)

    def test_validation_summary_is_generated_per_horizon(self):
        history = build_history_for_market("nq", self.legacy, self.tff, self.prices, self.config)
        summary = build_validation_summary(history)
        self.assertEqual({row["horizon"] for row in summary}, {"1w", "4w", "13w", "26w"})
        self.assertTrue(all(row["status"] == "exploratory_release_aligned" for row in summary))

    def test_latest_decision_blocks_new_signal_when_release_is_delayed(self):
        macro = {
            "macro_regime_score": 50.0,
            "liquidity_plumbing_score": 55.0,
            "market_transmission_score": 45.0,
            "supply_pressure_score": 50.0,
            "availability_ratio": 1.0,
            "hard_override": False,
            "severe_alerts": [],
        }
        delayed = {
            "effective_release_date": "2026-07-17",
            "release_date_source": "scheduled_assumption",
            "release_status": "delayed",
            "expected_report_date": "2026-07-21",
            "scheduled_release_utc": "2026-07-17T19:30:00+00:00",
            "scheduled_release_stockholm": "2026-07-17T21:30:00+02:00",
            "first_observed_utc": None,
            "first_observed_delay_minutes": None,
            "is_delayed": True,
            "is_awaiting_release": False,
        }
        with patch("build_directional_cot_system.observe_report", return_value=None), patch(
            "build_directional_cot_system.resolve_release_state", return_value=delayed
        ), patch(
            "build_directional_cot_system.latest_file", return_value=ROOT / "dummy.csv"
        ):
            decision = build_latest_market_decision(
                "nq", self.legacy, self.tff, self.prices, macro, self.config
            )
        self.assertEqual(decision["final_action"], "Hold Prior Signal — CFTC Report Delayed")
        self.assertFalse(decision["new_signal_available"])
        self.assertLess(decision["confidence_score"], 0.55)


if __name__ == "__main__":
    unittest.main()
