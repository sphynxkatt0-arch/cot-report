from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cftc_release_tracker import (  # noqa: E402
    expected_latest_report_date,
    observe_report,
    resolve_release_state,
    scheduled_release_datetime,
)
from inject_directional_dashboard import START, build_block, inject  # noqa: E402
from macro_direction_adapter import load_macro_direction_context, weighted_available_score  # noqa: E402


class ReleaseTrackerTests(unittest.TestCase):
    def test_scheduled_release_is_1530_new_york_and_2130_stockholm_in_summer(self):
        release = scheduled_release_datetime("2026-07-21")
        self.assertEqual(release.isoformat(), "2026-07-24T15:30:00-04:00")
        self.assertEqual(release.astimezone(ZoneInfo("Europe/Stockholm")).strftime("%H:%M"), "21:30")

    def test_expected_report_changes_after_friday_release(self):
        before = datetime(2026, 7, 24, 19, 20, tzinfo=UTC)
        after = datetime(2026, 7, 24, 19, 40, tzinfo=UTC)
        self.assertEqual(expected_latest_report_date(before).isoformat(), "2026-07-14")
        self.assertEqual(expected_latest_report_date(after).isoformat(), "2026-07-21")

    def test_delayed_report_is_explicit(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger = Path(directory) / "ledger.json"
            state = resolve_release_state(
                "2026-07-14",
                now=datetime(2026, 7, 24, 20, 0, tzinfo=UTC),
                path=ledger,
            )
            self.assertTrue(state["is_delayed"])
            self.assertEqual(state["expected_report_date"], "2026-07-21")

    def test_first_observation_is_persisted_without_claiming_official_timestamp(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger = Path(directory) / "ledger.json"
            now = datetime(2026, 7, 24, 19, 35, tzinfo=UTC)
            entry = observe_report("2026-07-21", now=now, path=ledger)
            self.assertIsNotNone(entry)
            self.assertEqual(entry["observation_source"], "local_refresh_first_seen")
            payload = json.loads(ledger.read_text(encoding="utf-8"))
            self.assertIn("2026-07-21", payload["reports"])

    def test_stale_report_is_not_recorded_as_new_during_delay(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger = Path(directory) / "ledger.json"
            entry = observe_report(
                "2026-07-14",
                now=datetime(2026, 7, 24, 20, 0, tzinfo=UTC),
                path=ledger,
            )
            self.assertIsNone(entry)
            self.assertFalse(ledger.exists())


class MacroAdapterTests(unittest.TestCase):
    NOW = datetime(2026, 7, 25, 8, 0, tzinfo=UTC)

    def test_missing_factor_reduces_available_weight(self):
        score, available = weighted_available_score(
            {"score_net_liquidity": 80, "score_bank_reserves": None},
            {"score_net_liquidity": 26, "score_bank_reserves": 10},
        )
        self.assertEqual(score, 80)
        self.assertEqual(available, 26)

    @staticmethod
    def metadata(latest_date: str = "2026-07-24") -> dict:
        return {
            "generated_at_utc": "2026-07-25T07:00:00Z",
            "liquidity_latest": {
                "fed_balance_sheet": "2026-07-22",
                "reverse_repo": latest_date,
                "treasury_cash": "2026-07-22",
                "bank_reserves": "2026-07-22",
                "bank_treasury_agency": "2026-07-22",
            },
            "funding_latest": {"sofr": latest_date, "iorb": latest_date},
            "factor_latest": {
                "real_yield_10y": latest_date,
                "hy_oas": latest_date,
                "dollar_index": latest_date,
                "fred_vix": latest_date,
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
            "alerts": [
                {"label": "Credit shock", "triggered": True, "severity": "red"},
                {"label": "Funding shock", "triggered": True, "severity": "red"},
            ],
        }

    def write_dashboard(self, path: Path, metadata: dict) -> None:
        macro = self.macro_payload()
        path.write_text(
            f'<html><script>const MACRO_MONITOR = {json.dumps(macro)}; const METADATA = {json.dumps(metadata)};</script></html>',
            encoding="utf-8",
        )

    def test_macro_context_decomposes_and_triggers_two_red_alert_override(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "dashboard.html"
            self.write_dashboard(path, self.metadata())
            context = load_macro_direction_context(path, now=self.NOW)
            self.assertTrue(context.hard_override)
            self.assertEqual(context.severe_alert_count, 2)
            self.assertAlmostEqual(context.availability_ratio, 1.0)
            self.assertFalse(context.stale_factors)
            self.assertIsNotNone(context.liquidity_plumbing_score)
            self.assertIsNotNone(context.market_transmission_score)

    def test_stale_daily_sources_are_removed_from_available_weight(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "dashboard.html"
            self.write_dashboard(path, self.metadata(latest_date="2026-07-01"))
            context = load_macro_direction_context(path, now=self.NOW)
            self.assertLess(context.availability_ratio, 1.0)
            self.assertTrue(any("score_repo_spread" in item for item in context.stale_factors))
            self.assertTrue(any("score_credit" in item for item in context.stale_factors))


class DashboardInjectionTests(unittest.TestCase):
    def test_injection_is_idempotent_and_marks_old_scores_as_research(self):
        rows = [{
            "market_label": "NASDAQ-100",
            "final_action": "Wait for Long",
            "structural_bias": "Bullish",
            "execution_state": "Waiting",
            "structural_score": 0.8,
            "tactical_modifier": -0.1,
            "exposure_multiplier": 0.3,
            "confidence_label": "Medium",
            "report_date": "2026-07-21",
            "release_status": "current",
            "macro_regime_score": 50,
        }]
        source = "<html><body><header>Header</header><main>Body</main></body></html>"
        once = inject(source, build_block(rows))
        twice = inject(once, build_block(rows))
        self.assertEqual(twice.count(START), 1)
        self.assertIn("Directional COT Decision", twice)
        self.assertIn("Selected-report research regime", twice)
        self.assertIn("Research report view", twice)


if __name__ == "__main__":
    unittest.main()
