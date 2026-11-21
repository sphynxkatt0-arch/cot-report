#!/usr/bin/env python3
"""Build a content-addressed GitHub Pages release bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
DASHBOARD = ROOT / "worldclass_dashboard.html"
WORLDCLASS = ROOT / "worldclass"
MODEL_OUTPUT = ROOT / "model_output"
DASHBOARD_TEMPLATE = ROOT / "dashboard_template"
POINTER_NAME = "release-manifest.json"

RUNTIME_MODEL_OUTPUT = (
    "macro_liquidity_expansion.json",
)
RUNTIME_DASHBOARD_TEMPLATE = (
    "plotly-2.35.2.min.js",
)

LAUNCHER_HTML = r'''<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate">
  <title>COT Intelligence</title>
  <style>
    html,body{height:100%;margin:0;background:#07111f;color:#dce7f5;font:14px/1.5 system-ui,sans-serif}
    main{height:100%;display:grid;place-items:center}.card{padding:24px 28px;border:1px solid #20334a;border-radius:14px;background:#0b1727}
  </style>
</head>
<body>
<main><div class="card" id="status">Loading validated release…</div></main>
<script>
(async () => {
  "use strict";
  const status = document.getElementById("status");
  const pointerUrl = `release-manifest.json?v=${Date.now()}`;

  async function exists(path) {
    try {
      const response = await fetch(`${path}${path.includes("?") ? "&" : "?"}probe=${Date.now()}`, {
        cache: "no-store",
        headers: { "Accept": "text/html,application/json;q=0.9,*/*;q=0.8" }
      });
      return response.ok;
    } catch (_) {
      return false;
    }
  }

  try {
    const response = await fetch(pointerUrl, { cache: "no-store" });
    if (!response.ok) throw new Error(`release-manifest HTTP ${response.status}`);
    const pointer = await response.json();
    const candidates = [pointer.current, pointer.previous].filter(Boolean);
    for (const candidate of candidates) {
      if (!candidate.entrypoint || !candidate.manifest) continue;
      const [entryOk, manifestOk] = await Promise.all([
        exists(candidate.entrypoint),
        exists(candidate.manifest)
      ]);
      if (!entryOk || !manifestOk) continue;
      const url = new URL(candidate.entrypoint, window.location.href);
      url.searchParams.set("release_id", candidate.release_id);
      window.location.replace(url.toString());
      return;
    }
    throw new Error("No validated immutable release is reachable yet");
  } catch (error) {
    console.error(error);
    status.textContent = "Validated release is temporarily unavailable. Refresh to retry.";
  }
})();
</script>
</body>
</html>
'''


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temp.replace(path)


def should_copy_worldclass(path: Path) -> bool:
    relative = path.relative_to(WORLDCLASS)
    if any(part in {"research", "__pycache__"} for part in relative.parts):
        return False
    if path.name.endswith((".tmp", ".pyc")):
        return False
    return path.is_file()


def copy_runtime_tree(destination: Path) -> None:
    if not DASHBOARD.is_file():
        raise FileNotFoundError(DASHBOARD)
    if not WORLDCLASS.is_dir():
        raise FileNotFoundError(WORLDCLASS)

    destination.mkdir(parents=True, exist_ok=True)
    shutil.copy2(DASHBOARD, destination / "index.html")

    for source in WORLDCLASS.rglob("*"):
        if not should_copy_worldclass(source):
            continue
        relative = source.relative_to(ROOT)
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)

    for name in RUNTIME_MODEL_OUTPUT:
        source = MODEL_OUTPUT / name
        if source.is_file():
            target = destination / "model_output" / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)

    for name in RUNTIME_DASHBOARD_TEMPLATE:
        source = DASHBOARD_TEMPLATE / name
        if source.is_file():
            target = destination / "dashboard_template" / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)


def runtime_file_records(release_root: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path in sorted(
        item for item in release_root.rglob("*")
        if item.is_file() and item.name != "manifest.json"
    ):
        records.append({
            "path": path.relative_to(release_root).as_posix(),
            "sha256": sha256_file(path),
            "size": path.stat().st_size,
        })
    return records


def release_id_from_records(records: list[dict[str, Any]]) -> str:
    digest = hashlib.sha256()
    for record in records:
        digest.update(record["path"].encode("utf-8"))
        digest.update(b"\0")
        digest.update(record["sha256"].encode("ascii"))
        digest.update(b"\0")
        digest.update(str(record["size"]).encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()[:24]


def read_pointer(root: Path | None) -> dict[str, Any]:
    if root is None:
        return {}
    path = root / POINTER_NAME
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def copy_previous_release(
    previous_root: Path, output_root: Path, release_id: str
) -> bool:
    source = previous_root / "releases" / release_id
    if not source.is_dir():
        return False
    target = output_root / "releases" / release_id
    if target.exists():
        return True
    shutil.copytree(source, target)
    verify_release(target)
    return True


def verify_release(release_root: Path) -> dict[str, Any]:
    manifest_path = release_root / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("release_id") != release_root.name:
        raise RuntimeError(
            f"Manifest release_id {manifest.get('release_id')} does not match directory {release_root.name}"
        )
    files = manifest.get("files") or []
    if not files:
        raise RuntimeError(f"Release {release_root.name} manifest has no files")
    for record in files:
        path = release_root / str(record["path"])
        if not path.is_file():
            raise FileNotFoundError(path)
        actual_size = path.stat().st_size
        actual_hash = sha256_file(path)
        if actual_size != int(record["size"]):
            raise RuntimeError(f"Size mismatch for {path}: {actual_size} != {record['size']}")
        if actual_hash != record["sha256"]:
            raise RuntimeError(f"SHA256 mismatch for {path}")
    return manifest


def verify_pages_root(root: Path) -> None:
    pointer = read_pointer(root)
    current = pointer.get("current") or {}
    if not current.get("release_id"):
        raise RuntimeError("release-manifest.json has no current release")
    release_root = root / "releases" / current["release_id"]
    verify_release(release_root)
    if current.get("entrypoint") != f"releases/{current['release_id']}/index.html":
        raise RuntimeError("Current entrypoint is inconsistent with release_id")
    if current.get("manifest") != f"releases/{current['release_id']}/manifest.json":
        raise RuntimeError("Current manifest path is inconsistent with release_id")


def build_pages(output_root: Path, previous_root: Path | None) -> dict[str, Any]:
    output_root.mkdir(parents=True, exist_ok=True)
    (output_root / ".nojekyll").write_text("", encoding="utf-8")
    (output_root / "index.html").write_text(LAUNCHER_HTML, encoding="utf-8")

    with tempfile.TemporaryDirectory(prefix="cot-release-") as temp_dir:
        staged = Path(temp_dir) / "release"
        copy_runtime_tree(staged)
        records = runtime_file_records(staged)
        release_id = release_id_from_records(records)
        destination = output_root / "releases" / release_id
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            shutil.rmtree(destination)
        shutil.copytree(staged, destination)

    manifest = {
        "schema_version": 1,
        "release_id": release_id,
        "immutable": True,
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "entrypoint": "index.html",
        "files": records,
    }
    atomic_write_json(destination / "manifest.json", manifest)
    verify_release(destination)

    previous_pointer = read_pointer(previous_root)
    previous_current = previous_pointer.get("current") or {}
    previous_id = str(previous_current.get("release_id") or "")
    previous_descriptor: dict[str, Any] | None = None
    if previous_root is not None and previous_id and previous_id != release_id:
        if copy_previous_release(previous_root, output_root, previous_id):
            previous_descriptor = {
                "release_id": previous_id,
                "entrypoint": f"releases/{previous_id}/index.html",
                "manifest": f"releases/{previous_id}/manifest.json",
            }

    current_descriptor = {
        "release_id": release_id,
        "entrypoint": f"releases/{release_id}/index.html",
        "manifest": f"releases/{release_id}/manifest.json",
    }
    pointer = {
        "schema_version": 1,
        "strategy": "immutable-release-with-verified-pointer-fallback",
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "current": current_descriptor,
        "previous": previous_descriptor,
    }
    atomic_write_json(output_root / POINTER_NAME, pointer)
    verify_pages_root(output_root)
    return pointer


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, help="Pages staging directory")
    parser.add_argument("--previous-root", type=Path, default=None, help="Checked-out current gh-pages root")
    parser.add_argument("--verify", type=Path, default=None, help="Verify an already-built Pages root")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.verify is not None:
        verify_pages_root(args.verify)
        print(f"Atomic release verification PASS: {args.verify}")
        return
    if args.output is None:
        raise SystemExit("--output is required unless --verify is used")
    if args.output.exists():
        shutil.rmtree(args.output)
    pointer = build_pages(args.output, args.previous_root)
    print(f"Built atomic Pages release {pointer['current']['release_id']} -> {args.output}")


if __name__ == "__main__":
    main()
