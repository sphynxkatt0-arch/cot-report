#!/usr/bin/env python3
"""Inject Treasury auction absorption context into dashboard and report."""
from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
PAYLOAD = ROOT / "model_output" / "macro_liquidity_expansion.json"
DASHBOARD = ROOT / "interactive_cot_dashboard.html"
REPORT = ROOT / "directional_cot_report.html"
START = "<!-- AUCTION_ABSORPTION_START -->"
END = "<!-- AUCTION_ABSORPTION_END -->"


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


def tone(value: Any) -> str:
    text = str(value or "").lower()
    if "support" in text:
        return "positive"
    if "defensive" in text:
        return "negative"
    if "neutral" in text:
        return "neutral"
    return "warning"


def auction_rows(context: dict[str, Any]) -> str:
    rows = []
    for row in (context.get("recent_coupon_auctions") or [])[:6]:
        rows.append(
            f'<tr><td>{html.escape(str(row.get("auction_date") or ""))}</td>'
            f'<td>{html.escape(str(row.get("security_term") or row.get("security_type") or ""))}</td>'
            f'<td>{fmt(row.get("bid_to_cover_ratio"),2)}</td>'
            f'<td>{fmt(row.get("bid_to_cover_delta"),2)}</td>'
            f'<td>{fmt(row.get("indirect_share_pct"),1,"%")}</td>'
            f'<td>{fmt(row.get("primary_dealer_share_pct"),1,"%")}</td>'
            f'<td>{fmt(row.get("quality_score"),0,"/100")}</td></tr>'
        )
    return "".join(rows) or '<tr><td colspan="7">Completed coupon-auction detail unavailable</td></tr>'


def build_block(payload: dict[str, Any]) -> str:
    pillar = (payload.get("pillars") or {}).get("auction_absorption") or {}
    context = payload.get("treasury_auction_context") or {}
    state = pillar.get("state") or "Unavailable"
    return f"""{START}
<style>
.au-shell{{max-width:1440px;margin:14px auto;padding:0 22px}}.au-panel{{background:var(--panel,#0d1727);border:1px solid var(--border,var(--line,#283c55));border-radius:18px;padding:18px}}.au-head{{display:flex;justify-content:space-between;align-items:flex-end;gap:14px;margin-bottom:13px}}.au-kicker{{font-size:11px;text-transform:uppercase;letter-spacing:.13em;font-weight:850;color:#fb7185}}.au-head h3{{font-size:19px;margin:4px 0}}.au-head p{{margin:0;color:var(--muted,#9fb0c6);font-size:12px}}.au-state{{border:1px solid var(--border,var(--line,#283c55));border-radius:999px;padding:7px 11px;font-size:12px;font-weight:800}}.au-state.positive{{color:#5eead4;border-color:rgba(45,212,191,.55)}}.au-state.negative{{color:#fca5a5;border-color:rgba(248,113,113,.55)}}.au-grid{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:9px;margin-bottom:13px}}.au-metric{{border:1px solid var(--border,var(--line,#283c55));border-radius:12px;padding:11px}}.au-metric span{{display:block;font-size:10px;color:var(--muted,#9fb0c6)}}.au-metric strong{{display:block;font-size:18px;margin-top:4px}}.au-table-wrap{{overflow:auto}}.au-table{{width:100%;border-collapse:collapse;font-size:11px}}.au-table th,.au-table td{{padding:8px;border-bottom:1px solid var(--border,var(--line,#283c55));text-align:left;white-space:nowrap}}.au-table th{{color:var(--muted,#9fb0c6)}}.au-note{{font-size:11px;color:var(--muted,#9fb0c6);margin-top:10px;line-height:1.45}}@media(max-width:820px){{.au-shell{{padding:0 12px}}.au-grid{{grid-template-columns:repeat(2,1fr)}}.au-head{{display:block}}.au-state{{display:inline-block;margin-top:8px}}}}
</style>
<section class="au-shell" id="auctionAbsorption">
 <div class="au-panel">
  <div class="au-head"><div><div class="au-kicker">Supply absorption</div><h3>Treasury Auction Demand Quality</h3><p>Compares each coupon auction with prior auctions of the same tenor.</p></div><div class="au-state {tone(state)}">{html.escape(str(state))} · {fmt(pillar.get('score'),0,'/100')}</div></div>
  <div class="au-grid">
   <div class="au-metric"><span>Average bid-to-cover delta</span><strong>{fmt(context.get('average_bid_to_cover_delta'),2)}</strong></div>
   <div class="au-metric"><span>Dealer share delta</span><strong>{fmt(context.get('average_dealer_share_delta_pp'),1,' pp')}</strong></div>
   <div class="au-metric"><span>Indirect share delta</span><strong>{fmt(context.get('average_indirect_share_delta_pp'),1,' pp')}</strong></div>
   <div class="au-metric"><span>Latest auction</span><strong>{html.escape(str(context.get('latest_auction_date') or 'n/a'))}</strong></div>
  </div>
  <div class="au-table-wrap"><table class="au-table"><thead><tr><th>Date</th><th>Term</th><th>BTC</th><th>BTC Δ</th><th>Indirect</th><th>Dealer</th><th>Quality</th></tr></thead><tbody>{auction_rows(context)}</tbody></table></div>
  <div class="au-note">A lower same-tenor bid-to-cover ratio, larger dealer take-down, or weaker indirect demand lowers absorption quality. This is relative demand context, not a standalone market-direction signal.</div>
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
    marker = "<!-- FISCAL_CASH_PATH_END -->"
    index = clean.find(marker)
    if index >= 0:
        index += len(marker)
        return clean[:index] + "\n" + block + clean[index:]
    marker = "<!-- MACRO_LIQUIDITY_CONTROL_ROOM_END -->"
    index = clean.find(marker)
    if index >= 0:
        index += len(marker)
        return clean[:index] + "\n" + block + clean[index:]
    raise ValueError("HTML has no fiscal or macro insertion point")


def main() -> None:
    payload = json.loads(PAYLOAD.read_text(encoding="utf-8"))
    block = build_block(payload)
    DASHBOARD.write_text(inject(DASHBOARD.read_text(encoding="utf-8", errors="replace"), block), encoding="utf-8")
    REPORT.write_text(inject(REPORT.read_text(encoding="utf-8", errors="replace"), block), encoding="utf-8")
    print("Injected Treasury auction absorption into dashboard and report")


if __name__ == "__main__":
    main()
