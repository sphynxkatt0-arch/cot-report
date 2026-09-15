#!/usr/bin/env python3
"""Add descriptive week-over-week participant changes for every governed market."""
from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

import pandas as pd

from build_directional_cot_system import HTML_OUT, OUT_DIR, common_report_dates, feature_snapshot, load_market_inputs, write_csv
from cot_direction_model import load_config, preserve_structural_sign, structural_score_from_percentile, tactical_modifier
from cot_market_registry import DIRECTIONAL_MARKETS, EQUITY_PARTICIPANTS, MARKETS

CATEGORY_SPECS = EQUITY_PARTICIPANTS

ROOT = Path(__file__).resolve().parent
DECISION_JSON = OUT_DIR / "cot_direction_latest.json"
DECISION_CSV = OUT_DIR / "cot_direction_latest.csv"
CHANGE_CSV = OUT_DIR / "cot_position_changes_latest.csv"
START = "<!-- WEEKLY_POSITION_CHANGE_START -->"
END = "<!-- WEEKLY_POSITION_CHANGE_END -->"


def finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number else None


def rounded(value: Any, digits: int = 4) -> float | None:
    number = finite(value)
    return round(number, digits) if number is not None else None


def difference(current: Any, previous: Any, digits: int = 4) -> float | None:
    a, b = finite(current), finite(previous)
    return round(a - b, digits) if a is not None and b is not None else None


def row_at(frame: pd.DataFrame, report_ts: pd.Timestamp) -> pd.Series | None:
    rows = frame.loc[frame["date"] == report_ts]
    return None if rows.empty else rows.iloc[-1]


def net_value(row: pd.Series | None, spec: dict[str, str]) -> float | None:
    if row is None:
        return None
    direct = finite(row.get(spec["net"])) if spec["net"] in row.index else None
    if direct is not None:
        return direct
    long_value = finite(row.get(spec["long"])) if spec["long"] in row.index else None
    short_value = finite(row.get(spec["short"])) if spec["short"] in row.index else None
    return long_value - short_value if long_value is not None and short_value is not None else None


def category_change(
    spec: dict[str, str],
    legacy: pd.DataFrame,
    secondary: pd.DataFrame,
    current_ts: pd.Timestamp,
    previous_ts: pd.Timestamp,
) -> dict[str, Any]:
    frame = legacy if spec["source"] == "legacy" else secondary
    current_row = row_at(frame, current_ts)
    previous_row = row_at(frame, previous_ts)
    current_net = net_value(current_row, spec)
    previous_net = net_value(previous_row, spec)
    current_pct = finite(current_row.get(spec["net_oi_pct"])) if current_row is not None and spec["net_oi_pct"] in current_row.index else None
    previous_pct = finite(previous_row.get(spec["net_oi_pct"])) if previous_row is not None and spec["net_oi_pct"] in previous_row.index else None
    return {
        "key": spec["key"],
        "label": spec["label"],
        "current_net": rounded(current_net, 1),
        "previous_net": rounded(previous_net, 1),
        "delta_net": difference(current_net, previous_net, 1),
        "current_net_oi_pct": rounded(current_pct, 4),
        "previous_net_oi_pct": rounded(previous_pct, 4),
        "delta_net_oi_pct": difference(current_pct, previous_pct, 4),
    }


def weekly_signal_state(current_score: float | None, previous_score: float | None, *, threshold: float = 0.25, material_delta: float = 0.10) -> str:
    current, previous = finite(current_score), finite(previous_score)
    if current is None or previous is None:
        return "Change unavailable"
    current_side = 1 if current >= threshold else -1 if current <= -threshold else 0
    previous_side = 1 if previous >= threshold else -1 if previous <= -threshold else 0
    side_label = "bullish" if current_side > 0 else "bearish"
    if previous_side == 0 and current_side != 0:
        return f"New {side_label} COT signal"
    if previous_side != 0 and current_side == 0:
        return "COT signal neutralized"
    if previous_side != 0 and current_side != 0 and previous_side != current_side:
        return f"COT direction flipped {side_label}"
    magnitude_change = abs(current) - abs(previous)
    if magnitude_change >= material_delta:
        return "COT signal strengthened"
    if magnitude_change <= -material_delta:
        return "COT signal weakened"
    return "COT signal little changed"


def score_snapshot(market: str, legacy: pd.DataFrame, secondary: pd.DataFrame, report_ts: pd.Timestamp, config: dict[str, Any]) -> dict[str, Any]:
    snapshot = feature_snapshot(legacy, secondary, report_ts, int(config["minimum_history_weeks"]), market)
    structural = structural_score_from_percentile(snapshot["noncommercial_percentile"], config)
    tactical, _ = tactical_modifier(
        structural,
        snapshot["other_reportable_trend13_rank"],
        snapshot["nonreportable_trend13_rank"],
        snapshot["noncommercial_flow4_rank"],
        config,
    )
    return {**snapshot, "structural_score": structural, "tactical_modifier": tactical, "adjusted_cot_score": preserve_structural_sign(structural, tactical)}


def build_market_change(market: str, legacy: pd.DataFrame, secondary: pd.DataFrame, config: dict[str, Any]) -> dict[str, Any]:
    dates = common_report_dates(legacy, secondary)
    if len(dates) < 2:
        return {"market": market, "previous_report_date": None, "weekly_signal_change": "Change unavailable", "weekly_signal_material": False, "position_changes": []}
    previous_ts, current_ts = dates[-2], dates[-1]
    current = score_snapshot(market, legacy, secondary, current_ts, config)
    previous = score_snapshot(market, legacy, secondary, previous_ts, config)
    changes = [category_change(dict(spec), legacy, secondary, current_ts, previous_ts) for spec in MARKETS[market]["participant_specs"]]
    state = weekly_signal_state(current["adjusted_cot_score"], previous["adjusted_cot_score"])
    material_position_move = any(abs(float(item["delta_net_oi_pct"])) >= 0.5 for item in changes if item.get("delta_net_oi_pct") is not None)
    return {
        "market": market,
        "previous_report_date": previous_ts.date().isoformat(),
        "weekly_signal_change": state,
        "weekly_signal_material": state != "COT signal little changed" or material_position_move,
        "previous_structural_score": rounded(previous["structural_score"]),
        "structural_score_change": difference(current["structural_score"], previous["structural_score"]),
        "previous_tactical_modifier": rounded(previous["tactical_modifier"]),
        "tactical_modifier_change": difference(current["tactical_modifier"], previous["tactical_modifier"]),
        "previous_adjusted_cot_score": rounded(previous["adjusted_cot_score"]),
        "adjusted_cot_score_change": difference(current["adjusted_cot_score"], previous["adjusted_cot_score"]),
        "noncommercial_percentile_change": difference(current["noncommercial_percentile"], previous["noncommercial_percentile"], 2),
        "asset_manager_percentile_change": difference(current["asset_manager_percentile"], previous["asset_manager_percentile"], 2),
        "position_changes": changes,
    }


def enrich_decisions(decisions: list[dict[str, Any]], changes_by_market: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for raw in decisions:
        row = dict(raw)
        row.update(changes_by_market.get(str(row.get("market")), {}))
        output.append(row)
    return output


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


def fmt_delta(value: Any, digits: int = 2, suffix: str = "") -> str:
    number = finite(value)
    if number is None:
        return "n/a"
    return f"{'+' if number > 0 else ''}{number:.{digits}f}{suffix}"


def change_panel(rows: list[dict[str, Any]]) -> str:
    cards: list[str] = []
    for row in rows:
        position_rows = "".join(
            f"<tr><td>{html.escape(str(item.get('label') or item.get('key')))}</td><td>{compact_contracts(item.get('delta_net'))}</td><td>{fmt_delta(item.get('delta_net_oi_pct'), 2, ' pp')}</td></tr>"
            for item in row.get("position_changes") or []
        ) or "<tr><td colspan='3'>Position change unavailable</td></tr>"
        cards.append(
            f"<article class='weekly-change-card'><div class='weekly-change-kicker'>{html.escape(str(row.get('market_label') or row.get('market')))}</div>"
            f"<h3>{html.escape(str(row.get('weekly_signal_change') or 'Change unavailable'))}</h3>"
            f"<p>Versus report {html.escape(str(row.get('previous_report_date') or 'n/a'))}; adjusted COT score {fmt_delta(row.get('adjusted_cot_score_change'))}.</p>"
            f"<table><thead><tr><th>Participant</th><th>Net contracts Δ</th><th>Net/OI Δ</th></tr></thead><tbody>{position_rows}</tbody></table></article>"
        )
    return f"""{START}
<style>
.weekly-change-panel{{margin-top:18px}}.weekly-change-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:18px}}.weekly-change-card{{background:linear-gradient(145deg,var(--panel,#0e1b2d),var(--panel2,#14243a));border:1px solid var(--line,#263b55);border-radius:18px;padding:20px}}.weekly-change-kicker{{text-transform:uppercase;letter-spacing:.12em;font-size:11px;font-weight:800;color:var(--muted,#9fb0c6)}}.weekly-change-card h3{{margin:5px 0 7px}}.weekly-change-card table{{width:100%;border-collapse:collapse}}.weekly-change-card th,.weekly-change-card td{{padding:8px;border-bottom:1px solid var(--line,#263b55);text-align:left}}.weekly-change-card th{{font-size:11px;color:var(--muted,#9fb0c6)}}
</style>
<section class="panel weekly-change-panel" id="weeklyPositionChange"><div class="panel-head"><div><div class="kicker">Latest CFTC movement</div><h3>What changed this week</h3></div><span class="badge">Descriptive, not a new vote</span></div><p>Contract changes use the two latest common Legacy and secondary-report dates. Participant labels follow TFF for financial indices and Disaggregated for Gold.</p><div class="weekly-change-grid">{''.join(cards)}</div></section>
{END}"""


def inject_panel(source: str, panel: str) -> str:
    start, end = source.find(START), source.find(END)
    if start >= 0 and end >= start:
        source = source[:start] + source[end + len(END):]
    insertion = source.find("<footer>")
    if insertion < 0:
        insertion = source.find("</main>")
    if insertion < 0:
        raise ValueError("Directional report has no footer/main insertion point")
    return source[:insertion] + panel + source[insertion:]


def main() -> None:
    try:
        decisions = json.loads(DECISION_JSON.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Cannot read {DECISION_JSON}: {exc}") from exc
    if not isinstance(decisions, list) or not decisions:
        raise ValueError("Directional decision JSON is empty")
    config = load_config(ROOT / "config" / "cot_direction_model_v1.json")
    changes_by_market: dict[str, dict[str, Any]] = {}
    detailed_rows: list[dict[str, Any]] = []
    for market in DIRECTIONAL_MARKETS:
        legacy, secondary, _prices = load_market_inputs(market)
        change = build_market_change(market, legacy, secondary, config)
        changes_by_market[market] = change
        for item in change.get("position_changes") or []:
            detailed_rows.append({
                "market": market,
                "report_date": next((row.get("report_date") for row in decisions if row.get("market") == market), None),
                "previous_report_date": change.get("previous_report_date"),
                **item,
            })
    enriched = enrich_decisions(decisions, changes_by_market)
    DECISION_JSON.write_text(json.dumps(enriched, indent=2) + "\n", encoding="utf-8")
    write_csv(DECISION_CSV, enriched)
    write_csv(CHANGE_CSV, detailed_rows)
    HTML_OUT.write_text(inject_panel(HTML_OUT.read_text(encoding="utf-8", errors="replace"), change_panel(enriched)), encoding="utf-8")
    for row in enriched:
        print(f"{row.get('market_label')}: {row.get('weekly_signal_change')} | score delta {row.get('adjusted_cot_score_change')}")


if __name__ == "__main__":
    main()
