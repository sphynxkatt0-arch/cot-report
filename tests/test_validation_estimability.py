from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from validate_directional_outputs_v11 import validate_release_evidence  # noqa: E402


class ValidationEstimabilityTests(unittest.TestCase):
    def base_row(self) -> dict[str, str]:
        return {
            "market": "nq",
            "horizon": "13w",
            "model": "new_release_decision",
            "evidence_grade": "Not estimable",
            "evidence_reason": "insufficient score variation",
            "score_hac_estimable": "False",
            "edge_hac_estimable": "False",
            "score_hac_p": "",
            "score_slope_pp_per_unit": "",
            "edge_hac_p": "",
            "positive_minus_negative": "",
            "stability_subperiods": "0",
            "subperiod_sign_agreement_pct": "",
            "drift_adjusted_n": "0",
            "drift_adjusted_accuracy_pct": "",
            "directional_n": "0",
            "avg_directional_return": "",
            "avg_adverse_move": "",
            "worst_adverse_move": "",
            "path_utility": "",
        }

    def test_not_estimable_row_is_valid_without_fabricated_statistics(self):
        failures: list[str] = []
        validate_release_evidence(self.base_row(), failures)
        self.assertEqual(failures, [])

    def test_estimable_hac_requires_finite_slope_and_p_value(self):
        row = self.base_row()
        row["evidence_grade"] = "Weak/Mixed"
        row["score_hac_estimable"] = "True"
        failures: list[str] = []
        validate_release_evidence(row, failures)
        self.assertTrue(any("score HAC marked estimable" in failure for failure in failures))

    def test_supported_evidence_requires_directional_sample(self):
        row = self.base_row()
        row.update(
            {
                "evidence_grade": "Supported",
                "score_hac_estimable": "True",
                "edge_hac_estimable": "True",
                "score_hac_p": "0.01",
                "score_slope_pp_per_unit": "1.2",
                "edge_hac_p": "0.02",
                "positive_minus_negative": "2.5",
                "stability_subperiods": "3",
                "subperiod_sign_agreement_pct": "100",
            }
        )
        failures: list[str] = []
        validate_release_evidence(row, failures)
        self.assertTrue(any("directional sample" in failure for failure in failures))

    def test_estimable_directional_path_requires_complete_metrics(self):
        row = self.base_row()
        row.update(
            {
                "evidence_grade": "Weak/Mixed",
                "directional_n": "25",
                "avg_directional_return": "1.1",
                "avg_adverse_move": "",
                "worst_adverse_move": "-4.0",
                "path_utility": "0.5",
            }
        )
        failures: list[str] = []
        validate_release_evidence(row, failures)
        self.assertTrue(any("avg_adverse_move" in failure for failure in failures))


if __name__ == "__main__":
    unittest.main()
