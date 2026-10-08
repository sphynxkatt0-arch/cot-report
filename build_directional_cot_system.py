#!/usr/bin/env python3
"""Build the governed multi-market directional COT system.

All markets share the same hierarchy:
Legacy Non-commercial structure -> report-family tactical context -> crowding
size -> macro size/guards -> release state -> price execution.
"""
from __future__ import annotations

import argparse
import csv
import html
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import pandas as pd

from build_directional_cot_report import (
    MARKETS,
    expanding_percentile,
    flow_rank,
    latest_file,
    latest_price,
    price_at_or_after,
    read_position_file,
    read_prices,
    tone_class,
    trend_rank,
)
from cftc_release_tracker import observe_report, resolve_release_state
from cot_direction_model import (
    build_decision,
    clamp,
    confidence_label,
    final_action,
    load_config,
    preserve_structural_sign,
    structural_score_from_percentile,
    tactical_modifier,
)
from cot_market_registry import DIRECTIONAL_MARKETS
from macro_direction_adapter import load_macro_direction_context

ROOT = Path(__file__).resolve().parent
OUT_DIR = ROOT / "model_output"
HTML_OUT = ROOT / "directional_cot_report.html"
HISTORY_OUT = OUT_DIR / "cot_direction_history.csv"
VALIDATION_OUT = OUT_DIR / "cot_direction_validation_summary.csv"


def finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number else None


def market_model_config(market: str, config: dict[str, Any]) -> dict[str, Any]:
    """Return a copied model config with market-specific confidence/invalidation."""
    meta = MARKETS[market]
    slot = str(meta.get("model_slot") or "sp500")
    configured = deepcopy(config)
    configured["execution"][f"{slot}_invalidation_pct"] = float(meta["invalidation_pct"])
    configured["confidence"][f"{slot}_structural_base"] = float(meta["confidence_base"])
    return configured


def load_market_inputs(market: str) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    meta = MARKETS[market]
    legacy = read_position_file(latest_file(str(meta["legacy_glob"])))
    secondary = read_position_file(latest_file(str(meta["secondary_glob"])))
    prices = read_prices(Path(meta["price_path"]), str(meta["price_col"]))
    return legacy, secondary, prices


def common_report_dates(legacy: pd.DataFrame, secondary: pd.DataFrame) -> list[pd.Timestamp]:
    return [pd.Timestamp(value) for value in sorted(set(legacy["date"]).intersection(set(secondary["date"])))]


def resolve_secondary_columns(
    secondary: pd.DataFrame,
    market: str | None = None,
) -> tuple[str, str, str, str]:
    if market is not None:
        meta = MARKETS[market]
        return (
            str(meta["conviction_column"]),
            str(meta["other_reportable_column"]),
            str(meta["nonreportable_column"]),
            str(meta["conviction_group_label"]),
        )
    if "asset_mgr_net_oi_pct" in secondary.columns:
        return (
            "asset_mgr_net_oi_pct",
            "other_reportable_net_oi_pct",
            "non_reportable_net_oi_pct",
            "Asset Manager",
        )
    if "managed_money_net_oi_pct" in secondary.columns:
        return (
            "managed_money_net_oi_pct",
            "other_reportable_net_oi_pct",
            "non_reportable_net_oi_pct",
            "Managed Money",
        )
    raise KeyError("Secondary report has neither Asset Manager nor Managed Money positioning")


def feature_snapshot(
    legacy: pd.DataFrame,
    secondary: pd.DataFrame,
    report_ts: pd.Timestamp,
    minimum: int,
    market: str | None = None,
) -> dict[str, float | str | None]:
    legacy_hist = legacy.loc[legacy["date"] <= report_ts].copy()
    secondary_hist = secondary.loc[secondary["date"] <= report_ts].copy()
    conviction_col, other_col, nonreportable_col, conviction_label = resolve_secondary_columns(secondary, market)
    conviction = expanding_percentile(secondary_hist[conviction_col], minimum)
    return {
        "noncommercial_percentile": expanding_percentile(legacy_hist["noncommercial_net_oi_pct"], minimum),
        # Compatibility field consumed by existing guards and report injectors.
        "asset_manager_percentile": conviction,
        "conviction_percentile": conviction,
        "conviction_group_label": conviction_label,
        "other_reportable_trend13_rank": trend_rank(secondary_hist, other_col, 13, minimum),
        "nonreportable_trend13_rank": trend_rank(secondary_hist, nonreportable_col, 13, minimum),
        "noncommercial_flow4_rank": flow_rank(legacy_hist, "noncommercial_net_oi_pct", 4, minimum),
    }


def price_index_at_or_after(prices: pd.DataFrame, target: pd.Timestamp) -> int | None:
    indices = prices.index[prices["date"] >= target]
    return int(indices[0]) if len(indices) else None


def build_history_for_market(
    market: str,
    legacy: pd.DataFrame,
    secondary: pd.DataFrame,
    prices: pd.DataFrame,
    config: dict[str, Any],
) -> list[dict[str, Any]]:
    minimum = int(config["minimum_history_weeks"])
    rows: list[dict[str, Any]] = []
    for report_ts in common_report_dates(legacy, secondary):
        snapshot = feature_snapshot(legacy, secondary, report_ts, minimum, market)
        structural = structural_score_from_percentile(snapshot["noncommercial_percentile"], config)
        tactical, _ = tactical_modifier(
            structural,
            snapshot["other_reportable_trend13_rank"],
            snapshot["nonreportable_trend13_rank"],
            snapshot["noncommercial_flow4_rank"],
            config,
        )
        adjusted = preserve_structural_sign(structural, tactical)
        scheduled = resolve_release_state(
            report_ts.date(),
            now=pd.Timestamp(report_ts + pd.Timedelta(days=3, hours=22)).to_pydatetime(),
        )
        release_date = pd.Timestamp(scheduled["effective_release_date"])
        base_index = price_index_at_or_after(prices, release_date)
        base_price = float(prices.iloc[base_index]["price"]) if base_index is not None else None
        row: dict[str, Any] = {
            "market": market,
            "market_label": MARKETS[market]["label"],
            "report_date": report_ts.date().isoformat(),
            "scheduled_release_date": release_date.date().isoformat(),
            **snapshot,
            "structural_score": structural,
            "tactical_modifier": tactical,
            "adjusted_cot_score": adjusted,
            "signal_price_date": prices.iloc[base_index]["date"].date().isoformat() if base_index is not None else None,
            "signal_price": base_price,
        }
        for label, trading_days in (("1w", 5), ("4w", 20), ("13w", 65), ("26w", 130)):
            target_index = base_index + trading_days if base_index is not None else None
            if target_index is not None and target_index < len(prices) and base_price not in (None, 0):
                target_price = float(prices.iloc[target_index]["price"])
                row[f"forward_return_{label}"] = (target_price / base_price - 1.0) * 100.0
            else:
                row[f"forward_return_{label}"] = None
        rows.append(row)
    return rows


def build_validation_summary(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    frame = pd.DataFrame(history)
    rows: list[dict[str, Any]] = []
    if frame.empty:
        return rows
    for market, market_frame in frame.groupby("market"):
        scores = pd.to_numeric(market_frame["adjusted_cot_score"], errors="coerce")
        for horizon in ("1w", "4w", "13w", "26w"):
            returns = pd.to_numeric(market_frame[f"forward_return_{horizon}"], errors="coerce")
            paired = pd.DataFrame({"score": scores, "return": returns}).dropna()
            bullish = paired.loc[paired["score"] >= 0.25, "return"]
            bearish = paired.loc[paired["score"] <= -0.25, "return"]
            neutral = paired.loc[paired["score"].abs() < 0.25, "return"]
            rows.append({
                "market": market,
                "horizon": horizon,
                "observations": int(len(paired)),
                "pearson_r": float(paired["score"].corr(paired["return"])) if len(paired) >= 3 else None,
                "spearman_r": float(paired["score"].corr(paired["return"], method="spearman")) if len(paired) >= 3 else None,
                "bullish_n": int(len(bullish)),
                "bullish_avg_return": float(bullish.mean()) if len(bullish) else None,
                "bearish_n": int(len(bearish)),
                "bearish_avg_return": float(bearish.mean()) if len(bearish) else None,
                "neutral_n": int(len(neutral)),
                "neutral_avg_return": float(neutral.mean()) if len(neutral) else None,
                "bullish_minus_bearish": float(bullish.mean() - bearish.mean()) if len(bullish) and len(bearish) else None,
                "status": "exploratory_release_aligned",
            })
    return rows


def build_latest_market_decision(
    market: str,
    legacy: pd.DataFrame,
    secondary: pd.DataFrame,
    prices: pd.DataFrame,
    macro: dict[str, Any],
    config: dict[str, Any],
) -> dict[str, Any]:
    meta = MARKETS[market]
    dates = common_report_dates(legacy, secondary)
    if not dates:
        raise RuntimeError(f"{market}: no common Legacy/{meta['secondary_label']} report dates")
    report_ts = dates[-1]
    observe_report(report_ts.date())
    release = resolve_release_state(report_ts.date())
    snapshot = feature_snapshot(legacy, secondary, report_ts, int(config["minimum_history_weeks"]), market)
    signal_date, signal_price = price_at_or_after(prices, pd.Timestamp(release["effective_release_date"]))
    latest_date, current_price = latest_price(prices)

    configured = market_model_config(market, config)
    model_slot = str(meta.get("model_slot") or "sp500")
    decision = build_decision(
        market=model_slot,
        report_date=report_ts.date().isoformat(),
        actual_release_date=release["effective_release_date"],
        release_date_source=release["release_date_source"],
        signal_price_date=signal_date,
        latest_price_date=latest_date,
        signal_price=signal_price,
        latest_price=current_price,
        noncommercial_percentile=snapshot["noncommercial_percentile"],
        other_reportable_trend13_rank=snapshot["other_reportable_trend13_rank"],
        nonreportable_trend13_rank=snapshot["nonreportable_trend13_rank"],
        noncommercial_flow4_rank=snapshot["noncommercial_flow4_rank"],
        asset_manager_percentile_value=snapshot["asset_manager_percentile"],
        macro_score_value=macro.get("macro_regime_score"),
        macro_override=bool(macro.get("hard_override")),
        config=configured,
    ).to_dict()
    decision["market"] = market

    conviction_label = str(meta["conviction_group_label"])
    decision["reasons"] = [
        str(reason).replace("Asset Manager", conviction_label)
        for reason in decision.get("reasons") or []
    ]

    availability = float(macro.get("availability_ratio") or 0.0)
    adjusted_confidence = float(decision["confidence_score"]) * (0.70 + 0.30 * availability)
    if release["is_delayed"]:
        adjusted_confidence *= 0.55
    adjusted_confidence = clamp(adjusted_confidence, 0.0, 1.0)
    action = final_action(
        decision.get("adjusted_cot_score"),
        str(decision.get("execution_state")),
        float(decision.get("exposure_multiplier") or 0.0),
        adjusted_confidence,
        bool(macro.get("hard_override")),
        configured,
    )
    if release["is_delayed"]:
        action = "Hold Prior Signal — CFTC Report Delayed"
    elif release["is_awaiting_release"]:
        action = "Hold Prior Signal — Awaiting Friday Release"

    decision.update(snapshot)
    decision.update({
        "market_label": meta["label"],
        "asset_class": meta["asset_class"],
        "secondary_report": meta["secondary_label"],
        "conviction_group_label": conviction_label,
        "contract_selection_mode": meta["contract_selection_mode"],
        "contract_selection_note": meta["contract_selection_note"],
        "final_action": action,
        "confidence_score": round(adjusted_confidence, 4),
        "confidence_label": confidence_label(adjusted_confidence),
        "signal_price": signal_price,
        "latest_price": current_price,
        "release_status": release["release_status"],
        "expected_report_date": release["expected_report_date"],
        "scheduled_release_utc": release["scheduled_release_utc"],
        "scheduled_release_stockholm": release["scheduled_release_stockholm"],
        "first_observed_utc": release["first_observed_utc"],
        "first_observed_delay_minutes": release["first_observed_delay_minutes"],
        "new_signal_available": not release["is_delayed"] and not release["is_awaiting_release"],
        "macro_regime_score": macro.get("macro_regime_score"),
        "liquidity_plumbing_score": macro.get("liquidity_plumbing_score"),
        "market_transmission_score": macro.get("market_transmission_score"),
        "supply_pressure_score": macro.get("supply_pressure_score"),
        "macro_availability_ratio": availability,
        "macro_severe_alerts": macro.get("severe_alerts") or [],
        "source_legacy": str(latest_file(str(meta["legacy_glob"])).relative_to(ROOT)),
        "source_secondary": str(latest_file(str(meta["secondary_glob"])).relative_to(ROOT)),
        # Backward-compatible source name retained for consumers expecting source_tff.
        "source_tff": str(latest_file(str(meta["secondary_glob"])).relative_to(ROOT)),
    })
    decision["reasons"] = list(decision.get("reasons") or []) + [
        f"CFTC release status {release['release_status']}; expected report {release['expected_report_date']}",
        f"Macro availability {availability * 100:.0f}%",
        str(meta["contract_selection_note"]),
    ]
    return decision


def format_value(value: Any, digits: int = 2, suffix: str = "") -> str:
    if value is None:
        return "n/a"
    try:
        return f"{float(value):.{digits}f}{suffix}"
    except (TypeError, ValueError):
        return html.escape(str(value))


def render_html(decisions: list[dict[str, Any]], validation: list[dict[str, Any]]) -> str:
    generated = pd.Timestamp.now(tz="UTC").isoformat()
    cards: list[str] = []
    panels: list[str] = []
    for row in decisions:
        action_class = tone_class(str(row["final_action"]))
        release_class = "warning" if row.get("release_status") in {"delayed", "awaiting_release", "catch_up_delayed"} else ""
        cards.append(f"""
        <article class="decision-card {action_class} {release_class}">
          <div class="kicker">{html.escape(str(row['market_label']))}</div>
          <h2>{html.escape(str(row['final_action']))}</h2>
          <div class="bias">{html.escape(str(row['structural_bias']))} · {html.escape(str(row['execution_state']))}</div>
          <div class="metric-grid">
            <div><span>Structural</span><strong>{format_value(row['structural_score'])}</strong></div>
            <div><span>Tactical</span><strong>{format_value(row['tactical_modifier'])}</strong></div>
            <div><span>Exposure</span><strong>{format_value(row['exposure_multiplier'])}×</strong></div>
            <div><span>Confidence</span><strong>{html.escape(str(row['confidence_label']))}</strong></div>
          </div>
          <p>Report {row['report_date']} · {html.escape(str(row.get('secondary_report')))} + Legacy · release <b>{html.escape(str(row['release_status']))}</b> · price since actionable date {format_value(row['price_change_since_release_pct'], 2, '%')}.</p>
        </article>""")
        tactical_rows = "".join(
            f"<tr><td>{html.escape(str(item['label']))}</td><td>{format_value(item['rank_score'])}</td><td>{format_value(item['contribution'])}</td></tr>"
            for item in row.get("tactical_components") or []
        ) or "<tr><td colspan='3'>No tactical contribution</td></tr>"
        reasons = "".join(f"<li>{html.escape(str(reason))}</li>" for reason in row.get("reasons") or [])
        alerts = ", ".join(row.get("macro_severe_alerts") or []) or "None"
        conviction_label = html.escape(str(row.get("conviction_group_label") or "Crowding group"))
        panels.append(f"""
        <section class="panel">
          <div class="panel-head"><div><div class="kicker">{html.escape(str(row['market_label']))}</div><h3>Decision evidence</h3></div><span class="badge">{html.escape(str(row['model_version']))}</span></div>
          <div class="evidence-grid">
            <div><span>NC percentile</span><strong>{format_value(row['noncommercial_percentile'], 1, '%')}</strong></div>
            <div><span>{conviction_label} percentile</span><strong>{format_value(row['asset_manager_percentile'], 1, '%')}</strong></div>
            <div><span>Liquidity plumbing</span><strong>{format_value(row['liquidity_plumbing_score'], 0, '/100')}</strong></div>
            <div><span>Transmission</span><strong>{format_value(row['market_transmission_score'], 0, '/100')}</strong></div>
            <div><span>Supply pressure</span><strong>{format_value(row['supply_pressure_score'], 0, '/100')}</strong></div>
            <div><span>Macro regime</span><strong>{format_value(row['macro_regime_score'], 0, '/100')}</strong></div>
          </div>
          <div class="columns"><div><h4>Reason chain</h4><ul>{reasons}</ul><p>Severe macro alerts: {html.escape(alerts)}</p></div><div><h4>Tactical contributions</h4><table><thead><tr><th>Input</th><th>Rank</th><th>Contribution</th></tr></thead><tbody>{tactical_rows}</tbody></table></div></div>
          <p class="note">Legacy Non-commercials set structural direction. {html.escape(str(row.get('secondary_report')))} changes conviction only. {conviction_label} and macro change size. Price controls execution. Contract selection: {html.escape(str(row.get('contract_selection_note') or 'n/a'))}</p>
        </section>""")

    validation_rows = "".join(
        f"<tr><td>{html.escape(str(row['market']).upper())}</td><td>{row['horizon']}</td><td>{row['observations']}</td><td>{format_value(row['spearman_r'], 3)}</td><td>{format_value(row['bullish_minus_bearish'], 2, ' pp')}</td></tr>"
        for row in validation
    )
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Directional COT Report</title>
<style>
:root{{--bg:#07111f;--panel:#0e1b2d;--panel2:#14243a;--text:#f5f7fb;--muted:#9fb0c6;--line:#263b55;--pos:#37d391;--neg:#ff6b75;--accent:#6aa8ff;--warn:#ffba55}}*{{box-sizing:border-box}}body{{margin:0;background:linear-gradient(160deg,#07111f,#0b1627 55%,#07111f);color:var(--text);font:15px/1.55 Inter,system-ui,sans-serif}}main{{max-width:1320px;margin:auto;padding:32px 20px 60px}}header{{display:flex;justify-content:space-between;gap:24px;align-items:flex-end;margin-bottom:24px}}h1{{font-size:clamp(30px,5vw,54px);line-height:1;margin:5px 0 10px}}h2{{font-size:25px;margin:8px 0}}h3{{font-size:22px;margin:4px 0}}h4{{margin:0 0 10px}}p,li{{color:var(--muted)}}a{{color:#9ec5ff}}.kicker{{text-transform:uppercase;letter-spacing:.13em;color:#82a8d6;font-size:12px;font-weight:700}}.actions a{{display:inline-block;border:1px solid var(--line);padding:9px 13px;border-radius:10px;text-decoration:none;background:var(--panel)}}.decision-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:18px}}.decision-card,.panel{{background:linear-gradient(145deg,var(--panel),var(--panel2));border:1px solid var(--line);border-radius:18px;padding:22px;box-shadow:0 18px 50px rgba(0,0,0,.18)}}.decision-card.positive{{border-color:rgba(55,211,145,.6)}}.decision-card.negative{{border-color:rgba(255,107,117,.6)}}.decision-card.warning{{border-color:var(--warn)}}.bias{{font-weight:700;color:var(--accent)}}.metric-grid,.evidence-grid{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;margin:20px 0}}.metric-grid div,.evidence-grid div{{background:rgba(5,12,22,.45);border:1px solid var(--line);border-radius:12px;padding:12px}}span{{display:block;color:var(--muted);font-size:12px}}strong{{font-size:18px}}.panel{{margin-top:18px}}.panel-head{{display:flex;justify-content:space-between;align-items:center}}.badge{{border:1px solid var(--line);border-radius:999px;padding:6px 10px}}.columns{{display:grid;grid-template-columns:1fr 1.5fr;gap:24px}}table{{width:100%;border-collapse:collapse}}th,td{{padding:9px;border-bottom:1px solid var(--line);text-align:left}}th{{color:var(--muted);font-size:12px}}.note{{border-left:3px solid var(--accent);padding-left:12px}}footer{{margin-top:26px;color:var(--muted)}}@media(max-width:760px){{header{{display:block}}.actions{{margin-top:16px}}.columns{{grid-template-columns:1fr}}.metric-grid,.evidence-grid{{grid-template-columns:repeat(2,1fr)}}}}
</style></head><body><main><header><div><div class="kicker">COT direction · macro risk · price execution</div><h1>Directional COT Report</h1><p>One governed decision hierarchy across S&amp;P 500, Nasdaq-100, Russell 2000, Dow Jones, and Gold.</p></div><div class="actions"><a href="interactive_cot_dashboard.html">Open full macro dashboard</a></div></header><div class="decision-grid">{''.join(cards)}</div>{''.join(panels)}<section class="panel"><div class="panel-head"><div><div class="kicker">Release-aligned history</div><h3>Exploratory model validation</h3></div></div><p>Diagnostics use Friday-aligned price bases. They are an audit aid, not a sealed out-of-sample result.</p><div style="overflow:auto"><table><thead><tr><th>Market</th><th>Horizon</th><th>N</th><th>Spearman</th><th>Bullish − bearish</th></tr></thead><tbody>{validation_rows}</tbody></table></div></section><footer>Generated {html.escape(generated)}. Research decision aid; not personalized financial advice.</footer></main></body></html>"""


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    flattened = [{key: value for key, value in row.items() if not isinstance(value, (list, dict, tuple))} for row in rows]
    fields = sorted({key for row in flattened for key in row})
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(flattened)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=ROOT / "config" / "cot_direction_model_v1.json")
    args = parser.parse_args()
    config = load_config(args.config)
    macro_context = load_macro_direction_context().to_dict()

    decisions: list[dict[str, Any]] = []
    history: list[dict[str, Any]] = []
    for market in DIRECTIONAL_MARKETS:
        legacy, secondary, prices = load_market_inputs(market)
        decisions.append(build_latest_market_decision(market, legacy, secondary, prices, macro_context, config))
        history.extend(build_history_for_market(market, legacy, secondary, prices, config))
    validation = build_validation_summary(history)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "cot_direction_latest.json").write_text(json.dumps(decisions, indent=2) + "\n", encoding="utf-8")
    (OUT_DIR / "macro_direction_context.json").write_text(json.dumps(macro_context, indent=2) + "\n", encoding="utf-8")
    write_csv(OUT_DIR / "cot_direction_latest.csv", decisions)
    write_csv(HISTORY_OUT, history)
    write_csv(VALIDATION_OUT, validation)
    HTML_OUT.write_text(render_html(decisions, validation), encoding="utf-8")

    for decision in decisions:
        print(f"{decision['market_label']}: {decision['final_action']} | {decision['structural_bias']} | release {decision['release_status']} | exposure {decision['exposure_multiplier']:.2f}x")
    print(f"Wrote {HTML_OUT}")
    print(f"Wrote {HISTORY_OUT}")


if __name__ == "__main__":
    main()
