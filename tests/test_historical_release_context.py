from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cot_direction_model import load_config  # noqa: E402
from enrich_directional_history_context import (  # noqa: E402
    enrich_history,
    historical_price_multiplier,
    historical_red_alert_count,
)


class HistoricalReleaseContextTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = load_config(ROOT / "config" / "cot_direction_model_v1.json")

    def test_red_alert_thresholds_match_live_macro_rules(self):
        previous = pd.Series({"liquidity_score": 50})
        current = pd.Series({
            "liquidity_score": 40,
            "net_liquidity_4w_change": -200,
            "bank_reserves_4w_change": -250,
            "sofr_iorb_spread": 0.15,
            "hy_oas_4w_change": 0.70,
        })
        count, alerts = historical_red_alert_count(current, previous)
        self.assertEqual(count, 5)
        self.assertIn("Score crossed below 45", alerts)
        self.assertIn("Repo funding pressure", alerts)

    def test_price_trend_is_interpreted_relative_to_cot_side(self):
        bullish = historical_price_multiplier(0.8, 2.0, "nq", self.config)
        bearish = historical_price_multiplier(-0.8, -2.0, "nq", self.config)
        contradicted = historical_price_multiplier(-0.8, 2.0, "nq", self.config)
        self.assertEqual(bullish, (1.0, "Trend confirmed"))
        self.assertEqual(bearish, (1.0, "Trend confirmed"))
        self.assertEqual(contradicted, (0.25, "Trend contradicted"))

    def test_macro_alignment_never_uses_future_record(self):
        history = pd.DataFrame([{
            "market": "nq",
            "report_date": "2026-07-07",
            "signal_price_date": "2026-07-10",
            "adjusted_cot_score": 0.8,
            "asset_manager_percentile": 50.0,
        }])
        macro = pd.DataFrame([
            {
                "date": pd.Timestamp("2026-07-09"),
                "liquidity_score": 60.0,
                "net_liquidity_4w_change": 0.0,
                "bank_reserves_4w_change": 0.0,
                "sofr_iorb_spread": 0.0,
                "hy_oas_4w_change": 0.0,
            },
            {
                "date": pd.Timestamp("2026-07-11"),
                "liquidity_score": 10.0,
                "net_liquidity_4w_change": -300.0,
                "bank_reserves_4w_change": -300.0,
                "sofr_iorb_spread": 0.20,
                "hy_oas_4w_change": 1.0,
            },
        ])
        prices = pd.DataFrame({
            "date": pd.bdate_range(end="2026-07-10", periods=40),
            "price": np.linspace(100.0, 110.0, 40),
        })
        with patch("enrich_directional_history_context.read_prices", return_value=prices):
            row = enrich_history(history, macro, self.config).iloc[0]
        self.assertEqual(pd.Timestamp(row["historical_macro_date"]).date().isoformat(), "2026-07-09")
        self.assertEqual(row["historical_macro_score"], 60.0)
        self.assertFalse(bool(row["historical_macro_override"]))
        self.assertGreater(row["release_decision_score"], 0)

    def test_two_red_alerts_block_release_decision_score(self):
        history = pd.DataFrame([{
            "market": "sp500",
            "report_date": "2026-07-07",
            "signal_price_date": "2026-07-10",
            "adjusted_cot_score": 0.8,
            "asset_manager_percentile": 50.0,
        }])
        macro = pd.DataFrame([
            {
                "date": pd.Timestamp("2026-07-09"),
                "liquidity_score": 50.0,
                "net_liquidity_4w_change": 0.0,
                "bank_reserves_4w_change": 0.0,
                "sofr_iorb_spread": 0.0,
                "hy_oas_4w_change": 0.0,
            },
            {
                "date": pd.Timestamp("2026-07-10"),
                "liquidity_score": 35.0,
                "net_liquidity_4w_change": -200.0,
                "bank_reserves_4w_change": -250.0,
                "sofr_iorb_spread": 0.0,
                "hy_oas_4w_change": 0.0,
            },
        ])
        prices = pd.DataFrame({
            "date": pd.bdate_range(end="2026-07-10", periods=40),
            "price": np.linspace(100.0, 110.0, 40),
        })
        with patch("enrich_directional_history_context.read_prices", return_value=prices):
            row = enrich_history(history, macro, self.config).iloc[0]
        self.assertTrue(bool(row["historical_macro_override"]))
        self.assertGreaterEqual(row["historical_red_alert_count"], 2)
        self.assertEqual(row["release_decision_score"], 0.0)


if __name__ == "__main__":
    unittest.main()
