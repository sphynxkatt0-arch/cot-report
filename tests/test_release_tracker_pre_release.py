from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cftc_release_tracker import observe_report  # noqa: E402


class ReleaseTrackerPreReleaseTests(unittest.TestCase):
    def test_pre_release_row_is_not_persisted(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger = Path(directory) / "ledger.json"
            entry = observe_report(
                "2026-07-21",
                now=datetime(2026, 7, 24, 19, 20, tzinfo=UTC),
                path=ledger,
            )
            self.assertIsNone(entry)
            self.assertFalse(ledger.exists())

    def test_same_report_is_recorded_after_release_if_seen_early_before(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger = Path(directory) / "ledger.json"
            observe_report(
                "2026-07-21",
                now=datetime(2026, 7, 24, 19, 20, tzinfo=UTC),
                path=ledger,
            )
            entry = observe_report(
                "2026-07-21",
                now=datetime(2026, 7, 24, 19, 35, tzinfo=UTC),
                path=ledger,
            )
            self.assertIsNotNone(entry)
            payload = json.loads(ledger.read_text(encoding="utf-8"))
            self.assertEqual(payload["latest_seen_report_date"], "2026-07-21")
            self.assertIn("2026-07-21", payload["reports"])


if __name__ == "__main__":
    unittest.main()
