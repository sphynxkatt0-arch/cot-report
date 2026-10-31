from __future__ import annotations

import sys
import unittest
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from macro_liquidity_expansion import IndicatorResult  # noqa: E402
from treasury_cash_flow_extension import (  # noqa: E402
    fiscal_pillar,
    fiscal_rows,
    operating_cash_result,
    treasury_flow_result,
)
import inject_fiscal_cash_ux as ux  # noqa: E402


class TreasuryCashFlowTests(unittest.TestCase):
    NOW = datetime(2026, 7, 16, tzinfo=UTC)

    def test_fiscal_rows_only_returns_dictionary_records(self):
        self.assertEqual(fiscal_rows({"data": [{"a": 1}, 2, "bad"]}), [{"a": 1}])

    def test_operating_cash_is_scaled_to_billions_and_tracks_five_day_change(self):
        values = [700000, 710000, 690000, 680000, 675000, 670000]
        rows = [
            {
                "record_date": f"2026-07-{10 + index:02d}",
                "account_type": "Treasury General Account (TGA) Closing Balance",
                "open_today_bal": str(value),
            }
            for index, value in enumerate(values)
        ]
        result, context = operating_cash_result(rows, self.NOW)
        self.assertEqual(result.status, "fresh")
        self.assertEqual(result.latest_value, 670.0)
        self.assertAlmostEqual(context["operating_cash_change_5d_bn"], -30.0)

    def test_withdrawals_are_private_cash_injection_and_tax_deposits_are_drain(self):
        rows = []
        for day in range(10, 16):
            rows.extend(
                [
                    {
                        "record_date": f"2026-07-{day:02d}",
                        "transaction_type": "Deposits",
                        "transaction_catg": "Federal Tax Deposits",
                        "transaction_today_amt": "20000",
                    },
                    {
                        "record_date": f"2026-07-{day:02d}",
                        "transaction_type": "Withdrawals",
                        "transaction_catg": "Social Security",
                        "transaction_today_amt": "30000",
                    },
                ]
            )
        result, context = treasury_flow_result(rows, self.NOW)
        self.assertEqual(result.status, "fresh")
        self.assertAlmostEqual(context["private_cash_flow_5d_bn"], 50.0)
        self.assertAlmostEqual(context["tax_deposits_5d_bn"], 100.0)
        self.assertIn("positive = Treasury withdrawal", context["sign_convention"])

    def test_fiscal_pillar_is_context_not_direction(self):
        results = {
            "treasury_operating_cash": IndicatorResult("a", "a", "fiscaldata", "Treasury", "USD bn", "fresh"),
            "treasury_cash_flows": IndicatorResult("b", "b", "fiscaldata", "Treasury", "USD bn", "fresh"),
        }
        pillar = fiscal_pillar(
            {
                "private_cash_flow_5d_bn": 80,
                "operating_cash_change_5d_bn": -20,
                "tax_deposits_5d_bn": 50,
            },
            results,
        )
        self.assertGreater(pillar["score"], 60)
        self.assertNotIn("direction", pillar)

    def test_fiscal_ux_is_idempotent(self):
        payload = {
            "pillars": {"fiscal_cash_flow": {"score": 55, "state": "Neutral"}},
            "treasury_cash_context": {"private_cash_flow_5d_bn": 20},
        }
        block = ux.build_block(payload)
        source = "<html><body><!-- MACRO_LIQUIDITY_CONTROL_ROOM_END --><main></main></body></html>"
        once = ux.inject(source, block)
        twice = ux.inject(once, block)
        self.assertEqual(twice.count(ux.START), 1)
        self.assertEqual(twice.count('id="fiscalCashPath"'), 1)
        self.assertIn("Daily Treasury Cash Flow", twice)


if __name__ == "__main__":
    unittest.main()
