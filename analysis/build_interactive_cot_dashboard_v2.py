#!/usr/bin/env python3
"""Build the source dashboard with deterministic data-content file selection.

The legacy builder's UI is retained because it is still the normalized source
container for COT_DATA/PRICE_DATA/MACRO_MONITOR. Only its source-file selector is
replaced: candidates are ranked by their contained maximum observation date,
then valid row coverage and deterministic pathname. Filesystem mtime is ignored.
"""
from __future__ import annotations
from pathlib import Path
from typing import Any
import pandas as pd
import build_interactive_cot_dashboard as legacy

ROOT=Path(__file__).resolve().parent

def file_rank(path:Path)->tuple[str,int,str]:
    try:
        df=pd.read_csv(path,usecols=lambda c:str(c).strip().lower() in {'date','report_date'})
    except Exception as exc:
        raise RuntimeError(f'cannot inspect candidate COT source {path}: {exc}') from exc
    date_col='date' if 'date' in df.columns else ('report_date' if 'report_date' in df.columns else None)
    if date_col is None:raise RuntimeError(f'candidate COT source has no date column: {path}')
    parsed=pd.to_datetime(df[date_col],errors='coerce').dropna()
    if parsed.empty:raise RuntimeError(f'candidate COT source has no valid dates: {path}')
    return (parsed.max().strftime('%Y-%m-%d'),int(parsed.nunique()),path.as_posix())

def latest_file(pattern:str)->Path:
    matches=list(ROOT.glob(pattern))
    if not matches:raise FileNotFoundError(f'No files match {ROOT/pattern}')
    ranked=sorted(((file_rank(path),path) for path in matches),key=lambda item:item[0])
    best_rank,best=ranked[-1]
    print(f'Source selection {pattern}: {best.name} latest={best_rank[0]} dated_rows={best_rank[1]} (mtime ignored)')
    return best

def main()->None:
    original=legacy.latest_file;legacy.latest_file=latest_file
    try:legacy.main()
    finally:legacy.latest_file=original
if __name__=='__main__':main()
