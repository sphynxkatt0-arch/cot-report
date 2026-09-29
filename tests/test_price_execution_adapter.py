from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cot_direction_model import load_config  # noqa: E402
from price_execution_adapter import evaluate_execution  # noqa: E402


class PriceExecutionAdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = load_config(ROOT / "config" / "cot_direction_model_v1.json")

    def test_small_release_gain_does_not_confirm_against_falling_20d_trend(self):
        result = evaluate_execution(
            market="nq",
            adjusted_cot_score=0.8,
            release_change_pct=0.6,
            trend_20d_pct=-1.2,
            trend_65d_pct=2.0,
            config=self.config,
        )
        self.assertEqual(result["state"], "Contradicted")
        self.assertEqual(result["alignment"], "opposed")

    def test_bullish_signal_confirms_when_release_and_20d_trend_align(self):
        result = evaluate_execution(
            market="nq",
            adjusted_cot_score=0.8,
            release_change_pct=0.8,
            trend_20d_pct=1.5,
            trend_65d_pct=-3.0,
            config=self.config,
        )
        self.assertEqual(result["state"], "Confirmed")
        self.assertEqual(result["multiplier"], 1.0)

    def test_bearish_signal_inverts_price_direction(self):
        result = evaluate_execution(
            market="sp500",
            adjusted_cot_score=-0.7,
            release_change_pct=-0.7,
            trend_20d_pct=-1.0,
            trend_65d_pct=4.0,
            config=self.config,
        )
        self.assertEqual(result["state"], "Confirmed")

    def test_large_opposite_move_invalidates(self):
        result = evaluate_execution(
            market="sp500",
            adjusted_cot_score=0.9,
            release_change_pct=-3.5,
            trend_20d_pct=-2.0,
            trend_65d_pct=-5.0,
            config=self.config,
        )
        self.assertEqual(result["state"], "Invalidated")
        self.assertEqual(result["multiplier"], 0.0)


if __name__ == "__main__":
    unittest.main()
