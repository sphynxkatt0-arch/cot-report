from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from build_directional_cot_report import select_latest_file  # noqa: E402
from validate_directional_inputs import (  # noqa: E402
    LEGACY_REQUIRED,
    TFF_REQUIRED,
    validate_frame,
    validate_price_frame,
)


class DirectionalInputValidationTests(unittest.TestCase):
    def position_frame(self, required: set[str], contract: str, rows: int = 120) -> pd.DataFrame:
        data = {
            "date": pd.date_range("2024-01-02", periods=rows, freq="W-TUE"),
            "contract": [contract] * rows,
            "open_interest": [100000] * rows,
        }
        for column in required - {"date", "open_interest"}:
            data[column] = [1.0] * rows
        return pd.DataFrame(data)

    def test_valid_exact_consolidated_frame_passes(self):
        expected = "NASDAQ-100 Consolidated - CHICAGO MERCANTILE EXCHANGE"
        frame = self.position_frame(TFF_REQUIRED, expected)
        failures: list[str] = []
        validate_frame(
            frame,
            label="nq TFF",
            required=TFF_REQUIRED,
            expected_contract=expected,
            minimum_rows=117,
            failures=failures,
        )
        self.assertEqual(failures, [])

    def test_component_contract_is_rejected(self):
        expected = "NASDAQ-100 Consolidated - CHICAGO MERCANTILE EXCHANGE"
        frame = self.position_frame(LEGACY_REQUIRED, "NASDAQ-100 E-MINI - CHICAGO MERCANTILE EXCHANGE")
        failures: list[str] = []
        validate_frame(
            frame,
            label="nq Legacy",
            required=LEGACY_REQUIRED,
            expected_contract=expected,
            minimum_rows=117,
            failures=failures,
        )
        self.assertTrue(any("expected exact contract" in failure for failure in failures))

    def test_missing_latest_position_value_is_rejected(self):
        expected = "S&P 500 Consolidated - CHICAGO MERCANTILE EXCHANGE"
        frame = self.position_frame(LEGACY_REQUIRED, expected)
        frame.loc[frame.index[-1], "noncommercial_net_oi_pct"] = None
        failures: list[str] = []
        validate_frame(
            frame,
            label="sp500 Legacy",
            required=LEGACY_REQUIRED,
            expected_contract=expected,
            minimum_rows=117,
            failures=failures,
        )
        self.assertTrue(any("latest row has missing" in failure for failure in failures))

    def test_non_positive_open_interest_is_rejected(self):
        expected = "S&P 500 Consolidated - CHICAGO MERCANTILE EXCHANGE"
        frame = self.position_frame(TFF_REQUIRED, expected)
        frame.loc[10, "open_interest"] = 0
        failures: list[str] = []
        validate_frame(
            frame,
            label="sp500 TFF",
            required=TFF_REQUIRED,
            expected_contract=expected,
            minimum_rows=117,
            failures=failures,
        )
        self.assertTrue(any("non-positive" in failure for failure in failures))

    def test_invalid_price_values_are_rejected(self):
        frame = pd.DataFrame({
            "date": pd.date_range("2025-01-01", periods=300, freq="B"),
            "price": [100.0] * 300,
        })
        frame.loc[20, "price"] = -1
        failures: list[str] = []
        validate_price_frame(frame, label="nq price", minimum_rows=260, failures=failures)
        self.assertTrue(any("non-positive" in failure for failure in failures))

    def test_latest_file_selection_uses_contained_date_not_mtime(self):
        with tempfile.TemporaryDirectory() as directory:
            older = Path(directory) / "z_newer_mtime.csv"
            newer = Path(directory) / "a_older_mtime.csv"
            pd.DataFrame({"date": ["2026-07-14"], "value": [1]}).to_csv(older, index=False)
            pd.DataFrame({"date": ["2026-07-21"], "value": [1]}).to_csv(newer, index=False)
            os.utime(older, (2_000_000_000, 2_000_000_000))
            os.utime(newer, (1_000_000_000, 1_000_000_000))
            self.assertEqual(select_latest_file([older, newer]), newer)


if __name__ == "__main__":
    unittest.main()
