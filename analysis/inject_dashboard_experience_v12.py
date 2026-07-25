#!/usr/bin/env python3
"""Add decision-first navigation, playbook, and research-surface controls."""
from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
DASHBOARD = ROOT / "interactive_cot_dashboard.html"
DECISIONS = ROOT / "model_output" / "cot_direction_latest.json"
MACRO = ROOT / "model_output" / "macro_liquidity_expansion.json"
START = "<!-- DECISION_EXPERIENCE_V12_START -->"
END = "<!-- DECISION_EXPERIENCE_V12_END -->"


def fmt(value: Any, digits: int = 1, suffix: str = "") -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "n/a"
    if number != number:
        return "n/a"
    return f"{number:.{digits}f}{suffix}"


def tone(value: Any) -> str:
    text = str(value or "").lower()
    if "long" in text or "bull" in text or "support" in text or "confirm" in text:
        return "positive"
    if "short" in text or "bear" in text or "defensive" in text or "invalid" in text or "override" in text or "active" in text:
        return "negative"
    if "wait" in text or "reduced" in text or "partial" in text or "tentative" in text or "unavailable" in text:
        return "warning"
    return "neutral"


def plumbing_state(row: dict[str, Any]) -> str:
    if bool(row.get("liquidity_plumbing_guard_active")):
        return "Active — blocks exposure"
    if not bool(row.get("liquidity_plumbing_guard_reliable")):
        return "Unavailable — insufficient coverage"
    return "Inactive"


def playbook_card(row: dict[str, Any], fiscal_state: str, macro_coverage: Any) -> str:
    action = str(row.get("final_action") or "Unavailable")
    evidence = str(row.get("historical_evidence_state") or "Not validated")
    weekly = str(row.get("weekly_signal_change") or "Change unavailable")
    release = str(row.get("release_status") or "unknown")
    execution = str(row.get("execution_state") or "Unavailable")
    guard_state = plumbing_state(row)
    next_step = (
        "Act only while price confirmation remains aligned."
        if execution.lower() == "confirmed"
        else "Wait for price confirmation; do not front-run the COT thesis."
    )
    if bool(row.get("liquidity_plumbing_guard_active")):
        next_step = "No new exposure until fewer than two reliable plumbing pillars remain severely stressed."
    if release != "current":
        next_step = "No new exposure until the expected CFTC release is current."
    return f"""
    <article class="xp-card {tone(action)}">
      <div class="xp-market">{html.escape(str(row.get('market_label') or row.get('market')))}</div>
      <h3>{html.escape(action)}</h3>
      <div class="xp-row"><span>Structural thesis</span><strong>{html.escape(str(row.get('structural_bias') or 'Unavailable'))}</strong></div>
      <div class="xp-row"><span>Weekly change</span><strong>{html.escape(weekly)}</strong></div>
      <div class="xp-row"><span>Macro / fiscal</span><strong>{fmt(row.get('macro_regime_score'),0,'/100')} · {html.escape(fiscal_state)}</strong></div>
      <div class="xp-row"><span>Plumbing guard</span><strong class="{tone(guard_state)}">{html.escape(guard_state)}</strong></div>
      <div class="xp-row"><span>Exposure</span><strong>{fmt(row.get('exposure_multiplier'),2,'×')}</strong></div>
      <div class="xp-row"><span>Evidence</span><strong>{html.escape(evidence)}</strong></div>
      <div class="xp-row"><span>Data quality</span><strong>Macro {fmt(float(macro_coverage or 0)*100,0,'%')} · CFTC {html.escape(release)}</strong></div>
      <div class="xp-next"><span>Next action</span>{html.escape(next_step)}</div>
    </article>"""


def build_block(decisions: list[dict[str, Any]], macro: dict[str, Any]) -> str:
    fiscal_state = str(((macro.get("pillars") or {}).get("fiscal_cash_flow") or {}).get("state") or "Unavailable")
    coverage = macro.get("source_coverage_ratio")
    cards = "".join(playbook_card(row, fiscal_state, coverage) for row in decisions)
    return f"""{START}
<style>
.xp-nav-wrap{{position:sticky;top:0;z-index:40;background:color-mix(in srgb,var(--bg,#07111f) 90%,transparent);backdrop-filter:blur(16px);border-bottom:1px solid var(--border,var(--line,#283c55))}}.xp-nav{{max-width:1440px;margin:auto;padding:9px 22px;display:flex;align-items:center;gap:7px;overflow:auto}}.xp-nav a,.xp-nav button{{border:1px solid var(--border,var(--line,#283c55));background:var(--panel,#0d1727);color:inherit;border-radius:999px;padding:7px 10px;font:inherit;font-size:11px;font-weight:750;white-space:nowrap;text-decoration:none;cursor:pointer}}.xp-nav a:hover,.xp-nav button:hover{{border-color:#38bdf8}}.xp-nav .xp-brand{{border:0;background:none;padding-left:0;color:#7dd3fc;text-transform:uppercase;letter-spacing:.12em}}.xp-shell{{max-width:1440px;margin:14px auto;padding:0 22px}}.xp-panel{{background:var(--panel,#0d1727);border:1px solid var(--border,var(--line,#283c55));border-radius:18px;padding:19px}}.xp-head{{display:flex;justify-content:space-between;gap:16px;align-items:flex-end;margin-bottom:14px}}.xp-kicker{{font-size:11px;text-transform:uppercase;letter-spacing:.13em;color:#fbbf24;font-weight:850}}.xp-head h2{{font-size:22px;margin:4px 0}}.xp-head p{{margin:0;color:var(--muted,#9fb0c6);font-size:12px}}.xp-grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:13px}}.xp-card{{border:1px solid var(--border,var(--line,#283c55));border-radius:15px;padding:16px;background:linear-gradient(145deg,var(--panel,#0d1727),var(--panel2,#122139))}}.xp-card.positive{{border-color:rgba(45,212,191,.55)}}.xp-card.negative{{border-color:rgba(248,113,113,.55)}}.xp-card.warning{{border-color:rgba(245,158,11,.62)}}.xp-market{{font-size:10px;text-transform:uppercase;letter-spacing:.12em;color:var(--muted,#9fb0c6);font-weight:800}}.xp-card h3{{font-size:20px;margin:5px 0 12px}}.xp-row{{display:flex;justify-content:space-between;gap:12px;padding:7px 0;border-bottom:1px solid var(--border,var(--line,#283c55));font-size:12px}}.xp-row span{{color:var(--muted,#9fb0c6)}}.xp-row strong{{text-align:right}}.xp-row strong.positive{{color:#5eead4}}.xp-row strong.warning{{color:#fbbf24}}.xp-row strong.negative{{color:#fca5a5}}.xp-next{{margin-top:12px;padding:10px;border-radius:11px;background:rgba(14,165,233,.08);font-size:12px;line-height:1.45}}.xp-next span{{display:block;text-transform:uppercase;font-size:9px;letter-spacing:.12em;color:#7dd3fc;font-weight:800;margin-bottom:3px}}.xp-research-hidden .xp-research-surface{{display:none!important}}@media(max-width:760px){{.xp-nav{{padding:8px 12px}}.xp-shell{{padding:0 12px}}.xp-grid{{grid-template-columns:1fr}}.xp-head{{display:block}}}}
</style>
<div class="xp-nav-wrap"><nav class="xp-nav" aria-label="Dashboard sections"><span class="xp-brand">COT Control</span><a href="#directionalDecisionSummary">Decision</a><a href="#marketPlaybook">Playbook</a><a href="#macroLiquidityControlRoom">Liquidity</a><a href="#fiscalCashPath">Fiscal Path</a><a href="#auctionAbsorption">Auctions</a><a href="#directionalDecisionQuality">Positioning Changes</a><button id="xpResearchToggle" type="button" aria-pressed="true">Show research</button></nav></div>
<section class="xp-shell" id="marketPlaybook"><div class="xp-panel"><div class="xp-head"><div><div class="xp-kicker">Market playbook</div><h2>What to do, what must confirm, what can block it</h2><p>Summarizes the governed output. It does not calculate a new direction.</p></div></div><div class="xp-grid">{cards}</div></div></section>
<script>
(function(){{
 function markResearch(){{
   document.querySelectorAll('.card,.panel').forEach(function(node){{
     var title=node.querySelector('.card-title,.panel-head h3');
     if(!title) return;
     var text=title.textContent.toLowerCase();
     if(text.indexOf('research')>=0 || text.indexOf('participant research')>=0 || text.indexOf('selected-report')>=0) node.classList.add('xp-research-surface');
   }});
 }}
 function setup(){{
   markResearch();
   document.body.classList.add('xp-research-hidden');
   var button=document.getElementById('xpResearchToggle');
   if(!button || button.dataset.ready) return;
   button.dataset.ready='1';
   button.addEventListener('click',function(){{
     var hidden=document.body.classList.toggle('xp-research-hidden');
     button.textContent=hidden?'Show research':'Hide research';
     button.setAttribute('aria-pressed',hidden?'true':'false');
   }});
   new MutationObserver(markResearch).observe(document.body,{{childList:true,subtree:true}});
 }}
 if(document.readyState==='loading') document.addEventListener('DOMContentLoaded',setup); else setup();
}})();
</script>
{END}"""


def remove_existing(source: str) -> str:
    start = source.find(START)
    end = source.find(END)
    if start >= 0 and end >= start:
        return source[:start] + source[end + len(END):]
    return source


def inject(source: str, block: str) -> str:
    clean = remove_existing(source)
    marker = "<!-- DIRECTIONAL_DECISION_END -->"
    index = clean.find(marker)
    if index >= 0:
        index += len(marker)
        return clean[:index] + "\n" + block + clean[index:]
    marker = "<!-- FISCAL_CASH_PATH_END -->"
    index = clean.find(marker)
    if index >= 0:
        index += len(marker)
        return clean[:index] + "\n" + block + clean[index:]
    raise ValueError("dashboard has no governed insertion point")


def main() -> None:
    decisions = json.loads(DECISIONS.read_text(encoding="utf-8"))
    macro = json.loads(MACRO.read_text(encoding="utf-8"))
    if not isinstance(decisions, list) or not decisions:
        raise ValueError("latest decisions are unavailable")
    block = build_block(decisions, macro)
    DASHBOARD.write_text(inject(DASHBOARD.read_text(encoding="utf-8", errors="replace"), block), encoding="utf-8")
    print("Injected decision-first dashboard navigation and playbook")


if __name__ == "__main__":
    main()
