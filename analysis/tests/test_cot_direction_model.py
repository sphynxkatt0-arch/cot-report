from __future__ import annotations

import copy
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
    tactical_modifier,
    validate_config,
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

    def test_neutral_zone_produces_no_structural_signal(self):
        self.assertEqual(structural_score_from_percentile(50, self.config), 0.0)
        self.assertEqual(structural_score_from_percentile(40, self.config), 0.0)
        self.assertEqual(structural_score_from_percentile(60, self.config), 0.0)

    def test_tactical_modifier_cannot_reverse_structural_sign(self):
        self.assertGreater(preserve_structural_sign(0.20, -0.25), 0.0)
        self.assertLess(preserve_structural_sign(-0.20, 0.25), 0.0)

    def test_weak_structural_signal_cannot_be_promoted_by_tff(self):
        modifier, components = tactical_modifier(0.10, -1.0, -1.0, 1.0, self.config)
        self.assertEqual(modifier, 0.0)
        self.assertEqual(components, [])
        decision = build_decision(
            market="nq",
            report_date="2026-07-21",
            actual_release_date="2026-07-24",
            release_date_source="actual",
            signal_price_date="2026-07-24",
            latest_price_date="2026-07-25",
            signal_price=20000,
            latest_price=20500,
            noncommercial_percentile=37,
            other_reportable_trend13_rank=-1,
            nonreportable_trend13_rank=-1,
            noncommercial_flow4_rank=1,
            asset_manager_percentile_value=50,
            macro_score_value=80,
            config=self.config,
        )
        self.assertLess(abs(decision.adjusted_cot_score), 0.25)
        self.assertEqual(decision.final_action, "No COT Trade")

    def test_contrarian_tactical_signal_is_relative_to_structural_side(self):
        bullish, _ = tactical_modifier(0.8, 1.0, 0.0, 0.0, self.config)
        bearish, _ = tactical_modifier(-0.8, 1.0, 0.0, 0.0, self.config)
        self.assertLess(bullish, 0.0)
        self.assertGreater(bearish, 0.0)

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

    def test_invalid_config_order_is_rejected(self):
        broken = copy.deepcopy(self.config)
        broken["structural"]["neutral_percentile_low"] = 95
        with self.assertRaises(ValueError):
            validate_config(broken)

    def test_invalid_price_does_not_create_execution_signal(self):
        decision = build_decision(
            market="sp500",
            report_date="2026-07-21",
            actual_release_date="2026-07-24",
            release_date_source="actual",
            signal_price_date="2026-07-24",
            latest_price_date="2026-07-25",
            signal_price=-1,
            latest_price=6000,
            noncommercial_percentile=5,
            other_reportable_trend13_rank=0,
            nonreportable_trend13_rank=0,
            noncommercial_flow4_rank=0,
            asset_manager_percentile_value=50,
            macro_score_value=60,
            config=self.config,
        )
        self.assertEqual(decision.execution_state, "Unavailable")
        self.assertEqual(decision.exposure_multiplier, 0.0)


if __name__ == "__main__":
    unittest.main()
