#!/usr/bin/env python3
"""Build presentation analytics strictly from immutable prospective ledger evidence."""
from __future__ import annotations

import argparse
import json
import math
import statistics
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ledger import (
    FAMILIES,
    HORIZONS,
    atomic_write_json,
    entry_files,
    finite,
    forecast_files,
    iso_utc,
    load_object,
    outcome_files,
    sha256_file,
    validate_ledger,
)

DEFAULT_OUT = Path(__file__).resolve().parents[1] / "worldclass" / "live-track-record.json"


def mean(values: list[float]) -> float | None:
    return statistics.mean(values) if values else None


def rounded(value: float | None, digits: int = 6) -> float | None:
    return round(value, digits) if value is not None and math.isfinite(value) else None


def correlation(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 2 or len(xs) != len(ys):
        return None
    mx = statistics.mean(xs)
    my = statistics.mean(ys)
    dx = [x - mx for x in xs]
    dy = [y - my for y in ys]
    denom = math.sqrt(sum(v * v for v in dx) * sum(v * v for v in dy))
    if denom <= 1e-12:
        return None
    return sum(a * b for a, b in zip(dx, dy)) / denom


def sample_stage(matured_vintages: int) -> str:
    if matured_vintages < 10:
        return "INSUFFICIENT SAMPLE"
    if matured_vintages < 20:
        return "PRELIMINARY"
    if matured_vintages < 40:
        return "EARLY"
    return "MEANINGFUL"


def probability_buckets(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    definitions = ((0.0, 0.4, "0–40%"), (0.4, 0.6, "40–60%"), (0.6, 1.0000001, "60–100%"))
    output = []
    for low, high, label in definitions:
        selected = [row for row in records if row.get("probability") is not None and low <= row["probability"] < high]
        positives = [1.0 if row["realized"] > 0 else 0.0 for row in selected]
        output.append({
            "bucket": label,
            "count": len(selected),
            "average_predicted_probability": rounded(mean([row["probability"] for row in selected])),
            "realized_positive_rate": rounded(mean(positives)),
        })
    return output


def drift_state(records: list[dict[str, Any]], matured_vintages: int) -> dict[str, Any]:
    stage = sample_stage(matured_vintages)
    if matured_vintages < 10 or not records:
        return {"state": "INSUFFICIENT SAMPLE", "sample_stage": stage, "return_z": None, "hit_rate_z": None}

    errors = [row["realized"] - row["predicted"] for row in records if row.get("predicted") is not None]
    effective_n = max(1, min(len(records), matured_vintages))
    return_z = None
    if len(errors) >= 2:
        std = statistics.stdev(errors)
        if std > 1e-12:
            return_z = statistics.mean(errors) / (std / math.sqrt(effective_n))

    probability_rows = [row for row in records if row.get("probability") is not None]
    hit_z = None
    if probability_rows:
        expected_p = statistics.mean(row["probability"] for row in probability_rows)
        actual_p = statistics.mean(1.0 if row["realized"] > 0 else 0.0 for row in probability_rows)
        variance = expected_p * (1.0 - expected_p) / max(1, min(len(probability_rows), matured_vintages))
        if variance > 1e-12:
            hit_z = (actual_p - expected_p) / math.sqrt(variance)

    downside = [value for value in (return_z, hit_z) if value is not None]
    worst_z = min(downside) if downside else None
    if worst_z is not None and worst_z <= -2.0:
        label = "MATERIAL DRIFT"
    elif worst_z is not None and worst_z <= -1.0:
        label = "WEAKENING"
    else:
        label = "WITHIN EXPECTATION"
    return {
        "state": label,
        "sample_stage": stage,
        "return_z": rounded(return_z, 4),
        "hit_rate_z": rounded(hit_z, 4),
    }


def compute_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    matured = [row for row in rows if row.get("outcome") is not None]
    paired = []
    for row in matured:
        outcome = row["outcome"]
        realized = finite(outcome.get("realized_return_pct"))
        if realized is None:
            continue
        paired.append({
            "realized": realized,
            "predicted": finite(row["horizon_meta"].get("expected_return_pct")),
            "probability": finite(row["horizon_meta"].get("probability_positive")),
            "mae": finite(outcome.get("max_adverse_excursion_pct")),
            "mfe": finite(outcome.get("max_favorable_excursion_pct")),
            "baseline": finite(row["horizon_meta"].get("historical_unconditional_return_pct")),
            "hist_drawdown": finite(row["horizon_meta"].get("historical_average_drawdown_pct")),
            "hist_worst": finite(row["horizon_meta"].get("historical_worst_drawdown_pct")),
            "vintage": row["forecast"].get("release_target_date"),
        })

    raw_vintages = {str(row["forecast"].get("release_target_date")) for row in rows}
    matured_vintages = {str(row["forecast"].get("release_target_date")) for row in matured}
    realized = [row["realized"] for row in paired]
    predicted = [row["predicted"] for row in paired if row["predicted"] is not None]
    paired_predicted = [(row["predicted"], row["realized"]) for row in paired if row["predicted"] is not None]
    errors = [real - pred for pred, real in paired_predicted]
    probabilities = [(row["probability"], row["realized"]) for row in paired if row["probability"] is not None]
    baselines = [row["baseline"] for row in paired if row["baseline"] is not None]
    hist_drawdowns = [row["hist_drawdown"] for row in paired if row["hist_drawdown"] is not None]
    hist_worst = [row["hist_worst"] for row in paired if row["hist_worst"] is not None]
    directional = [bool(row["outcome"].get("direction_correct")) for row in matured if row["outcome"].get("direction_correct") is not None]
    maes = [row["mae"] for row in paired if row["mae"] is not None]
    mfes = [row["mfe"] for row in paired if row["mfe"] is not None]

    brier_values = [(prob - (1.0 if actual > 0 else 0.0)) ** 2 for prob, actual in probabilities]
    live_mean = mean(realized)
    baseline_mean = mean(baselines)
    pred_x = [item[0] for item in paired_predicted]
    pred_y = [item[1] for item in paired_predicted]
    drift = drift_state(paired, len(matured_vintages))

    return {
        "forecasts_issued": len(rows),
        "forecasts_matured": len(matured),
        "open_forecasts": len(rows) - len(matured),
        "weekly_vintages": len(raw_vintages),
        "matured_vintages": len(matured_vintages),
        "sample_stage": drift["sample_stage"],
        "directional_hit_rate_pct": rounded(mean([1.0 if value else 0.0 for value in directional]) * 100.0 if directional else None, 3),
        "average_predicted_return_pct": rounded(mean(predicted)),
        "average_realized_return_pct": rounded(live_mean),
        "median_realized_return_pct": rounded(statistics.median(realized) if realized else None),
        "mean_forecast_error_pct": rounded(mean(errors)),
        "rmse_pct": rounded(math.sqrt(mean([value * value for value in errors])) if errors else None),
        "correlation_predicted_realized": rounded(correlation(pred_x, pred_y), 5),
        "average_max_adverse_excursion_pct": rounded(mean(maes)),
        "average_max_favorable_excursion_pct": rounded(mean(mfes)),
        "historical_expected_return_pct": rounded(mean(predicted)),
        "historical_hit_rate_pct": rounded(mean([prob for prob, _ in probabilities]) * 100.0 if probabilities else None, 3),
        "historical_average_drawdown_pct": rounded(mean(hist_drawdowns)),
        "historical_worst_drawdown_pct": rounded(mean(hist_worst)),
        "average_unconditional_return_pct": rounded(baseline_mean),
        "live_edge_vs_unconditional_pct": rounded(live_mean - baseline_mean if live_mean is not None and baseline_mean is not None else None),
        "brier_score": rounded(mean(brier_values), 6),
        "probability_calibration": probability_buckets(paired),
        "drift": drift,
    }


def signal_status(outcomes: dict[str, dict[str, Any]], has_entry: bool) -> str:
    if not has_entry:
        return "awaiting close"
    if not outcomes:
        return "live"
    if "26w" in outcomes:
        return "complete"
    order = {key: index for index, key in enumerate(HORIZONS)}
    latest = max(outcomes, key=lambda key: order.get(key, -1))
    return f"{latest.upper()} matured"


def build(ledger_root: Path, generated_at: datetime) -> dict[str, Any]:
    integrity = validate_ledger(ledger_root)
    forecasts: dict[str, dict[str, Any]] = {}
    forecast_hashes: dict[str, str] = {}
    for path in forecast_files(ledger_root):
        payload = load_object(path)
        signal_id = str(payload["signal_id"])
        forecasts[signal_id] = payload
        forecast_hashes[signal_id] = sha256_file(path)

    entries = {str(payload["signal_id"]): payload for path in entry_files(ledger_root) if (payload := load_object(path))}
    outcomes: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for path in outcome_files(ledger_root):
        payload = load_object(path)
        outcomes[str(payload["signal_id"])][str(payload["horizon"])] = payload

    rows_by_group: dict[tuple[str, str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
    aggregate_by_family: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    history = []
    current_predictions = []

    for signal_id, forecast in sorted(forecasts.items(), key=lambda item: (item[1].get("created_at_utc", ""), item[0])):
        entry = entries.get(signal_id)
        signal_outcomes = outcomes.get(signal_id, {})
        status = signal_status(signal_outcomes, entry is not None)
        audit = {
            "signal_id": signal_id,
            "forecast_hash": forecast_hashes[signal_id],
            "created_at_utc": forecast.get("created_at_utc"),
            "report_date": forecast.get("report_date"),
            "release_target_date": forecast.get("release_target_date"),
            "market": forecast.get("market"),
            "dataset": forecast.get("dataset"),
            "model_family": forecast.get("model_family"),
            "model_version": forecast.get("model_version"),
            "model_spec_hash": forecast.get("model_spec_hash"),
            "cot_score": forecast.get("cot_score"),
            "cot_state": forecast.get("cot_state"),
            "macro_score": forecast.get("macro_score"),
            "macro_state": forecast.get("macro_state"),
            "combined_state": forecast.get("combined_state"),
            "historical_sample_size": forecast.get("historical_sample_size"),
            "confidence": forecast.get("confidence"),
            "input_manifest_hash": forecast.get("input_manifest_hash"),
            "research_artifact_hash": forecast.get("research_artifact_hash"),
            "historical_horizons": forecast.get("historical_horizons"),
            "entry": entry,
            "outcomes": signal_outcomes,
            "status": status,
        }
        history.append(audit)
        if status != "complete":
            current_predictions.append({
                "signal_id": signal_id,
                "market": forecast.get("market"),
                "dataset": forecast.get("dataset"),
                "model_family": forecast.get("model_family"),
                "signal": forecast.get("combined_state") if forecast.get("model_family") == "combined" else forecast.get(f"{forecast.get('model_family')}_state"),
                "cot_score": forecast.get("cot_score"),
                "macro_score": forecast.get("macro_score"),
                "expected_1w_return_pct": forecast.get("expected_1w_return"),
                "expected_4w_return_pct": forecast.get("expected_4w_return"),
                "probability_positive_4w": forecast.get("probability_positive_4w"),
                "confidence": forecast.get("confidence"),
                "entry": entry,
                "status": status,
            })

        for horizon in HORIZONS:
            horizon_meta = (forecast.get("historical_horizons") or {}).get(horizon) or {}
            row = {
                "forecast": forecast,
                "horizon_meta": horizon_meta,
                "outcome": signal_outcomes.get(horizon),
            }
            key = (
                str(forecast.get("market")),
                str(forecast.get("dataset")),
                str(forecast.get("model_version")),
                str(forecast.get("model_family")),
                horizon,
            )
            rows_by_group[key].append(row)
            aggregate_by_family[(str(forecast.get("model_version")), str(forecast.get("model_family")), horizon)].append(row)

    statistics_rows = []
    for key, rows in sorted(rows_by_group.items()):
        market, dataset, version, family, horizon = key
        statistics_rows.append({
            "market": market,
            "dataset": dataset,
            "model_version": version,
            "model_family": family,
            "horizon": horizon,
            **compute_metrics(rows),
        })

    comparison_index: dict[tuple[str, str], dict[str, Any]] = {}
    for (version, family, horizon), rows in sorted(aggregate_by_family.items()):
        node = comparison_index.setdefault((version, horizon), {
            "model_version": version,
            "horizon": horizon,
            "champion": "combined",
            "challengers": ["cot", "macro"],
            "families": {},
        })
        node["families"][family] = compute_metrics(rows)

    vintage_values = [str(forecast.get("release_target_date")) for forecast in forecasts.values() if forecast.get("release_target_date")]
    matured_signals = sum(1 for signal_id in forecasts if outcomes.get(signal_id))
    complete_signals = sum(1 for signal_id in forecasts if "26w" in outcomes.get(signal_id, {}))
    return {
        "schema_version": 1,
        "generated_at_utc": iso_utc(generated_at),
        "evidence_policy": {
            "historical_research": "Frozen inside each forecast at issuance; never recomputed here",
            "forward_test": "Forecast file recorded before outcome",
            "matured_live": "Separate immutable entry/outcome files",
            "sample_counts_are_separate": True,
        },
        "ledger": {
            "integrity": integrity["integrity"],
            "latest_manifest_hash": integrity["latest_manifest_hash"],
            "forecast_count": integrity["forecast_count"],
            "entry_count": integrity["entry_count"],
            "outcome_count": integrity["outcome_count"],
        },
        "latest_forecast_vintage": max(vintage_values) if vintage_values else None,
        "model_versions": sorted({str(forecast.get("model_version")) for forecast in forecasts.values()}),
        "forecast_count": len(forecasts),
        "entry_count": len(entries),
        "outcome_count": sum(len(value) for value in outcomes.values()),
        "weekly_vintage_count": len(set(vintage_values)),
        "matured_signal_count": matured_signals,
        "complete_signal_count": complete_signals,
        "open_signal_count": len(forecasts) - complete_signals,
        "current_predictions": current_predictions,
        "statistics": statistics_rows,
        "model_comparison": list(comparison_index.values()),
        "signal_history": history,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ledger-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--now-utc", help="Override generation time for deterministic tests")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    now = datetime.fromisoformat(args.now_utc.replace("Z", "+00:00")) if args.now_utc else datetime.now(UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    payload = build(args.ledger_root, now.astimezone(UTC))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(args.output, payload)
    print(
        f"Live track record built · forecasts={payload['forecast_count']} · "
        f"matured_signals={payload['matured_signal_count']} · vintages={payload['weekly_vintage_count']}"
    )


if __name__ == "__main__":
    main()
