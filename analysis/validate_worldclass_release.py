#!/usr/bin/env python3
"""Validate the production COT dashboard payload and publish release health.

Hard data-contract failures stop deployment. A late/missing expected CFTC report
is *not* converted to neutral and does not stop deployment: the validator writes
worldclass/release-status.json with state=DELAYED so the last valid observation
can remain live with an explicit warning.
"""
from __future__ import annotations

import gzip
import json
import math
import os
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
WORLDCLASS = ROOT / "worldclass"
BASE = WORLDCLASS / "base.json"
METALS = WORLDCLASS / "metals.json"
BACKTEST = WORLDCLASS / "backtest.json"
REGIME = WORLDCLASS / "regime_backtest.json"
STATUS = WORLDCLASS / "release-status.json"
PLUMBING = ROOT / "model_output" / "macro_liquidity_expansion.json"

MARKETS = ("sp500", "nq", "vix", "rty", "dow", "gold", "silver")
INDEX_MARKETS = ("sp500", "nq", "vix", "rty", "dow")
METAL_MARKETS = ("gold", "silver")
MAX_INITIAL_GZIP = int(os.getenv("WORLDCLASS_INITIAL_GZIP_BUDGET", "1000000"))


def load(path: Path, required: bool = True) -> Any:
    if not path.exists():
        if required:
            raise AssertionError(f"missing required file: {path}")
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def finite_number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def parse_day(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def expected_cot_report(now: datetime) -> date:
    """Most recent Tuesday report that should already be public at 21:35 Stockholm."""
    local = now.astimezone(ZoneInfo("Europe/Stockholm"))
    today = local.date()
    days_since_friday = (today.weekday() - 4) % 7
    friday = today - timedelta(days=days_since_friday)
    if today.weekday() == 4 and (local.hour, local.minute) < (21, 35):
        friday -= timedelta(days=7)
    return friday - timedelta(days=3)


def combined_cot(base: dict[str, Any], metals: dict[str, Any]) -> dict[str, Any]:
    cot = json.loads(json.dumps(base.get("COT_DATA") or {}))
    if metals:
        cot.setdefault("disaggregated", {}).update(metals.get("markets") or {})
    return cot


def validate_records(dataset: str, market: str, payload: dict[str, Any]) -> None:
    rows = payload.get("records") or []
    assert len(rows) >= 2, f"{dataset}/{market}: fewer than two observations"
    dates = [str(row.get("date") or "")[:10] for row in rows]
    assert all(parse_day(value) for value in dates), f"{dataset}/{market}: invalid date"
    assert len(dates) == len(set(dates)), f"{dataset}/{market}: duplicate report dates"
    assert dates == sorted(dates), f"{dataset}/{market}: dates not sorted"
    categories = payload.get("categories") or {}
    assert categories, f"{dataset}/{market}: category map missing"
    for row in rows:
        oi = row.get("open_interest")
        if oi is not None:
            assert float(oi) >= 0, f"{dataset}/{market}: negative open interest"
        for key in categories:
            for suffix in ("long", "short"):
                value = row.get(f"{key}_{suffix}")
                if value is not None:
                    assert float(value) >= 0, f"{dataset}/{market}: negative {key}_{suffix}"


def validate_market_coverage(cot: dict[str, Any], base: dict[str, Any], metals: dict[str, Any]) -> None:
    for market in INDEX_MARKETS:
        assert any((cot.get(dataset) or {}).get(market) for dataset in ("tff", "legacy")), f"{market}: no TFF/Legacy COT payload"
    for market in METAL_MARKETS:
        assert (cot.get("disaggregated") or {}).get(market), f"{market}: no Disaggregated COT payload"
    prices = dict(base.get("PRICE_DATA") or {})
    prices.update(metals.get("prices") or {})
    for market in MARKETS:
        payload = prices.get(market)
        rows = payload if isinstance(payload, list) else (payload or {}).get("records") or []
        assert rows, f"{market}: price history missing"


def validate_backtests(backtest: dict[str, Any], regime: dict[str, Any]) -> None:
    assert backtest.get("markets"), "standard backtest has no markets"
    assert regime.get("markets"), "regime backtest has no markets"
    for market, market_payload in backtest["markets"].items():
        for dataset, payload in (market_payload.get("datasets") or {}).items():
            assert payload.get("methodology", {}).get("lookahead_safe") is True, f"{market}/{dataset}: COT backtest not lookahead-safe"
            score = payload.get("current", {}).get("score")
            assert score is None or 0 <= float(score) <= 100, f"{market}/{dataset}: COT score out of bounds"
    for market, market_payload in regime["markets"].items():
        for dataset, payload in (market_payload.get("datasets") or {}).items():
            assert payload.get("methodology", {}).get("lookahead_safe") is True, f"{market}/{dataset}: regime backtest not lookahead-safe"
            current = payload.get("current") or {}
            for key in ("cot_score", "macro_score"):
                value = current.get(key)
                assert value is None or 0 <= float(value) <= 100, f"{market}/{dataset}: {key} out of bounds"
            release = parse_day(current.get("release_target_date"))
            report = parse_day(current.get("report_date"))
            if release and report:
                assert release == report + timedelta(days=3), f"{market}/{dataset}: release anchor mismatch"
            families = payload.get("families") or {}
            assert all(key in families for key in ("cot", "macro", "combined")), f"{market}/{dataset}: model families missing"


def validate_macro_plumbing(plumbing: dict[str, Any]) -> dict[str, Any]:
    """Reject deployments that would render the control room as an empty shell."""
    assert isinstance(plumbing, dict) and plumbing, "macro plumbing payload is empty"
    assert plumbing.get("schema_version") == 1, "macro plumbing schema_version must be 1"
    assert plumbing.get("model_version"), "macro plumbing model_version missing"

    pillars = plumbing.get("pillars")
    assert isinstance(pillars, dict), "macro plumbing pillars missing"
    required = (
        "net_liquidity",
        "bank_reserves",
        "funding_microstructure",
        "dealer_absorption",
        "fiscal_cash_flow",
        "auction_absorption",
    )
    for key in required:
        assert isinstance(pillars.get(key), dict), f"macro plumbing pillar missing: {key}"
        assert pillars[key].get("state"), f"macro plumbing pillar state missing: {key}"

    # These two are backed by the same macro monitor that drives the populated
    # headline cards. If they are missing here, the builder/extraction path is
    # broken and deployment must stop rather than publish a wall of n/a values.
    assert finite_number(pillars["net_liquidity"].get("value")) is not None, "macro plumbing net_liquidity value missing"
    assert finite_number(pillars["bank_reserves"].get("value")) is not None, "macro plumbing bank_reserves value missing"

    external = ("funding_microstructure", "dealer_absorption", "fiscal_cash_flow", "auction_absorption")
    available_external = [key for key in external if str(pillars[key].get("state")) != "Unavailable"]
    assert available_external, "all external macro-plumbing pillars are unavailable; refusing empty control-room deploy"

    sources = plumbing.get("sources")
    assert isinstance(sources, list) and sources, "macro plumbing source matrix missing"
    coverage = finite_number(plumbing.get("source_coverage_ratio"))
    assert coverage is not None and 0 <= coverage <= 1, "macro plumbing coverage ratio invalid"

    return {
        "model_version": plumbing.get("model_version"),
        "generated_at_utc": plumbing.get("generated_at_utc"),
        "source_coverage_ratio": coverage,
        "source_coverage_label": plumbing.get("source_coverage_label"),
        "available_external_pillars": available_external,
        "required_pillars": list(required),
    }


def gzip_size(path: Path) -> int:
    return len(gzip.compress(path.read_bytes(), compresslevel=9)) if path.exists() else 0


def validate_performance_budget() -> dict[str, int]:
    immediate = [
        WORLDCLASS / "base.json",
        WORLDCLASS / "app.js",
        WORLDCLASS / "styles.css",
        WORLDCLASS / "bootstrap.js",
        WORLDCLASS / "kpi-accent.css",
        WORLDCLASS / "enhancements.js",
        WORLDCLASS / "enhancements.css",
        WORLDCLASS / "decision-system.js",
        WORLDCLASS / "decision-system.css",
        WORLDCLASS / "macro-control-fallback.js",
        WORLDCLASS / "regime_backtest.json",
        PLUMBING,
    ]
    sizes = {str(path.relative_to(ROOT)): gzip_size(path) for path in immediate if path.exists()}
    total = sum(sizes.values())
    assert total <= MAX_INITIAL_GZIP, f"initial non-Plotly payload {total:,} gzip bytes exceeds budget {MAX_INITIAL_GZIP:,}"
    sizes["initial_total"] = total
    return sizes


def latest_report_by_market(cot: dict[str, Any]) -> dict[str, date | None]:
    output: dict[str, date | None] = {market: None for market in MARKETS}
    for dataset in cot.values():
        if not isinstance(dataset, dict):
            continue
        for market, payload in dataset.items():
            if market not in output or not isinstance(payload, dict):
                continue
            rows = payload.get("records") or []
            if not rows:
                continue
            parsed = parse_day(rows[-1].get("date"))
            if parsed and (output[market] is None or parsed > output[market]):
                output[market] = parsed
    return output


def main() -> None:
    base = load(BASE)
    metals = load(METALS, required=False)
    backtest = load(BACKTEST)
    regime = load(REGIME)
    plumbing = load(PLUMBING)
    cot = combined_cot(base, metals)

    validate_market_coverage(cot, base, metals)
    for dataset, markets in cot.items():
        if not isinstance(markets, dict):
            continue
        for market, payload in markets.items():
            if isinstance(payload, dict) and market in MARKETS:
                validate_records(dataset, market, payload)
    validate_backtests(backtest, regime)
    plumbing_health = validate_macro_plumbing(plumbing)
    performance = validate_performance_budget()

    now = datetime.now(UTC)
    latest_by_market = latest_report_by_market(cot)
    expected = expected_cot_report(now)
    market_states = {
        market: {
            "state": "DELAYED" if latest is None or latest < expected else "LIVE",
            "latest_cot_report_date": latest.isoformat() if latest else None,
            "expected_cot_report_date": expected.isoformat(),
        }
        for market, latest in latest_by_market.items()
    }
    delayed_markets = [market for market, value in market_states.items() if value["state"] == "DELAYED"]
    delayed = bool(delayed_markets)
    latest_values = [value for value in latest_by_market.values() if value is not None]
    latest = max(latest_values) if latest_values else None
    status = {
        "schema_version": 1,
        "state": "DELAYED" if delayed else "LIVE",
        "generated_at_utc": now.isoformat(timespec="seconds").replace("+00:00", "Z"),
        "latest_cot_report_date": latest.isoformat() if latest else None,
        "expected_cot_report_date": expected.isoformat(),
        "market_states": market_states,
        "markets": {
            market: {
                "status": value["state"],
                "latest_report_date": value["latest_cot_report_date"],
                "expected_report_date": value["expected_cot_report_date"],
            }
            for market, value in market_states.items()
        },
        "delayed_markets": delayed_markets,
        "message": (
            f"Expected CFTC report for {expected.isoformat()} is missing for: {', '.join(delayed_markets)}; serving each market's last valid observation."
            if delayed else f"Validated current CFTC report {expected.isoformat()} across all required markets."
        ),
        "markets_validated": list(MARKETS),
        "data_contracts": "PASS",
        "lookahead_safety": "PASS",
        "macro_plumbing": plumbing_health,
        "performance_gzip_bytes": performance,
    }
    STATUS.write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")
    print(f"Worldclass release validation PASS · state={status['state']}")
    print(f"Macro plumbing coverage: {plumbing_health['source_coverage_ratio']:.0%} · external pillars: {', '.join(plumbing_health['available_external_pillars'])}")
    print(f"Initial non-Plotly gzip payload: {performance['initial_total']:,} bytes")
    if delayed:
        print(f"::warning::{status['message']}")


if __name__ == "__main__":
    main()
