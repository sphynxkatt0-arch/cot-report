#!/usr/bin/env python3
"""Build a decision-first COT report without replacing the macro dashboard.

Outputs:
  model_output/cot_direction_latest.json
  model_output/cot_direction_latest.csv
  directional_cot_report.html
"""

from __future__ import annotations

import argparse
import csv
import html
import json
from pathlib import Path
from typing import Any

import pandas as pd

from cot_direction_model import (
    build_decision,
    load_config,
    percentile_rank_prior,
    rank_score,
    scheduled_release_date,
)

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
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    return frame.dropna(subset=["date"]).sort_values("date").drop_duplicates("date", keep="last").reset_index(drop=True)


def read_prices(path: Path, value_col: str) -> pd.DataFrame:
    frame = pd.read_csv(path)
    frame.columns = [str(col).strip().lstrip("\ufeff") for col in frame.columns]
    date_col = "observation_date" if "observation_date" in frame.columns else "date"
    frame["date"] = pd.to_datetime(frame[date_col], errors="coerce")
    frame["price"] = pd.to_numeric(frame[value_col], errors="coerce")
    return frame[["date", "price"]].dropna().sort_values("date").reset_index(drop=True)


def expanding_percentile(values: pd.Series, minimum: int) -> float | None:
    clean = pd.to_numeric(values, errors="coerce").dropna()
    if len(clean) < minimum:
        return None
    return percentile_rank_prior(clean.iloc[:-1], clean.iloc[-1], minimum=minimum - 1)


def trend_rank(frame: pd.DataFrame, column: str, weeks: int, minimum: int) -> float | None:
    values = pd.to_numeric(frame[column], errors="coerce")
    trends = values - values.shift(weeks)
    percentile = expanding_percentile(trends, minimum)
    return rank_score(percentile)


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
        elif char == ";" and depth == 0:
            try:
                return json.loads(source[index:cursor])
            except json.JSONDecodeError:
                return None
    return None


def load_macro_context() -> tuple[float | None, bool, str]:
    dashboard = ROOT / "interactive_cot_dashboard.html"
    if not dashboard.exists():
        return None, False, "Macro dashboard unavailable"
    payload = extract_js_object(dashboard.read_text(encoding="utf-8", errors="replace"), "MACRO_MONITOR")
    latest = (payload or {}).get("latest") or {}
    score = latest.get("liquidity_score")
    try:
        score_value = float(score)
    except (TypeError, ValueError):
        return None, False, "Macro score unavailable"
    alerts = (payload or {}).get("alerts") or []
    severe = [row for row in alerts if row.get("triggered") and str(row.get("severity")) == "red"]
    return score_value, len(severe) >= 2, "; ".join(str(row.get("label")) for row in severe) or "No hard override"


def build_market_decision(market: str, config: dict[str, Any]) -> dict[str, Any]:
    meta = MARKETS[market]
    legacy_path = latest_file(meta["legacy_glob"])
    tff_path = latest_file(meta["tff_glob"])
    legacy = read_position_file(legacy_path)
    tff = read_position_file(tff_path)
    prices = read_prices(meta["price_path"], meta["price_col"])
    minimum = int(config["minimum_history_weeks"])

    common_dates = sorted(set(legacy["date"]).intersection(set(tff["date"])))
    if not common_dates:
        raise RuntimeError(f"{market}: Legacy and TFF have no common report date")
    report_ts = pd.Timestamp(common_dates[-1])
    legacy = legacy.loc[legacy["date"] <= report_ts].copy()
    tff = tff.loc[tff["date"] <= report_ts].copy()

    nc_percentile = expanding_percentile(legacy["noncommercial_net_oi_pct"], minimum)
    am_percentile = expanding_percentile(tff["asset_mgr_net_oi_pct"], minimum)
    other_trend_rank = trend_rank(tff, "other_reportable_net_oi_pct", 13, minimum)
    nonreportable_trend_rank = trend_rank(tff, "non_reportable_net_oi_pct", 13, minimum)
    nc_flow_rank = flow_rank(legacy, "noncommercial_net_oi_pct", 4, minimum)

    release = scheduled_release_date(report_ts)
    signal_price_date, signal_price = price_at_or_after(prices, pd.Timestamp(release))
    latest_price_date, current_price = latest_price(prices)
    macro_score, macro_override, macro_override_detail = load_macro_context()

    decision = build_decision(
        market=market,
        report_date=report_ts.date().isoformat(),
        actual_release_date=release.isoformat(),
        release_date_source="scheduled_assumption",
        signal_price_date=signal_price_date,
        latest_price_date=latest_price_date,
        signal_price=signal_price,
        latest_price=current_price,
        noncommercial_percentile=nc_percentile,
        other_reportable_trend13_rank=other_trend_rank,
        nonreportable_trend13_rank=nonreportable_trend_rank,
        noncommercial_flow4_rank=nc_flow_rank,
        asset_manager_percentile_value=am_percentile,
        macro_score_value=macro_score,
        macro_override=macro_override,
        config=config,
    ).to_dict()
    decision.update({
        "market_label": meta["label"],
        "macro_override_detail": macro_override_detail,
        "signal_price": signal_price,
        "latest_price": current_price,
        "other_reportable_trend13_rank": other_trend_rank,
        "nonreportable_trend13_rank": nonreportable_trend_rank,
        "noncommercial_flow4_rank": nc_flow_rank,
        "source_legacy": str(legacy_path.relative_to(ROOT)),
        "source_tff": str(tff_path.relative_to(ROOT)),
    })
    return decision


def tone_class(value: str) -> str:
    lower = value.lower()
    if "long" in lower or "bull" in lower or "support" in lower or "confirmed" in lower:
        return "positive"
    if "short" in lower or "bear" in lower or "risk-off" in lower or "invalid" in lower:
        return "negative"
    return "neutral"


def fmt(value: Any, digits: int = 2, suffix: str = "") -> str:
    if value is None:
        return "n/a"
    try:
        return f"{float(value):.{digits}f}{suffix}"
    except (TypeError, ValueError):
        return html.escape(str(value))


def render_html(decisions: list[dict[str, Any]]) -> str:
    generated = pd.Timestamp.now(tz="UTC").isoformat()
    cards = []
    details = []
    for row in decisions:
        action_cls = tone_class(str(row["final_action"]))
        cards.append(f"""
        <article class="decision-card {action_cls}">
          <div class="kicker">{html.escape(row['market_label'])}</div>
          <h2>{html.escape(row['final_action'])}</h2>
          <div class="bias">{html.escape(row['structural_bias'])} · {html.escape(row['execution_state'])}</div>
          <div class="metric-grid">
            <div><span>Structural</span><strong>{fmt(row['structural_score'])}</strong></div>
            <div><span>Tactical</span><strong>{fmt(row['tactical_modifier'])}</strong></div>
            <div><span>Exposure</span><strong>{fmt(row['exposure_multiplier'])}×</strong></div>
            <div><span>Confidence</span><strong>{html.escape(row['confidence_label'])}</strong></div>
          </div>
          <p>Report {html.escape(row['report_date'])}; actionable from {html.escape(row['actual_release_date'])}. Price since release: {fmt(row['price_change_since_release_pct'], 2, '%')}.</p>
        </article>
        """)
        tactical_rows = "".join(
            f"<tr><td>{html.escape(item['label'])}</td><td>{fmt(item['rank_score'])}</td><td>{fmt(item['contribution'])}</td></tr>"
            for item in row.get("tactical_components") or []
        ) or "<tr><td colspan='3'>No tactical contribution</td></tr>"
        reasons = "".join(f"<li>{html.escape(reason)}</li>" for reason in row.get("reasons") or [])
        details.append(f"""
        <section class="panel">
          <div class="panel-head"><div><div class="kicker">{html.escape(row['market_label'])}</div><h3>Decision evidence</h3></div><span class="badge">{html.escape(row['model_version'])}</span></div>
          <div class="evidence-grid">
            <div><span>NC percentile</span><strong>{fmt(row['noncommercial_percentile'], 1, '%')}</strong></div>
            <div><span>AM percentile</span><strong>{fmt(row['asset_manager_percentile'], 1, '%')}</strong></div>
            <div><span>Macro score</span><strong>{fmt(row['macro_score'], 0, '/100')}</strong></div>
            <div><span>Macro state</span><strong>{html.escape(row['macro_state'])}</strong></div>
          </div>
          <div class="columns">
            <div><h4>Reason chain</h4><ul>{reasons}</ul></div>
            <div><h4>Tactical contributions</h4><table><thead><tr><th>Input</th><th>Rank</th><th>Contribution</th></tr></thead><tbody>{tactical_rows}</tbody></table></div>
          </div>
          <p class="note">Legacy Non-commercials set direction. TFF can only adjust conviction. Asset Managers and macro adjust size. Price controls execution. Release date is currently a scheduled Friday assumption; delayed historical publication metadata is not yet available.</p>
        </section>
        """)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Directional COT Report</title>
<style>
:root{{--bg:#07111f;--panel:#0e1b2d;--panel2:#14243a;--text:#f5f7fb;--muted:#9fb0c6;--line:#263b55;--pos:#37d391;--neg:#ff6b75;--accent:#6aa8ff}}
*{{box-sizing:border-box}}body{{margin:0;background:linear-gradient(160deg,#07111f,#0b1627 55%,#07111f);color:var(--text);font:15px/1.55 Inter,system-ui,sans-serif}}main{{max-width:1180px;margin:auto;padding:32px 20px 60px}}header{{display:flex;justify-content:space-between;gap:24px;align-items:flex-end;margin-bottom:24px}}h1{{font-size:clamp(30px,5vw,54px);line-height:1;margin:5px 0 10px}}h2{{font-size:28px;margin:8px 0}}h3{{font-size:22px;margin:4px 0}}h4{{margin:0 0 10px}}p{{color:var(--muted)}}a{{color:#9ec5ff}}.kicker{{text-transform:uppercase;letter-spacing:.13em;color:#82a8d6;font-size:12px;font-weight:700}}.actions a{{display:inline-block;border:1px solid var(--line);padding:9px 13px;border-radius:10px;text-decoration:none;background:var(--panel)}}.decision-grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px}}.decision-card,.panel{{background:linear-gradient(145deg,var(--panel),var(--panel2));border:1px solid var(--line);border-radius:18px;padding:22px;box-shadow:0 18px 50px rgba(0,0,0,.18)}}.decision-card.positive{{border-color:rgba(55,211,145,.6)}}.decision-card.negative{{border-color:rgba(255,107,117,.6)}}.bias{{font-weight:700;color:var(--accent)}}.metric-grid,.evidence-grid{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin:20px 0}}.metric-grid div,.evidence-grid div{{background:rgba(5,12,22,.45);border:1px solid var(--line);border-radius:12px;padding:12px}}span{{display:block;color:var(--muted);font-size:12px}}strong{{font-size:18px}}.panel{{margin-top:18px}}.panel-head{{display:flex;justify-content:space-between;align-items:center}}.badge{{border:1px solid var(--line);border-radius:999px;padding:6px 10px}}.columns{{display:grid;grid-template-columns:1fr 1.5fr;gap:24px}}table{{width:100%;border-collapse:collapse}}th,td{{padding:9px;border-bottom:1px solid var(--line);text-align:left}}th{{color:var(--muted);font-size:12px}}ul{{padding-left:20px;color:var(--muted)}}.note{{border-left:3px solid var(--accent);padding-left:12px}}footer{{margin-top:26px;color:var(--muted)}}
@media(max-width:760px){{header{{display:block}}.actions{{margin-top:16px}}.decision-grid,.columns{{grid-template-columns:1fr}}.metric-grid,.evidence-grid{{grid-template-columns:repeat(2,1fr)}}}}
</style></head><body><main><header><div><div class="kicker">COT direction · macro risk · price execution</div><h1>Directional COT Report</h1><p>One decision hierarchy for S&amp;P 500 and Nasdaq-100.</p></div><div class="actions"><a href="interactive_cot_dashboard.html">Open full macro dashboard</a></div></header><div class="decision-grid">{''.join(cards)}</div>{''.join(details)}<footer>Generated {html.escape(generated)}. This is a research decision aid, not a guarantee or personalized financial advice.</footer></main></body></html>"""


def write_outputs(decisions: list[dict[str, Any]]) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "cot_direction_latest.json").write_text(json.dumps(decisions, indent=2) + "\n", encoding="utf-8")
    flat_rows = []
    for row in decisions:
        flat = {key: value for key, value in row.items() if not isinstance(value, (list, dict))}
        flat_rows.append(flat)
    with (OUT_DIR / "cot_direction_latest.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=sorted({key for row in flat_rows for key in row}))
        writer.writeheader()
        writer.writerows(flat_rows)
    HTML_OUT.write_text(render_html(decisions), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=ROOT / "config" / "cot_direction_model_v1.json")
    args = parser.parse_args()
    config = load_config(args.config)
    decisions = [build_market_decision(market, config) for market in ("sp500", "nq")]
    write_outputs(decisions)
    for decision in decisions:
        print(f"{decision['market_label']}: {decision['final_action']} | {decision['structural_bias']} | exposure {decision['exposure_multiplier']:.2f}x")
    print(f"Wrote {HTML_OUT}")


if __name__ == "__main__":
    main()
