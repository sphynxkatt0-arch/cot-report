#!/usr/bin/env python3
"""Build a source-backed macro-liquidity control-room payload.

The extension is intentionally non-directional. It explains liquidity plumbing,
funding microstructure, dealer absorption, money-market allocation, and near-term
Treasury pressure without changing the governed COT decision.
"""
from __future__ import annotations

import json
import math
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, asdict
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable

try:
    from build_directional_cot_report import extract_js_object
except ImportError:
    extract_js_object = None

ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / "config" / "macro_liquidity_sources_v1.json"
DASHBOARD = ROOT / "interactive_cot_dashboard.html"
OUT_DIR = ROOT / "model_output"
JSON_OUT = OUT_DIR / "macro_liquidity_expansion.json"
CSV_OUT = OUT_DIR / "macro_liquidity_source_status.csv"
OFR_BASE = "https://data.financialresearch.gov/v1"
USER_AGENT = "cot-report-macro-liquidity/1.0 (public-data research)"


def finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def iso_date(value: Any) -> str | None:
    if value in {None, ""}:
        return None
    text = str(value)[:10]
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError:
        return None


def days_old(value: str | None, now: datetime | None = None) -> int | None:
    parsed = iso_date(value)
    if not parsed:
        return None
    today = (now or datetime.now(UTC)).date()
    return max(0, (today - date.fromisoformat(parsed)).days)


def request_json(url: str, *, timeout: int = 25, retries: int = 2) -> Any:
    error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8-sig"))
        except Exception as exc:
            error = exc
            if attempt < retries:
                time.sleep(0.8 * (attempt + 1))
    raise RuntimeError(f"GET {url} failed: {error}")


def load_config(path: Path = CONFIG) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1:
        raise ValueError("macro liquidity source config must use schema_version 1")
    if not isinstance(payload.get("indicators"), list) or not payload["indicators"]:
        raise ValueError("macro liquidity source config has no indicators")
    return payload


def series_points(payload: Any, mnemonic: str | None = None) -> list[tuple[str, float]]:
    raw: Any = payload
    if isinstance(payload, dict) and mnemonic and mnemonic in payload:
        raw = payload[mnemonic]
    if isinstance(raw, dict) and "timeseries" in raw:
        raw = raw["timeseries"]
    if isinstance(raw, dict):
        preferred = raw.get("aggregation")
        if isinstance(preferred, list):
            raw = preferred
        else:
            raw = next((value for value in raw.values() if isinstance(value, list)), [])
    if not isinstance(raw, list):
        return []
    output: list[tuple[str, float]] = []
    for item in raw:
        if not isinstance(item, (list, tuple)) or len(item) < 2:
            continue
        stamp = iso_date(item[0])
        value = finite(item[1])
        if stamp and value is not None:
            output.append((stamp, value))
    return sorted(dict(output).items())


def metadata_text(row: dict[str, Any]) -> str:
    return " ".join(str(row.get(key, "")) for key in ("value", "field", "mnemonic", "dataset")).lower()


def candidate_score(row: dict[str, Any], spec: dict[str, Any]) -> float:
    if str(row.get("dataset", "")).lower() != str(spec.get("dataset", "")).lower():
        return -1e9
    text = metadata_text(row)
    score = 0.0
    for term in spec.get("include_terms", []):
        score += 3.0 if str(term).lower() in text else -1.0
    for term in spec.get("exclude_terms", []):
        if str(term).lower() in text:
            score -= 8.0
    if str(row.get("field", "")).startswith("description/"):
        score += 0.5
    return score


def resolve_mnemonic(spec: dict[str, Any]) -> tuple[str | None, str]:
    for mnemonic in spec.get("preferred_mnemonics", []):
        if mnemonic:
            return str(mnemonic), "configured"
    query = str(spec.get("search_query") or "").strip()
    if not query:
        return None, "no query"
    url = f"{OFR_BASE}/metadata/search?{urllib.parse.urlencode({'query': query})}"
    rows = request_json(url)
    if not isinstance(rows, list):
        return None, "search response invalid"
    ranked = sorted(
        ((candidate_score(row, spec), row) for row in rows if isinstance(row, dict)),
        key=lambda item: item[0],
        reverse=True,
    )
    if not ranked or ranked[0][0] < float(spec.get("minimum_match_score", 2.0)):
        return None, "no qualified match"
    return str(ranked[0][1].get("mnemonic") or "") or None, "metadata search"


def change(points: list[tuple[str, float]], observations: int) -> float | None:
    if len(points) <= observations:
        return None
    return points[-1][1] - points[-1 - observations][1]


def zscore_latest(points: list[tuple[str, float]], window: int = 156) -> float | None:
    values = [value for _, value in points[-window:]]
    if len(values) < 26:
        return None
    mean = sum(values) / len(values)
    variance = sum((value - mean) ** 2 for value in values) / max(1, len(values) - 1)
    std = math.sqrt(variance)
    return None if std <= 1e-12 else (values[-1] - mean) / std


@dataclass
class IndicatorResult:
    key: str
    label: str
    dataset: str
    source: str
    unit: str
    status: str
    mnemonic: str | None = None
    resolution: str | None = None
    latest_date: str | None = None
    latest_value: float | None = None
    change_short: float | None = None
    change_medium: float | None = None
    zscore: float | None = None
    age_days: int | None = None
    error: str | None = None


def fetch_indicator(spec: dict[str, Any], *, now: datetime | None = None) -> IndicatorResult:
    result = IndicatorResult(
        key=str(spec["key"]),
        label=str(spec["label"]),
        dataset=str(spec["dataset"]),
        source="Office of Financial Research STFM",
        unit=str(spec.get("unit") or "number"),
        status="unavailable",
    )
    try:
        mnemonic, resolution = resolve_mnemonic(spec)
        result.mnemonic = mnemonic
        result.resolution = resolution
        if not mnemonic:
            result.error = resolution
            return result
        start = (now or datetime.now(UTC)).date() - timedelta(days=int(spec.get("history_days", 1400)))
        url = f"{OFR_BASE}/series/full?{urllib.parse.urlencode({'mnemonic': mnemonic, 'start_date': start.isoformat()})}"
        points = series_points(request_json(url), mnemonic)
        if not points:
            result.error = "series has no usable observations"
            return result
        result.latest_date, result.latest_value = points[-1]
        result.change_short = change(points, int(spec.get("short_observations", 5)))
        result.change_medium = change(points, int(spec.get("medium_observations", 20)))
        result.zscore = zscore_latest(points)
        result.age_days = days_old(result.latest_date, now)
        stale_after = int(spec.get("stale_after_days", 10))
        result.status = "fresh" if result.age_days is not None and result.age_days <= stale_after else "stale"
        return result
    except Exception as exc:
        result.error = str(exc)[:400]
        return result


def extract_macro_monitor(path: Path = DASHBOARD) -> dict[str, Any]:
    if not path.exists() or extract_js_object is None:
        return {}
    source = path.read_text(encoding="utf-8", errors="replace")
    payload = extract_js_object(source, "MACRO_MONITOR") or {}
    return payload if isinstance(payload, dict) else {}


def last_macro(payload: dict[str, Any]) -> dict[str, Any]:
    latest = payload.get("latest")
    if isinstance(latest, dict):
        return latest
    rows = payload.get("records")
    if isinstance(rows, list) and rows and isinstance(rows[-1], dict):
        return rows[-1]
    return {}


def state_from_score(score: float | None, *, supportive: float = 60, defensive: float = 40) -> str:
    if score is None:
        return "Unavailable"
    if score >= supportive:
        return "Supportive"
    if score <= defensive:
        return "Defensive"
    return "Neutral"


def repo_pillar(results: dict[str, IndicatorResult]) -> dict[str, Any]:
    rates = [result.latest_value for key, result in results.items() if key.startswith("repo_") and key.endswith("_rate") and result.status == "fresh" and result.latest_value is not None]
    changes = [result.change_short for key, result in results.items() if key.startswith("repo_") and key.endswith("_rate") and result.status == "fresh" and result.change_short is not None]
    dispersion_bp = (max(rates) - min(rates)) * 100 if len(rates) >= 2 else None
    max_change_bp = max((abs(value) * 100 for value in changes), default=None)
    score = 50.0
    reasons: list[str] = []
    if dispersion_bp is not None:
        score -= min(25.0, max(0.0, dispersion_bp - 2.0) * 1.8)
        reasons.append(f"repo rate dispersion {dispersion_bp:.1f} bp")
    if max_change_bp is not None:
        score -= min(20.0, max(0.0, max_change_bp - 3.0) * 1.2)
        reasons.append(f"largest short-term rate move {max_change_bp:.1f} bp")
    coverage = sum(result.status == "fresh" for key, result in results.items() if key.startswith("repo_"))
    total = sum(1 for key in results if key.startswith("repo_"))
    if not coverage:
        return {"label": "Funding microstructure", "score": None, "state": "Unavailable", "coverage": 0.0, "reasons": ["OFR repo series unavailable"]}
    return {
        "label": "Funding microstructure",
        "score": round(clamp(score, 0, 100), 1),
        "state": state_from_score(score),
        "coverage": round(coverage / max(1, total), 3),
        "repo_rate_dispersion_bp": round(dispersion_bp, 2) if dispersion_bp is not None else None,
        "largest_rate_move_bp": round(max_change_bp, 2) if max_change_bp is not None else None,
        "reasons": reasons,
    }


def dealer_pillar(results: dict[str, IndicatorResult]) -> dict[str, Any]:
    relevant = [result for key, result in results.items() if key.startswith("dealer_") and result.status == "fresh"]
    if not relevant:
        return {"label": "Dealer absorption", "score": None, "state": "Unavailable", "coverage": 0.0, "reasons": ["Primary-dealer series unavailable"]}
    score = 50.0
    reasons: list[str] = []
    by_key = {result.key: result for result in relevant}
    inventory = by_key.get("dealer_treasury_positions")
    financing = by_key.get("dealer_treasury_financing")
    fails = by_key.get("dealer_treasury_fails")
    if inventory and inventory.zscore is not None:
        score -= max(0.0, inventory.zscore) * 10.0
        reasons.append(f"dealer inventory z {inventory.zscore:.2f}")
    if financing and financing.zscore is not None:
        score -= max(0.0, financing.zscore) * 6.0
        reasons.append(f"dealer financing z {financing.zscore:.2f}")
    if fails and fails.zscore is not None:
        score -= max(0.0, fails.zscore) * 12.0
        reasons.append(f"settlement fails z {fails.zscore:.2f}")
    return {"label": "Dealer absorption", "score": round(clamp(score, 0, 100), 1), "state": state_from_score(score), "coverage": round(len(relevant) / 3.0, 3), "reasons": reasons}


def mmf_pillar(results: dict[str, IndicatorResult]) -> dict[str, Any]:
    relevant = [result for key, result in results.items() if key.startswith("mmf_") and result.status == "fresh"]
    if not relevant:
        return {"label": "Money-market allocation", "score": None, "state": "Unavailable", "coverage": 0.0, "reasons": ["OFR MMF series unavailable"]}
    reasons = [f"{result.label} change {result.change_medium:+.2f} {result.unit}" for result in relevant if result.change_medium is not None]
    return {"label": "Money-market allocation", "score": 50.0, "state": "Context", "coverage": round(len(relevant) / 3.0, 3), "reasons": reasons}


def existing_pillars(macro_latest: dict[str, Any]) -> dict[str, Any]:
    score = finite(macro_latest.get("liquidity_score"))
    net_change = finite(macro_latest.get("net_liquidity_4w_change"))
    reserves = finite(macro_latest.get("bank_reserves_4w_change"))
    issuance = finite(macro_latest.get("treasury_issuance_next_7d"))
    repo_spread = finite(macro_latest.get("sofr_iorb_spread"))
    return {
        "macro_regime": {"label": "Macro risk regime", "score": score, "state": state_from_score(score)},
        "net_liquidity": {"label": "Net liquidity impulse", "value": net_change, "unit": "USD bn / 4w", "state": "Supportive" if net_change is not None and net_change > 0 else "Defensive" if net_change is not None and net_change < 0 else "Unavailable"},
        "bank_reserves": {"label": "Reserve impulse", "value": reserves, "unit": "USD bn / 4w", "state": "Supportive" if reserves is not None and reserves > 0 else "Defensive" if reserves is not None and reserves < 0 else "Unavailable"},
        "treasury_supply": {"label": "Treasury settlement pressure", "value": issuance, "unit": "USD bn / 7d", "state": "High" if issuance is not None and issuance >= 250 else "Moderate" if issuance is not None and issuance >= 100 else "Low" if issuance is not None else "Unavailable"},
        "repo_admin_spread": {"label": "SOFR-IORB", "value": repo_spread, "unit": "pp", "state": "Stress" if repo_spread is not None and repo_spread >= 0.10 else "Caution" if repo_spread is not None and repo_spread >= 0.05 else "Normal" if repo_spread is not None else "Unavailable"},
    }


def source_rows(results: Iterable[IndicatorResult]) -> list[dict[str, Any]]:
    return [asdict(result) for result in results]


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    import csv
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    columns = list(rows[0])
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def build_payload(config: dict[str, Any] | None = None, *, now: datetime | None = None) -> dict[str, Any]:
    config = config or load_config()
    current = now or datetime.now(UTC)
    results = [fetch_indicator(spec, now=current) for spec in config["indicators"]]
    by_key = {result.key: result for result in results}
    macro_latest = last_macro(extract_macro_monitor())
    fresh = sum(result.status == "fresh" for result in results)
    coverage = fresh / max(1, len(results))
    pillars = existing_pillars(macro_latest)
    pillars.update({"funding_microstructure": repo_pillar(by_key), "dealer_absorption": dealer_pillar(by_key), "money_market_allocation": mmf_pillar(by_key)})
    return {
        "schema_version": 1,
        "model_version": "macro-liquidity-control-room-v1.0",
        "generated_at_utc": current.isoformat(),
        "role": "descriptive risk and plumbing context; does not create or reverse COT direction",
        "source_coverage_ratio": round(coverage, 3),
        "source_coverage_label": "Good" if coverage >= 0.75 else "Partial" if coverage >= 0.40 else "Low",
        "existing_macro_latest": macro_latest,
        "pillars": pillars,
        "sources": source_rows(results),
        "source_notes": [
            "OFR Short-term Funding Monitor is used for repo, primary-dealer, and money-market-fund series.",
            "Missing or stale series reduce coverage and are never filled with a neutral score.",
            "Primary-dealer and MMF indicators are context until their exact series selection is reviewed in generated source status."
        ]
    }


def main() -> None:
    payload = build_payload()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    JSON_OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    write_csv(CSV_OUT, payload["sources"])
    print(f"Wrote {JSON_OUT}")
    print(f"Wrote {CSV_OUT}")
    print(f"New-source coverage: {payload['source_coverage_ratio'] * 100:.0f}%")


if __name__ == "__main__":
    main()
