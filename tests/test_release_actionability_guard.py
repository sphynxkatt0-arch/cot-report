from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from release_actionability_guard import apply_release_guard  # noqa: E402


class ReleaseActionabilityGuardTests(unittest.TestCase):
    def base_decision(self) -> dict:
        return {
            "market": "nq",
            "market_label": "NASDAQ-100",
            "release_status": "current",
            "final_action": "Strong Long",
            "exposure_multiplier": 0.8,
            "new_signal_available": True,
            "first_observed_utc": "2026-07-31T20:00:00+00:00",
            "expected_report_date": "2026-07-28",
            "expected_gap_weeks": 1,
            "reasons": [],
        }

    def test_catch_up_report_is_visible_but_not_actionable(self):
        decision = self.base_decision()
        decision["release_status"] = "catch_up_delayed"
        row = apply_release_guard([decision])[0]
        self.assertEqual(row["final_action"], "Wait — CFTC Catch-Up Still Behind")
        self.assertEqual(row["exposure_multiplier"], 0.0)
        self.assertFalse(row["new_signal_available"])
        self.assertTrue(row["new_report_observed"])
        self.assertEqual(row["pre_release_quality_action"], "Strong Long")

    def test_unchanged_delayed_report_holds_prior_signal(self):
        decision = self.base_decision()
        decision["release_status"] = "delayed"
        decision["first_observed_utc"] = None
        row = apply_release_guard([decision])[0]
        self.assertEqual(row["final_action"], "Hold Prior Signal — CFTC Report Delayed")
        self.assertEqual(row["exposure_multiplier"], 0.0)
        self.assertFalse(row["new_signal_available"])
        self.assertFalse(row["new_report_observed"])

    def test_awaiting_release_holds_prior_signal(self):
        decision = self.base_decision()
        decision["release_status"] = "awaiting_release"
        row = apply_release_guard([decision])[0]
        self.assertEqual(row["final_action"], "Hold Prior Signal — Awaiting Friday Release")
        self.assertEqual(row["exposure_multiplier"], 0.0)

    def test_current_release_preserves_action(self):
        row = apply_release_guard([self.base_decision()])[0]
        self.assertEqual(row["final_action"], "Strong Long")
        self.assertEqual(row["exposure_multiplier"], 0.8)
        self.assertTrue(row["new_signal_available"])


if __name__ == "__main__":
    unittest.main()
