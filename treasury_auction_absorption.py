#!/usr/bin/env python3
"""Treasury auction absorption diagnostics from the official Fiscal Data API."""
from __future__ import annotations

import statistics
import urllib.parse
from datetime import UTC, datetime, timedelta
from typing import Any

from macro_liquidity_expansion import IndicatorResult, clamp, days_old, finite, iso_date, request_json, state_from_score

AUCTIONS_API = "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/od/auctions_query"
COUPON_TYPES = {"note", "bond", "tips"}


def auction_url(start: str, page_size: int = 1000) -> str:
    params = {
        "filter": f"auction_date:gte:{start}",
        "sort": "auction_date",
        "page[size]": str(page_size),
    }
    return f"{AUCTIONS_API}?{urllib.parse.urlencode(params)}"


def auction_rows(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        return []
    rows: list[dict[str, Any]] = []
    for raw in payload["data"]:
        if not isinstance(raw, dict):
            continue
        auction_date = iso_date(raw.get("auction_date"))
        bid_to_cover = finite(raw.get("bid_to_cover_ratio"))
        total_accepted = finite(raw.get("total_accepted"))
        if not auction_date or bid_to_cover is None or total_accepted is None or total_accepted <= 0:
            continue
        dealer = finite(raw.get("primary_dealer_accepted"))
        indirect = finite(raw.get("indirect_bidder_accepted"))
        direct = finite(raw.get("direct_bidder_accepted"))
        security_type = str(raw.get("security_type") or "Unknown")
        term = str(raw.get("original_security_term") or raw.get("security_term") or "Unknown")
        rows.append(
            {
                "auction_date": auction_date,
                "security_type": security_type,
                "security_term": term,
                "term_key": f"{security_type.lower()}|{term.lower()}",
                "bid_to_cover_ratio": bid_to_cover,
                "total_accepted": total_accepted,
                "primary_dealer_share_pct": dealer / total_accepted * 100 if dealer is not None else None,
                "indirect_share_pct": indirect / total_accepted * 100 if indirect is not None else None,
                "direct_share_pct": direct / total_accepted * 100 if direct is not None else None,
                "high_yield": finite(raw.get("high_yield")),
                "high_discount_rate": finite(raw.get("high_discount_rate")),
                "offering_amt": finite(raw.get("offering_amt")),
                "cusip": raw.get("cusip"),
            }
        )
    return sorted(rows, key=lambda row: row["auction_date"])


def mean(values: list[float]) -> float | None:
    return statistics.fmean(values) if values else None


def same_term_comparison(rows: list[dict[str, Any]], latest: dict[str, Any], lookback: int = 8) -> dict[str, Any]:
    prior = [row for row in rows if row["term_key"] == latest["term_key"] and row["auction_date"] < latest["auction_date"]][-lookback:]
    btc_prior = mean([float(row["bid_to_cover_ratio"]) for row in prior if row.get("bid_to_cover_ratio") is not None])
    dealer_prior = mean([float(row["primary_dealer_share_pct"]) for row in prior if row.get("primary_dealer_share_pct") is not None])
    indirect_prior = mean([float(row["indirect_share_pct"]) for row in prior if row.get("indirect_share_pct") is not None])
    btc_delta = latest["bid_to_cover_ratio"] - btc_prior if btc_prior is not None else None
    dealer_delta = latest["primary_dealer_share_pct"] - dealer_prior if latest.get("primary_dealer_share_pct") is not None and dealer_prior is not None else None
    indirect_delta = latest["indirect_share_pct"] - indirect_prior if latest.get("indirect_share_pct") is not None and indirect_prior is not None else None
    quality = 50.0
    if btc_delta is not None:
        quality += btc_delta * 30.0
    if dealer_delta is not None:
        quality -= dealer_delta * 0.6
    if indirect_delta is not None:
        quality += indirect_delta * 0.4
    output = dict(latest)
    output.update(
        {
            "same_term_prior_n": len(prior),
            "bid_to_cover_prior_avg": btc_prior,
            "bid_to_cover_delta": btc_delta,
            "dealer_share_prior_avg_pct": dealer_prior,
            "dealer_share_delta_pp": dealer_delta,
            "indirect_share_prior_avg_pct": indirect_prior,
            "indirect_share_delta_pp": indirect_delta,
            "quality_score": round(clamp(quality, 0, 100), 1) if prior else None,
        }
    )
    return output


def build_auction_context(rows: list[dict[str, Any]], current: datetime) -> tuple[IndicatorResult, dict[str, Any]]:
    result = IndicatorResult(
        "treasury_auction_absorption",
        "Treasury auction absorption",
        "fiscaldata",
        "U.S. Treasury Fiscal Data — Treasury Securities Auctions",
        "score",
        "unavailable",
        resolution="official fiscaldata API",
    )
    coupons = [row for row in rows if str(row.get("security_type")).lower() in COUPON_TYPES]
    if not coupons:
        result.error = "auction response contained no completed coupon auctions"
        return result, {}
    latest_by_term: dict[str, dict[str, Any]] = {}
    for row in coupons:
        latest_by_term[row["term_key"]] = row
    comparisons = [same_term_comparison(coupons, row) for row in latest_by_term.values()]
    comparisons = sorted(comparisons, key=lambda row: row["auction_date"], reverse=True)
    recent_cutoff = (current.date() - timedelta(days=45)).isoformat()
    recent = [row for row in comparisons if row["auction_date"] >= recent_cutoff and row.get("quality_score") is not None]
    if not recent:
        recent = [row for row in comparisons if row.get("quality_score") is not None][:5]
    weights = [max(1.0, float(row.get("total_accepted") or 1.0)) for row in recent]
    score = (
        sum(float(row["quality_score"]) * weight for row, weight in zip(recent, weights)) / sum(weights)
        if recent and sum(weights) > 0
        else None
    )
    result.latest_date = max(row["auction_date"] for row in coupons)
    result.latest_value = round(score, 1) if score is not None else None
    result.change_short = mean([float(row["bid_to_cover_delta"]) for row in recent if row.get("bid_to_cover_delta") is not None])
    result.change_medium = mean([float(row["dealer_share_delta_pp"]) for row in recent if row.get("dealer_share_delta_pp") is not None])
    result.age_days = days_old(result.latest_date, current)
    result.status = "fresh" if result.age_days is not None and result.age_days <= 14 else "stale"
    reasons: list[str] = []
    btc_delta = result.change_short
    dealer_delta = result.change_medium
    indirect_delta = mean([float(row["indirect_share_delta_pp"]) for row in recent if row.get("indirect_share_delta_pp") is not None])
    if btc_delta is not None:
        reasons.append(f"same-tenor bid-to-cover delta {btc_delta:+.2f}")
    if dealer_delta is not None:
        reasons.append(f"dealer share delta {dealer_delta:+.1f} pp")
    if indirect_delta is not None:
        reasons.append(f"indirect share delta {indirect_delta:+.1f} pp")
    context = {
        "score": result.latest_value,
        "state": state_from_score(result.latest_value),
        "coverage": len(recent),
        "latest_auction_date": result.latest_date,
        "average_bid_to_cover_delta": btc_delta,
        "average_dealer_share_delta_pp": dealer_delta,
        "average_indirect_share_delta_pp": indirect_delta,
        "recent_coupon_auctions": comparisons[:10],
        "reasons": reasons,
        "definition": "same-tenor relative demand; lower bid-to-cover, higher dealer share, and lower indirect share reduce the score",
    }
    return result, context


def fetch_auction_context(*, now: datetime | None = None) -> tuple[IndicatorResult, dict[str, Any]]:
    current = now or datetime.now(UTC)
    start = (current.date() - timedelta(days=730)).isoformat()
    try:
        rows = auction_rows(request_json(auction_url(start)))
        return build_auction_context(rows, current)
    except Exception as exc:
        return (
            IndicatorResult(
                "treasury_auction_absorption",
                "Treasury auction absorption",
                "fiscaldata",
                "U.S. Treasury Fiscal Data — Treasury Securities Auctions",
                "score",
                "unavailable",
                resolution="official fiscaldata API",
                error=str(exc)[:500],
            ),
            {},
        )
