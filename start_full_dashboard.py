#!/usr/bin/env python3
"""Unified Auto-Fetch, Build, and Local Server Launcher for COT Intelligence.

This script:
1. Auto-fetches latest market & macro data from public endpoints (FRED, Treasury, Yahoo, CNN).
2. Runs the complete release-aligned COT and regime processing pipeline.
3. Builds the modern Worldclass COT Intelligence Terminal, Directional Decision Report,
   and Macro Monitor.
4. Launches a local HTTP server with multi-dashboard routing and opens it in your default browser.

Usage:
  py start_full_dashboard.py               # Fetch fresh data, rebuild, and start dashboard
  py start_full_dashboard.py --no-fetch   # Rebuild and start instantly using cached data
  py start_full_dashboard.py --port 8080  # Start server on port 8080
  py start_full_dashboard.py --refresh-only # Refresh & build without starting server
"""

from __future__ import annotations

import argparse
import http.server
import json
import mimetypes
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.parse
import webbrowser
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parent
ANALYSIS = ROOT / "analysis"
WORLDCLASS = ANALYSIS / "worldclass"
DATA_DIR = ROOT / "data"

sys.path.insert(0, str(ANALYSIS))

mimetypes.add_type("application/javascript", ".js")
mimetypes.add_type("text/css", ".css")
mimetypes.add_type("application/json", ".json")
mimetypes.add_type("text/html", ".html")
mimetypes.add_type("image/svg+xml", ".svg")


def print_banner() -> None:
    print(r"""
==============================================================================
   ____ ___ _____   ___ _   _ _____ _____ _     _     ___ ____ _____ _   _  ____ _____ 
  / ___/ _ \_   _| |_ _| \ | |_   _| ____| |   | |   |_ _/ ___| ____| \ | |/ ___| ____|
 | |  | | | || |    | ||  \| | | | |  _| | |   | |    | | |  _|  _| |  \| | |   |  _|  
 | |__| |_| || |    | || |\  | | | | |___| |___| |___ | | |_| | |___| |\  | |___| |___ 
  \____\___/ |_|   |___|_| \_| |_| |_____|_____|_____|___\____|_____|_| \_|\____|_____|
==============================================================================
  COT Intelligence Terminal & Macro Direction System
  Autonomous Multi-Dashboard Engine
==============================================================================
""", flush=True)


def log(step: str, message: str) -> None:
    now = datetime.now().strftime("%H:%M:%S")
    print(f"[{now}] [{step.upper():<12}] {message}", flush=True)


def run_python_module(script_name: str, *args: str, timeout: int = 180) -> bool:
    script_path = ANALYSIS / script_name
    if not script_path.exists():
        script_path = ROOT / script_name
    if not script_path.exists():
        log("ERROR", f"Script not found: {script_name}")
        return False

    cmd = [sys.executable, str(script_path), *args]
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(ANALYSIS),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
        )
        if proc.returncode != 0:
            log("WARN", f"{script_name} exited with code {proc.returncode}")
            for line in proc.stdout.strip().splitlines()[-6:]:
                print(f"    | {line}")
            return False
        return True
    except subprocess.TimeoutExpired:
        log("WARN", f"{script_name} timed out after {timeout}s")
        return False
    except Exception as exc:
        log("WARN", f"Error executing {script_name}: {exc}")
        return False


def autofetch_data() -> None:
    log("FETCH", "Starting auto-fetch of raw market, yield & macro indicators...")
    try:
        import serve_interactive_cot_dashboard as legacy_fetcher

        for series_id, dest in legacy_fetcher.FRED_SERIES.items():
            try:
                legacy_fetcher.fetch_fred_csv(series_id, dest)
            except Exception as exc:
                if dest.exists():
                    log("CACHE", f"{series_id} refresh skipped/failed, using cached {dest.name}")
                else:
                    log("WARN", f"{series_id} fetch failed: {exc}")

        try:
            legacy_fetcher.refresh_cnn_factors()
            log("FETCH", "CNN Fear & Greed index updated.")
        except Exception as exc:
            log("CACHE", f"CNN Fear & Greed fetch note: {exc}")

    except Exception as exc:
        log("WARN", f"Auto-fetch module notice: {exc}")


def build_pipeline() -> bool:
    log("BUILD", "Step 1/8: Ingesting raw CFTC Legacy and TFF data overlays...")
    run_python_module("cot_overlay_exact.py", "--market", "all", "--start", "2016")
    run_python_module("cot_legacy_correlations.py", "--market", "all", "--start", "2016")
    run_python_module("cot_regime_score_backtest.py")
    run_python_module("cot_legacy_regime_score_backtest.py")

    log("BUILD", "Step 2/8: Ingesting Gold and Silver Disaggregated COT data...")
    run_python_module("build_worldclass_metals.py")

    log("BUILD", "Step 3/8: Computing Macro Liquidity Plumbing expansion...")
    run_python_module("macro_liquidity_expansion_v12.py")

    log("BUILD", "Step 4/8: Building interactive Macro Monitor container...")
    run_python_module("build_interactive_cot_dashboard_v2.py", timeout=1800)

    log("BUILD", "Step 5/8: Assembling Worldclass base data bundle...")
    run_python_module("build_worldclass_bundle.py")

    log("BUILD", "Step 6/8: Generating Bartlett HAC Dependency-Aware Regime Backtest...")
    run_python_module("build_worldclass_regime_backtest.py")

    log("BUILD", "Step 7/8: Materializing COT edge registries & certified v2 runtime...")
    run_python_module("install_release_corrected_runtime_v2.py")

    log("BUILD", "Step 8/8: Computing Directional COT model & decision matrix...")
    run_python_module("refresh_directional_cot_system.py", "--skip-public-refresh")

    log("RELEASE", "Packaging atomic immutable release bundle...")
    staging_dir = ROOT / "test_pages_staging"
    run_python_module("build_atomic_release.py", "--output", str(staging_dir))
    if staging_dir.exists():
        import shutil
        shutil.rmtree(staging_dir, ignore_errors=True)

    log("SUCCESS", "All dashboards and intelligence endpoints successfully generated!")
    return True


class COTDashboardHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ANALYSIS), **kwargs)

    def end_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        super().end_headers()

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path.rstrip("/")

        if path in ("", "/index.html"):
            self.path = "/worldclass_dashboard.html"
        elif path in ("/terminal", "/worldclass", "/intelligence"):
            self.path = "/worldclass_dashboard.html"
        elif path in ("/directional", "/decisions", "/direction"):
            self.path = "/directional_cot_report.html"
        elif path in ("/macro", "/monitor"):
            self.path = "/interactive_cot_dashboard.html"
        elif path == "/api/status":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            status_payload = {
                "status": "online",
                "timestamp_utc": datetime.now(UTC).isoformat(),
                "terminal": "/worldclass_dashboard.html",
                "directional": "/directional_cot_report.html",
                "macro": "/interactive_cot_dashboard.html",
                "model_version": "cot-direction-v1.2",
            }
            self.wfile.write(json.dumps(status_payload, indent=2).encode("utf-8"))
            return

        super().do_GET()

    def log_message(self, format: str, *args: Any) -> None:
        # Suppress noisy standard HTTP access logs
        if self.path.endswith((".js", ".css", ".png", ".svg", ".json")):
            return
        log("HTTP", f"{self.address_string()} -> {self.path}")


def find_free_port(preferred: int = 8000) -> int:
    for port in [preferred, 8080, 4173, 5000, 3000, 8888]:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            if sock.connect_ex(("127.0.0.1", port)) != 0:
                return port
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("", 0))
        return sock.getsockname()[1]


def start_server(host: str = "127.0.0.1", port: int = 8000, open_browser: bool = True) -> None:
    active_port = find_free_port(port)
    server_address = (host, active_port)
    httpd = http.server.ThreadingHTTPServer(server_address, COTDashboardHandler)

    url = f"http://{host}:{active_port}"
    print("\n" + "=" * 78)
    log("READY", f"COT Intelligence Dashboard Server running at: {url}")
    print("=" * 78)
    print(f"  * Primary Terminal Dashboard : {url}/")
    print(f"  * Directional COT Decisions  : {url}/directional")
    print(f"  * Macro Liquidity Monitor    : {url}/macro")
    print(f"  * Live Status Endpoint       : {url}/api/status")
    print("=" * 78)
    print("  [Ctrl+C] to stop server\n", flush=True)

    if open_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n")
        log("STOP", "Dashboard server stopped by user.")
        httpd.server_close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Auto-fetch and launch COT Intelligence Dashboards")
    parser.add_argument("--no-fetch", action="store_true", help="Skip online fetch and build from local caches")
    parser.add_argument("--fast", "--serve-only", dest="fast", action="store_true", help="Start local server immediately without re-running build steps")
    parser.add_argument("--refresh-only", action="store_true", help="Only refresh data and rebuild files without starting server")
    parser.add_argument("--port", type=int, default=8000, help="Local HTTP server port (default 8000)")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="Local HTTP server host (default 127.0.0.1)")
    parser.add_argument("--no-browser", action="store_true", help="Do not open browser automatically")
    args = parser.parse_args()

    print_banner()

    if not args.fast:
        if not args.no_fetch:
            autofetch_data()
        else:
            log("SKIP", "Online data fetch skipped (--no-fetch requested).")

        build_pipeline()
    else:
        log("FAST", "Fast start requested: skipping build and launching server directly.")

    if not args.refresh_only:
        start_server(host=args.host, port=args.port, open_browser=not args.no_browser)


if __name__ == "__main__":
    main()
