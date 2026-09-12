#!/usr/bin/env python3
"""Canonical v1.1 model-comparison report injection."""

from __future__ import annotations

import inject_model_comparison_report as engine

engine.MODEL_LABELS["new_release_decision"] = "New full release decision"

START = engine.START
END = engine.END
MODEL_LABELS = engine.MODEL_LABELS
build_block = engine.build_block
ordered_rows = engine.ordered_rows
read_csv = engine.read_csv
remove_existing = engine.remove_existing


def main() -> None:
    engine.main()


if __name__ == "__main__":
    main()
