#!/usr/bin/env python3
"""Daily Treasury Statement cash-flow extension for macro-liquidity diagnosis."""
from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any, Iterable
import urllib.parse

from macro_liquidity_expansion import IndicatorResult, clamp, days_old, finite, iso_date, request_json, state_from_score, zscore_latest

FISCAL_BASE = "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/dts"


def fiscal_rows(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    rows = payload.get("data")
    return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def fiscal_value(row: dict[str, Any], candidates: Iterable[str]) -> float | None:
    for key in candidates:
        value = finite(row.get(key))
        if value is not None:
            return value
    return None


def fiscal_url(endpoint: str, start: date, page_size: int = 10000) -> str:
    params = {
        "filter": f"record_date:gte:{start.isoformat()}",
        "sort": "record_date",
        "page[size]": str(page_size),
    }
    return f"{FISCAL_BASE}/{endpoint}?{urllib.parse.urlencode(params)}"


def change(points: list[tuple[str, float]], observations: int) -> float | None:
    if len(points) <= observations:
        return None
    return points[-1][1] - points[-1 - observations][1]


def operating_cash_result(rows: list[dict[str, Any]], current: datetime) -> tuple[IndicatorResult, dict[str, Any]]:
    result = IndicatorResult(
        "treasury_operating_cash",
        "Daily Treasury operating cash",
        "fiscaldata",
        "U.S. Treasury Fiscal Data — Daily Treasury Statement",
        "USD bn",
        "unavailable",
        resolution="official fiscaldata API",
    )
    candidates: list[tuple[str, float]] = []
    for row in rows:
        stamp = iso_date(row.get("record_date"))
        if not stamp:
            continue
        account = str(row.get("account_type") or "").lower()
        if account and "treasury general account" not in account and "closing balance" not in account:
            continue
        value = fiscal_value(
            row,
            (
                "close_today_bal",
                "closing_balance",
                "open_today_bal",
                "account_bal",
                "current_day_bal",
            ),
        )
        if value is not None:
            candidates.append((stamp, value / 1000.0))
    points = sorted(dict(candidates).items())
    if not points:
        result.error = "operating-cash response contained no recognized TGA balance field"
        return result, {}
    result.latest_date, result.latest_value = points[-1]
    result.change_short = change(points, min(5, max(1, len(points) - 1)))
    result.change_medium = change(points, min(20, max(1, len(points) - 1)))
    result.zscore = zscore_latest(points)
    result.age_days = days_old(result.latest_date, current)
    result.status = "fresh" if result.age_days is not None and result.age_days <= 4 else "stale"
    return result, {
        "latest_operating_cash_bn": result.latest_value,
        "operating_cash_change_5d_bn": result.change_short,
        "operating_cash_change_20d_bn": result.change_medium,
    }


def treasury_flow_result(rows: list[dict[str, Any]], current: datetime) -> tuple[IndicatorResult, dict[str, Any]]:
    result = IndicatorResult(
        "treasury_cash_flows",
        "Daily Treasury deposits and withdrawals",
        "fiscaldata",
        "U.S. Treasury Fiscal Data — Daily Treasury Statement",
        "USD bn",
        "unavailable",
        resolution="official fiscaldata API",
    )
    by_date: dict[str, dict[str, Any]] = {}
    for row in rows:
        stamp = iso_date(row.get("record_date"))
        amount_mn = fiscal_value(row, ("transaction_today_amt", "current_day_amt", "today_amt", "amount"))
        if not stamp or amount_mn is None:
            continue
        transaction_type = str(row.get("transaction_type") or row.get("type") or "").lower()
        category = str(row.get("transaction_catg") or row.get("transaction_category") or row.get("account_type") or "Other")
        bucket = by_date.setdefault(
            stamp,
            {"deposits": 0.0, "withdrawals": 0.0, "tax_deposits": 0.0, "categories": {}},
        )
        amount_bn = amount_mn / 1000.0
        if "withdraw" in transaction_type:
            bucket["withdrawals"] += amount_bn
            sign = 1.0
        elif "deposit" in transaction_type:
            bucket["deposits"] += amount_bn
            sign = -1.0
            if "tax" in category.lower() or "internal revenue" in category.lower():
                bucket["tax_deposits"] += amount_bn
        else:
            continue
        bucket["categories"][category] = bucket["categories"].get(category, 0.0) + sign * amount_bn

    points = [(stamp, values["withdrawals"] - values["deposits"]) for stamp, values in sorted(by_date.items())]
    if not points:
        result.error = "deposits/withdrawals response contained no recognized transaction rows"
        return result, {}

    result.latest_date, result.latest_value = points[-1]
    last5 = points[-5:]
    last20 = points[-20:]
    result.change_short = sum(value for _, value in last5)
    result.change_medium = sum(value for _, value in last20)
    result.zscore = zscore_latest(points)
    result.age_days = days_old(result.latest_date, current)
    result.status = "fresh" if result.age_days is not None and result.age_days <= 4 else "stale"
    five_dates = {stamp for stamp, _ in last5}
    deposits5 = sum(by_date[stamp]["deposits"] for stamp in five_dates)
    withdrawals5 = sum(by_date[stamp]["withdrawals"] for stamp in five_dates)
    tax5 = sum(by_date[stamp]["tax_deposits"] for stamp in five_dates)
    categories: dict[str, float] = {}
    for stamp in five_dates:
        for category, value in by_date[stamp]["categories"].items():
            categories[category] = categories.get(category, 0.0) + value
    top_categories = sorted(categories.items(), key=lambda item: abs(item[1]), reverse=True)[:6]
    return result, {
        "latest_flow_date": result.latest_date,
        "daily_private_cash_flow_bn": result.latest_value,
        "private_cash_flow_5d_bn": result.change_short,
        "private_cash_flow_20d_bn": result.change_medium,
        "deposits_5d_bn": deposits5,
        "withdrawals_5d_bn": withdrawals5,
        "tax_deposits_5d_bn": tax5,
        "top_cash_flow_categories_5d": [
            {"category": category, "private_cash_effect_bn": round(value, 2)}
            for category, value in top_categories
        ],
        "sign_convention": "positive = Treasury withdrawal / private-sector cash injection; negative = Treasury deposit / private-sector cash drain",
    }


def fetch_treasury_cash_context(*, now: datetime | None = None) -> tuple[list[IndicatorResult], dict[str, Any]]:
    current = now or datetime.now(UTC)
    start = current.date() - timedelta(days=70)
    results: list[IndicatorResult] = []
    context: dict[str, Any] = {}
    endpoints = (
        ("operating_cash_balance", 500, operating_cash_result),
        ("deposits_withdrawals_operating_cash", 10000, treasury_flow_result),
    )
    for endpoint, page_size, parser in endpoints:
        try:
            result, extra = parser(fiscal_rows(request_json(fiscal_url(endpoint, start, page_size))), current)
        except Exception as exc:
            key = "treasury_operating_cash" if endpoint == "operating_cash_balance" else "treasury_cash_flows"
            label = "Daily Treasury operating cash" if endpoint == "operating_cash_balance" else "Daily Treasury deposits and withdrawals"
            result = IndicatorResult(
                key,
                label,
                "fiscaldata",
                "U.S. Treasury Fiscal Data — Daily Treasury Statement",
                "USD bn",
                "unavailable",
                resolution="official fiscaldata API",
                error=str(exc)[:500],
            )
            extra = {}
        results.append(result)
        context.update(extra)
    return results, context


def fiscal_pillar(context: dict[str, Any], results: dict[str, IndicatorResult]) -> dict[str, Any]:
    flow = finite(context.get("private_cash_flow_5d_bn"))
    tga_change = finite(context.get("operating_cash_change_5d_bn"))
    available = [results.get("treasury_operating_cash"), results.get("treasury_cash_flows")]
    fresh_count = sum(result is not None and result.status == "fresh" for result in available)
    if fresh_count == 0:
        return {
            "label": "Daily fiscal cash flow",
            "score": None,
            "state": "Unavailable",
            "coverage": 0.0,
            "reasons": ["Daily Treasury Statement feeds unavailable"],
        }
    score = 50.0
    reasons: list[str] = []
    if flow is not None:
        score += clamp(flow / 4.0, -25.0, 25.0)
        reasons.append(f"5d private cash effect {flow:+.1f} bn")
    if tga_change is not None:
        score -= clamp(tga_change / 5.0, -15.0, 15.0)
        reasons.append(f"5d operating-cash change {tga_change:+.1f} bn")
    tax = finite(context.get("tax_deposits_5d_bn"))
    if tax is not None and tax > 100:
        reasons.append(f"5d tax deposits {tax:.1f} bn")
    final_score = round(clamp(score, 0, 100), 1)
    return {
        "label": "Daily fiscal cash flow",
        "score": final_score,
        "state": state_from_score(final_score),
        "coverage": round(fresh_count / 2.0, 3),
        "private_cash_flow_5d_bn": flow,
        "private_cash_flow_20d_bn": finite(context.get("private_cash_flow_20d_bn")),
        "operating_cash_change_5d_bn": tga_change,
        "tax_deposits_5d_bn": tax,
        "reasons": reasons,
    }
