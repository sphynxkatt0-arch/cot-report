from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from weekly_position_change import (  # noqa: E402
    CATEGORY_SPECS,
    category_change,
    enrich_decisions,
    inject_panel,
    weekly_signal_state,
)


class WeeklyPositionChangeTests(unittest.TestCase):
    def test_signal_state_detects_new_strengthened_and_flipped_signals(self):
        self.assertEqual(weekly_signal_state(0.40, 0.10), "New bullish COT signal")
        self.assertEqual(weekly_signal_state(0.70, 0.45), "COT signal strengthened")
        self.assertEqual(weekly_signal_state(-0.60, 0.60), "COT direction flipped bearish")
        self.assertEqual(weekly_signal_state(0.15, 0.55), "COT signal neutralized")

    def test_category_change_computes_contract_and_open_interest_deltas(self):
        dates = pd.to_datetime(["2026-07-14", "2026-07-21"])
        legacy = pd.DataFrame({
            "date": dates,
            "noncommercial_long": [100.0, 130.0],
            "noncommercial_short": [160.0, 150.0],
            "noncommercial_net_oi_pct": [-6.0, -2.0],
        })
        tff = pd.DataFrame({"date": dates})
        row = category_change(
            CATEGORY_SPECS[0],
            legacy,
            tff,
            pd.Timestamp("2026-07-21"),
            pd.Timestamp("2026-07-14"),
        )
        self.assertEqual(row["previous_net"], -60.0)
        self.assertEqual(row["current_net"], -20.0)
        self.assertEqual(row["delta_net"], 40.0)
        self.assertEqual(row["delta_net_oi_pct"], 4.0)

    def test_enrichment_never_changes_action_or_exposure(self):
        decisions = [{
            "market": "nq",
            "final_action": "Long — Reduced Size",
            "exposure_multiplier": 0.55,
        }]
        changes = {
            "nq": {
                "weekly_signal_change": "COT signal strengthened",
                "position_changes": [],
            }
        }
        enriched = enrich_decisions(decisions, changes)[0]
        self.assertEqual(enriched["final_action"], "Long — Reduced Size")
        self.assertEqual(enriched["exposure_multiplier"], 0.55)
        self.assertEqual(enriched["weekly_signal_change"], "COT signal strengthened")

    def test_report_injection_is_idempotent(self):
        panel = "<!-- WEEKLY_POSITION_CHANGE_START --><section>change</section><!-- WEEKLY_POSITION_CHANGE_END -->"
        source = "<html><body><main><footer>footer</footer></main></body></html>"
        once = inject_panel(source, panel)
        twice = inject_panel(once, panel)
        self.assertEqual(twice.count("WEEKLY_POSITION_CHANGE_START"), 1)
        self.assertEqual(twice.count("<section>change</section>"), 1)


if __name__ == "__main__":
    unittest.main()
