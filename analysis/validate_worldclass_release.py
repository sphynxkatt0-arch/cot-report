#!/usr/bin/env python3
"""Validate the production COT dashboard payload and publish release health.

Hard data-contract failures stop deployment. A late/missing expected CFTC report
or a temporary external macro-source outage is not converted to neutral: the
validator publishes explicit delayed/degraded health while preserving valid core
data and the browser's official-source recovery path.
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

import model_spec as model_cfg

ROOT = Path(__file__).resolve().parent
WORLDCLASS = ROOT / "worldclass"
BASE = WORLDCLASS / "base.json"
RUNTIME_MODEL = WORLDCLASS / "model-spec.json"
METALS = WORLDCLASS / "metals.json"
BACKTEST = WORLDCLASS / "backtest.json"
REGIME = WORLDCLASS / "regime_backtest.json"
STATUS = WORLDCLASS / "release-status.json"
PLUMBING = ROOT / "model_output" / "macro_liquidity_expansion.json"

MARKETS = ("sp500", "nq", "vix", "rty", "dow", "gold", "silver")
INDEX_MARKETS = ("sp500", "nq", "vix", "rty", "dow")
METAL_MARKETS = ("gold", "silver")
MAX_INITIAL_GZIP = int(os.getenv("WORLDCLASS_INITIAL_GZIP_BUDGET", "1000000"))
MODEL_SPEC = model_cfg.load_model_spec()
MODEL_VERSION = str(MODEL_SPEC["model_version"])
MODEL_SPEC_HASH = model_cfg.model_spec_hash(MODEL_SPEC)
ACTOR_TAXONOMY = MODEL_SPEC["actor_taxonomy"]
HISTORICAL_SIGNAL_FLOORS = {
    ("nq", "tff"): 500,
    ("nq", "legacy"): 500,
    ("sp500", "tff"): 450,
    ("sp500", "legacy"): 450,
    ("gold", "disaggregated"): 500,
    ("silver", "disaggregated"): 500,
}


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


def approx_equal(left: float, right: float, absolute: float = 0.05) -> bool:
    return abs(left - right) <= max(absolute, 1e-9 * max(abs(left), abs(right), 1.0))


def validate_actor_taxonomy(dataset: str, market: str, payload: dict[str, Any]) -> None:
    taxonomy = ACTOR_TAXONOMY.get(dataset)
    assert isinstance(taxonomy, dict), f"{dataset}/{market}: unsupported COT dataset taxonomy"
    expected = set(taxonomy.get("required_categories") or [])
    categories = payload.get("categories") or {}
    actual = set(categories)
    assert expected, f"{dataset}/{market}: canonical actor taxonomy empty"
    assert actual == expected, (
        f"{dataset}/{market}: actor taxonomy mismatch; "
        f"missing={sorted(expected - actual)} extra={sorted(actual - expected)}"
    )
    # Gold/Silver are required to have Disaggregated coverage, but valid Legacy
    # history may coexist. Only the Disaggregated actor schema is metal-specific.
    if dataset == "disaggregated":
        assert market in METAL_MARKETS, f"{dataset}/{market}: Disaggregated production payload is reserved for metals"


def validate_records(dataset: str, market: str, payload: dict[str, Any]) -> None:
    rows = payload.get("records") or []
    assert len(rows) >= 2, f"{dataset}/{market}: fewer than two observations"
    dates = [str(row.get("date") or "")[:10] for row in rows]
    assert all(parse_day(value) for value in dates), f"{dataset}/{market}: invalid date"
    assert len(dates) == len(set(dates)), f"{dataset}/{market}: duplicate report dates"
    assert dates == sorted(dates), f"{dataset}/{market}: dates not sorted"
    validate_actor_taxonomy(dataset, market, payload)
    categories = payload.get("categories") or {}

    for row in rows:
        row_date = str(row.get("date") or "")[:10]
        oi_raw = row.get("open_interest")
        oi = None
        if oi_raw is not None:
            oi = finite_number(oi_raw)
            assert oi is not None, f"{dataset}/{market}/{row_date}: invalid open interest"
            assert oi >= 0, f"{dataset}/{market}/{row_date}: negative open interest"

        for key in categories:
            long = finite_number(row.get(f"{key}_long")) if row.get(f"{key}_long") is not None else None
            short = finite_number(row.get(f"{key}_short")) if row.get(f"{key}_short") is not None else None
            net = finite_number(row.get(f"{key}_net")) if row.get(f"{key}_net") is not None else None
            net_pct = finite_number(row.get(f"{key}_net_oi_pct")) if row.get(f"{key}_net_oi_pct") is not None else None
            short_pct = finite_number(row.get(f"{key}_short_oi_pct")) if row.get(f"{key}_short_oi_pct") is not None else None

            for field_name, value in (
                ("long", long), ("short", short), ("net", net),
                ("net_oi_pct", net_pct), ("short_oi_pct", short_pct),
            ):
                raw = row.get(f"{key}_{field_name}")
                if raw is not None:
                    assert value is not None, f"{dataset}/{market}/{row_date}: non-finite {key}_{field_name}"

            if long is not None:
                assert long >= 0, f"{dataset}/{market}/{row_date}: negative {key}_long"
            if short is not None:
                assert short >= 0, f"{dataset}/{market}/{row_date}: negative {key}_short"
            if long is not None and short is not None and net is not None:
                assert approx_equal(long - short, net, absolute=1.0), (
                    f"{dataset}/{market}/{row_date}: {key} net arithmetic mismatch"
                )
            if oi is not None and oi > 0 and net is not None and net_pct is not None:
                assert approx_equal(net / oi * 100.0, net_pct), (
                    f"{dataset}/{market}/{row_date}: {key} net/OI percentage mismatch"
                )
            if oi is not None and oi > 0 and short is not None and short_pct is not None:
                assert approx_equal(short / oi * 100.0, short_pct), (
                    f"{dataset}/{market}/{row_date}: {key} short/OI percentage mismatch"
                )


def validate_market_coverage(cot: dict[str, Any], base: dict[str, Any], metals: dict[str, Any]) -> None:
    for market in INDEX_MARKETS:
        assert any((cot.get(dataset) or {}).get(market) for dataset in ("tff", "legacy")), f"{market}: no TFF/Legacy COT payload"
    for market in METAL_MARKETS:
        payload = (cot.get("disaggregated") or {}).get(market)
        assert payload, f"{market}: no Disaggregated COT payload"
        validate_actor_taxonomy("disaggregated", market, payload)
    prices = dict(base.get("PRICE_DATA") or {})
    prices.update(metals.get("prices") or {})
    for market in MARKETS:
        payload = prices.get(market)
        rows = payload if isinstance(payload, list) else (payload or {}).get("records") or []
        assert rows, f"{market}: price history missing"


def validate_model_identity(payload: dict[str, Any], name: str) -> None:
    assert payload.get("model_version") == MODEL_VERSION, f"{name}: model_version mismatch"
    assert payload.get("model_spec_hash") == MODEL_SPEC_HASH, f"{name}: model_spec_hash mismatch"


def validate_backtests(backtest: dict[str, Any], regime: dict[str, Any]) -> None:
    assert backtest.get("markets"), "standard backtest has no markets"
    assert regime.get("markets"), "regime backtest has no markets"
    validate_model_identity(backtest, "standard backtest")
    validate_model_identity(regime, "regime backtest")

    for market, market_payload in backtest["markets"].items():
        for dataset, payload in (market_payload.get("datasets") or {}).items():
            assert payload.get("methodology", {}).get("lookahead_safe") is True, f"{market}/{dataset}: COT backtest not lookahead-safe"
            validate_model_identity(payload, f"{market}/{dataset} COT backtest")
            score = payload.get("current", {}).get("score")
            assert score is None or 0 <= float(score) <= 100, f"{market}/{dataset}: COT score out of bounds"

    for (market, dataset), floor in HISTORICAL_SIGNAL_FLOORS.items():
        payload = ((backtest.get("markets") or {}).get(market) or {}).get("datasets", {}).get(dataset)
        assert isinstance(payload, dict), f"{market}/{dataset}: required historical research missing"
        count = int(payload.get("historical_signal_count") or 0)
        assert count >= floor, f"{market}/{dataset}: historical signal count {count} below regression floor {floor}"

    for market, market_payload in regime["markets"].items():
        for dataset, payload in (market_payload.get("datasets") or {}).items():
            assert payload.get("methodology", {}).get("lookahead_safe") is True, f"{market}/{dataset}: regime backtest not lookahead-safe"
            validate_model_identity(payload, f"{market}/{dataset} regime backtest")
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


def validate_runtime_model_contract(base: dict[str, Any], runtime_model: dict[str, Any]) -> None:
    embedded = base.get("MODEL_SPEC") or {}
    for name, runtime in (("embedded runtime MODEL_SPEC", embedded), ("standalone runtime model-spec.json", runtime_model)):
        assert runtime.get("model_version") == MODEL_VERSION, f"{name}: model_version mismatch"
        assert runtime.get("model_spec_hash") == MODEL_SPEC_HASH, f"{name}: model_spec_hash mismatch"
        assert runtime.get("score_models") == MODEL_SPEC.get("score_models"), f"{name}: score models diverge"
        assert runtime.get("actor_taxonomy") == MODEL_SPEC.get("actor_taxonomy"), f"{name}: actor taxonomy diverges"
        assert runtime.get("horizons") == MODEL_SPEC.get("horizons"), f"{name}: horizons diverge"
    assert embedded == runtime_model, "embedded and standalone runtime model contracts differ"
    bundle_meta = base.get("bundle_meta") or {}
    assert bundle_meta.get("model_version") == MODEL_VERSION, "bundle model_version mismatch"
    assert bundle_meta.get("model_spec_hash") == MODEL_SPEC_HASH, "bundle model_spec_hash mismatch"


def validate_macro_plumbing(plumbing: dict[str, Any]) -> dict[str, Any]:
    """Require the macro contract, while treating third-party outages as degraded health."""
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

    # These two values come from the same validated macro monitor already shown
    # by the top cards, so their absence indicates a real internal data-contract
    # break and remains a hard deployment failure.
    assert finite_number(pillars["net_liquidity"].get("value")) is not None, "macro plumbing net_liquidity value missing"
    assert finite_number(pillars["bank_reserves"].get("value")) is not None, "macro plumbing bank_reserves value missing"

    external = ("funding_microstructure", "dealer_absorption", "fiscal_cash_flow", "auction_absorption")
    available_external = [key for key in external if str(pillars[key].get("state")) != "Unavailable"]
    unavailable_external = [key for key in external if key not in available_external]

    sources = plumbing.get("sources")
    assert isinstance(sources, list) and sources, "macro plumbing source matrix missing"
    coverage = finite_number(plumbing.get("source_coverage_ratio"))
    assert coverage is not None and 0 <= coverage <= 1, "macro plumbing coverage ratio invalid"

    return {
        "state": "LIVE" if available_external else "DEGRADED",
        "model_version": plumbing.get("model_version"),
        "generated_at_utc": plumbing.get("generated_at_utc"),
        "source_coverage_ratio": coverage,
        "source_coverage_label": plumbing.get("source_coverage_label"),
        "available_external_pillars": available_external,
        "unavailable_external_pillars": unavailable_external,
        "browser_official_recovery": True,
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
        WORLDCLASS / "macro-state-renderer.js",
        WORLDCLASS / "macro-live-sources.js",
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
    runtime_model = load(RUNTIME_MODEL)
    metals = load(METALS, required=False)
    backtest = load(BACKTEST)
    regime = load(REGIME)
    plumbing = load(PLUMBING)
    cot = combined_cot(base, metals)

    validate_runtime_model_contract(base, runtime_model)
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
        "schema_version": 2,
        "state": "DELAYED" if delayed else "LIVE",
        "generated_at_utc": now.isoformat(timespec="seconds").replace("+00:00", "Z"),
        "latest_cot_report_date": latest.isoformat() if latest else None,
        "expected_cot_report_date": expected.isoformat(),
        "model": {
            "model_version": MODEL_VERSION,
            "model_spec_hash": MODEL_SPEC_HASH,
        },
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
        "actor_taxonomy": "PASS",
        "lookahead_safety": "PASS",
        "historical_regression_floors": {
            f"{market}/{dataset}": floor for (market, dataset), floor in HISTORICAL_SIGNAL_FLOORS.items()
        },
        "macro_plumbing": plumbing_health,
        "performance_gzip_bytes": performance,
    }
    STATUS.write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")
    print(f"Worldclass release validation PASS · state={status['state']}")
    print(f"Model {MODEL_VERSION} · sha256={MODEL_SPEC_HASH}")
    external_text = ", ".join(plumbing_health["available_external_pillars"]) or "none"
    print(f"Macro plumbing coverage: {plumbing_health['source_coverage_ratio']:.0%} · external pillars: {external_text}")
    if plumbing_health["state"] == "DEGRADED":
        print("::warning::All server-side external macro feeds are unavailable; deploying validated core macro data with browser official-source recovery enabled.")
    elif plumbing_health["unavailable_external_pillars"]:
        print(f"::warning::Macro plumbing partial coverage; unavailable: {', '.join(plumbing_health['unavailable_external_pillars'])}.")
    print(f"Initial non-Plotly gzip payload: {performance['initial_total']:,} bytes")
    if delayed:
        print(f"::warning::{status['message']}")


if __name__ == "__main__":
    main()
