from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cot_direction_model import load_config  # noqa: E402
from rebuild_directional_history import build_deterministic_history_for_market  # noqa: E402


class DeterministicHistoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = load_config(ROOT / "config" / "cot_direction_model_v1.json")
        dates = pd.date_range(end="2026-07-21", periods=150, freq="W-TUE")
        cls.legacy = pd.DataFrame({
            "date": dates,
            "noncommercial_net_oi_pct": np.linspace(20.0, -20.0, len(dates)),
        })
        cls.tff = pd.DataFrame({
            "date": dates,
            "asset_mgr_net_oi_pct": np.linspace(5.0, 25.0, len(dates)),
            "other_reportable_net_oi_pct": np.sin(np.linspace(0, 8, len(dates))) * 10,
            "non_reportable_net_oi_pct": np.cos(np.linspace(0, 7, len(dates))) * 8,
        })
        price_dates = pd.bdate_range(start=dates.min() - pd.Timedelta(days=7), end="2027-03-31")
        cls.prices = pd.DataFrame({"date": price_dates, "price": np.linspace(1000, 1500, len(price_dates))})

    def test_history_does_not_read_live_release_ledger(self):
        with patch("cftc_release_tracker.load_ledger", side_effect=AssertionError("ledger must not be read")):
            rows = build_deterministic_history_for_market(
                "nq", self.legacy, self.tff, self.prices, self.config
            )
        self.assertEqual(len(rows), len(self.legacy))
        self.assertTrue(all(row["release_date_source"] == "scheduled_history" for row in rows))

    def test_each_tuesday_uses_same_week_friday_price_or_next_business_day(self):
        rows = build_deterministic_history_for_market(
            "nq", self.legacy, self.tff, self.prices, self.config
        )
        for row in rows[-20:]:
            report = pd.Timestamp(row["report_date"])
            expected_friday = report + pd.Timedelta(days=3)
            self.assertEqual(row["scheduled_release_date"], expected_friday.date().isoformat())
            if row["signal_price_date"] is not None:
                self.assertGreaterEqual(row["signal_price_date"], row["scheduled_release_date"])


if __name__ == "__main__":
    unittest.main()
