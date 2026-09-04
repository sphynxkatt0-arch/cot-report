#!/usr/bin/env python3
"""Inject Daily Treasury cash-path context into both dashboard surfaces."""
from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
PAYLOAD = ROOT / "model_output" / "macro_liquidity_expansion.json"
DASHBOARD = ROOT / "interactive_cot_dashboard.html"
REPORT = ROOT / "directional_cot_report.html"
START = "<!-- FISCAL_CASH_PATH_START -->"
END = "<!-- FISCAL_CASH_PATH_END -->"


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
    if "support" in value or "inject" in value:
        return "positive"
    if "defensive" in value or "drain" in value:
        return "negative"
    if "neutral" in value:
        return "neutral"
    return "warning"


def category_label(value: Any) -> str:
    label = str(value or "").strip()
    if not label or label.lower() in {"null", "none", "n/a", "-"}:
        return "Other"
    return label


def top_categories(context: dict[str, Any]) -> str:
    rows = []
    for item in context.get("top_cash_flow_categories_5d") or []:
        effect = finite(item.get("private_cash_effect_bn"))
        state = "Injection" if effect is not None and effect > 0 else "Drain"
        rows.append(
            f'<tr><td>{html.escape(category_label(item.get("category")))}</td>'
            f'<td>{fmt(effect, 1, " bn")}</td><td class="{tone(state)}">{state}</td></tr>'
        )
    return "".join(rows) or '<tr><td colspan="3">Category detail unavailable</td></tr>'


def build_block(payload: dict[str, Any]) -> str:
    pillar = (payload.get("pillars") or {}).get("fiscal_cash_flow") or {}
    context = payload.get("treasury_cash_context") or {}
    state = pillar.get("state") or "Unavailable"
    return f"""{START}
<style>
.fc-shell{{max-width:1440px;margin:14px auto;padding:0 22px}}.fc-panel{{background:linear-gradient(145deg,var(--panel,#0d1727),var(--panel2,#122139));border:1px solid var(--border,var(--line,#283c55));border-radius:18px;padding:18px}}.fc-head{{display:flex;justify-content:space-between;align-items:flex-end;gap:14px;margin-bottom:14px}}.fc-kicker{{font-size:11px;font-weight:850;letter-spacing:.13em;text-transform:uppercase;color:#a78bfa}}.fc-head h3{{font-size:19px;margin:4px 0}}.fc-head p{{margin:0;color:var(--muted,#9fb0c6);font-size:12px}}.fc-state{{border:1px solid var(--border,var(--line,#283c55));border-radius:999px;padding:7px 11px;font-size:12px;font-weight:800}}.fc-state.positive{{color:#5eead4;border-color:rgba(45,212,191,.55)}}.fc-state.negative{{color:#fca5a5;border-color:rgba(248,113,113,.55)}}.fc-grid{{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:9px}}.fc-metric{{border:1px solid var(--border,var(--line,#283c55));border-radius:12px;padding:11px}}.fc-metric span{{display:block;color:var(--muted,#9fb0c6);font-size:10px}}.fc-metric strong{{display:block;font-size:18px;margin-top:4px}}.fc-body{{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,.8fr);gap:12px;margin-top:12px}}.fc-explain,.fc-table-wrap{{border:1px solid var(--border,var(--line,#283c55));border-radius:13px;padding:13px}}.fc-explain h4,.fc-table-wrap h4{{margin:0 0 7px}}.fc-explain p{{font-size:12px;line-height:1.55;color:var(--muted,#9fb0c6);margin:0}}.fc-table{{width:100%;border-collapse:collapse;font-size:11px}}.fc-table th,.fc-table td{{padding:7px;border-bottom:1px solid var(--border,var(--line,#283c55));text-align:left}}.fc-table th{{color:var(--muted,#9fb0c6)}}.fc-table .positive{{color:#5eead4}}.fc-table .negative{{color:#fca5a5}}@media(max-width:980px){{.fc-grid{{grid-template-columns:repeat(3,1fr)}}}}@media(max-width:760px){{.fc-shell{{padding:0 12px}}.fc-head{{display:block}}.fc-state{{display:inline-block;margin-top:8px}}.fc-body{{grid-template-columns:1fr}}}}@media(max-width:480px){{.fc-grid{{grid-template-columns:repeat(2,1fr)}}}}
</style>
<section class="fc-shell" id="fiscalCashPath">
 <div class="fc-panel">
  <div class="fc-head"><div><div class="fc-kicker">Forward liquidity path</div><h3>Daily Treasury Cash Flow</h3><p>Actual TGA deposits and withdrawals—not only the weekly TGA level.</p></div><div class="fc-state {tone(state)}">{html.escape(str(state))} · {fmt(pillar.get('score'),0,'/100')}</div></div>
  <div class="fc-grid">
   <div class="fc-metric"><span>Private cash effect · 5d</span><strong>{fmt(context.get('private_cash_flow_5d_bn'),1,' bn')}</strong></div>
   <div class="fc-metric"><span>Private cash effect · 20d</span><strong>{fmt(context.get('private_cash_flow_20d_bn'),1,' bn')}</strong></div>
   <div class="fc-metric"><span>TGA change · 5d</span><strong>{fmt(context.get('operating_cash_change_5d_bn'),1,' bn')}</strong></div>
   <div class="fc-metric"><span>Tax deposits · 5d</span><strong>{fmt(context.get('tax_deposits_5d_bn'),1,' bn')}</strong></div>
   <div class="fc-metric"><span>Treasury deposits · 5d</span><strong>{fmt(context.get('deposits_5d_bn'),1,' bn')}</strong></div>
   <div class="fc-metric"><span>Treasury withdrawals · 5d</span><strong>{fmt(context.get('withdrawals_5d_bn'),1,' bn')}</strong></div>
  </div>
  <div class="fc-body">
   <div class="fc-explain"><h4>How to read it</h4><p><strong>Positive</strong> means Treasury withdrawals put cash into the private sector. <strong>Negative</strong> means deposits—especially tax receipts—pulled cash into the TGA. A rising TGA is therefore treated as a drain. This panel explains the liquidity path and may reduce risk, but it cannot reverse the COT structural direction.</p></div>
   <div class="fc-table-wrap"><h4>Largest 5-day cash-flow categories</h4><table class="fc-table"><thead><tr><th>Category</th><th>Private cash effect</th><th>Role</th></tr></thead><tbody>{top_categories(context)}</tbody></table></div>
  </div>
 </div>
</section>
{END}"""


def remove_existing(source: str) -> str:
    start = source.find(START)
    end = source.find(END)
    if start >= 0 and end >= start:
        return source[:start] + source[end + len(END):]
    return source


def inject(source: str, block: str) -> str:
    clean = remove_existing(source)
    marker = "<!-- MACRO_LIQUIDITY_CONTROL_ROOM_END -->"
    index = clean.find(marker)
    if index >= 0:
        index += len(marker)
        return clean[:index] + "\n" + block + clean[index:]
    marker = "<!-- WEEKLY_POSITION_CHANGE_START -->"
    index = clean.find(marker)
    if index >= 0:
        return clean[:index] + block + "\n" + clean[index:]
    raise ValueError("HTML has no macro-control-room or weekly-change insertion point")


def main() -> None:
    payload = json.loads(PAYLOAD.read_text(encoding="utf-8"))
    block = build_block(payload)
    DASHBOARD.write_text(inject(DASHBOARD.read_text(encoding="utf-8", errors="replace"), block), encoding="utf-8")
    REPORT.write_text(inject(REPORT.read_text(encoding="utf-8", errors="replace"), block), encoding="utf-8")
    print("Injected Daily Treasury cash path into dashboard and report")


if __name__ == "__main__":
    main()
