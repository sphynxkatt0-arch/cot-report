from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import macro_liquidity_expansion as model  # noqa: E402
import inject_macro_liquidity_ux as ux  # noqa: E402


class MacroLiquidityExpansionTests(unittest.TestCase):
    def test_series_points_parses_full_ofr_response(self):
        payload = {
            "REPO-X": {
                "timeseries": {
                    "aggregation": [["2026-07-01", 4.1], ["2026-07-02", None], ["2026-07-03", 4.2]]
                }
            }
        }
        self.assertEqual(model.series_points(payload, "REPO-X"), [("2026-07-01", 4.1), ("2026-07-03", 4.2)])

    def test_candidate_score_rejects_wrong_dataset_and_excluded_terms(self):
        spec = {"dataset": "nypd", "include_terms": ["treasury", "positions"], "exclude_terms": ["agency"]}
        good = {"dataset": "nypd", "value": "Treasury Net Positions", "field": "description/name", "mnemonic": "A"}
        bad = {"dataset": "nypd", "value": "Agency Treasury Positions", "field": "description/name", "mnemonic": "B"}
        other = {"dataset": "repo", "value": "Treasury Net Positions", "field": "description/name", "mnemonic": "C"}
        self.assertGreater(model.candidate_score(good, spec), model.candidate_score(bad, spec))
        self.assertLess(model.candidate_score(other, spec), -1000)

    def test_repo_pillar_detects_dispersion_without_direction_vote(self):
        rows = {
            "repo_dvp_rate": model.IndicatorResult("repo_dvp_rate", "DVP", "repo", "OFR", "%", "fresh", latest_value=4.10, change_short=0.02),
            "repo_gcf_rate": model.IndicatorResult("repo_gcf_rate", "GCF", "repo", "OFR", "%", "fresh", latest_value=4.22, change_short=0.08),
            "repo_triparty_rate": model.IndicatorResult("repo_triparty_rate", "Tri", "repo", "OFR", "%", "fresh", latest_value=4.11, change_short=0.01),
        }
        pillar = model.repo_pillar(rows)
        self.assertLess(pillar["score"], 50)
        self.assertAlmostEqual(pillar["repo_rate_dispersion_bp"], 12.0)
        self.assertNotIn("direction", pillar)

    def test_ux_injection_is_idempotent(self):
        payload = {
            "source_coverage_ratio": 0.5,
            "source_coverage_label": "Partial",
            "pillars": {
                "macro_regime": {"score": 55, "state": "Neutral"},
                "net_liquidity": {"value": 20, "state": "Supportive"},
                "bank_reserves": {"value": -10, "state": "Defensive"},
                "treasury_supply": {"value": 180, "state": "Moderate"},
                "repo_admin_spread": {"value": 0.02, "state": "Normal"},
                "funding_microstructure": {"score": 48, "state": "Neutral", "coverage": 0.75, "reasons": []},
                "dealer_absorption": {"score": 42, "state": "Neutral", "coverage": 0.66, "reasons": []},
                "money_market_allocation": {"score": 50, "state": "Context", "coverage": 0.33, "reasons": []},
            },
            "sources": [],
        }
        block = ux.build_block(payload)
        source = "<html><body><header></header><!-- DIRECTIONAL_DECISION_END --><main></main></body></html>"
        once = ux.inject_dashboard(source, block)
        twice = ux.inject_dashboard(once, block)
        self.assertEqual(twice.count(ux.START), 1)
        self.assertEqual(twice.count('id="macroLiquidityControlRoom"'), 1)
        self.assertIn("Current State", twice)


if __name__ == "__main__":
    unittest.main()
