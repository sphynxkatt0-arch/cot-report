#!/usr/bin/env python3
"""Materialize the independently certified release-corrected v2 snapshot.

GitHub-hosted Actions were unavailable during certification, so the full research
was executed on an independent Vercel build plane. This fetcher makes that
certification reproducible for production: it validates the final certification,
then the snapshot verification-manifest hash, then every downloaded file's
per-file SHA256 before installation.
"""
from __future__ import annotations

import hashlib
import json
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
SNAP = ROOT / "worldclass" / "research" / "snapshots" / "2026-08-11-release-corrected-v2"
REMOTE = "https://cot-v2-final-certification.vercel.app"
FINAL_URL = f"{REMOTE}/FINAL_CERTIFICATION.json"
SNAP_URL = f"{REMOTE}/snapshot"
EXPECTED_GATE_A_SHA256 = "8025d66ca4cf4ff1f05cdb59f3cd254ce40a855d274ef4094f2a9bd4ac51a7e6"
REQUIRED_FILES = (
    "verification-manifest.json",
    "SHA256SUMS.txt",
    "cot-edge-registry-v2.json",
    "cot-actor-event-summary.json",
    "cot-threshold-inference-v2.json.gz",
    "cot-actor-event-research.json.gz",
    "cot-edge-details-v2/sp500.json",
    "cot-edge-details-v2/nq.json",
    "cot-edge-details-v2/vix.json",
    "cot-edge-details-v2/rty.json",
    "cot-edge-details-v2/dow.json",
    "cot-edge-details-v2/gold.json",
    "cot-edge-details-v2/silver.json",
)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fetch_bytes(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "cot-report-release-corrected-v2"})
    with urllib.request.urlopen(request, timeout=120) as response:
        return response.read()


def load_json_bytes(data: bytes, label: str) -> dict[str, Any]:
    value = json.loads(data.decode("utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"{label} root must be an object")
    return value


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_bytes(data)
    temp.replace(path)


def verify_existing() -> bool:
    manifest_path = SNAP / "verification-manifest.json"
    if not manifest_path.exists():
        return False
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        return False
    if manifest.get("snapshot_id") != "2026-08-11-release-corrected-v2":
        return False
    if manifest.get("research_generation") != "release-corrected-v2":
        return False
    files = manifest.get("files") or {}
    for relative in REQUIRED_FILES:
        if relative in {"verification-manifest.json", "SHA256SUMS.txt"}:
            continue
        expected = ((files.get(relative) or {}).get("sha256"))
        path = SNAP / relative
        if not expected or not path.exists() or sha256(path) != expected:
            return False
    return True


def materialize(force: bool = False) -> dict[str, Any]:
    if not force and verify_existing():
        return json.loads((SNAP / "verification-manifest.json").read_text(encoding="utf-8"))

    final_bytes = fetch_bytes(FINAL_URL)
    final = load_json_bytes(final_bytes, "final certification")
    if final.get("status") != "PASS":
        raise RuntimeError("remote v2 final certification is not PASS")
    if final.get("gate_a_archive_sha256") != EXPECTED_GATE_A_SHA256:
        raise RuntimeError("remote v2 Gate A hash differs from the independently certified parent")

    manifest_bytes = fetch_bytes(f"{SNAP_URL}/verification-manifest.json")
    manifest_sha = sha256_bytes(manifest_bytes)
    if final.get("snapshot_manifest_sha256") != manifest_sha:
        raise RuntimeError("remote v2 snapshot-manifest hash does not match FINAL_CERTIFICATION")
    manifest = load_json_bytes(manifest_bytes, "snapshot verification manifest")
    if manifest.get("snapshot_id") != "2026-08-11-release-corrected-v2":
        raise RuntimeError("unexpected v2 snapshot id")
    if manifest.get("research_generation") != "release-corrected-v2":
        raise RuntimeError("unexpected v2 research generation")
    if manifest.get("promotion_eligible") is not False or manifest.get("production_weight_changes") is not False:
        raise RuntimeError("v2 snapshot governance flags unexpectedly permit promotion/weight changes")
    if manifest.get("gate_a_archive_sha256") != EXPECTED_GATE_A_SHA256:
        raise RuntimeError("snapshot Gate A hash mismatch")

    files = manifest.get("files") or {}
    staged: dict[str, bytes] = {"verification-manifest.json": manifest_bytes}
    staged["SHA256SUMS.txt"] = fetch_bytes(f"{SNAP_URL}/SHA256SUMS.txt")
    for relative in REQUIRED_FILES:
        if relative in staged:
            continue
        expected = ((files.get(relative) or {}).get("sha256"))
        if not expected:
            raise RuntimeError(f"snapshot manifest lacks SHA256 for {relative}")
        data = fetch_bytes(f"{SNAP_URL}/{relative}")
        actual = sha256_bytes(data)
        if actual != expected:
            raise RuntimeError(f"snapshot SHA256 mismatch for {relative}: {actual} != {expected}")
        staged[relative] = data

    for relative, data in staged.items():
        atomic_write(SNAP / relative, data)

    if not verify_existing():
        raise RuntimeError("materialized v2 snapshot failed local verification")
    return manifest


def main() -> None:
    manifest = materialize()
    print(
        "Release-corrected v2 snapshot materialized · "
        f"snapshot={manifest['snapshot_id']} · files={len(manifest.get('files') or {})}"
    )


if __name__ == "__main__":
    main()
