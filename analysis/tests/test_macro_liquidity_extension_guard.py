from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from macro_liquidity_extension_guard import apply_guard, evaluate_guard  # noqa: E402


class MacroLiquidityExtensionGuardTests(unittest.TestCase):
    SOURCE_KEYS = (
        "repo_dvp_rate",
        "repo_gcf_rate",
        "repo_triparty_rate",
        "repo_dvp_volume",
        "dealer_treasury_positions",
        "dealer_treasury_financing",
        "dealer_treasury_fails",
        "treasury_operating_cash",
        "treasury_cash_flows",
        "treasury_auction_absorption",
    )

    def config(self) -> dict:
        return {
            "schema_version": 1,
            "model_version": "macro-liquidity-guard-v1.0",
            "minimum_source_coverage": 0.60,
            "severe_score_threshold": 25.0,
            "minimum_severe_pillars": 2,
            "eligible_pillars": [
                "funding_microstructure",
                "dealer_absorption",
                "fiscal_cash_flow",
                "auction_absorption",
            ],
            "action": "Wait — Liquidity Plumbing Stress",
        }

    def decision(self) -> dict:
        return {
            "market": "nq",
            "market_label": "NASDAQ-100",
            "final_action": "Long — Reduced Size",
            "exposure_multiplier": 0.50,
            "structural_bias": "Bullish",
            "structural_score": 0.75,
            "adjusted_cot_score": 0.65,
            "reasons": [],
        }

    def macro(
        self,
        scores: dict[str, float | None],
        coverage: float = 0.8,
        source_overrides: dict[str, str] | None = None,
    ) -> dict:
        overrides = source_overrides or {}
        return {
            "source_coverage_ratio": coverage,
            "pillars": {
                key: {
                    "score": value,
                    "state": "Defensive" if value is not None and value <= 25 else "Neutral" if value is not None else "Unavailable",
                    "reasons": [f"{key} fixture"],
                }
                for key, value in scores.items()
            },
            "sources": [
                {"key": key, "status": overrides.get(key, "fresh")}
                for key in self.SOURCE_KEYS
            ],
        }

    def test_one_severe_pillar_is_not_enough(self):
        evaluation = evaluate_guard(
            self.macro(
                {
                    "funding_microstructure": 20,
                    "dealer_absorption": 50,
                    "fiscal_cash_flow": 50,
                    "auction_absorption": 50,
                }
            ),
            self.config(),
        )
        self.assertTrue(evaluation["reliable"])
        self.assertFalse(evaluation["active"])
        self.assertEqual(evaluation["severe_pillars"], ["funding_microstructure"])

    def test_two_severe_fresh_pillars_block_exposure_without_reversing_direction(self):
        decision = self.decision()
        guarded = apply_guard(
            [decision],
            self.macro(
                {
                    "funding_microstructure": 18,
                    "dealer_absorption": 22,
                    "fiscal_cash_flow": 55,
                    "auction_absorption": 48,
                }
            ),
            self.config(),
        )[0]
        self.assertTrue(guarded["liquidity_plumbing_guard_active"])
        self.assertEqual(guarded["final_action"], "Wait — Liquidity Plumbing Stress")
        self.assertEqual(guarded["exposure_multiplier"], 0.0)
        self.assertEqual(guarded["structural_bias"], decision["structural_bias"])
        self.assertEqual(guarded["structural_score"], decision["structural_score"])
        self.assertEqual(guarded["adjusted_cot_score"], decision["adjusted_cot_score"])
        self.assertEqual(guarded["pre_liquidity_plumbing_action"], "Long — Reduced Size")

    def test_stale_auction_score_cannot_count_as_severe(self):
        evaluation = evaluate_guard(
            self.macro(
                {
                    "funding_microstructure": 50,
                    "dealer_absorption": 50,
                    "fiscal_cash_flow": 20,
                    "auction_absorption": 10,
                },
                source_overrides={"treasury_auction_absorption": "stale"},
            ),
            self.config(),
        )
        self.assertEqual(evaluation["severe_pillars"], ["fiscal_cash_flow"])
        auction = next(
            item for item in evaluation["pillar_evaluations"]
            if item["pillar"] == "auction_absorption"
        )
        self.assertFalse(auction["fresh"])
        self.assertFalse(auction["available"])
        self.assertFalse(evaluation["active"])

    def test_incomplete_repo_sources_cannot_count_funding_pillar(self):
        evaluation = evaluate_guard(
            self.macro(
                {
                    "funding_microstructure": 10,
                    "dealer_absorption": 50,
                    "fiscal_cash_flow": 50,
                    "auction_absorption": 50,
                },
                source_overrides={
                    "repo_gcf_rate": "stale",
                    "repo_triparty_rate": "unavailable",
                    "repo_dvp_volume": "stale",
                },
            ),
            self.config(),
        )
        funding = next(
            item for item in evaluation["pillar_evaluations"]
            if item["pillar"] == "funding_microstructure"
        )
        self.assertEqual(funding["fresh_source_count"], 1)
        self.assertFalse(funding["available"])
        self.assertEqual(evaluation["severe_pillars"], [])

    def test_low_source_coverage_cannot_activate_guard(self):
        guarded = apply_guard(
            [self.decision()],
            self.macro(
                {
                    "funding_microstructure": 10,
                    "dealer_absorption": 10,
                    "fiscal_cash_flow": 10,
                    "auction_absorption": 10,
                },
                coverage=0.40,
            ),
            self.config(),
        )[0]
        self.assertFalse(guarded["liquidity_plumbing_guard_reliable"])
        self.assertFalse(guarded["liquidity_plumbing_guard_active"])
        self.assertEqual(guarded["final_action"], "Long — Reduced Size")
        self.assertEqual(guarded["exposure_multiplier"], 0.50)

    def test_higher_priority_macro_override_is_preserved(self):
        decision = self.decision()
        decision["final_action"] = "Hedge / Risk Override"
        decision["exposure_multiplier"] = 0.0
        guarded = apply_guard(
            [decision],
            self.macro(
                {
                    "funding_microstructure": 10,
                    "dealer_absorption": 10,
                    "fiscal_cash_flow": 50,
                    "auction_absorption": 50,
                }
            ),
            self.config(),
        )[0]
        self.assertTrue(guarded["liquidity_plumbing_guard_active"])
        self.assertEqual(guarded["final_action"], "Hedge / Risk Override")
        self.assertEqual(guarded["exposure_multiplier"], 0.0)

    def test_missing_pillars_do_not_count_as_severe(self):
        evaluation = evaluate_guard(
            self.macro(
                {
                    "funding_microstructure": None,
                    "dealer_absorption": None,
                    "fiscal_cash_flow": 20,
                    "auction_absorption": 60,
                }
            ),
            self.config(),
        )
        self.assertFalse(evaluation["active"])
        self.assertEqual(evaluation["severe_pillars"], ["fiscal_cash_flow"])


if __name__ == "__main__":
    unittest.main()
