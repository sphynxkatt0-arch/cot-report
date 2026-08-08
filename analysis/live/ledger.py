#!/usr/bin/env python3
"""Shared primitives for the append-only prospective COT live ledger."""
from __future__ import annotations

import hashlib
import json
import math
import re
import subprocess
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable
from zoneinfo import ZoneInfo

FORECAST_SCHEMA_VERSION = 1
ENTRY_SCHEMA_VERSION = 1
OUTCOME_SCHEMA_VERSION = 1
MANIFEST_SCHEMA_VERSION = 1
FAMILIES = ("cot", "macro", "combined")
HORIZONS = ("1w", "2w", "4w", "13w", "26w")
STOCKHOLM = ZoneInfo("Europe/Stockholm")
SIGNAL_ID_RE = re.compile(r"^[a-f0-9]{64}$")
COMMIT_SHA_RE = re.compile(r"^[a-f0-9]{40}$")


class LedgerError(RuntimeError):
    """Raised when an immutable-ledger invariant is violated."""


def canonical_json_bytes(payload: Any) -> bytes:
    return (json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(data)
    temporary.replace(path)


def atomic_write_json(path: Path, payload: Any) -> None:
    atomic_write_bytes(path, canonical_json_bytes(payload))


def parse_iso_day(value: Any) -> date:
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError) as exc:
        raise LedgerError(f"invalid ISO date: {value!r}") from exc


def parse_utc(value: str) -> datetime:
    text = str(value or "").strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise LedgerError(f"invalid UTC timestamp: {value!r}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def iso_utc(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def release_vintage_utc(release_target_date: str | date) -> datetime:
    day = release_target_date if isinstance(release_target_date, date) else parse_iso_day(release_target_date)
    local = datetime(day.year, day.month, day.day, 21, 35, tzinfo=STOCKHOLM)
    return local.astimezone(UTC)


def within_forecast_window(
    now_utc: datetime,
    release_target_date: str | date,
    *,
    early_minutes: int = 5,
    window_hours: int = 4,
) -> bool:
    vintage = release_vintage_utc(release_target_date)
    now = now_utc.astimezone(UTC)
    return vintage - timedelta(minutes=early_minutes) <= now <= vintage + timedelta(hours=window_hours)


def deterministic_signal_id(
    report_date: str,
    market: str,
    dataset: str,
    model_family: str,
    model_version: str,
    model_spec_hash: str,
) -> str:
    identity = "|".join((report_date, market, dataset, model_family, model_version, model_spec_hash))
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def version_slug(model_version: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", str(model_version)).strip("-")
    if not cleaned:
        raise LedgerError("model_version cannot be converted to a filename")
    return cleaned


def forecast_relative_path(forecast: dict[str, Any]) -> Path:
    release_day = parse_iso_day(forecast.get("release_target_date"))
    market = str(forecast.get("market") or "").strip()
    dataset = str(forecast.get("dataset") or "").strip()
    family = str(forecast.get("model_family") or "").strip()
    version = version_slug(str(forecast.get("model_version") or ""))
    if not market or not dataset or family not in FAMILIES:
        raise LedgerError("forecast market/dataset/model_family is invalid")
    filename = f"{market}-{dataset}-{family}-v{version}.json"
    return Path("live") / "forecasts" / str(release_day.year) / release_day.isoformat() / filename


def entry_relative_path(signal_id: str) -> Path:
    if not SIGNAL_ID_RE.fullmatch(str(signal_id)):
        raise LedgerError("entry signal_id is invalid")
    return Path("live") / "entries" / f"{signal_id}.json"


def outcome_relative_path(signal_id: str, horizon: str) -> Path:
    if not SIGNAL_ID_RE.fullmatch(str(signal_id)) or horizon not in HORIZONS:
        raise LedgerError("outcome signal_id/horizon is invalid")
    return Path("live") / "outcomes" / str(signal_id) / f"{horizon}.json"


def aggregate_artifact_hash(items: dict[str, str]) -> str:
    return sha256_bytes(canonical_json_bytes(dict(sorted(items.items()))))


def hash_artifacts(paths: Iterable[Path], *, base: Path | None = None) -> tuple[str, dict[str, str]]:
    hashes: dict[str, str] = {}
    for path in paths:
        if not path.exists():
            continue
        key = str(path.relative_to(base)) if base is not None else str(path)
        hashes[key] = sha256_file(path)
    if not hashes:
        raise LedgerError("no artifacts were available to hash")
    return aggregate_artifact_hash(hashes), dict(sorted(hashes.items()))


def finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def approx_equal(left: Any, right: Any, tolerance: float = 1e-7) -> bool:
    a = finite(left)
    b = finite(right)
    if a is None or b is None:
        return a is None and b is None
    return abs(a - b) <= tolerance * max(1.0, abs(a), abs(b))


def load_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise LedgerError(f"invalid JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise LedgerError(f"JSON root must be an object: {path}")
    return payload


def validate_forecast(forecast: dict[str, Any]) -> None:
    if not isinstance(forecast, dict):
        raise LedgerError("forecast must be an object")
    if forecast.get("schema_version") != FORECAST_SCHEMA_VERSION:
        raise LedgerError("forecast schema_version mismatch")
    family = str(forecast.get("model_family") or "")
    if family not in FAMILIES:
        raise LedgerError(f"unsupported model family: {family!r}")
    report_date = parse_iso_day(forecast.get("report_date")).isoformat()
    release_date = parse_iso_day(forecast.get("release_target_date")).isoformat()
    if parse_iso_day(release_date) != parse_iso_day(report_date) + timedelta(days=3):
        raise LedgerError("forecast release_target_date must equal report_date + 3 calendar days")
    model_version = str(forecast.get("model_version") or "")
    model_hash = str(forecast.get("model_spec_hash") or "")
    if not model_version or not SIGNAL_ID_RE.fullmatch(model_hash):
        raise LedgerError("forecast model identity is invalid")
    signal_id = str(forecast.get("signal_id") or "")
    expected_id = deterministic_signal_id(
        report_date,
        str(forecast.get("market") or ""),
        str(forecast.get("dataset") or ""),
        family,
        model_version,
        model_hash,
    )
    if signal_id != expected_id or not SIGNAL_ID_RE.fullmatch(signal_id):
        raise LedgerError("forecast signal_id is not deterministic")
    expected_created_at = iso_utc(release_vintage_utc(release_date))
    if forecast.get("created_at_utc") != expected_created_at:
        raise LedgerError("forecast created_at_utc must be the deterministic 21:35 Stockholm vintage")
    if "entry_price" in forecast or "exit_price" in forecast:
        raise LedgerError("forecast must not contain realized entry/exit prices")
    for key in ("cot_score", "macro_score"):
        value = forecast.get(key)
        if value is not None:
            number = finite(value)
            if number is None or not 0 <= number <= 100:
                raise LedgerError(f"forecast {key} is invalid")
    if int(forecast.get("historical_sample_size") or 0) < 0:
        raise LedgerError("historical_sample_size cannot be negative")
    horizons = forecast.get("historical_horizons")
    if not isinstance(horizons, dict) or set(horizons) != set(HORIZONS):
        raise LedgerError("forecast historical_horizons missing/incomplete")
    for horizon in HORIZONS:
        item = horizons.get(horizon)
        if not isinstance(item, dict):
            raise LedgerError(f"forecast horizon missing: {horizon}")
        if int(item.get("trading_closes") or 0) <= 0:
            raise LedgerError(f"forecast {horizon} trading_closes is invalid")
        probability = item.get("probability_positive")
        if probability is not None:
            p = finite(probability)
            if p is None or not 0 <= p <= 1:
                raise LedgerError(f"forecast {horizon} probability is invalid")
        for numeric_key in (
            "expected_return_pct",
            "median_return_pct",
            "historical_average_drawdown_pct",
            "historical_worst_drawdown_pct",
            "historical_unconditional_return_pct",
        ):
            if item.get(numeric_key) is not None and finite(item.get(numeric_key)) is None:
                raise LedgerError(f"forecast {horizon} {numeric_key} is non-finite")
    if not SIGNAL_ID_RE.fullmatch(str(forecast.get("input_manifest_hash") or "")):
        raise LedgerError("forecast input_manifest_hash is invalid")
    if not SIGNAL_ID_RE.fullmatch(str(forecast.get("research_artifact_hash") or "")):
        raise LedgerError("forecast research_artifact_hash is invalid")
    expected_path = forecast_relative_path(forecast)
    if expected_path.name != str(forecast.get("forecast_filename") or expected_path.name):
        raise LedgerError("forecast filename metadata does not match deterministic path")


def validate_entry(entry: dict[str, Any], forecast: dict[str, Any], forecast_hash: str) -> None:
    if entry.get("schema_version") != ENTRY_SCHEMA_VERSION:
        raise LedgerError("entry schema_version mismatch")
    if entry.get("signal_id") != forecast.get("signal_id"):
        raise LedgerError("entry signal_id does not match forecast")
    if entry.get("forecast_hash") != forecast_hash:
        raise LedgerError("entry forecast_hash does not match frozen forecast")
    if entry.get("market") != forecast.get("market"):
        raise LedgerError("entry market does not match forecast")
    if entry.get("release_target_date") != forecast.get("release_target_date"):
        raise LedgerError("entry release target does not match forecast")
    entry_day = parse_iso_day(entry.get("entry_date"))
    release_day = parse_iso_day(forecast.get("release_target_date"))
    if entry_day < release_day:
        raise LedgerError("entry predates forecast release target")
    price = finite(entry.get("entry_price"))
    if price is None or price <= 0:
        raise LedgerError("entry price is invalid")
    if not str(entry.get("price_source") or "").strip():
        raise LedgerError("entry price source missing")
    parse_utc(str(entry.get("settled_at_utc") or ""))


def validate_outcome(
    outcome: dict[str, Any],
    forecast: dict[str, Any],
    forecast_hash: str,
    entry: dict[str, Any],
) -> None:
    if outcome.get("schema_version") != OUTCOME_SCHEMA_VERSION:
        raise LedgerError("outcome schema_version mismatch")
    if outcome.get("signal_id") != forecast.get("signal_id"):
        raise LedgerError("outcome signal_id does not match forecast")
    if outcome.get("forecast_hash") != forecast_hash:
        raise LedgerError("outcome forecast_hash does not match frozen forecast")
    horizon = str(outcome.get("horizon") or "")
    if horizon not in HORIZONS:
        raise LedgerError("outcome horizon invalid")
    horizon_meta = (forecast.get("historical_horizons") or {}).get(horizon) or {}
    expected_steps = int(horizon_meta.get("trading_closes") or 0)
    if int(outcome.get("trading_closes") or 0) != expected_steps:
        raise LedgerError("outcome trading-close definition differs from frozen forecast")
    if outcome.get("entry_date") != entry.get("entry_date") or not approx_equal(outcome.get("entry_price"), entry.get("entry_price")):
        raise LedgerError("outcome entry does not match immutable entry artifact")
    entry_day = parse_iso_day(outcome.get("entry_date"))
    exit_day = parse_iso_day(outcome.get("exit_date"))
    if exit_day <= entry_day:
        raise LedgerError("outcome exit date must follow entry date")
    entry_price = finite(outcome.get("entry_price"))
    exit_price = finite(outcome.get("exit_price"))
    realized = finite(outcome.get("realized_return_pct"))
    if entry_price is None or entry_price <= 0 or exit_price is None or exit_price <= 0 or realized is None:
        raise LedgerError("outcome entry/exit/return values are invalid")
    expected_realized = (exit_price / entry_price - 1.0) * 100.0
    if not approx_equal(realized, expected_realized, tolerance=1e-6):
        raise LedgerError("outcome realized return arithmetic mismatch")
    mae = finite(outcome.get("max_adverse_excursion_pct"))
    mfe = finite(outcome.get("max_favorable_excursion_pct"))
    if mae is None or mfe is None or mae > 1e-6 or mfe < -1e-6 or realized < mae - 1e-5 or realized > mfe + 1e-5:
        raise LedgerError("outcome MAE/MFE bounds are invalid")
    predicted = finite(horizon_meta.get("expected_return_pct"))
    probability = finite(horizon_meta.get("probability_positive"))
    if not approx_equal(outcome.get("predicted_return_pct"), predicted):
        raise LedgerError("outcome predicted return differs from frozen forecast")
    if not approx_equal(outcome.get("predicted_probability_positive"), probability):
        raise LedgerError("outcome predicted probability differs from frozen forecast")
    expected_error = realized - predicted if predicted is not None else None
    if not approx_equal(outcome.get("forecast_error_pct"), expected_error, tolerance=1e-6):
        raise LedgerError("outcome forecast error arithmetic mismatch")
    expected_direction = None
    if predicted is not None and abs(predicted) > 1e-12:
        expected_direction = bool(realized > 0) if predicted > 0 else bool(realized < 0)
    if outcome.get("direction_correct") is not expected_direction:
        raise LedgerError("outcome direction_correct differs from frozen prediction and realized return")
    if not str(outcome.get("price_source") or "").strip():
        raise LedgerError("outcome price source missing")
    parse_utc(str(outcome.get("settled_at_utc") or ""))


def write_immutable_forecast(path: Path, forecast: dict[str, Any]) -> str:
    validate_forecast(forecast)
    data = canonical_json_bytes(forecast)
    if path.exists():
        existing = path.read_bytes()
        if existing != data:
            raise LedgerError(f"immutable forecast collision: {path}")
        return "unchanged"
    atomic_write_bytes(path, data)
    return "created"


def manifest_files(ledger_root: Path) -> list[Path]:
    directory = ledger_root / "live" / "manifests"
    if not directory.exists():
        return []
    return sorted(path for path in directory.glob("*.json") if path.is_file())


def forecast_files(ledger_root: Path) -> list[Path]:
    directory = ledger_root / "live" / "forecasts"
    if not directory.exists():
        return []
    return sorted(path for path in directory.rglob("*.json") if path.is_file())


def entry_files(ledger_root: Path) -> list[Path]:
    directory = ledger_root / "live" / "entries"
    if not directory.exists():
        return []
    return sorted(path for path in directory.glob("*.json") if path.is_file())


def outcome_files(ledger_root: Path) -> list[Path]:
    directory = ledger_root / "live" / "outcomes"
    if not directory.exists():
        return []
    return sorted(path for path in directory.glob("*/*.json") if path.is_file())


def _git_blob(repo_root: Path, commit_sha: str, relative_path: str) -> bytes:
    completed = subprocess.run(
        ["git", "-C", str(repo_root), "show", f"{commit_sha}:{relative_path}"],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if completed.returncode != 0:
        raise LedgerError(
            f"forecast {relative_path} not found at recorded commit {commit_sha}: "
            f"{completed.stderr.decode('utf-8', errors='replace').strip()}"
        )
    return completed.stdout


def validate_manifest_chain(
    ledger_root: Path,
    *,
    verify_git_history: bool = False,
    allowed_uncovered: set[str] | None = None,
) -> dict[str, Any]:
    manifests = manifest_files(ledger_root)
    previous_hash = "GENESIS"
    covered: dict[str, str] = {}
    signals: set[str] = set()

    for manifest_path in manifests:
        manifest = load_object(manifest_path)
        if manifest.get("schema_version") != MANIFEST_SCHEMA_VERSION:
            raise LedgerError(f"manifest schema mismatch: {manifest_path}")
        if manifest.get("previous_manifest_hash") != previous_hash:
            raise LedgerError(f"broken manifest hash chain at {manifest_path}")
        signal_id = str(manifest.get("signal_id") or "")
        if not SIGNAL_ID_RE.fullmatch(signal_id) or signal_id in signals:
            raise LedgerError(f"invalid/duplicate manifest signal_id at {manifest_path}")
        signals.add(signal_id)
        forecast_path_text = str(manifest.get("forecast_path") or "")
        if not forecast_path_text.startswith("live/forecasts/"):
            raise LedgerError(f"invalid manifest forecast_path at {manifest_path}")
        if forecast_path_text in covered:
            raise LedgerError(f"forecast has multiple manifest entries: {forecast_path_text}")
        forecast_path = ledger_root / forecast_path_text
        if not forecast_path.exists():
            raise LedgerError(f"manifest references missing forecast: {forecast_path_text}")
        forecast_hash = sha256_file(forecast_path)
        if forecast_hash != manifest.get("forecast_hash"):
            raise LedgerError(f"forecast hash mismatch: {forecast_path_text}")
        forecast = load_object(forecast_path)
        validate_forecast(forecast)
        if forecast.get("signal_id") != signal_id:
            raise LedgerError(f"manifest signal_id does not match forecast: {forecast_path_text}")
        commit_sha = str(manifest.get("git_commit_sha") or "")
        if not COMMIT_SHA_RE.fullmatch(commit_sha):
            raise LedgerError(f"manifest git_commit_sha invalid: {manifest_path}")
        if verify_git_history:
            historical = _git_blob(ledger_root, commit_sha, forecast_path_text)
            if sha256_bytes(historical) != forecast_hash:
                raise LedgerError(f"recorded git commit does not contain the frozen forecast: {forecast_path_text}")
        covered[forecast_path_text] = signal_id
        previous_hash = sha256_file(manifest_path)

    forecasts = forecast_files(ledger_root)
    forecast_paths = {str(path.relative_to(ledger_root)).replace("\\", "/") for path in forecasts}
    allowed = set(allowed_uncovered or set())
    missing_allowed = sorted(allowed - forecast_paths)
    if missing_allowed:
        raise LedgerError(f"allowed transition forecast does not exist: {', '.join(missing_allowed[:5])}")
    uncovered = forecast_paths - set(covered)
    unexpected_uncovered = sorted(uncovered - allowed)
    if unexpected_uncovered:
        raise LedgerError(f"uncovered forecast files: {', '.join(unexpected_uncovered[:5])}")
    unknown = sorted(set(covered) - forecast_paths)
    if unknown:
        raise LedgerError(f"manifest references unknown forecasts: {', '.join(unknown[:5])}")

    return {
        "forecast_count": len(forecasts),
        "manifest_count": len(manifests),
        "latest_manifest_hash": previous_hash,
        "transition_uncovered_count": len(uncovered),
        "integrity": "TRANSITION" if uncovered else "PASS",
    }


def validate_ledger(ledger_root: Path, *, verify_git_history: bool = False) -> dict[str, Any]:
    state = validate_manifest_chain(ledger_root, verify_git_history=verify_git_history)
    forecasts: dict[str, tuple[dict[str, Any], str]] = {}
    for path in forecast_files(ledger_root):
        forecast = load_object(path)
        validate_forecast(forecast)
        signal_id = str(forecast["signal_id"])
        if signal_id in forecasts:
            raise LedgerError(f"duplicate forecast signal_id: {signal_id}")
        forecasts[signal_id] = (forecast, sha256_file(path))

    entries: dict[str, dict[str, Any]] = {}
    for path in entry_files(ledger_root):
        entry = load_object(path)
        signal_id = str(entry.get("signal_id") or "")
        if path != ledger_root / entry_relative_path(signal_id):
            raise LedgerError(f"entry path does not match signal_id: {path}")
        if signal_id in entries:
            raise LedgerError(f"duplicate entry signal_id: {signal_id}")
        if signal_id not in forecasts:
            raise LedgerError(f"entry has no frozen forecast: {signal_id}")
        forecast, forecast_hash = forecasts[signal_id]
        validate_entry(entry, forecast, forecast_hash)
        entries[signal_id] = entry

    seen_outcomes: set[tuple[str, str]] = set()
    for path in outcome_files(ledger_root):
        outcome = load_object(path)
        signal_id = str(outcome.get("signal_id") or "")
        horizon = str(outcome.get("horizon") or "")
        if path != ledger_root / outcome_relative_path(signal_id, horizon):
            raise LedgerError(f"outcome path does not match signal/horizon: {path}")
        identity = (signal_id, horizon)
        if identity in seen_outcomes:
            raise LedgerError(f"duplicate outcome: {signal_id}/{horizon}")
        seen_outcomes.add(identity)
        if signal_id not in forecasts or signal_id not in entries:
            raise LedgerError(f"outcome requires both forecast and entry: {signal_id}/{horizon}")
        forecast, forecast_hash = forecasts[signal_id]
        validate_outcome(outcome, forecast, forecast_hash, entries[signal_id])

    state.update({
        "entry_count": len(entries),
        "outcome_count": len(seen_outcomes),
        "open_entry_count": max(0, len(forecasts) - len(entries)),
        "integrity": "PASS",
    })
    return state
