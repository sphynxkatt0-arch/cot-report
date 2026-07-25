#!/usr/bin/env python3
"""Canonical macro-liquidity v1.2 builder with Daily Treasury cash flows."""
from __future__ import annotations

import json
from datetime import UTC, datetime

import macro_liquidity_expansion as base
from treasury_cash_flow_extension import fetch_treasury_cash_context, fiscal_pillar

FISCAL_CSV = base.OUT_DIR / "treasury_cash_source_status.csv"


def build_payload(*, now: datetime | None = None) -> dict:
    current = now or datetime.now(UTC)
    payload = base.build_payload(now=current)
    fiscal_results, fiscal_context = fetch_treasury_cash_context(now=current)
    by_key = {result.key: result for result in fiscal_results}
    payload["model_version"] = "macro-liquidity-control-room-v1.2"
    payload["treasury_cash_context"] = fiscal_context
    payload.setdefault("pillars", {})["fiscal_cash_flow"] = fiscal_pillar(fiscal_context, by_key)
    payload.setdefault("sources", []).extend(base.source_rows(fiscal_results))
    all_sources = payload["sources"]
    fresh = sum(str(source.get("status")) == "fresh" for source in all_sources)
    coverage = fresh / max(1, len(all_sources))
    payload["source_coverage_ratio"] = round(coverage, 3)
    payload["source_coverage_label"] = "Good" if coverage >= 0.75 else "Partial" if coverage >= 0.40 else "Low"
    payload["source_notes"] = [
        "Treasury Daily Treasury Statement provides daily operating cash plus deposits and withdrawals on a modified-cash basis.",
        "Positive fiscal cash flow means Treasury withdrawals injected cash into the private sector; deposits and tax receipts are drains.",
        *list(payload.get("source_notes") or []),
    ]
    payload["role"] = "descriptive risk and plumbing context; does not create or reverse COT direction"
    return payload


def main() -> None:
    payload = build_payload()
    base.OUT_DIR.mkdir(parents=True, exist_ok=True)
    base.JSON_OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    # Keep the reviewed OFR source contract separate from the Treasury source contract.
    base.write_csv(
        base.CSV_OUT,
        [source for source in payload["sources"] if source.get("dataset") != "fiscaldata"],
    )
    base.write_csv(
        FISCAL_CSV,
        [source for source in payload["sources"] if source.get("dataset") == "fiscaldata"],
    )
    print(f"Wrote {base.JSON_OUT}")
    print(f"Wrote {base.CSV_OUT}")
    print(f"Wrote {FISCAL_CSV}")
    print(f"Expanded source coverage: {payload['source_coverage_ratio'] * 100:.0f}%")


if __name__ == "__main__":
    main()
