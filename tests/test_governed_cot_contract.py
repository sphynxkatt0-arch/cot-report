from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import build_worldclass_regime_backtest as regime_bt  # noqa: E402
from cot_direction_model import MACRO_PRODUCTION_MULTIPLIER, load_config, macro_multiplier  # noqa: E402
from macro_direction_adapter import (  # noqa: E402
    COMPONENT_WEIGHTS,
    load_macro_direction_context,
    shrink_toward_neutral,
)


class GovernedMacroContractTests(unittest.TestCase):
    NOW = datetime(2026, 7, 25, 8, 0, tzinfo=UTC)

    @staticmethod
    def metadata() -> dict:
        return {
            "generated_at_utc": "2026-07-25T07:00:00Z",
            "liquidity_latest": {
                "fed_balance_sheet": "2026-07-22",
                "reverse_repo": "2026-07-24",
                "treasury_cash": "2026-07-22",
                "bank_reserves": "2026-07-22",
                "bank_treasury_agency": "2026-07-22",
            },
            "funding_latest": {"sofr": "2026-07-24", "iorb": "2026-07-24"},
            "factor_latest": {
                "real_yield_10y": "2026-07-24",
                "hy_oas": "2026-07-24",
                "dollar_index": "2026-07-24",
                "fred_vix": "2026-07-24",
            },
        }

    @staticmethod
    def macro_payload() -> dict:
        return {
            "latest": {
                "score_net_liquidity": 70,
                "score_bank_reserves": 60,
                "score_repo_spread": 40,
                "score_slr_load": 50,
                "score_real_yield": 30,
                "score_credit": 20,
                "score_dollar": 45,
                "score_vix": 25,
                "score_treasury_supply": 55,
            },
            "alerts": [],
        }

    def test_canonical_component_weights_are_48_42_10(self):
        self.assertEqual(
            COMPONENT_WEIGHTS,
            {"plumbing": 48.0, "transmission": 42.0, "supply": 10.0},
        )

    def test_missing_data_shrinks_toward_neutral(self):
        self.assertAlmostEqual(shrink_toward_neutral(80.0, 0.25), 57.5)
        self.assertAlmostEqual(shrink_toward_neutral(20.0, 0.25), 42.5)
        self.assertAlmostEqual(shrink_toward_neutral(80.0, 0.0), 50.0)

    def test_aggregate_macro_score_uses_one_canonical_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "dashboard.html"
            path.write_text(
                "<html><script>"
                f"const MACRO_MONITOR = {json.dumps(self.macro_payload())};"
                f"const METADATA = {json.dumps(self.metadata())};"
                "</script></html>",
                encoding="utf-8",
            )
            context = load_macro_direction_context(path, now=self.NOW)
            # Canonical weighted total:
            # plumbing=2940, transmission=1210, supply=550 => 4700 / 100 = 47.
            self.assertEqual(context.macro_observed_score, 47.0)
            self.assertEqual(context.macro_regime_score, 47.0)
            self.assertEqual(context.availability_confidence, 1.0)
            self.assertEqual(context.macro_risk_budget["production_macro_multiplier"], 1.0)
            self.assertEqual(context.macro_risk_budget["production_directional_weight"], 0.0)
            self.assertEqual(len(context.macro_directional_edges), 3)

    def test_production_macro_multiplier_is_neutral_in_all_regimes(self):
        config = load_config(ROOT / "config" / "cot_direction_model_v1.json")
        for score in (10.0, 35.0, 50.0, 60.0, 80.0, None):
            multiplier, _ = macro_multiplier(score, config)
            self.assertEqual(multiplier, MACRO_PRODUCTION_MULTIPLIER)


class RegimeIndependenceTests(unittest.TestCase):
    @staticmethod
    def row(index: int, state: str, value: float = 1.0) -> dict:
        return {
            "report_date": f"2026-01-{index + 1:02d}",
            "signal_date": f"2026-01-{index + 1:02d}",
            "signal_index": index * 5,
            "cot_state": state,
            "macro_state": "neutral",
            "horizons": {
                "4w": {
                    "return_pct": value,
                    "drawdown_pct": -abs(value),
                }
            },
        }

    def test_contiguous_regime_runs_collapse_to_episodes(self):
        states = ["bullish", "bullish", "neutral", "bullish", "bullish", "bearish"]
        history = [self.row(index, state) for index, state in enumerate(states)]
        episodes = regime_bt.count_regime_episodes(
            history,
            lambda row: row["cot_state"] == "bullish",
        )
        self.assertEqual(episodes, 2)

    def test_multiweek_horizon_reports_non_overlapping_and_effective_n(self):
        selected = [self.row(index, "bullish", float(index + 1)) for index in range(8)]
        # 4w is 20 trading days in the production horizon map. Weekly rows are
        # spaced by five trading days, so only every fourth row is independent.
        independent = regime_bt.non_overlapping_records(selected, "4w")
        self.assertEqual([row["signal_index"] for row in independent], [0, 20])
        result = regime_bt.summary(selected, "4w", selected, regime_episode_n=3)
        self.assertEqual(result["observations"], 8)
        self.assertEqual(result["non_overlapping_n"], 2)
        self.assertEqual(result["regime_episode_n"], 3)
        self.assertEqual(result["effective_n"], 2)
        self.assertEqual(result["confidence"], "Low")


if __name__ == "__main__":
    unittest.main()
