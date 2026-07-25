#!/usr/bin/env python3
"""Inject the latest directional decision into the generated macro dashboard.

The dashboard builder remains untouched. This post-build step is idempotent and
replaces its own marked block after every dashboard refresh.
"""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
DASHBOARD = ROOT / "interactive_cot_dashboard.html"
DECISIONS = ROOT / "model_output" / "cot_direction_latest.json"
START = "<!-- DIRECTIONAL_DECISION_START -->"
END = "<!-- DIRECTIONAL_DECISION_END -->"


def fmt(value: Any, digits: int = 2, suffix: str = "") -> str:
    if value is None:
        return "n/a"
    try:
        return f"{float(value):.{digits}f}{suffix}"
    except (TypeError, ValueError):
        return html.escape(str(value))


def tone(value: str) -> str:
    lower = value.lower()
    if "delayed" in lower or "awaiting" in lower:
        return "warning"
    if "long" in lower or "bull" in lower:
        return "positive"
    if "short" in lower or "bear" in lower or "override" in lower:
        return "negative"
    return "neutral"


def build_block(rows: list[dict[str, Any]]) -> str:
    cards = []
    for row in rows:
        release = str(row.get("release_status") or "unknown")
        cards.append(f"""
        <article class="directional-summary-card {tone(str(row.get('final_action') or ''))}">
          <div class="directional-kicker">{html.escape(str(row.get('market_label') or row.get('market') or 'Market'))}</div>
          <div class="directional-action">{html.escape(str(row.get('final_action') or 'Unavailable'))}</div>
          <div class="directional-bias">{html.escape(str(row.get('structural_bias') or 'Unavailable'))} · {html.escape(str(row.get('execution_state') or 'Unavailable'))}</div>
          <div class="directional-metrics">
            <div><span>Structural</span><strong>{fmt(row.get('structural_score'))}</strong></div>
            <div><span>Tactical</span><strong>{fmt(row.get('tactical_modifier'))}</strong></div>
            <div><span>Exposure</span><strong>{fmt(row.get('exposure_multiplier'))}×</strong></div>
            <div><span>Confidence</span><strong>{html.escape(str(row.get('confidence_label') or 'n/a'))}</strong></div>
          </div>
          <div class="directional-meta">COT {html.escape(str(row.get('report_date') or 'n/a'))} · release {html.escape(release)} · macro {fmt(row.get('macro_regime_score'), 0, '/100')}</div>
        </article>
        """)
    delayed = [row for row in rows if row.get("release_status") == "delayed"]
    notice = ""
    if delayed:
        markets = ", ".join(str(row.get("market_label") or row.get("market")) for row in delayed)
        notice = f'<div class="directional-release-warning"><strong>CFTC release delayed:</strong> {html.escape(markets)} keeps the prior signal; no new recommendation is issued.</div>'
    return f"""{START}
<style>
.directional-decision-shell{{max-width:1440px;margin:18px auto 8px;padding:0 22px}}.directional-decision-head{{display:flex;justify-content:space-between;align-items:end;gap:16px;margin-bottom:12px}}.directional-decision-title{{font-size:22px;font-weight:800}}.directional-decision-sub{{color:var(--muted,#94a3b8);font-size:13px}}.directional-decision-link{{border:1px solid var(--border,#334155);border-radius:10px;padding:8px 11px;text-decoration:none;color:inherit}}.directional-summary-grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}}.directional-summary-card{{background:var(--panel,#111827);border:1px solid var(--border,#334155);border-radius:16px;padding:17px;box-shadow:0 12px 32px rgba(0,0,0,.16)}}.directional-summary-card.positive{{border-color:rgba(34,197,94,.65)}}.directional-summary-card.negative{{border-color:rgba(239,68,68,.65)}}.directional-summary-card.warning{{border-color:rgba(245,158,11,.75)}}.directional-kicker{{font-size:11px;letter-spacing:.12em;text-transform:uppercase;color:var(--muted,#94a3b8);font-weight:800}}.directional-action{{font-size:25px;font-weight:850;margin:5px 0}}.directional-bias{{color:#60a5fa;font-weight:700}}.directional-metrics{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px;margin:13px 0}}.directional-metrics div{{border:1px solid var(--border,#334155);border-radius:10px;padding:8px}}.directional-metrics span{{display:block;font-size:10px;color:var(--muted,#94a3b8)}}.directional-metrics strong{{font-size:16px}}.directional-meta{{font-size:12px;color:var(--muted,#94a3b8)}}.directional-release-warning{{margin-bottom:12px;padding:10px 13px;border:1px solid rgba(245,158,11,.7);border-radius:10px;background:rgba(245,158,11,.10)}}@media(max-width:760px){{.directional-decision-shell{{padding:0 12px}}.directional-decision-head{{display:block}}.directional-decision-link{{display:inline-block;margin-top:8px}}.directional-summary-grid{{grid-template-columns:1fr}}.directional-metrics{{grid-template-columns:repeat(2,1fr)}}}}
</style>
<section class="directional-decision-shell" id="directionalDecisionSummary">
  <div class="directional-decision-head"><div><div class="directional-decision-title">Directional COT Decision</div><div class="directional-decision-sub">Non-commercial structure → TFF timing → macro sizing → price execution</div></div><a class="directional-decision-link" href="directional_cot_report.html">Open full decision report</a></div>
  {notice}
  <div class="directional-summary-grid">{''.join(cards)}</div>
</section>
<script>
(function () {{
  function setText(node, text) {{ if (node && node.textContent !== text) node.textContent = text; }}
  function relabelResearchSurfaces() {{
    document.querySelectorAll('.summary-card').forEach(function (card) {{
      var label = card.querySelector('.summary-label');
      if (label && label.textContent.trim() === 'Regime') setText(label, 'Selected-report research regime');
    }});
    document.querySelectorAll('.card-title').forEach(function (title) {{
      var value = title.textContent.trim();
      if (value === 'Weekly Desk Scanner') setText(title, 'Participant Research Scanner');
      if (value === 'Signal Regime Panel') setText(title, 'Selected-Report Regime Research');
    }});
    document.querySelectorAll('.card-meta').forEach(function (meta) {{
      var value = meta.textContent.trim();
      if (value.indexOf('Ranks local SP/NQ/VIX setups') === 0) setText(meta, 'Exploratory participant ranking; the headline direction is fixed by the decision panel above.');
      if (value.indexOf('COT + factor percentile-score engine') === 0) setText(meta, 'Research-only selected-report score; it does not replace the headline directional model.');
    }});
    var datasetLabel = document.querySelector('label[for="dataset"]');
    if (datasetLabel) setText(datasetLabel, 'Research report view');
  }}
  window.addEventListener('DOMContentLoaded', function () {{
    relabelResearchSurfaces();
    var observer = new MutationObserver(relabelResearchSurfaces);
    observer.observe(document.body, {{ childList: true, subtree: true }});
    window.setTimeout(relabelResearchSurfaces, 250);
  }});
}}());
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
    header_end = clean.find("</header>")
    if header_end >= 0:
        index = header_end + len("</header>")
        return clean[:index] + "\n" + block + "\n" + clean[index:]
    body_start = clean.find("<body>")
    if body_start >= 0:
        index = body_start + len("<body>")
        return clean[:index] + "\n" + block + "\n" + clean[index:]
    raise ValueError("Dashboard HTML has no </header> or <body> insertion point")


def main() -> None:
    if not DASHBOARD.exists():
        raise FileNotFoundError(f"Missing {DASHBOARD}")
    if not DECISIONS.exists():
        raise FileNotFoundError(f"Missing {DECISIONS}; run build_directional_cot_system.py first")
    rows = json.loads(DECISIONS.read_text(encoding="utf-8"))
    if not isinstance(rows, list) or not rows:
        raise ValueError("Directional decision JSON is empty")
    DASHBOARD.write_text(inject(DASHBOARD.read_text(encoding="utf-8", errors="replace"), build_block(rows)), encoding="utf-8")
    print(f"Injected decision summary into {DASHBOARD}")


if __name__ == "__main__":
    main()
