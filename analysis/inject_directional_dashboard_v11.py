#!/usr/bin/env python3
"""Canonical v1.1 dashboard injection with delayed catch-up presentation."""

from __future__ import annotations

import json
from copy import deepcopy

import inject_directional_dashboard as engine

START = engine.START
END = engine.END
inject = engine.inject
remove_existing = engine.remove_existing


def build_block(rows):
    visual_rows = deepcopy(rows)
    catch_up = []
    for row in visual_rows:
        if row.get("release_status") == "catch_up_delayed":
            catch_up.append(str(row.get("market_label") or row.get("market")))
            # Reuse the base delayed-warning layout while the action text retains
            # the explicit catch-up state.
            row["release_status"] = "delayed"
    block = engine.build_block(visual_rows)
    if catch_up:
        block = block.replace(
            "<strong>CFTC release delayed:</strong>",
            "<strong>CFTC delayed/catch-up release:</strong>",
            1,
        )
        block = block.replace(
            "keeps the prior signal; no new recommendation is issued.",
            "is not fully current; positioning is shown for context and no new exposure is permitted.",
            1,
        )
    return block


def main() -> None:
    if not engine.DASHBOARD.exists():
        raise FileNotFoundError(f"Missing {engine.DASHBOARD}")
    if not engine.DECISIONS.exists():
        raise FileNotFoundError(
            f"Missing {engine.DECISIONS}; run refresh_directional_cot_system.py first"
        )
    rows = json.loads(engine.DECISIONS.read_text(encoding="utf-8"))
    if not isinstance(rows, list) or not rows:
        raise ValueError("Directional decision JSON is empty")
    source = engine.DASHBOARD.read_text(encoding="utf-8", errors="replace")
    engine.DASHBOARD.write_text(inject(source, build_block(rows)), encoding="utf-8")
    print(f"Injected v1.1 decision summary into {engine.DASHBOARD}")


if __name__ == "__main__":
    main()
