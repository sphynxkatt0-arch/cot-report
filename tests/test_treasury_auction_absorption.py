from __future__ import annotations

import sys
import unittest
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from treasury_auction_absorption import (  # noqa: E402
    auction_rows,
    build_auction_context,
    same_term_comparison,
)
import inject_auction_absorption_ux as ux  # noqa: E402


class TreasuryAuctionAbsorptionTests(unittest.TestCase):
    def sample_rows(self):
        rows = []
        for index in range(10):
            rows.append(
                {
                    "auction_date": f"2026-{1 + index // 5:02d}-{5 + (index % 5) * 4:02d}",
                    "security_type": "Note",
                    "security_term": "10-Year",
                    "original_security_term": "10-Year",
                    "bid_to_cover_ratio": str(2.50 - index * 0.02),
                    "total_accepted": "40000000000",
                    "primary_dealer_accepted": str(8000000000 + index * 300000000),
                    "indirect_bidder_accepted": str(26000000000 - index * 200000000),
                    "direct_bidder_accepted": "6000000000",
                    "cusip": f"TEST{index}",
                }
            )
        return rows

    def test_auction_rows_calculates_bidder_shares(self):
        rows = auction_rows({"data": self.sample_rows()[:1]})
        self.assertEqual(len(rows), 1)
        self.assertAlmostEqual(rows[0]["primary_dealer_share_pct"], 20.0)
        self.assertAlmostEqual(rows[0]["indirect_share_pct"], 65.0)

    def test_same_term_comparison_penalizes_weaker_demand(self):
        rows = auction_rows({"data": self.sample_rows()})
        comparison = same_term_comparison(rows, rows[-1])
        self.assertLess(comparison["bid_to_cover_delta"], 0)
        self.assertGreater(comparison["dealer_share_delta_pp"], 0)
        self.assertLess(comparison["quality_score"], 50)

    def test_context_is_relative_and_non_directional(self):
        rows = auction_rows({"data": self.sample_rows()})
        result, context = build_auction_context(rows, datetime(2026, 3, 1, tzinfo=UTC))
        self.assertIn(result.status, {"fresh", "stale"})
        self.assertIn("same-tenor relative demand", context["definition"])
        self.assertNotIn("direction", context)

    def test_auction_ux_is_idempotent(self):
        payload = {
            "pillars": {"auction_absorption": {"score": 45, "state": "Neutral"}},
            "treasury_auction_context": {"recent_coupon_auctions": []},
        }
        block = ux.build_block(payload)
        source = "<html><body><!-- FISCAL_CASH_PATH_END --><main></main></body></html>"
        twice = ux.inject(ux.inject(source, block), block)
        self.assertEqual(twice.count(ux.START), 1)
        self.assertEqual(twice.count('id="auctionAbsorption"'), 1)
        self.assertIn("Treasury Auction Demand Quality", twice)


if __name__ == "__main__":
    unittest.main()
