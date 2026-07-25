from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from model_evidence_actionability_guard import (  # noqa: E402
    aggregate_evidence,
    apply_evidence_guard,
)


class ModelEvidenceActionabilityGuardTests(unittest.TestCase):
    def base_decision(self) -> dict:
        return {
            "market": "nq",
            "market_label": "NASDAQ-100",
            "release_status": "current",
            "final_action": "Strong Long",
            "adjusted_cot_score": 0.9,
            "exposure_multiplier": 0.9,
            "reasons": [],
        }

    @staticmethod
    def rows(grades: dict[str, str]) -> list[dict[str, str]]:
        return [
            {
                "market": "nq",
                "model": "new_release_decision",
                "horizon": horizon,
                "evidence_grade": grade,
            }
            for horizon, grade in grades.items()
        ]

    def test_cross_horizon_support_preserves_exposure(self):
        summary = self.rows({"4w": "Supported", "13w": "Supported", "26w": "Tentative"})
        state, _, _ = aggregate_evidence(summary)
        self.assertEqual(state, "Supported")
        row = apply_evidence_guard([self.base_decision()], summary)[0]
        self.assertEqual(row["final_action"], "Strong Long")
        self.assertEqual(row["exposure_multiplier"], 0.9)

    def test_tentative_evidence_caps_and_reduces_strong_action(self):
        summary = self.rows({"4w": "Tentative", "13w": "Weak/Mixed", "26w": "Weak/Mixed"})
        row = apply_evidence_guard([self.base_decision()], summary)[0]
        self.assertEqual(row["historical_evidence_state"], "Tentative")
        self.assertEqual(row["final_action"], "Long — Reduced Size")
        self.assertEqual(row["exposure_multiplier"], 0.75)

    def test_unvalidated_evidence_caps_to_point_35(self):
        summary = self.rows({"4w": "Not estimable", "13w": "Weak/Mixed", "26w": "Not estimable"})
        row = apply_evidence_guard([self.base_decision()], summary)[0]
        self.assertEqual(row["historical_evidence_state"], "Not validated")
        self.assertEqual(row["exposure_multiplier"], 0.35)
        self.assertEqual(row["final_action"], "Long — Reduced Size")

    def test_contradictory_horizon_blocks_exposure_without_reversing_side(self):
        summary = self.rows({"4w": "Contradictory", "13w": "Supported", "26w": "Supported"})
        row = apply_evidence_guard([self.base_decision()], summary)[0]
        self.assertEqual(row["historical_evidence_state"], "Contradictory")
        self.assertEqual(row["exposure_multiplier"], 0.0)
        self.assertEqual(row["final_action"], "Wait for Long — Historical Evidence Conflict")
        self.assertGreater(row["adjusted_cot_score"], 0)

    def test_macro_override_is_not_weakened_by_evidence_guard(self):
        decision = self.base_decision()
        decision["final_action"] = "Hedge / Risk Override"
        decision["exposure_multiplier"] = 0.0
        summary = self.rows({"4w": "Supported", "13w": "Supported", "26w": "Supported"})
        row = apply_evidence_guard([decision], summary)[0]
        self.assertEqual(row["final_action"], "Hedge / Risk Override")
        self.assertEqual(row["exposure_multiplier"], 0.0)

    def test_delayed_release_has_priority(self):
        decision = self.base_decision()
        decision["release_status"] = "delayed"
        decision["final_action"] = "Hold Prior Signal — CFTC Report Delayed"
        summary = self.rows({"4w": "Contradictory", "13w": "Contradictory", "26w": "Contradictory"})
        row = apply_evidence_guard([decision], summary)[0]
        self.assertEqual(row["final_action"], "Hold Prior Signal — CFTC Report Delayed")


if __name__ == "__main__":
    unittest.main()
