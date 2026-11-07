#!/usr/bin/env python3
"""Canonical v1.1 dashboard injection with release and evidence context."""

from __future__ import annotations

import html
import json
from copy import deepcopy
from typing import Any

import inject_directional_dashboard as engine

START = engine.START
END = engine.END
inject = engine.inject
remove_existing = engine.remove_existing


def finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number else None


def compact_contracts(value: Any) -> str:
    number = finite(value)
    if number is None:
        return "n/a"
    sign = "+" if number > 0 else ""
    absolute = abs(number)
    if absolute >= 1_000_000:
        return f"{sign}{number / 1_000_000:.2f}m"
    if absolute >= 1_000:
        return f"{sign}{number / 1_000:.1f}k"
    return f"{sign}{number:.0f}"


def signed(value: Any, digits: int = 2, suffix: str = "") -> str:
    number = finite(value)
    if number is None:
        return "n/a"
    sign = "+" if number > 0 else ""
    return f"{sign}{number:.{digits}f}{suffix}"


def quality_panel(rows: list[dict[str, Any]]) -> str:
    cards: list[str] = []
    for row in rows:
        changes = row.get("position_changes") or []
        position_rows = "".join(
            f"<tr><td>{html.escape(str(item.get('label') or item.get('key')))}</td>"
            f"<td>{compact_contracts(item.get('delta_net'))}</td>"
            f"<td>{signed(item.get('delta_net_oi_pct'), 2, ' pp')}</td></tr>"
            for item in changes
        ) or "<tr><td colspan='3'>Weekly participant change unavailable</td></tr>"
        evidence = str(row.get("historical_evidence_state") or "Not graded")
        cap = finite(row.get("historical_evidence_exposure_cap"))
        cap_text = f"{cap:.2f}× cap" if cap is not None else "cap n/a"
        cards.append(
            f"<article class='directional-quality-card'>"
            f"<div class='directional-kicker'>{html.escape(str(row.get('market_label') or row.get('market')))}</div>"
            f"<div class='directional-quality-line'><strong>Historical validation:</strong> "
            f"{html.escape(evidence)} · {html.escape(cap_text)}</div>"
            f"<div class='directional-quality-line'><strong>Weekly signal:</strong> "
            f"{html.escape(str(row.get('weekly_signal_change') or 'Change unavailable'))} · "
            f"adjusted score {signed(row.get('adjusted_cot_score_change'))}</div>"
            f"<div class='directional-quality-meta'>Compared with COT report "
            f"{html.escape(str(row.get('previous_report_date') or 'n/a'))}.</div>"
            f"<table><thead><tr><th>Participant</th><th>Net contracts Δ</th><th>Net/OI Δ</th></tr></thead>"
            f"<tbody>{position_rows}</tbody></table></article>"
        )
    return f"""
<style>
.directional-quality-grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px;margin-top:14px}}.directional-quality-card{{background:var(--panel,#111827);border:1px solid var(--border,#334155);border-radius:14px;padding:15px}}.directional-quality-line{{margin-top:7px}}.directional-quality-meta{{font-size:12px;color:var(--muted,#94a3b8);margin:5px 0 10px}}.directional-quality-card table{{width:100%;border-collapse:collapse}}.directional-quality-card th,.directional-quality-card td{{padding:7px;border-bottom:1px solid var(--border,#334155);text-align:left}}.directional-quality-card th{{font-size:10px;color:var(--muted,#94a3b8)}}@media(max-width:760px){{.directional-quality-grid{{grid-template-columns:1fr}}}}
</style>
<div class="directional-quality-grid" id="directionalDecisionQuality">{''.join(cards)}</div>
"""


def build_block(rows: list[dict[str, Any]]) -> str:
    visual_rows = deepcopy(rows)
    catch_up: list[str] = []
    for row in visual_rows:
        if row.get("release_status") == "catch_up_delayed":
            catch_up.append(str(row.get("market_label") or row.get("market")))
            # Reuse the base warning visual while retaining the explicit action.
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

    return block.replace(END, quality_panel(rows) + "\n" + END, 1)


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
