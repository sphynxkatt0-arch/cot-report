#!/usr/bin/env python3
"""Shared directional-model I/O helpers and backward-compatible launcher.

The original standalone v1 builder has been retired. Running this file directly
now delegates to the integrated cached-data workflow so there is no code path
that can silently bypass release tracking, macro freshness, trend-aware price
execution, output validation, or dashboard injection.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pandas as pd

from cot_direction_model import percentile_rank_prior, rank_score

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parent
OUT_DIR = ROOT / "model_output"
HTML_OUT = ROOT / "directional_cot_report.html"

MARKETS = {
    "sp500": {
        "label": "S&P 500",
        "legacy_glob": "cot_legacy_output/sp500_legacy_data_*.csv",
        "tff_glob": "cot_exact_output/sp500_exact_consolidated_data_*.csv",
        "price_path": PROJECT / "data" / "SP500.csv",
        "price_col": "SP500",
    },
    "nq": {
        "label": "NASDAQ-100",
        "legacy_glob": "cot_legacy_output/nq_legacy_data_*.csv",
        "tff_glob": "cot_exact_output/nq_exact_consolidated_data_*.csv",
        "price_path": PROJECT / "data" / "NASDAQ100.csv",
        "price_col": "NASDAQ100",
    },
}


def latest_file(pattern: str) -> Path:
    matches = sorted(ROOT.glob(pattern), key=lambda path: path.stat().st_mtime)
    if not matches:
        raise FileNotFoundError(f"No file matched {ROOT / pattern}")
    return matches[-1]


def read_position_file(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path)
    if "date" not in frame.columns:
        raise KeyError(f"{path} has no date column")
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    return (
        frame.dropna(subset=["date"])
        .sort_values("date")
        .drop_duplicates("date", keep="last")
        .reset_index(drop=True)
    )


def read_prices(path: Path, value_col: str) -> pd.DataFrame:
    frame = pd.read_csv(path)
    frame.columns = [str(col).strip().lstrip("\ufeff") for col in frame.columns]
    date_col = "observation_date" if "observation_date" in frame.columns else "date"
    if date_col not in frame.columns:
        raise KeyError(f"{path} has no observation_date or date column")
    if value_col not in frame.columns:
        raise KeyError(f"{path} has no {value_col} column")
    frame["date"] = pd.to_datetime(frame[date_col], errors="coerce")
    frame["price"] = pd.to_numeric(frame[value_col], errors="coerce")
    return frame[["date", "price"]].dropna().sort_values("date").reset_index(drop=True)


def expanding_percentile(values: pd.Series, minimum: int) -> float | None:
    clean = pd.to_numeric(values, errors="coerce").dropna()
    if len(clean) < minimum:
        return None
    return percentile_rank_prior(clean.iloc[:-1], clean.iloc[-1], minimum=minimum - 1)


def trend_rank(frame: pd.DataFrame, column: str, weeks: int, minimum: int) -> float | None:
    if column not in frame.columns:
        return None
    values = pd.to_numeric(frame[column], errors="coerce")
    trends = values - values.shift(weeks)
    return rank_score(expanding_percentile(trends, minimum))


def flow_rank(frame: pd.DataFrame, column: str, weeks: int, minimum: int) -> float | None:
    return trend_rank(frame, column, weeks, minimum)


def price_at_or_after(prices: pd.DataFrame, target: pd.Timestamp) -> tuple[str | None, float | None]:
    eligible = prices.loc[prices["date"] >= target]
    if eligible.empty:
        return None, None
    row = eligible.iloc[0]
    return row["date"].date().isoformat(), float(row["price"])


def latest_price(prices: pd.DataFrame) -> tuple[str | None, float | None]:
    if prices.empty:
        return None, None
    row = prices.iloc[-1]
    return row["date"].date().isoformat(), float(row["price"])


def extract_js_object(source: str, variable: str) -> dict[str, Any] | None:
    """Read a JSON object assigned as `const NAME = <json>;` in generated HTML."""
    marker = f"const {variable} = "
    start = source.find(marker)
    if start < 0:
        return None
    index = start + len(marker)
    depth = 0
    in_string = False
    escaped = False
    for cursor in range(index, len(source)):
        char = source[cursor]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char in "[{":
            depth += 1
        elif char in "]}":
            depth -= 1
            if depth < 0:
                return None
        elif char == ";" and depth == 0:
            try:
                parsed = json.loads(source[index:cursor])
            except json.JSONDecodeError:
                return None
            return parsed if isinstance(parsed, dict) else None
    return None


def tone_class(value: str) -> str:
    lower = value.lower()
    if "delayed" in lower or "awaiting" in lower:
        return "warning"
    if "long" in lower or "bull" in lower or "support" in lower or "confirmed" in lower:
        return "positive"
    if "short" in lower or "bear" in lower or "risk-off" in lower or "invalid" in lower or "override" in lower:
        return "negative"
    return "neutral"


def main() -> None:
    command = [
        sys.executable,
        str(ROOT / "refresh_directional_cot_system.py"),
        "--skip-public-refresh",
    ]
    print("Deprecated standalone entry point; running integrated cached-data workflow:")
    print("$", " ".join(command))
    subprocess.run(command, cwd=ROOT, check=True)


if __name__ == "__main__":
    main()
