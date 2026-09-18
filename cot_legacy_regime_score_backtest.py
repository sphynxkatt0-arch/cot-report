#!/usr/bin/env python3
"""Run the walk-forward COT regime engine against Legacy classifications."""

from __future__ import annotations

import cot_regime_score_backtest as engine


engine.CONFIG = engine.ROOT / "config" / "regime_rules_legacy.json"
engine.DATA_DIR = engine.ROOT / "cot_legacy_output"
engine.OUT_DIR = engine.ROOT / "cot_legacy_regime_backtest_output"
engine.DATASET_LABEL = "Legacy COT"
engine.CATEGORIES = ("noncommercial", "nonreportable")
engine.MARKETS = {
    "sp500": {
        "label": "S&P 500",
        "price_file": engine.PROJECT / "data" / "SP500.csv",
        "price_col": "SP500",
        "cot_glob": "sp500_legacy_data_*.csv",
    },
    "nq": {
        "label": "NASDAQ-100",
        "price_file": engine.PROJECT / "data" / "NASDAQ100.csv",
        "price_col": "NASDAQ100",
        "cot_glob": "nq_legacy_data_*.csv",
    },
    "vix": {
        "label": "VIX Futures",
        "price_file": engine.PROJECT / "data" / "VIXCLS.csv",
        "price_col": "VIXCLS",
        "cot_glob": "vix_legacy_data_*.csv",
    },
    "rty": {
        "label": "Russell 2000",
        "price_file": engine.PROJECT / "data" / "RUT.csv",
        "price_col": "RUT",
        "cot_glob": "rty_legacy_data_*.csv",
    },
    "dow": {
        "label": "Dow Jones",
        "price_file": engine.PROJECT / "data" / "DJIA.csv",
        "price_col": "DJIA",
        "cot_glob": "dow_legacy_data_*.csv",
    },
    "gold": {
        "label": "Gold",
        "price_file": engine.PROJECT / "data" / "GOLD.csv",
        "price_col": "GOLD",
        "cot_glob": "gold_legacy_data_*.csv",
    },
}


if __name__ == "__main__":
    engine.main()
