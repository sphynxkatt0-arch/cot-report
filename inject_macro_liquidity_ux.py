#!/usr/bin/env python3
"""Inject the macro-liquidity control room into both HTML surfaces."""
from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
PAYLOAD = ROOT / "model_output" / "macro_liquidity_expansion.json"
DASHBOARD = ROOT / "interactive_cot_dashboard.html"
REPORT = ROOT / "directional_cot_report.html"
START = "<!-- MACRO_LIQUIDITY_CONTROL_ROOM_START -->"
END = "<!-- MACRO_LIQUIDITY_CONTROL_ROOM_END -->"


def finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number else None


def fmt(value: Any, digits: int = 1, suffix: str = "") -> str:
    number = finite(value)
    if number is None:
        return "n/a"
    sign = "+" if number > 0 else ""
    return f"{sign}{number:.{digits}f}{suffix}"


def tone(state: Any) -> str:
    value = str(state or "").lower()
    if any(word in value for word in ("supportive", "normal", "good", "low")):
        return "positive"
    if any(word in value for word in ("defensive", "stress", "high", "low coverage")):
        return "negative"
    if any(word in value for word in ("caution", "partial", "moderate")):
        return "warning"
    return "neutral"


def metric_card(label: str, value: str, state: Any, detail: str) -> str:
    return (
        f'<article class="ml-card {tone(state)}"><div class="ml-label">{html.escape(label)}</div>'
        f'<div class="ml-value">{html.escape(value)}</div><div class="ml-state">{html.escape(str(state or "Unavailable"))}</div>'
        f'<div class="ml-detail">{html.escape(detail)}</div></article>'
    )


def source_table(payload: dict[str, Any]) -> str:
    rows = []
    for source in payload.get("sources") or []:
        status = str(source.get("status") or "unavailable")
        rows.append(
            f'<tr><td>{html.escape(str(source.get("label") or source.get("key")))}</td>'
            f'<td>{html.escape(str(source.get("dataset") or ""))}</td>'
            f'<td><span class="ml-source-status {tone(status)}">{html.escape(status)}</span></td>'
            f'<td>{html.escape(str(source.get("latest_date") or "n/a"))}</td>'
            f'<td>{html.escape(str(source.get("mnemonic") or "not resolved"))}</td></tr>'
        )
    return "".join(rows) or '<tr><td colspan="5">No OFR source status available.</td></tr>'


def reason_list(pillar: dict[str, Any]) -> str:
    reasons = pillar.get("reasons") or []
    return " · ".join(str(item) for item in reasons[:3]) if reasons else "No additional source-backed detail."


def build_block(payload: dict[str, Any]) -> str:
    pillars = payload.get("pillars") or {}
    macro = pillars.get("macro_regime") or {}
    net = pillars.get("net_liquidity") or {}
    reserves = pillars.get("bank_reserves") or {}
    treasury = pillars.get("treasury_supply") or {}
    admin_repo = pillars.get("repo_admin_spread") or {}
    funding = pillars.get("funding_microstructure") or {}
    dealer = pillars.get("dealer_absorption") or {}
    mmf = pillars.get("money_market_allocation") or {}
    coverage = finite(payload.get("source_coverage_ratio"))

    cards = [
        metric_card("Macro risk regime", fmt(macro.get("score"), 0, "/100"), macro.get("state"), "Broad risk and transmission backdrop"),
        metric_card("Net liquidity · 4 weeks", fmt(net.get("value"), 0, " bn"), net.get("state"), "Fed assets minus TGA and reverse repo impulse"),
        metric_card("Funding microstructure", fmt(funding.get("score"), 0, "/100"), funding.get("state"), reason_list(funding)),
        metric_card("Dealer absorption", fmt(dealer.get("score"), 0, "/100"), dealer.get("state"), reason_list(dealer)),
        metric_card("Treasury · next 7 days", fmt(treasury.get("value"), 0, " bn"), treasury.get("state"), "Scheduled settlement and issuance pressure"),
        metric_card("New-source coverage", fmt((coverage or 0) * 100, 0, "%"), payload.get("source_coverage_label"), "OFR repo, primary-dealer, and MMF feeds"),
    ]
    diagnostics = [
        ("Reserve impulse", fmt(reserves.get("value"), 0, " bn"), reserves.get("state")),
        ("SOFR − IORB", fmt(admin_repo.get("value"), 3, " pp"), admin_repo.get("state")),
        ("Repo dispersion", fmt(funding.get("repo_rate_dispersion_bp"), 1, " bp"), funding.get("state")),
        ("Largest repo-rate move", fmt(funding.get("largest_rate_move_bp"), 1, " bp"), funding.get("state")),
        ("MMF allocation", mmf.get("state") or "Unavailable", mmf.get("state")),
        ("Dealer data coverage", fmt((finite(dealer.get("coverage")) or 0) * 100, 0, "%"), dealer.get("state")),
    ]
    diagnostic_html = "".join(
        f'<div class="ml-driver"><span>{html.escape(label)}</span><strong>{html.escape(str(value))}</strong><em class="{tone(state)}">{html.escape(str(state or "Unavailable"))}</em></div>'
        for label, value, state in diagnostics
    )
    return f"""{START}
<style>
.ml-shell{{--ml-panel:var(--panel,#0d1727);--ml-panel-2:var(--panel2,#122139);--ml-border:var(--border,var(--line,#283c55));max-width:1440px;margin:18px auto;padding:0 22px}}.ml-head{{display:flex;justify-content:space-between;align-items:flex-end;gap:18px;margin-bottom:14px}}.ml-eyebrow{{font-size:11px;font-weight:850;letter-spacing:.14em;text-transform:uppercase;color:#5eead4}}.ml-head h2{{font-size:24px;margin:4px 0 0}}.ml-head p{{margin:5px 0 0;color:var(--muted,#9fb0c6);max-width:820px}}.ml-coverage{{border:1px solid var(--ml-border);border-radius:999px;padding:7px 11px;font-size:12px;white-space:nowrap}}.ml-grid{{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:11px}}.ml-card{{min-height:142px;background:linear-gradient(145deg,var(--ml-panel),var(--ml-panel-2));border:1px solid var(--ml-border);border-radius:17px;padding:15px;box-shadow:0 14px 36px rgba(0,0,0,.14)}}.ml-card.positive{{border-color:rgba(45,212,191,.55)}}.ml-card.warning{{border-color:rgba(245,158,11,.62)}}.ml-card.negative{{border-color:rgba(248,113,113,.62)}}.ml-label{{font-size:11px;color:var(--muted,#9fb0c6);font-weight:750}}.ml-value{{font-size:25px;font-weight:850;margin:8px 0 2px}}.ml-state{{font-size:12px;font-weight:800;color:#7dd3fc}}.ml-detail{{font-size:11px;line-height:1.4;color:var(--muted,#9fb0c6);margin-top:9px}}.ml-body{{display:grid;grid-template-columns:minmax(0,1.15fr) minmax(0,.85fr);gap:14px;margin-top:14px}}.ml-panel{{background:var(--ml-panel);border:1px solid var(--ml-border);border-radius:17px;padding:17px}}.ml-panel h3{{margin:0 0 4px;font-size:16px}}.ml-panel-sub{{font-size:12px;color:var(--muted,#9fb0c6);margin-bottom:12px}}.ml-drivers{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}}.ml-driver{{border:1px solid var(--ml-border);border-radius:11px;padding:10px;display:grid;grid-template-columns:1fr auto;gap:3px 8px}}.ml-driver span{{font-size:11px;color:var(--muted,#9fb0c6)}}.ml-driver strong{{font-size:14px}}.ml-driver em{{grid-column:1/-1;font-size:10px;font-style:normal;font-weight:800}}.ml-driver em.positive,.ml-source-status.positive{{color:#5eead4}}.ml-driver em.warning,.ml-source-status.warning{{color:#fbbf24}}.ml-driver em.negative,.ml-source-status.negative{{color:#fca5a5}}.ml-source-wrap{{overflow:auto;max-height:280px}}.ml-source-table{{width:100%;border-collapse:collapse;font-size:11px}}.ml-source-table th,.ml-source-table td{{padding:8px;border-bottom:1px solid var(--ml-border);text-align:left;white-space:nowrap}}.ml-source-table th{{color:var(--muted,#9fb0c6);position:sticky;top:0;background:var(--ml-panel)}}.ml-note{{margin-top:12px;padding:10px 12px;border-radius:11px;background:rgba(14,165,233,.08);border:1px solid rgba(14,165,233,.22);font-size:11px;color:var(--muted,#9fb0c6)}}@media(max-width:1180px){{.ml-grid{{grid-template-columns:repeat(3,1fr)}}}}@media(max-width:760px){{.ml-shell{{padding:0 12px}}.ml-head{{display:block}}.ml-coverage{{display:inline-block;margin-top:9px}}.ml-grid{{grid-template-columns:repeat(2,1fr)}}.ml-body{{grid-template-columns:1fr}}.ml-drivers{{grid-template-columns:1fr}}}}@media(max-width:460px){{.ml-grid{{grid-template-columns:1fr}}}}
</style>
<section class="ml-shell" id="macroLiquidityControlRoom">
  <div class="ml-head"><div><div class="ml-eyebrow">Macro liquidity control room</div><h2>Current State → Funding Capacity → Forward Pressure</h2><p>Separates liquidity supply from market transmission. OFR repo, primary-dealer, and money-market-fund data improve diagnosis but do not cast an independent COT vote.</p></div><div class="ml-coverage">Sources {fmt((coverage or 0)*100,0,'%')} · {html.escape(str(payload.get('source_coverage_label') or 'Low'))}</div></div>
  <div class="ml-grid">{''.join(cards)}</div>
  <div class="ml-body">
    <section class="ml-panel"><h3>Plumbing and absorption diagnostics</h3><div class="ml-panel-sub">Focus on whether cash withdrawal can be absorbed without funding or dealer stress.</div><div class="ml-drivers">{diagnostic_html}</div><div class="ml-note"><strong>Interpretation:</strong> liquidity, dealer capacity, and repo conditions may reduce exposure or block execution; they do not reverse the Legacy Non-commercial structural thesis.</div></section>
    <section class="ml-panel"><h3>Official source health</h3><div class="ml-panel-sub">Missing and stale feeds remain visible and reduce coverage instead of becoming neutral scores.</div><div class="ml-source-wrap"><table class="ml-source-table"><thead><tr><th>Series</th><th>Dataset</th><th>Status</th><th>Latest</th><th>Mnemonic</th></tr></thead><tbody>{source_table(payload)}</tbody></table></div></section>
  </div>
</section>
{END}"""


def remove_existing(source: str) -> str:
    start = source.find(START)
    end = source.find(END)
    if start >= 0 and end >= start:
        return source[:start] + source[end + len(END):]
    return source


def inject_dashboard(source: str, block: str) -> str:
    clean = remove_existing(source)
    marker = "<!-- DIRECTIONAL_DECISION_END -->"
    index = clean.find(marker)
    if index >= 0:
        index += len(marker)
        return clean[:index] + "\n" + block + clean[index:]
    header_end = clean.find("</header>")
    if header_end >= 0:
        index = header_end + len("</header>")
        return clean[:index] + "\n" + block + clean[index:]
    raise ValueError("dashboard has no directional or header insertion point")


def inject_report(source: str, block: str) -> str:
    clean = remove_existing(source)
    marker = "<!-- WEEKLY_POSITION_CHANGE_START -->"
    index = clean.find(marker)
    if index >= 0:
        return clean[:index] + block + "\n" + clean[index:]
    footer = clean.find("<footer>")
    if footer >= 0:
        return clean[:footer] + block + clean[footer:]
    raise ValueError("directional report has no insertion point")


def main() -> None:
    payload = json.loads(PAYLOAD.read_text(encoding="utf-8"))
    block = build_block(payload)
    DASHBOARD.write_text(inject_dashboard(DASHBOARD.read_text(encoding="utf-8", errors="replace"), block), encoding="utf-8")
    REPORT.write_text(inject_report(REPORT.read_text(encoding="utf-8", errors="replace"), block), encoding="utf-8")
    print("Injected macro-liquidity control room into dashboard and directional report")


if __name__ == "__main__":
    main()
