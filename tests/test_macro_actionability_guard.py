from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from macro_actionability_guard import apply_macro_actionability_guard  # noqa: E402


class MacroActionabilityGuardTests(unittest.TestCase):
    def base_decision(self) -> dict:
        return {
            "market": "nq",
            "market_label": "NASDAQ-100",
            "release_status": "current",
            "final_action": "Strong Long",
            "exposure_multiplier": 0.8,
            "macro_override": False,
            "reasons": [],
        }

    def test_insufficient_fresh_macro_coverage_blocks_trade(self):
        context = {
            "availability_ratio": 0.45,
            "reliable_for_action": False,
            "hard_override_suppressed_by_freshness": False,
        }
        row = apply_macro_actionability_guard([self.base_decision()], context)[0]
        self.assertEqual(row["final_action"], "Wait — Macro Data Incomplete")
        self.assertEqual(row["exposure_multiplier"], 0.0)
        self.assertEqual(row["pre_macro_quality_action"], "Strong Long")

    def test_reliable_macro_coverage_preserves_action(self):
        context = {
            "availability_ratio": 0.80,
            "reliable_for_action": True,
            "hard_override_suppressed_by_freshness": False,
        }
        row = apply_macro_actionability_guard([self.base_decision()], context)[0]
        self.assertEqual(row["final_action"], "Strong Long")
        self.assertEqual(row["exposure_multiplier"], 0.8)

    def test_delayed_release_has_priority_over_macro_data_guard(self):
        decision = self.base_decision()
        decision["release_status"] = "delayed"
        decision["final_action"] = "Hold Prior Signal — CFTC Report Delayed"
        context = {"availability_ratio": 0.10, "reliable_for_action": False}
        row = apply_macro_actionability_guard([decision], context)[0]
        self.assertEqual(row["final_action"], "Hold Prior Signal — CFTC Report Delayed")

    def test_stale_alert_override_is_suppressed_and_explained(self):
        context = {
            "availability_ratio": 0.30,
            "reliable_for_action": False,
            "hard_override_suppressed_by_freshness": True,
        }
        row = apply_macro_actionability_guard([self.base_decision()], context)[0]
        self.assertFalse(row["macro_override"])
        self.assertTrue(any("not allowed to trigger" in reason for reason in row["reasons"]))


if __name__ == "__main__":
    unittest.main()
