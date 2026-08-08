#!/usr/bin/env python3
from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import UTC, date, datetime
from pathlib import Path

ANALYSIS = Path(__file__).resolve().parent
SENTIMENT = ANALYSIS / "sentiment"
if str(SENTIMENT) not in sys.path:
    sys.path.insert(0, str(SENTIMENT))

from adanos_daily import SentimentError, composite, normalize_source, snapshot_relative_path, write_immutable


class MarketSentimentTests(unittest.TestCase):
    def source(self, sentiment: float, bullish: float, bearish: float, buzz: float) -> dict:
        return {
            "ok": True,
            "http_status": 200,
            "rate_limit": {"remaining_monthly": "200"},
            "raw": {
                "sentiment_score": sentiment,
                "bullish_pct": bullish,
                "bearish_pct": bearish,
                "buzz_score": buzz,
                "trend": "stable",
                "drivers": [{"ticker": "NVDA", "buzz_score": 70}],
            },
        }

    def test_normalization_maps_minus_one_plus_one_to_zero_hundred(self) -> None:
        when = datetime(2026, 8, 9, 21, 45, tzinfo=UTC)
        bearish = normalize_source("reddit", self.source(-1, 0, 100, 50), date(2026, 8, 9), when)
        bullish = normalize_source("x", self.source(1, 100, 0, 50), date(2026, 8, 9), when)
        self.assertEqual(bearish["sentiment_index"], 0)
        self.assertEqual(bullish["sentiment_index"], 100)

    def test_composite_is_equal_weight_and_explicitly_degraded(self) -> None:
        when = datetime(2026, 8, 9, 21, 45, tzinfo=UTC)
        sources = {
            "reddit": normalize_source("reddit", self.source(0.4, 70, 10, 80), date(2026, 8, 9), when),
            "x": normalize_source("x", self.source(0.0, 45, 30, 60), date(2026, 8, 9), when),
            "news": {"source_id": "news", "status": "UNAVAILABLE"},
            "polymarket": normalize_source("polymarket", self.source(-0.2, 35, 55, 50), date(2026, 8, 9), when),
        }
        result = composite(sources)
        self.assertEqual(result["state"], "DEGRADED")
        self.assertEqual(result["available_sources"], 3)
        self.assertAlmostEqual(result["sentiment_score"], (0.4 + 0.0 - 0.2) / 3)
        self.assertEqual(set(result["source_weights"]), {"reddit", "x", "polymarket"})
        self.assertEqual(result["missing_sources"], ["news"])

    def test_single_source_is_failed_not_neutral(self) -> None:
        when = datetime(2026, 8, 9, 21, 45, tzinfo=UTC)
        sources = {
            "reddit": normalize_source("reddit", self.source(0.1, 50, 20, 60), date(2026, 8, 9), when),
            "x": {"source_id": "x", "status": "UNAVAILABLE"},
            "news": {"source_id": "news", "status": "UNAVAILABLE"},
            "polymarket": {"source_id": "polymarket", "status": "UNAVAILABLE"},
        }
        result = composite(sources)
        self.assertEqual(result["state"], "FAILED")
        self.assertNotEqual(result["sentiment_index"], 50)

    def test_daily_snapshot_path_and_immutability(self) -> None:
        relative = snapshot_relative_path(date(2026, 8, 9))
        self.assertEqual(str(relative).replace("\\", "/"), "sentiment/2026/2026-08-09.json")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / relative
            payload = {"schema_version": 1, "observation_date": "2026-08-09"}
            self.assertEqual(write_immutable(path, payload), "created")
            self.assertEqual(write_immutable(path, payload), "unchanged")
            with self.assertRaises(SentimentError):
                write_immutable(path, {**payload, "changed": True})


if __name__ == "__main__":
    unittest.main()
