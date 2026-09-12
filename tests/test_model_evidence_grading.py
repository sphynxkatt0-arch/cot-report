from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from grade_directional_model_evidence import evidence_grade, grade_rows  # noqa: E402


class ModelEvidenceGradingTests(unittest.TestCase):
    def supported_row(self) -> dict:
        return {
            "score_hac_p": 0.02,
            "score_slope_pp_per_unit": 1.2,
            "edge_hac_p": 0.03,
            "positive_minus_negative": 2.5,
            "subperiod_sign_agreement_pct": 100.0,
            "directional_n": 80,
            "avg_directional_return": 2.0,
            "path_utility": 1.5,
        }

    def test_supported_requires_hac_stability_and_positive_path(self):
        grade, reason = evidence_grade(self.supported_row())
        self.assertEqual(grade, "Supported")
        self.assertIn("positive HAC", reason)

    def test_adverse_sign_is_contradictory(self):
        row = self.supported_row()
        row["positive_minus_negative"] = -2.0
        row["edge_hac_p"] = 0.04
        grade, _ = evidence_grade(row)
        self.assertEqual(grade, "Contradictory")

    def test_unestimable_tests_are_explicit(self):
        row = {
            "score_hac_p": None,
            "score_slope_pp_per_unit": None,
            "edge_hac_p": None,
            "positive_minus_negative": None,
            "subperiod_sign_agreement_pct": None,
            "directional_n": 0,
            "avg_directional_return": None,
            "path_utility": None,
        }
        grade, reason = evidence_grade(row)
        self.assertEqual(grade, "Not estimable")
        self.assertIn("not estimable", reason)

    def test_low_sample_cannot_be_supported(self):
        row = self.supported_row()
        row["directional_n"] = 10
        grade, reason = evidence_grade(row)
        self.assertNotIn(grade, {"Supported", "Tentative"})
        self.assertIn("directional sample", reason)

    def test_grade_rows_sets_consistent_estimability_flags(self):
        graded = grade_rows([self.supported_row()])[0]
        self.assertTrue(graded["score_hac_estimable"])
        self.assertTrue(graded["edge_hac_estimable"])
        self.assertEqual(graded["evidence_grade"], "Supported")
        self.assertTrue(graded["evidence_reason"])


if __name__ == "__main__":
    unittest.main()
