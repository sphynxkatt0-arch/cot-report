#!/usr/bin/env python3
"""Canonical model specification loader and integrity helpers.

All authoritative research builders read the same versioned JSON specification.
The canonical SHA-256 is computed from sorted/minified JSON so equivalent files
produce the same model identity independent of formatting.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
MODEL_SPEC_PATH = ROOT / "config" / "model_spec.json"


def canonical_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def validate_model_spec(spec: dict[str, Any]) -> None:
    if spec.get("schema_version") != 1:
        raise ValueError("model_spec schema_version must be 1")
    if not str(spec.get("model_version") or "").strip():
        raise ValueError("model_spec model_version is required")

    score_models = spec.get("score_models")
    if not isinstance(score_models, dict):
        raise ValueError("model_spec score_models must be an object")
    for dataset in ("tff", "legacy", "disaggregated"):
        model = score_models.get(dataset)
        if not isinstance(model, dict) or not isinstance(model.get("category_weights"), dict):
            raise ValueError(f"model_spec missing score model for {dataset}")

    thresholds = spec.get("thresholds") or {}
    bullish = float(thresholds.get("bullish", -1))
    bearish = float(thresholds.get("bearish", 101))
    if not 0 <= bearish < bullish <= 100:
        raise ValueError("model_spec bullish/bearish thresholds are invalid")
    lower = float(thresholds.get("extreme_lower_percentile", -1))
    upper = float(thresholds.get("extreme_upper_percentile", 101))
    if not 0 <= lower < upper <= 100:
        raise ValueError("model_spec extreme percentile thresholds are invalid")

    lookback = int((spec.get("lookback") or {}).get("minimum_weeks", 0))
    if lookback < 2:
        raise ValueError("model_spec minimum lookback must be >= 2 weeks")

    horizons = spec.get("horizons")
    if not isinstance(horizons, dict) or not horizons:
        raise ValueError("model_spec horizons are required")
    for label, steps in horizons.items():
        if int(steps) <= 0:
            raise ValueError(f"model_spec horizon {label} must be positive")

    taxonomy = spec.get("actor_taxonomy")
    if not isinstance(taxonomy, dict):
        raise ValueError("model_spec actor_taxonomy must be an object")
    for dataset, model in score_models.items():
        required = set((taxonomy.get(dataset) or {}).get("required_categories") or [])
        weighted = set((model or {}).get("category_weights") or {})
        if not required or required != weighted:
            raise ValueError(f"model_spec taxonomy/weights mismatch for {dataset}")


def load_model_spec(path: Path = MODEL_SPEC_PATH) -> dict[str, Any]:
    spec = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(spec, dict):
        raise ValueError("model_spec root must be an object")
    validate_model_spec(spec)
    return spec


def model_spec_hash(spec: dict[str, Any] | None = None) -> str:
    resolved = spec if spec is not None else load_model_spec()
    return hashlib.sha256(canonical_bytes(resolved)).hexdigest()


def score_weights(spec: dict[str, Any]) -> dict[str, dict[str, float]]:
    return {
        dataset: {key: float(value) for key, value in model["category_weights"].items()}
        for dataset, model in spec["score_models"].items()
    }


def horizons(spec: dict[str, Any]) -> dict[str, int]:
    return {label: int(steps) for label, steps in spec["horizons"].items()}


def runtime_metadata(spec: dict[str, Any] | None = None) -> dict[str, Any]:
    resolved = spec if spec is not None else load_model_spec()
    return {
        "schema_version": resolved["schema_version"],
        "model_version": resolved["model_version"],
        "model_spec_hash": model_spec_hash(resolved),
        "score_models": resolved["score_models"],
        "actor_taxonomy": resolved["actor_taxonomy"],
        "thresholds": resolved["thresholds"],
        "lookback": resolved["lookback"],
        "analogs": resolved["analogs"],
        "horizons": resolved["horizons"],
    }
