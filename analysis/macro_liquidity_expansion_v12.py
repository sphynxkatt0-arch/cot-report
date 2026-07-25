#!/usr/bin/env python3
"""Canonical macro-liquidity v1.2 builder with Daily Treasury cash flows."""
from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import macro_liquidity_expansion as base
from treasury_cash_flow_extension import fetch_treasury_cash_context, fiscal_pillar

FISCAL_CSV = base.OUT_DIR / "treasury_cash_source_status.csv"


def resilient_ofr_indicator(spec: dict[str, Any], current: datetime) -> base.IndicatorResult:
    """Verify configured series, then fall back to metadata search when needed."""
    result = base.fetch_indicator(spec, now=current)
    if result.status != "unavailable" or not spec.get("preferred_mnemonics"):
        return result
    fallback = dict(spec)
    fallback["preferred_mnemonics"] = []
    searched = base.fetch_indicator(fallback, now=current)
    if searched.status != "unavailable":
        searched.resolution = "metadata fallback after configured series failure"
        return searched
    if searched.error:
        result.error = f"configured: {result.error}; metadata fallback: {searched.error}"[-500:]
    return result


def build_payload(*, now: datetime | None = None) -> dict:
    current = now or datetime.now(UTC)
    config = base.load_config()
    ofr_results = [resilient_ofr_indicator(spec, current) for spec in config["indicators"]]
    by_key = {result.key: result for result in ofr_results}
    macro_latest = base.last_macro(base.extract_macro_monitor())
    pillars = base.existing_pillars(macro_latest)
    pillars.update(
        {
            "funding_microstructure": base.repo_pillar(by_key),
            "dealer_absorption": base.dealer_pillar(by_key),
            "money_market_allocation": base.mmf_pillar(by_key),
        }
    )

    fiscal_results, fiscal_context = fetch_treasury_cash_context(now=current)
    fiscal_by_key = {result.key: result for result in fiscal_results}
    pillars["fiscal_cash_flow"] = fiscal_pillar(fiscal_context, fiscal_by_key)
    all_results = [*ofr_results, *fiscal_results]
    fresh = sum(result.status == "fresh" for result in all_results)
    coverage = fresh / max(1, len(all_results))

    return {
        "schema_version": 1,
        "model_version": "macro-liquidity-control-room-v1.2",
        "generated_at_utc": current.isoformat(),
        "role": "descriptive risk and plumbing context; does not create or reverse COT direction",
        "source_coverage_ratio": round(coverage, 3),
        "source_coverage_label": "Good" if coverage >= 0.75 else "Partial" if coverage >= 0.40 else "Low",
        "existing_macro_latest": macro_latest,
        "treasury_cash_context": fiscal_context,
        "pillars": pillars,
        "sources": base.source_rows(all_results),
        "source_notes": [
            "Treasury Daily Treasury Statement provides daily operating cash plus deposits and withdrawals on a modified-cash basis.",
            "Positive fiscal cash flow means Treasury withdrawals injected cash into the private sector; deposits and tax receipts are drains.",
            "OFR Short-term Funding Monitor provides repo, primary-dealer, and money-market-fund series.",
            "Configured OFR mnemonics are verified by their data response; metadata search is the automatic fallback.",
            "Missing or stale series reduce coverage and are never filled with a neutral score.",
            "All extension pillars are descriptive and cannot create or reverse the governed COT direction.",
        ],
    }


def main() -> None:
    payload = build_payload()
    base.OUT_DIR.mkdir(parents=True, exist_ok=True)
    base.JSON_OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    # Keep OFR and Treasury source contracts separate for easier source auditing.
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
