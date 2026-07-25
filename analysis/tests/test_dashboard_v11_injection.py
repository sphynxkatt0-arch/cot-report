from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from inject_directional_dashboard_v11 import START, build_block, inject  # noqa: E402


class DashboardV11InjectionTests(unittest.TestCase):
    def rows(self):
        return [
            {
                "market_label": "S&P 500",
                "final_action": "Long — Reduced Size",
                "structural_bias": "Bullish",
                "execution_state": "Confirmed",
                "structural_score": 0.7,
                "tactical_modifier": 0.1,
                "exposure_multiplier": 0.35,
                "confidence_label": "Medium",
                "report_date": "2026-07-21",
                "release_status": "current",
                "macro_regime_score": 55,
                "historical_evidence_state": "Not validated",
                "historical_evidence_exposure_cap": 0.35,
            },
            {
                "market_label": "NASDAQ-100",
                "final_action": "Wait — CFTC Catch-Up Still Behind",
                "structural_bias": "Bullish",
                "execution_state": "Waiting",
                "structural_score": 0.8,
                "tactical_modifier": -0.1,
                "exposure_multiplier": 0.0,
                "confidence_label": "Low",
                "report_date": "2026-07-21",
                "release_status": "catch_up_delayed",
                "macro_regime_score": 45,
                "historical_evidence_state": "Tentative",
                "historical_evidence_exposure_cap": 0.75,
            },
        ]

    def test_block_shows_evidence_caps_and_catch_up_warning(self):
        block = build_block(self.rows())
        self.assertIn("Historical validation", block)
        self.assertIn("Not validated", block)
        self.assertIn("0.35× cap", block)
        self.assertIn("Tentative", block)
        self.assertIn("delayed/catch-up release", block)
        self.assertIn("no new exposure is permitted", block)

    def test_v11_injection_remains_idempotent(self):
        source = "<html><body><header>Header</header><main>Body</main></body></html>"
        once = inject(source, build_block(self.rows()))
        twice = inject(once, build_block(self.rows()))
        self.assertEqual(twice.count(START), 1)
        self.assertEqual(twice.count('id="directionalDecisionSummary"'), 1)
        self.assertEqual(twice.count("Historical validation"), 1)


if __name__ == "__main__":
    unittest.main()
