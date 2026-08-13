#!/usr/bin/env python3
"""Focused tests for deterministic v2 COT source-file selection."""
from __future__ import annotations

import tempfile
from pathlib import Path

import build_interactive_cot_dashboard_v2 as selector


def write_csv(path: Path, text: str) -> None:
    path.write_text(text.strip() + "\n", encoding="utf-8")


def test_latest_file_skips_summary_csv_without_dates() -> None:
    original_root = selector.ROOT
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write_csv(
            root / "cot_exact_summary_2016_2026.csv",
            "market,latest_report,source\nnq,2026-08-04,nq_exact_consolidated_data_2016_2026.csv",
        )
        older = root / "nq_exact_consolidated_data_2016_2025.csv"
        newer = root / "nq_exact_consolidated_data_2016_2026.csv"
        write_csv(older, "date,value\n2026-07-28,1\n2026-08-01,2")
        write_csv(newer, "date,value\n2026-07-28,1\n2026-08-04,3")
        selector.ROOT = root
        try:
            selected = selector.latest_file("*.csv")
        finally:
            selector.ROOT = original_root
    assert selected == newer


def test_latest_file_keeps_explicit_summary_metadata_globs() -> None:
    original_root = selector.ROOT
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        summary = root / "cot_exact_summary_2016_2026.csv"
        write_csv(summary, "market,latest_report\nnq,2026-08-04")
        selector.ROOT = root
        try:
            selected = selector.latest_file("cot_exact_summary_*.csv")
        finally:
            selector.ROOT = original_root
    assert selected == summary


def test_latest_file_fails_when_broad_glob_has_no_dated_sources() -> None:
    original_root = selector.ROOT
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write_csv(root / "cot_exact_summary_2016_2026.csv", "market,latest_report\nnq,2026-08-04")
        selector.ROOT = root
        try:
            try:
                selector.latest_file("*.csv")
            except RuntimeError as exc:
                assert "No valid dated COT source files" in str(exc)
            else:
                raise AssertionError("broad summary-only match should fail")
        finally:
            selector.ROOT = original_root


def main() -> None:
    test_latest_file_skips_summary_csv_without_dates()
    test_latest_file_keeps_explicit_summary_metadata_globs()
    test_latest_file_fails_when_broad_glob_has_no_dated_sources()
    print("interactive COT v2 source selection tests PASS")


if __name__ == "__main__":
    main()
