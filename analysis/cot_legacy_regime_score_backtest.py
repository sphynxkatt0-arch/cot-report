#!/usr/bin/env python3
"""Run the walk-forward COT regime engine against Legacy classifications."""

from __future__ import annotations

import cot_regime_score_backtest as engine


engine.CONFIG = engine.ROOT / "config" / "regime_rules_legacy.json"
engine.DATA_DIR = engine.ROOT / "cot_legacy_output"
engine.OUT_DIR = engine.ROOT / "cot_legacy_regime_backtest_output"
engine.DATASET_LABEL = "Legacy COT"
engine.CATEGORIES = ("noncommercial", "commercial", "nonreportable")
engine.MARKETS["sp500"]["cot_glob"] = "sp500_legacy_data_*.csv"
engine.MARKETS["nq"]["cot_glob"] = "nq_legacy_data_*.csv"


if __name__ == "__main__":
    engine.main()
