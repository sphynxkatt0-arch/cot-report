from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from compare_directional_models import (  # noqa: E402
    agreement_rows,
    model_summary_rows,
)
from inject_model_comparison_report import (  # noqa: E402
    START,
    build_block,
    remove_existing,
)


class ModelComparisonTests(unittest.TestCase):
    def aligned_frame(self) -> pd.DataFrame:
        rows = []
        for market_index, market in enumerate(("sp500", "nq")):
            for index in range(80):
                base = np.sin(index / 7.0 + market_index)
                rows.append({
                    "market": market,
                    "report_date": (pd.Timestamp("2020-01-07") + pd.Timedelta(weeks=index)).date().isoformat(),
                    "old_tff_score": base * 2.0,
                    "old_legacy_score": -base * 1.5,
                    "structural_score": base,
                    "adjusted_cot_score": np.clip(base + 0.15 * np.cos(index / 4.0), -1, 1),
                    "forward_return_1w": base * 0.4 + 0.1,
                    "forward_return_4w": base * 0.8 + 0.4,
                    "forward_return_13w": base * 1.5 + 1.0,
                    "forward_return_26w": base * 2.0 + 2.0,
                })
        return pd.DataFrame(rows)

    def test_summary_contains_all_32_model_horizon_combinations(self):
        rows = model_summary_rows(self.aligned_frame())
        self.assertEqual(len(rows), 32)
        combinations = {(row["market"], row["horizon"], row["model"]) for row in rows}
        self.assertEqual(len(combinations), 32)
        self.assertTrue(all(row["status"] == "exploratory_release_aligned" for row in rows))
        new_rows = [row for row in rows if row["model"] == "new_structural_tactical"]
        self.assertTrue(all(row["observations"] == 80 for row in new_rows))

    def test_agreement_contains_six_pairs_per_market(self):
        rows = agreement_rows(self.aligned_frame())
        self.assertEqual(len(rows), 12)
        self.assertTrue(all(row["overlap_n"] == 80 for row in rows))

    def test_report_block_is_idempotent_when_replaced(self):
        summary = model_summary_rows(self.aligned_frame())
        agreement = agreement_rows(self.aligned_frame())
        block = build_block(summary, agreement)
        source = f"<html><body><main>{block}<footer>Footer</footer></main></body></html>"
        clean = remove_existing(source)
        insertion = clean.find("<footer>")
        twice = clean[:insertion] + block + clean[insertion:]
        self.assertEqual(twice.count(START), 1)
        self.assertIn('id="modelComparisonPanel"', twice)
        self.assertIn("Old TFF regime", twice)
        self.assertIn("New NC + TFF tactical", twice)


if __name__ == "__main__":
    unittest.main()
