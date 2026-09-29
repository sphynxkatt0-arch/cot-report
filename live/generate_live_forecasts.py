#!/usr/bin/env python3
"""Generate deterministic prospective forecast snapshots for a live COT vintage.

Production generation is intentionally time-gated around the 21:35 Stockholm
Friday release window. This prevents a normal code deployment on a later date
from manufacturing a retrospective "live" forecast.
"""
from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ledger import (
    FAMILIES,
    HORIZONS,
    LedgerError,
    atomic_write_json,
    deterministic_signal_id,
    finite,
    forecast_relative_path,
    hash_artifacts,
    iso_utc,
    parse_utc,
    release_vintage_utc,
    validate_forecast,
    within_forecast_window,
    write_immutable_forecast,
)

ROOT = Path(__file__).resolve().parents[1]
WORLDCLASS = ROOT / "worldclass"
MODEL_OUTPUT = ROOT / "model_output"
DEFAULT_STAGING = ROOT / ".live-ledger-staging"


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise LedgerError(f"missing required artifact: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise LedgerError(f"artifact root must be an object: {path}")
    return payload


def probability(hit_rate_pct: Any) -> float | None:
    value = finite(hit_rate_pct)
    if value is None:
        return None
    return round(max(0.0, min(100.0, value)) / 100.0, 6)


def build_horizon_contract(
    family_payload: dict[str, Any],
    horizon_steps: dict[str, Any],
) -> dict[str, Any]:
    source = family_payload.get("horizons") or {}
    result: dict[str, Any] = {}
    for horizon in HORIZONS:
        item = source.get(horizon) or {}
        steps = int(horizon_steps.get(horizon) or 0)
        if steps <= 0:
            raise LedgerError(f"canonical model contract has invalid {horizon} trading-close horizon")
        result[horizon] = {
            "trading_closes": steps,
            "expected_return_pct": finite(item.get("mean_return_pct")),
            "median_return_pct": finite(item.get("median_return_pct")),
            "probability_positive": probability(item.get("hit_rate_pct")),
            "historical_average_drawdown_pct": finite(item.get("avg_drawdown_pct")),
            "historical_worst_drawdown_pct": finite(item.get("max_drawdown_pct")),
            "historical_unconditional_return_pct": finite(item.get("baseline_return_pct")),
            "observations": int(item.get("observations") or 0),
            "confidence": str(item.get("confidence") or "Low"),
        }
    return result


def family_available(family: str, current: dict[str, Any]) -> tuple[bool, str | None]:
    if family == "cot":
        score = finite(current.get("cot_score"))
        return (score is not None, None if score is not None else "COT score unavailable")
    macro = finite(current.get("macro_score"))
    if macro is None or current.get("macro_state") == "unavailable":
        return False, "Macro score unavailable"
    if family == "combined" and finite(current.get("cot_score")) is None:
        return False, "COT score unavailable"
    return True, None


def build_forecast(
    *,
    market: str,
    dataset: str,
    family: str,
    dataset_payload: dict[str, Any],
    family_payload: dict[str, Any],
    model_version: str,
    model_spec_hash: str,
    horizon_steps: dict[str, Any],
    input_manifest_hash: str,
    input_artifacts: dict[str, str],
    research_artifact_hash: str,
    research_artifacts: dict[str, str],
) -> dict[str, Any]:
    current = dataset_payload.get("current") or {}
    report_date = str(current.get("report_date") or "")[:10]
    release_target_date = str(current.get("release_target_date") or "")[:10]
    if not report_date or not release_target_date:
        raise LedgerError(f"{market}/{dataset}: current report/release date missing")
    created_at = iso_utc(release_vintage_utc(release_target_date))
    signal_id = deterministic_signal_id(
        report_date,
        market,
        dataset,
        family,
        model_version,
        model_spec_hash,
    )
    horizons = build_horizon_contract(family_payload, horizon_steps)
    h4 = horizons["4w"]
    forecast: dict[str, Any] = {
        "schema_version": 1,
        "signal_id": signal_id,
        "created_at_utc": created_at,
        "report_date": report_date,
        "release_target_date": release_target_date,
        "market": market,
        "dataset": dataset,
        "model_family": family,
        "model_version": model_version,
        "model_spec_hash": model_spec_hash,
        "cot_score": finite(current.get("cot_score")),
        "cot_state": current.get("cot_state"),
        "cot_score_delta_4w": finite(current.get("cot_score_delta_4w")),
        "extreme_count": int(current.get("extreme_count") or 0),
        "macro_score": finite(current.get("macro_score")),
        "macro_state": current.get("macro_state"),
        "transmission_state": current.get("transmission_state"),
        "combined_state": current.get("combined_state"),
        "historical_sample_size": int(family_payload.get("sample_size") or 0),
        "expected_1w_return": horizons["1w"]["expected_return_pct"],
        "expected_2w_return": horizons["2w"]["expected_return_pct"],
        "expected_4w_return": horizons["4w"]["expected_return_pct"],
        "expected_13w_return": horizons["13w"]["expected_return_pct"],
        "expected_26w_return": horizons["26w"]["expected_return_pct"],
        "probability_positive_1w": horizons["1w"]["probability_positive"],
        "probability_positive_2w": horizons["2w"]["probability_positive"],
        "probability_positive_4w": horizons["4w"]["probability_positive"],
        "probability_positive_13w": horizons["13w"]["probability_positive"],
        "probability_positive_26w": horizons["26w"]["probability_positive"],
        "historical_drawdown_expectancy": h4["historical_average_drawdown_pct"],
        "historical_worst_drawdown": h4["historical_worst_drawdown_pct"],
        "confidence": h4["confidence"],
        "historical_horizons": horizons,
        "input_manifest_hash": input_manifest_hash,
        "input_artifacts": input_artifacts,
        "research_artifact_hash": research_artifact_hash,
        "research_artifacts": research_artifacts,
    }
    forecast["forecast_filename"] = forecast_relative_path(forecast).name
    validate_forecast(forecast)
    return forecast


def generate(
    *,
    worldclass: Path,
    model_output: Path,
    staging: Path,
    now_utc: datetime,
    allow_outside_window: bool = False,
) -> dict[str, Any]:
    regime = load_json(worldclass / "regime_backtest.json")
    backtest = load_json(worldclass / "backtest.json")
    model = load_json(worldclass / "model-spec.json")

    model_version = str(model.get("model_version") or "")
    model_spec_hash = str(model.get("model_spec_hash") or "")
    horizon_steps = model.get("horizons") or {}
    if not model_version or not model_spec_hash:
        raise LedgerError("runtime model identity missing")
    if set(horizon_steps) != set(HORIZONS):
        raise LedgerError("runtime model horizon contract is incomplete")
    for name, artifact in (("backtest", backtest), ("regime", regime)):
        if artifact.get("model_version") != model_version or artifact.get("model_spec_hash") != model_spec_hash:
            raise LedgerError(f"{name} model identity does not match runtime model contract")

    input_paths = [
        worldclass / "base.json",
        worldclass / "model-spec.json",
        worldclass / "metals.json",
        model_output / "macro_liquidity_expansion.json",
    ]
    research_paths = [worldclass / "backtest.json", worldclass / "regime_backtest.json"]
    input_manifest_hash, input_artifacts = hash_artifacts(input_paths, base=ROOT)
    research_artifact_hash, research_artifacts = hash_artifacts(research_paths, base=ROOT)

    staging.mkdir(parents=True, exist_ok=True)
    generated: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []

    for market, market_payload in sorted((regime.get("markets") or {}).items()):
        for dataset, dataset_payload in sorted(((market_payload or {}).get("datasets") or {}).items()):
            current = (dataset_payload or {}).get("current") or {}
            release_target_date = str(current.get("release_target_date") or "")[:10]
            if not release_target_date:
                skipped.append({"market": market, "dataset": dataset, "family": "*", "reason": "release target missing"})
                continue
            if not allow_outside_window and not within_forecast_window(now_utc, release_target_date):
                skipped.append({
                    "market": market,
                    "dataset": dataset,
                    "family": "*",
                    "reason": f"outside prospective release window for {release_target_date}",
                })
                continue

            families = (dataset_payload or {}).get("families") or {}
            for family in FAMILIES:
                available, reason = family_available(family, current)
                if not available:
                    skipped.append({"market": market, "dataset": dataset, "family": family, "reason": reason or "unavailable"})
                    continue
                family_payload = families.get(family)
                if not isinstance(family_payload, dict):
                    skipped.append({"market": market, "dataset": dataset, "family": family, "reason": "family research missing"})
                    continue
                forecast = build_forecast(
                    market=market,
                    dataset=dataset,
                    family=family,
                    dataset_payload=dataset_payload,
                    family_payload=family_payload,
                    model_version=model_version,
                    model_spec_hash=model_spec_hash,
                    horizon_steps=horizon_steps,
                    input_manifest_hash=input_manifest_hash,
                    input_artifacts=input_artifacts,
                    research_artifact_hash=research_artifact_hash,
                    research_artifacts=research_artifacts,
                )
                relative = forecast_relative_path(forecast)
                destination = staging / relative
                write_immutable_forecast(destination, forecast)
                generated.append({
                    "signal_id": forecast["signal_id"],
                    "relative_path": str(relative).replace("\\", "/"),
                    "forecast_hash": __import__("hashlib").sha256(destination.read_bytes()).hexdigest(),
                    "created_at_utc": forecast["created_at_utc"],
                })

    plan = {
        "schema_version": 1,
        "generated_at_utc": iso_utc(now_utc),
        "prospective_window_enforced": not allow_outside_window,
        "model_version": model_version,
        "model_spec_hash": model_spec_hash,
        "forecast_count": len(generated),
        "forecasts": sorted(generated, key=lambda item: item["relative_path"]),
        "skipped": skipped,
    }
    atomic_write_json(staging / "plan.json", plan)
    return plan


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--worldclass-dir", type=Path, default=WORLDCLASS)
    parser.add_argument("--model-output-dir", type=Path, default=MODEL_OUTPUT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_STAGING)
    parser.add_argument("--now-utc", help="Override current UTC time for deterministic tests/simulation")
    parser.add_argument(
        "--allow-outside-window",
        action="store_true",
        help="Simulation/testing only. Production workflows must not use this flag.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    now = parse_utc(args.now_utc) if args.now_utc else datetime.now(UTC)
    plan = generate(
        worldclass=args.worldclass_dir,
        model_output=args.model_output_dir,
        staging=args.output_root,
        now_utc=now,
        allow_outside_window=args.allow_outside_window,
    )
    print(
        f"Live forecast staging complete · forecasts={plan['forecast_count']} · "
        f"prospective_window_enforced={plan['prospective_window_enforced']}"
    )
    for item in plan["skipped"][:20]:
        print(f"SKIP {item['market']}/{item['dataset']}/{item['family']}: {item['reason']}")


if __name__ == "__main__":
    main()
