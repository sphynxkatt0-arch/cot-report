#!/usr/bin/env python3
"""Build and verify the production static-release integrity manifest.

GitHub Pages serves files from a single published tree. The deployment workflow
must validate every runtime asset before publishing and then publish the entire
validated tree in one gh-pages commit. This manifest records the exact bytes of
that tree's runtime surface so a mixed/stale deployment can be detected instead
of silently serving an old COT payload with a new application shell.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
DEFAULT_MANIFEST = Path("worldclass/release-manifest.json")
RUNTIME_SUFFIXES = {".html", ".js", ".css", ".json"}
EXCLUDED_NAMES = {"release-manifest.json"}
REQUIRED_RUNTIME_PATHS = (
    "index.html",
    "worldclass/base.json",
    "worldclass/model-spec.json",
    "worldclass/backtest.json",
    "worldclass/regime_backtest.json",
    "worldclass/cot-current-state.json",
    "worldclass/cot-edge-registry.json",
    "worldclass/cot-active-edges.json",
    "worldclass/cot-cross-market.json",
    "worldclass/cot-research-provenance.json",
    "worldclass/live-track-record.json",
    "worldclass/release-status.json",
    "model_output/macro_liquidity_expansion.json",
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def discover_runtime_files(root: Path) -> list[Path]:
    files: set[Path] = set()
    for relative in REQUIRED_RUNTIME_PATHS:
        path = root / relative
        if not path.is_file():
            raise FileNotFoundError(f"Required production runtime file is missing: {relative}")
        files.add(path)

    worldclass = root / "worldclass"
    if worldclass.is_dir():
        for path in worldclass.iterdir():
            if not path.is_file():
                continue
            if path.name in EXCLUDED_NAMES or path.suffix.lower() not in RUNTIME_SUFFIXES:
                continue
            files.add(path)

    for name in ("worldclass_dashboard.html",):
        path = root / name
        if path.is_file():
            files.add(path)

    return sorted(files, key=lambda path: path.relative_to(root).as_posix())


def build_manifest(root: Path, source_commit: str | None = None) -> dict[str, Any]:
    files = discover_runtime_files(root)
    entries: list[dict[str, Any]] = []
    aggregate = hashlib.sha256()
    for path in files:
        relative = path.relative_to(root).as_posix()
        digest = sha256_file(path)
        size = path.stat().st_size
        entries.append({"path": relative, "bytes": size, "sha256": digest})
        aggregate.update(relative.encode("utf-8"))
        aggregate.update(b"\0")
        aggregate.update(digest.encode("ascii"))
        aggregate.update(b"\n")

    generated = datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
    source = (source_commit or os.environ.get("GITHUB_SHA") or "local").strip()
    content_hash = aggregate.hexdigest()
    release_id = f"{generated.replace(':', '').replace('-', '')}-{source[:12]}-{content_hash[:12]}"
    return {
        "schema_version": 1,
        "release_id": release_id,
        "generated_at_utc": generated,
        "source_commit": source,
        "release_content_sha256": content_hash,
        "publish_contract": {
            "strategy": "single-commit-gh-pages",
            "atomic_publish_unit": "validated publish tree",
            "predeploy_hash_verification_required": True,
            "postdeploy_hash_verification_required": True,
            "mixed_version_runtime_allowed": False,
        },
        "required_runtime_paths": list(REQUIRED_RUNTIME_PATHS),
        "file_count": len(entries),
        "files": entries,
    }


def write_manifest(root: Path, manifest_relative: Path, source_commit: str | None = None) -> Path:
    output = root / manifest_relative
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = build_manifest(root, source_commit=source_commit)
    temp = output.with_suffix(output.suffix + ".tmp")
    temp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    temp.replace(output)
    return output


def verify_manifest(root: Path, manifest_path: Path) -> dict[str, Any]:
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    failures: list[str] = []
    aggregate = hashlib.sha256()
    entries = payload.get("files") or []
    for entry in entries:
        relative = str(entry.get("path") or "")
        expected_hash = str(entry.get("sha256") or "")
        expected_bytes = int(entry.get("bytes") or 0)
        path = root / relative
        if not path.is_file():
            failures.append(f"missing:{relative}")
            continue
        actual_bytes = path.stat().st_size
        actual_hash = sha256_file(path)
        if actual_bytes != expected_bytes:
            failures.append(f"size:{relative}:{actual_bytes}!={expected_bytes}")
        if actual_hash != expected_hash:
            failures.append(f"sha256:{relative}:{actual_hash}!={expected_hash}")
        aggregate.update(relative.encode("utf-8"))
        aggregate.update(b"\0")
        aggregate.update(actual_hash.encode("ascii"))
        aggregate.update(b"\n")

    actual_content_hash = aggregate.hexdigest()
    expected_content_hash = str(payload.get("release_content_sha256") or "")
    if actual_content_hash != expected_content_hash:
        failures.append(
            f"release_content_sha256:{actual_content_hash}!={expected_content_hash}"
        )
    if failures:
        raise RuntimeError("Release manifest verification failed: " + "; ".join(failures))
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--source-commit", default=None)
    parser.add_argument("--verify", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    root = args.root.resolve()
    manifest_path = args.manifest
    if not manifest_path.is_absolute():
        manifest_path = root / manifest_path
    if args.verify:
        payload = verify_manifest(root, manifest_path)
        print(
            f"Release manifest PASS: {payload['release_id']} "
            f"({payload['file_count']} files)"
        )
        return
    output = write_manifest(root, args.manifest, source_commit=args.source_commit)
    payload = json.loads(output.read_text(encoding="utf-8"))
    print(f"Wrote {output}: {payload['release_id']} ({payload['file_count']} files)")


if __name__ == "__main__":
    main()
