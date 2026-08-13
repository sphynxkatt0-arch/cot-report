#!/usr/bin/env python3
"""Canonical macro-liquidity v1.2 builder with Treasury cash and auction absorption."""
from __future__ import annotations

import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import macro_liquidity_expansion as base
import treasury_auction_absorption as auction_module
import treasury_cash_flow_extension as fiscal_module
from treasury_auction_absorption import fetch_auction_context
from treasury_cash_flow_extension import fetch_treasury_cash_context, fiscal_pillar

FISCAL_CSV = base.OUT_DIR / "treasury_cash_source_status.csv"
CANONICAL_MACRO_HISTORY = base.OUT_DIR / "macro_history.csv"
CANONICAL_MACRO_LATEST = base.OUT_DIR / "macro_history_latest.json"
CANONICAL_MACRO_PROVENANCE = base.OUT_DIR / "macro_history_provenance.json"
SOURCE_TIMEOUT_SECONDS = 10
SOURCE_RETRIES = 1


def transport_failure(error: str | None) -> bool:
    """Identify failures where a metadata retry against the same host is wasteful."""
    text = str(error or "").lower()
    return any(
        marker in text
        for marker in (
            "timed out",
            "temporary failure",
            "name or service not known",
            "connection reset",
            "connection refused",
            "remote end closed",
            "urlopen error",
            "http error 500",
            "http error 502",
            "http error 503",
            "http error 504",
        )
    )


def resilient_ofr_indicator(spec: dict[str, Any], current: datetime) -> base.IndicatorResult:
    """Verify configured series, then fall back to metadata search when useful."""
    result = base.fetch_indicator(spec, now=current)
    if result.status != "unavailable" or not spec.get("preferred_mnemonics"):
        return result
    if transport_failure(result.error):
        result.resolution = f"{result.resolution or 'configured'}; metadata fallback skipped after transport failure"
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


def load_canonical_macro_latest() -> tuple[dict[str, Any], dict[str, Any]]:
    """Read the persisted macro history instead of scraping generated dashboard HTML."""
    if not CANONICAL_MACRO_LATEST.exists():
        return {}, {}
    try:
        payload = json.loads(CANONICAL_MACRO_LATEST.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}, {}
    latest = payload.get("latest")
    if not isinstance(latest, dict) or not latest.get("date"):
        return {}, {}
    provenance: dict[str, Any] = {}
    if CANONICAL_MACRO_PROVENANCE.exists():
        try:
            loaded = json.loads(CANONICAL_MACRO_PROVENANCE.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                provenance = loaded
        except (OSError, json.JSONDecodeError):
            provenance = {}
    return latest, {
        "source": "model_output/macro_history_latest.json",
        "generated_at_utc": payload.get("generated_at_utc"),
        "lookahead_safe": bool(payload.get("lookahead_safe")),
        "status": payload.get("status"),
        "provenance": provenance,
    }


def resolve_core_macro_latest() -> tuple[dict[str, Any], dict[str, Any]]:
    """Prefer canonical persisted history; retain HTML extraction only as legacy fallback."""
    latest, metadata = load_canonical_macro_latest()
    if latest:
        return latest, metadata
    legacy = base.last_macro(base.extract_macro_monitor())
    return legacy, {
        "source": "interactive_cot_dashboard.html (legacy fallback)",
        "generated_at_utc": None,
        "lookahead_safe": False,
        "status": "legacy_fallback" if legacy else "missing",
        "provenance": {},
    }


def canonical_artifacts() -> tuple[Path, ...]:
    return (CANONICAL_MACRO_HISTORY, CANONICAL_MACRO_LATEST, CANONICAL_MACRO_PROVENANCE)


def restore_canonical_from_gh_pages() -> dict[str, Any]:
    """Recover the last published canonical history after the workflow fetches gh-pages."""
    restored: list[str] = []
    for path in canonical_artifacts():
        if path.exists() and path.stat().st_size > 0:
            continue
        relative = path.relative_to(base.ROOT).as_posix()
        try:
            result = subprocess.run(
                ["git", "show", f"origin/gh-pages:{relative}"],
                cwd=base.ROOT.parent,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except (OSError, subprocess.CalledProcessError):
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(result.stdout)
        restored.append(relative)
    return {"restored": restored}


def snapshot_canonical_artifacts() -> dict[Path, bytes]:
    return {
        path: path.read_bytes()
        for path in canonical_artifacts()
        if path.exists() and path.stat().st_size > 0
    }


def restore_canonical_snapshot(snapshot: dict[Path, bytes]) -> None:
    for path in canonical_artifacts():
        if path in snapshot:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(snapshot[path])
        elif path.exists():
            path.unlink()


def canonical_latest_date() -> str | None:
    latest, _metadata = load_canonical_macro_latest()
    stamp = str(latest.get("date") or "")
    return stamp[:10] if len(stamp) >= 10 else None


def refresh_canonical_macro_history() -> dict[str, Any]:
    """Refresh canonical history without allowing a failed run to regress last-good data."""
    restore_report = restore_canonical_from_gh_pages()
    snapshot = snapshot_canonical_artifacts()
    previous_date = canonical_latest_date()
    try:
        import refresh_macro_history as canonical
        canonical.main()
        latest, metadata = load_canonical_macro_latest()
        refreshed_date = canonical_latest_date()
        if previous_date and (not refreshed_date or refreshed_date < previous_date):
            restore_canonical_snapshot(snapshot)
            latest, metadata = load_canonical_macro_latest()
            return {
                "status": "cached_fallback" if latest else "unavailable",
                "source": metadata.get("source"),
                "restored_from_gh_pages": restore_report["restored"],
                "error": (
                    "canonical refresh regressed latest date "
                    f"from {previous_date} to {refreshed_date or 'missing'}"
                ),
            }
        return {
            "status": "refreshed" if latest else "missing_after_refresh",
            "source": metadata.get("source"),
            "restored_from_gh_pages": restore_report["restored"],
            "error": None,
        }
    except Exception as exc:
        restore_canonical_snapshot(snapshot)
        latest, metadata = load_canonical_macro_latest()
        return {
            "status": "cached_fallback" if latest else "unavailable",
            "source": metadata.get("source"),
            "restored_from_gh_pages": restore_report["restored"],
            "error": str(exc)[:500],
        }


def apply_core_macro_fallbacks(pillars: dict[str, Any], macro_latest: dict[str, Any]) -> None:
    """Keep core macro context populated without inventing directional signals.

    A reserve *change* can be interpreted as an impulse. A reserve *level* cannot,
    so when only the level is available it is published as Context rather than
    being labelled supportive/defensive. This mirrors the populated headline
    macro card and prevents a missing derivative field from breaking deployment.
    """
    reserves = pillars.get("bank_reserves") or {}
    if base.finite(reserves.get("value")) is None:
        reserve_level = base.finite(macro_latest.get("bank_reserves"))
        if reserve_level is None:
            reserve_level = base.finite(macro_latest.get("reserves"))
        if reserve_level is not None:
            pillars["bank_reserves"] = {
                "label": "Bank reserve level",
                "value": reserve_level,
                "unit": "USD bn",
                "state": "Context",
                "basis": "level_fallback",
                "reason": "4-week reserve impulse unavailable; using observed reserve level without directional inference",
            }

    repo = pillars.get("repo_admin_spread") or {}
    if base.finite(repo.get("value")) is None:
        spread = base.finite(macro_latest.get("effr_iorb_spread"))
        if spread is not None:
            pillars["repo_admin_spread"] = {
                "label": "EFFR-IORB fallback",
                "value": spread,
                "unit": "pp",
                "state": "Stress" if spread >= 0.10 else "Caution" if spread >= 0.05 else "Normal",
                "basis": "effr_iorb_fallback",
            }


def fetch_external_sources(config: dict[str, Any], current: datetime):
    """Fetch independent public sources concurrently with bounded network waits.

    Production must degrade quickly when OFR or Treasury APIs are unavailable;
    a broad source outage must not turn into a 20+ minute serial retry chain.
    """
    original_base_request = base.request_json
    original_fiscal_request = fiscal_module.request_json
    original_auction_request = auction_module.request_json

    def bounded_request_json(url: str, *, timeout: int = SOURCE_TIMEOUT_SECONDS, retries: int = SOURCE_RETRIES):
        return original_base_request(
            url,
            timeout=min(int(timeout), SOURCE_TIMEOUT_SECONDS),
            retries=min(int(retries), SOURCE_RETRIES),
        )

    base.request_json = bounded_request_json
    fiscal_module.request_json = bounded_request_json
    auction_module.request_json = bounded_request_json
    try:
        with ThreadPoolExecutor(max_workers=6, thread_name_prefix="ofr") as ofr_pool, ThreadPoolExecutor(
            max_workers=2, thread_name_prefix="treasury"
        ) as treasury_pool:
            fiscal_future = treasury_pool.submit(fetch_treasury_cash_context, now=current)
            auction_future = treasury_pool.submit(fetch_auction_context, now=current)
            ofr_results = list(
                ofr_pool.map(
                    lambda spec: resilient_ofr_indicator(spec, current),
                    config["indicators"],
                )
            )
            fiscal_results, fiscal_context = fiscal_future.result()
            auction_result, auction_context = auction_future.result()
        return ofr_results, fiscal_results, fiscal_context, auction_result, auction_context
    finally:
        base.request_json = original_base_request
        fiscal_module.request_json = original_fiscal_request
        auction_module.request_json = original_auction_request


def build_payload(*, now: datetime | None = None) -> dict:
    current = now or datetime.now(UTC)
    config = base.load_config()
    ofr_results, fiscal_results, fiscal_context, auction_result, auction_context = fetch_external_sources(
        config, current
    )
    by_key = {result.key: result for result in ofr_results}
    macro_latest, macro_history = resolve_core_macro_latest()
    pillars = base.existing_pillars(macro_latest)
    apply_core_macro_fallbacks(pillars, macro_latest)
    pillars.update(
        {
            "funding_microstructure": base.repo_pillar(by_key),
            "dealer_absorption": base.dealer_pillar(by_key),
            "money_market_allocation": base.mmf_pillar(by_key),
        }
    )

    fiscal_by_key = {result.key: result for result in fiscal_results}
    pillars["fiscal_cash_flow"] = fiscal_pillar(fiscal_context, fiscal_by_key)

    pillars["auction_absorption"] = {
        "label": "Treasury auction absorption",
        "score": auction_context.get("score"),
        "state": auction_context.get("state", "Unavailable"),
        "coverage": auction_context.get("coverage", 0),
        "reasons": auction_context.get("reasons") or [auction_result.error or "Auction data unavailable"],
        "average_bid_to_cover_delta": auction_context.get("average_bid_to_cover_delta"),
        "average_dealer_share_delta_pp": auction_context.get("average_dealer_share_delta_pp"),
        "average_indirect_share_delta_pp": auction_context.get("average_indirect_share_delta_pp"),
    }

    all_results = [*ofr_results, *fiscal_results, auction_result]
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
        "canonical_macro_history": macro_history,
        "treasury_cash_context": fiscal_context,
        "treasury_auction_context": auction_context,
        "pillars": pillars,
        "sources": base.source_rows(all_results),
        "source_notes": [
            "Core macro state is read from the persisted canonical macro-history artifact when available; generated HTML is legacy fallback only.",
            "Canonical history uses conservative business-day availability lags and admits future Treasury issue amounts only after the auction date.",
            "Treasury Daily Treasury Statement provides daily operating cash plus deposits and withdrawals on a modified-cash basis.",
            "Positive fiscal cash flow means Treasury withdrawals injected cash into the private sector; deposits and tax receipts are drains.",
            "Treasury auction absorption compares bid-to-cover, dealer share, and indirect share against prior auctions of the same tenor.",
            "OFR Short-term Funding Monitor provides repo, primary-dealer, and money-market-fund series.",
            "Configured OFR mnemonics are verified by their data response; metadata search is the automatic fallback when the host is reachable.",
            "Official-source requests are bounded and independent feeds are fetched concurrently so source outages degrade quickly instead of blocking deployment.",
            "If the 4-week reserve impulse is absent, the observed reserve level is shown as Context and never converted into a directional score.",
            "Missing or stale series reduce coverage and are never filled with a neutral score.",
            "All extension pillars are descriptive and cannot create or reverse the governed COT direction.",
        ],
    }


def main() -> None:
    refresh_result = refresh_canonical_macro_history()
    if refresh_result.get("error"):
        print(
            "WARNING: canonical macro refresh failed; "
            f"status={refresh_result['status']} error={refresh_result['error']}"
        )
    payload = build_payload()
    payload["canonical_macro_refresh"] = refresh_result
    base.OUT_DIR.mkdir(parents=True, exist_ok=True)
    base.JSON_OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
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
    print(f"Core macro source: {payload['canonical_macro_history'].get('source')}")
    print(f"Expanded source coverage: {payload['source_coverage_ratio'] * 100:.0f}%")


if __name__ == "__main__":
    main()
