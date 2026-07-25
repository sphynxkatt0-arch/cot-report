from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import inject_dashboard_experience_v12 as ux  # noqa: E402


class DashboardExperienceV12Tests(unittest.TestCase):
    def decisions(self):
        return [
            {
                "market_label": "S&P 500",
                "final_action": "Long — Reduced Size",
                "structural_bias": "Bullish",
                "weekly_signal_change": "COT signal strengthened",
                "macro_regime_score": 52,
                "exposure_multiplier": 0.35,
                "historical_evidence_state": "Not validated",
                "release_status": "current",
                "execution_state": "Waiting",
            },
            {
                "market_label": "NASDAQ-100",
                "final_action": "Wait for Long",
                "structural_bias": "Bullish",
                "weekly_signal_change": "COT signal little changed",
                "macro_regime_score": 48,
                "exposure_multiplier": 0.0,
                "historical_evidence_state": "Tentative",
                "release_status": "current",
                "execution_state": "Waiting",
            },
        ]

    def test_playbook_is_summary_only_and_contains_navigation(self):
        block = ux.build_block(
            self.decisions(),
            {
                "source_coverage_ratio": 0.75,
                "pillars": {"fiscal_cash_flow": {"state": "Neutral"}},
            },
        )
        self.assertIn("What to do, what must confirm", block)
        self.assertIn('href="#macroLiquidityControlRoom"', block)
        self.assertIn('href="#fiscalCashPath"', block)
        self.assertIn("It does not calculate a new direction", block)
        self.assertIn("Show research", block)
        self.assertIn("xp-research-hidden", block)

    def test_dashboard_experience_injection_is_idempotent(self):
        block = ux.build_block(
            self.decisions(),
            {"source_coverage_ratio": 0.5, "pillars": {"fiscal_cash_flow": {"state": "Defensive"}}},
        )
        source = "<html><body><!-- DIRECTIONAL_DECISION_END --><main></main></body></html>"
        once = ux.inject(source, block)
        twice = ux.inject(once, block)
        self.assertEqual(twice.count(ux.START), 1)
        self.assertEqual(twice.count('id="marketPlaybook"'), 1)
        self.assertEqual(twice.count('id="xpResearchToggle"'), 1)


if __name__ == "__main__":
    unittest.main()
