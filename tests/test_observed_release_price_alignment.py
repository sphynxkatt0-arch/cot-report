from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from align_observed_release_price import align_decisions, observed_signal_target  # noqa: E402


class ObservedReleasePriceAlignmentTests(unittest.TestCase):
    def test_before_cash_close_uses_same_calendar_date(self):
        self.assertEqual(observed_signal_target("2026-07-24T19:45:00+00:00"), "2026-07-24")

    def test_after_cash_close_uses_next_calendar_date(self):
        self.assertEqual(observed_signal_target("2026-07-24T20:30:00+00:00"), "2026-07-25")

    def test_after_close_observation_uses_next_available_trading_close(self):
        decisions = [{
            "market": "nq",
            "release_date_source": "first_observed_delayed",
            "first_observed_utc": "2026-07-24T20:30:00+00:00",
            "latest_price": 103.0,
            "reasons": [],
        }]
        prices = pd.DataFrame({
            "date": pd.to_datetime(["2026-07-24", "2026-07-27", "2026-07-28"]),
            "price": [100.0, 101.0, 103.0],
        })
        with patch("align_observed_release_price.read_prices", return_value=prices):
            row = align_decisions(decisions)[0]
        self.assertEqual(row["effective_signal_target_date"], "2026-07-25")
        self.assertEqual(row["signal_price_date"], "2026-07-27")
        self.assertEqual(row["signal_price"], 101.0)
        self.assertAlmostEqual(row["price_change_since_release_pct"], (103 / 101 - 1) * 100, places=4)

    def test_scheduled_release_is_not_modified(self):
        decision = {
            "market": "sp500",
            "release_date_source": "scheduled_assumption",
            "first_observed_utc": None,
            "signal_price_date": "2026-07-24",
            "signal_price": 100.0,
        }
        self.assertEqual(align_decisions([decision])[0], decision)


if __name__ == "__main__":
    unittest.main()
