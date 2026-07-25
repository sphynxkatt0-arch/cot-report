from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cot_direction_model import (  # noqa: E402
    asset_manager_multiplier,
    build_decision,
    load_config,
    preserve_structural_sign,
    scheduled_release_date,
    structural_score_from_percentile,
)


class DirectionModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = load_config(ROOT / "config" / "cot_direction_model_v1.json")

    def test_release_alignment_uses_friday(self):
        self.assertEqual(scheduled_release_date("2026-07-21").isoformat(), "2026-07-24")

    def test_low_noncommercial_percentile_is_bullish(self):
        self.assertGreater(structural_score_from_percentile(5, self.config), 0.9)

    def test_high_noncommercial_percentile_is_bearish(self):
        self.assertLess(structural_score_from_percentile(95, self.config), -0.9)

    def test_tactical_modifier_cannot_reverse_structural_sign(self):
        self.assertGreater(preserve_structural_sign(0.20, -0.25), 0.0)
        self.assertLess(preserve_structural_sign(-0.20, 0.25), 0.0)

    def test_asset_manager_is_size_only(self):
        multiplier, state = asset_manager_multiplier(95, self.config)
        self.assertEqual(state, "High")
        self.assertEqual(multiplier, 0.75)

    def test_bullish_structure_with_crowding_remains_bullish(self):
        decision = build_decision(
            market="nq",
            report_date="2026-07-21",
            actual_release_date="2026-07-24",
            release_date_source="actual",
            signal_price_date="2026-07-24",
            latest_price_date="2026-07-25",
            signal_price=20000,
            latest_price=20200,
            noncommercial_percentile=5,
            other_reportable_trend13_rank=1,
            nonreportable_trend13_rank=1,
            noncommercial_flow4_rank=-1,
            asset_manager_percentile_value=98,
            macro_score_value=40,
            config=self.config,
        )
        self.assertGreater(decision.adjusted_cot_score, 0)
        self.assertIn("Long", decision.final_action)
        self.assertLess(decision.exposure_multiplier, 1)

    def test_macro_override_blocks_execution_not_structural_bias(self):
        decision = build_decision(
            market="sp500",
            report_date="2026-07-21",
            actual_release_date="2026-07-24",
            release_date_source="actual",
            signal_price_date="2026-07-24",
            latest_price_date="2026-07-25",
            signal_price=6000,
            latest_price=6050,
            noncommercial_percentile=5,
            other_reportable_trend13_rank=0,
            nonreportable_trend13_rank=0,
            noncommercial_flow4_rank=0,
            asset_manager_percentile_value=50,
            macro_score_value=20,
            macro_override=True,
            config=self.config,
        )
        self.assertGreater(decision.structural_score, 0)
        self.assertEqual(decision.final_action, "Hedge / Risk Override")


if __name__ == "__main__":
    unittest.main()
