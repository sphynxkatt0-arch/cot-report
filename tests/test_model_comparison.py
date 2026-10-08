from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from compare_directional_models_v11 import (  # noqa: E402
    agreement_rows,
    hac_slope_stats,
    model_summary_rows,
)
from inject_model_comparison_report_v11 import (  # noqa: E402
    START,
    build_block,
    remove_existing,
)


class ModelComparisonTests(unittest.TestCase):
    def aligned_frame(self) -> pd.DataFrame:
        rows = []
        for market_index, market in enumerate(("sp500", "nq")):
            for index in range(120):
                base = np.sin(index / 7.0 + market_index)
                tactical = np.clip(base + 0.15 * np.cos(index / 4.0), -1, 1)
                row = {
                    "market": market,
                    "report_date": (pd.Timestamp("2020-01-07") + pd.Timedelta(weeks=index)).date().isoformat(),
                    "old_tff_score": base * 2.0,
                    "old_legacy_score": -base * 1.5,
                    "structural_score": base,
                    "adjusted_cot_score": tactical,
                    "release_decision_score": tactical * (0.75 + 0.15 * np.sin(index / 11.0)),
                }
                for horizon, scale in (("1w", 0.4), ("4w", 0.8), ("13w", 1.5), ("26w", 2.0)):
                    terminal = base * scale + scale * 0.25
                    row[f"forward_return_{horizon}"] = terminal
                    row[f"forward_worst_path_return_{horizon}"] = min(0.0, terminal - abs(scale) * 0.8)
                    row[f"forward_best_path_return_{horizon}"] = max(0.0, terminal + abs(scale) * 0.9)
                rows.append(row)
        return pd.DataFrame(rows)

    def test_hac_slope_detects_clear_positive_relationship(self):
        x = pd.Series(np.linspace(-1, 1, 120))
        y = 2.5 * x + np.sin(np.arange(120) / 8.0) * 0.05
        result = hac_slope_stats(x, y, lags=4)
        self.assertGreater(result["slope"], 2.4)
        self.assertLess(result["hac_p"], 0.01)

    def test_summary_contains_all_40_model_horizon_combinations(self):
        rows = model_summary_rows(self.aligned_frame())
        self.assertEqual(len(rows), 40)
        combinations = {(row["market"], row["horizon"], row["model"]) for row in rows}
        self.assertEqual(len(combinations), 40)
        self.assertTrue(all(row["status"] == "exploratory_release_aligned_hac" for row in rows))
        new_rows = [row for row in rows if row["model"] in {"new_structural_tactical", "new_release_decision"}]
        self.assertTrue(all(row["observations"] == 120 for row in new_rows))
        self.assertTrue(all(row["directional_n"] > 0 for row in new_rows))
        self.assertTrue(all(row["avg_adverse_move"] <= 0 for row in new_rows))
        self.assertTrue(all(row["stability_subperiods"] == 3 for row in new_rows))
        self.assertTrue(all(row["score_hac_p"] is not None for row in new_rows))

    def test_agreement_contains_ten_pairs_per_market(self):
        rows = agreement_rows(self.aligned_frame())
        self.assertEqual(len(rows), 20)
        self.assertTrue(all(row["overlap_n"] == 120 for row in rows))

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
        self.assertIn("New full release decision", twice)
        self.assertIn("HAC p", twice)
        self.assertIn("Path utility", twice)


if __name__ == "__main__":
    unittest.main()
