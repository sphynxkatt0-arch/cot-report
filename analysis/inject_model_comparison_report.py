#!/usr/bin/env python3
"""Inject release-aligned old-versus-new model comparison into the report."""

from __future__ import annotations

import csv
import html
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
REPORT = ROOT / "directional_cot_report.html"
SUMMARY = ROOT / "model_output" / "directional_model_comparison_summary.csv"
AGREEMENT = ROOT / "model_output" / "directional_model_agreement.csv"
START = "<!-- MODEL_COMPARISON_START -->"
END = "<!-- MODEL_COMPARISON_END -->"
MODEL_LABELS = {
    "old_tff": "Old TFF regime",
    "old_legacy": "Old Legacy regime",
    "new_structural": "New NC structure",
    "new_structural_tactical": "New NC + TFF tactical",
}


def read_csv(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def fmt(value: Any, digits: int = 3, suffix: str = "") -> str:
    if value in {None, ""}:
        return "n/a"
    try:
        return f"{float(value):.{digits}f}{suffix}"
    except (TypeError, ValueError):
        return html.escape(str(value))


def build_block(summary: list[dict[str, Any]], agreement: list[dict[str, Any]]) -> str:
    ordered = sorted(
        summary,
        key=lambda row: (
            str(row.get("market")),
            {"1w": 1, "4w": 2, "13w": 3, "26w": 4}.get(str(row.get("horizon")), 99),
            list(MODEL_LABELS).index(str(row.get("model"))) if str(row.get("model")) in MODEL_LABELS else 99,
        ),
    )
    rows = "".join(
        f"<tr><td>{html.escape(str(row.get('market', '')).upper())}</td><td>{html.escape(str(row.get('horizon', '')))}</td><td>{html.escape(MODEL_LABELS.get(str(row.get('model')), str(row.get('model'))))}</td><td>{row.get('observations', 'n/a')}</td><td>{fmt(row.get('spearman_r'))}</td><td>{fmt(row.get('positive_minus_negative'), 2, ' pp')}</td><td>{fmt(row.get('directional_coverage_pct'), 1, '%')}</td></tr>"
        for row in ordered
    ) or "<tr><td colspan='7'>Comparison output unavailable</td></tr>"
    agreement_rows = "".join(
        f"<tr><td>{html.escape(str(row.get('market', '')).upper())}</td><td>{html.escape(MODEL_LABELS.get(str(row.get('left_model')), str(row.get('left_model'))))}</td><td>{html.escape(MODEL_LABELS.get(str(row.get('right_model')), str(row.get('right_model'))))}</td><td>{row.get('directional_overlap_n', 'n/a')}</td><td>{fmt(row.get('directional_agreement_pct'), 1, '%')}</td></tr>"
        for row in agreement
    ) or "<tr><td colspan='5'>Agreement output unavailable</td></tr>"
    return f"""{START}
<section class="panel" id="modelComparisonPanel">
  <div class="panel-head"><div><div class="kicker">Model governance</div><h3>Old versus new COT models</h3></div><span class="badge">Friday aligned</span></div>
  <p>The same report dates and forward-return targets are used for all models. Positive-minus-negative compares average returns when each model is directionally positive versus directionally negative. This remains exploratory evidence, not sealed out-of-sample optimization.</p>
  <div style="overflow:auto"><table><thead><tr><th>Market</th><th>Horizon</th><th>Model</th><th>N</th><th>Spearman</th><th>Positive − negative</th><th>Coverage</th></tr></thead><tbody>{rows}</tbody></table></div>
  <h4 style="margin-top:22px">Directional agreement</h4>
  <div style="overflow:auto"><table><thead><tr><th>Market</th><th>Model A</th><th>Model B</th><th>Directional overlap</th><th>Agreement</th></tr></thead><tbody>{agreement_rows}</tbody></table></div>
</section>
{END}"""


def remove_existing(source: str) -> str:
    start = source.find(START)
    end = source.find(END)
    if start >= 0 and end >= start:
        return source[:start] + source[end + len(END):]
    return source


def main() -> None:
    if not REPORT.exists():
        raise FileNotFoundError(f"Missing {REPORT}")
    source = remove_existing(REPORT.read_text(encoding="utf-8", errors="replace"))
    block = build_block(read_csv(SUMMARY), read_csv(AGREEMENT))
    insertion = source.find("<footer>")
    if insertion < 0:
        insertion = source.find("</main>")
    if insertion < 0:
        raise ValueError("Directional report has no footer/main insertion point")
    REPORT.write_text(source[:insertion] + block + source[insertion:], encoding="utf-8")
    print("Injected model comparison into directional report.")


if __name__ == "__main__":
    main()
