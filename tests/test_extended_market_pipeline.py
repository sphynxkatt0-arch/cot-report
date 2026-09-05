from __future__ import annotations

import sys
import unittest
from pathlib import Path

ANALYSIS = Path(__file__).resolve().parents[1]
if str(ANALYSIS) not in sys.path:
    sys.path.insert(0, str(ANALYSIS))

from cot_market_registry import DIRECTIONAL_MARKETS, MARKETS


class ExtendedMarketRegistryTests(unittest.TestCase):
    def test_governed_market_set(self) -> None:
        self.assertEqual(
            DIRECTIONAL_MARKETS,
            ("sp500", "nq", "russell2000", "dow", "gold"),
        )

    def test_new_contract_identity(self) -> None:
        expected = {
            "russell2000": ("239742", "RUSSELL E-MINI - CHICAGO MERCANTILE EXCHANGE"),
            "dow": ("12460+", "DJIA Consolidated - CHICAGO BOARD OF TRADE"),
            "gold": ("088691", "GOLD - COMMODITY EXCHANGE INC."),
        }
        for market, (code, name) in expected.items():
            with self.subTest(market=market):
                meta = MARKETS[market]
                self.assertEqual(meta["legacy_cftc_code"], code)
                self.assertEqual(meta["secondary_cftc_code"], code)
                self.assertEqual(meta["legacy_contract_name"], name)
                self.assertEqual(meta["secondary_contract_name"], name)

    def test_report_families(self) -> None:
        self.assertEqual(MARKETS["russell2000"]["secondary_kind"], "tff")
        self.assertEqual(MARKETS["dow"]["secondary_kind"], "tff")
        self.assertEqual(MARKETS["gold"]["secondary_kind"], "disaggregated")
        self.assertEqual(MARKETS["gold"]["conviction_group_label"], "Managed Money")
        self.assertEqual(MARKETS["gold"]["conviction_column"], "managed_money_net_oi_pct")

    def test_russell_integrity_caveat_is_explicit(self) -> None:
        meta = MARKETS["russell2000"]
        self.assertEqual(meta["contract_selection_mode"], "primary_contract_exact")
        note = meta["contract_selection_note"].lower()
        self.assertIn("does not publish", note)
        self.assertIn("micro", note)
        self.assertIn("dividend", note)

    def test_consolidated_parent_rows_for_dow_and_existing_indices(self) -> None:
        for market in ("sp500", "nq", "dow"):
            with self.subTest(market=market):
                self.assertEqual(MARKETS[market]["contract_selection_mode"], "consolidated_exact")
                self.assertTrue(str(MARKETS[market]["secondary_cftc_code"]).endswith("+"))

    def test_participant_definitions_match_report_family(self) -> None:
        equity_keys = {spec["key"] for spec in MARKETS["dow"]["participant_specs"]}
        gold_keys = {spec["key"] for spec in MARKETS["gold"]["participant_specs"]}
        self.assertEqual(
            equity_keys,
            {"legacy_noncommercial", "asset_manager", "leveraged_money", "other_reportables", "nonreportables"},
        )
        self.assertEqual(
            gold_keys,
            {"legacy_noncommercial", "managed_money", "swap_dealer", "producer_merchant", "other_reportables", "nonreportables"},
        )

    def test_price_series_are_distinct(self) -> None:
        series = [str(MARKETS[market]["price_col"]) for market in DIRECTIONAL_MARKETS]
        self.assertEqual(len(series), len(set(series)))


if __name__ == "__main__":
    unittest.main()
