#!/usr/bin/env python3
"""Fetch one immutable daily market-wide sentiment snapshot from all Adanos stock sources.

Four calls are used per UTC day: Reddit Stocks, X/FinTwit Stocks, Financial News
Stocks, and Polymarket Stocks. Raw source responses are retained so the derived
composite can evolve without rewriting historical source evidence.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import statistics
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

BASE_URL = "https://api.adanos.org"
SOURCES = {
    "reddit": "/reddit/stocks/v1/market-sentiment",
    "x": "/x/stocks/v1/market-sentiment",
    "news": "/news/stocks/v1/market-sentiment",
    "polymarket": "/polymarket/stocks/v1/market-sentiment",
}
SOURCE_LABELS = {
    "reddit": "Reddit Stocks",
    "x": "X / FinTwit",
    "news": "Financial News",
    "polymarket": "Polymarket",
}


class SentimentError(RuntimeError):
    pass


def canonical_bytes(payload: Any) -> bytes:
    return (json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(data)
    temporary.replace(path)


def write_immutable(path: Path, payload: dict[str, Any]) -> str:
    data = canonical_bytes(payload)
    if path.exists():
        if path.read_bytes() != data:
            raise SentimentError(f"immutable daily sentiment collision: {path}")
        return "unchanged"
    atomic_write(path, data)
    return "created"


def finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def response_header(headers: Any, name: str) -> str | None:
    try:
        value = headers.get(name)
    except Exception:
        return None
    return str(value) if value not in (None, "") else None


def fetch_source(source: str, endpoint: str, api_key: str, observation_date: date, timeout: float) -> dict[str, Any]:
    query = urllib.parse.urlencode({"from": observation_date.isoformat(), "to": observation_date.isoformat()})
    url = f"{BASE_URL}{endpoint}?{query}"
    request = urllib.request.Request(
        url,
        headers={
            "X-API-Key": api_key,
            "Accept": "application/json",
            "User-Agent": "cot-report-market-sentiment/1.0",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
            payload = json.loads(body)
            if not isinstance(payload, dict):
                raise SentimentError(f"{source}: market-sentiment response root is not an object")
            return {
                "ok": True,
                "http_status": int(getattr(response, "status", 200)),
                "raw": payload,
                "rate_limit": {
                    "remaining_monthly": response_header(response.headers, "X-RateLimit-Remaining-Monthly"),
                    "reset_monthly": response_header(response.headers, "X-RateLimit-Reset-Monthly"),
                },
            }
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        return {"ok": False, "http_status": exc.code, "error": f"HTTP {exc.code}: {detail}"}
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, SentimentError) as exc:
        return {"ok": False, "http_status": None, "error": str(exc)}


def activity_fields(payload: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "mentions",
        "unique_posts",
        "unique_tweets",
        "unique_articles",
        "unique_authors",
        "source_count",
        "subreddit_count",
        "trade_count",
        "market_count",
        "current_market_count",
        "unique_traders",
        "active_tickers",
        "total_upvotes",
        "total_liquidity",
    )
    return {key: payload.get(key) for key in keys if payload.get(key) is not None}


def normalize_source(source: str, fetched: dict[str, Any], observation_date: date, retrieved_at: datetime) -> dict[str, Any]:
    base = {
        "source_id": source,
        "label": SOURCE_LABELS[source],
        "provider": "Adanos",
        "endpoint": SOURCES[source],
        "observation_date": observation_date.isoformat(),
        "retrieved_at_utc": retrieved_at.isoformat(timespec="seconds").replace("+00:00", "Z"),
        "status": "LIVE" if fetched.get("ok") else "UNAVAILABLE",
        "http_status": fetched.get("http_status"),
        "rate_limit": fetched.get("rate_limit") or {},
    }
    if not fetched.get("ok"):
        base["error"] = fetched.get("error") or "unknown source failure"
        return base

    payload = fetched["raw"]
    sentiment = finite(payload.get("sentiment_score"))
    bullish = finite(payload.get("bullish_pct"))
    bearish = finite(payload.get("bearish_pct"))
    buzz = finite(payload.get("buzz_score"))
    if sentiment is None or not -1 <= sentiment <= 1:
        base.update({"status": "INVALID", "error": "sentiment_score missing or outside [-1, 1]", "raw": payload})
        return base
    if bullish is not None and not 0 <= bullish <= 100:
        base.update({"status": "INVALID", "error": "bullish_pct outside [0, 100]", "raw": payload})
        return base
    if bearish is not None and not 0 <= bearish <= 100:
        base.update({"status": "INVALID", "error": "bearish_pct outside [0, 100]", "raw": payload})
        return base
    if buzz is not None and not 0 <= buzz <= 100:
        base.update({"status": "INVALID", "error": "buzz_score outside [0, 100]", "raw": payload})
        return base

    base.update({
        "sentiment_score": round(sentiment, 8),
        "sentiment_index": round((sentiment + 1.0) * 50.0, 6),
        "bullish_pct": round(bullish, 6) if bullish is not None else None,
        "bearish_pct": round(bearish, 6) if bearish is not None else None,
        "buzz_score": round(buzz, 6) if buzz is not None else None,
        "trend": payload.get("trend"),
        "trend_history": payload.get("trend_history") if isinstance(payload.get("trend_history"), list) else [],
        "activity": activity_fields(payload),
        "drivers": payload.get("drivers") if isinstance(payload.get("drivers"), list) else [],
        "raw": payload,
    })
    return base


def regime_label(index: float | None) -> str:
    if index is None:
        return "UNAVAILABLE"
    if index >= 70:
        return "VERY BULLISH"
    if index >= 58:
        return "BULLISH"
    if index <= 30:
        return "VERY BEARISH"
    if index <= 42:
        return "BEARISH"
    return "NEUTRAL"


def composite(sources: dict[str, dict[str, Any]]) -> dict[str, Any]:
    live = [payload for payload in sources.values() if payload.get("status") == "LIVE" and finite(payload.get("sentiment_score")) is not None]
    sentiments = [float(payload["sentiment_score"]) for payload in live]
    indices = [float(payload["sentiment_index"]) for payload in live]
    bullish = [float(value) for payload in live if (value := finite(payload.get("bullish_pct"))) is not None]
    bearish = [float(value) for payload in live if (value := finite(payload.get("bearish_pct"))) is not None]
    buzz = [float(value) for payload in live if (value := finite(payload.get("buzz_score"))) is not None]
    required = len(SOURCES)
    available = len(live)
    if available == required:
        state = "LIVE"
    elif available >= 2:
        state = "DEGRADED"
    else:
        state = "FAILED"
    sentiment = statistics.mean(sentiments) if sentiments else None
    index = statistics.mean(indices) if indices else None
    disagreement = statistics.pstdev(sentiments) if len(sentiments) >= 2 else None
    return {
        "state": state,
        "required_sources": required,
        "available_sources": available,
        "coverage_ratio": round(available / required, 4),
        "method": "equal-weight mean across available Adanos stock market-sentiment sources",
        "sentiment_score": round(sentiment, 8) if sentiment is not None else None,
        "sentiment_index": round(index, 6) if index is not None else None,
        "regime": regime_label(index),
        "bullish_pct": round(statistics.mean(bullish), 6) if bullish else None,
        "bearish_pct": round(statistics.mean(bearish), 6) if bearish else None,
        "buzz_score": round(statistics.mean(buzz), 6) if buzz else None,
        "source_disagreement": round(disagreement, 8) if disagreement is not None else None,
        "source_weights": {payload["source_id"]: round(1.0 / available, 6) for payload in live} if available else {},
        "missing_sources": sorted(source for source, payload in sources.items() if payload.get("status") != "LIVE"),
    }


def build_snapshot(api_key: str, observation_date: date, retrieved_at: datetime, timeout: float = 20.0) -> dict[str, Any]:
    normalized: dict[str, dict[str, Any]] = {}
    for source, endpoint in SOURCES.items():
        fetched = fetch_source(source, endpoint, api_key, observation_date, timeout)
        normalized[source] = normalize_source(source, fetched, observation_date, retrieved_at)
    return {
        "schema_version": 1,
        "provider": "Adanos",
        "observation_date": observation_date.isoformat(),
        "retrieved_at_utc": retrieved_at.isoformat(timespec="seconds").replace("+00:00", "Z"),
        "scope": "stock-market-wide sentiment across Reddit, X/FinTwit, financial news and Polymarket",
        "composite": composite(normalized),
        "sources": normalized,
    }


def snapshot_relative_path(observation_date: date) -> Path:
    return Path("sentiment") / str(observation_date.year) / f"{observation_date.isoformat()}.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ledger-root", type=Path, required=True)
    parser.add_argument("--date", help="UTC observation date YYYY-MM-DD; default current UTC date")
    parser.add_argument("--timeout", type=float, default=20.0)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    api_key = os.getenv("ADANOS_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("ADANOS_API_KEY is required and must be supplied as a runtime secret")
    observation_date = date.fromisoformat(args.date) if args.date else datetime.now(UTC).date()
    retrieved_at = datetime.now(UTC)
    payload = build_snapshot(api_key, observation_date, retrieved_at, timeout=args.timeout)
    destination = args.ledger_root / snapshot_relative_path(observation_date)
    result = write_immutable(destination, payload)
    print(
        f"Adanos daily sentiment {result} · date={observation_date} · "
        f"state={payload['composite']['state']} · coverage={payload['composite']['available_sources']}/{payload['composite']['required_sources']}"
    )
    for source, item in payload["sources"].items():
        print(f"{source}: {item['status']} sentiment={item.get('sentiment_score')} buzz={item.get('buzz_score')}")
    if payload["composite"]["state"] == "FAILED":
        raise SystemExit("fewer than two Adanos stock sentiment sources were valid; refusing healthy production status")


if __name__ == "__main__":
    main()
