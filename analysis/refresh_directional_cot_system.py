#!/usr/bin/env python3
"""Refresh data, validate inputs/model, build outputs, and integrate the dashboard."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import webbrowser
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STATUS = ROOT / "model_output" / "directional_refresh_status.json"
DIRECTIONAL_HTML = ROOT / "directional_cot_report.html"
DASHBOARD_HTML = ROOT / "interactive_cot_dashboard.html"


def run(script: str, *args: str, allow_failure: bool = False) -> bool:
    if script == "-m":
        command = [sys.executable, "-m", *args]
        label = "python -m " + " ".join(args)
    else:
        command = [sys.executable, str(ROOT / script), *args]
        label = script
    print("$", " ".join(command), flush=True)
    result = subprocess.run(command, cwd=ROOT)
    if result.returncode and not allow_failure:
        raise RuntimeError(f"{label} failed with exit code {result.returncode}")
    return result.returncode == 0


def write_status(status: str, message: str, refresh_ok: bool | None = None) -> None:
    STATUS.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "status": status,
        "message": message,
        "updated_at": datetime.now(UTC).isoformat(),
        "public_data_refresh_ok": refresh_ok,
        "directional_report_exists": DIRECTIONAL_HTML.exists(),
        "macro_dashboard_exists": DASHBOARD_HTML.exists(),
    }
    STATUS.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def run_model_tests() -> None:
    run(
        "-m",
        "unittest",
        "tests.test_cot_direction_model",
        "tests.test_release_and_macro",
        "tests.test_directional_system",
        "tests.test_price_execution_adapter",
        "tests.test_deterministic_history",
        "tests.test_macro_actionability_guard",
        "tests.test_directional_input_validation",
        "tests.test_observed_release_price_alignment",
        "tests.test_historical_release_context",
        "tests.test_model_comparison",
        "-v",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=int, default=2016)
    parser.add_argument("--end", type=int, default=datetime.now(UTC).year)
    parser.add_argument("--skip-public-refresh", action="store_true")
    parser.add_argument("--strict-refresh", action="store_true", help="Stop when public-data refresh fails instead of using validated cached files.")
    parser.add_argument("--open", action="store_true")
    args = parser.parse_args()

    write_status("running", "Directional COT refresh is in progress.")
    refresh_ok: bool | None = None
    try:
        if not args.skip_public_refresh:
            refresh_ok = run(
                "serve_interactive_cot_dashboard.py",
                "--refresh-only",
                "--start",
                str(args.start),
                "--end",
                str(args.end),
                allow_failure=not args.strict_refresh,
            )
            if not refresh_ok:
                print("WARNING: public-data refresh failed; continuing only with existing validated local outputs.", file=sys.stderr)
        run("validate_directional_inputs.py")
        run_model_tests()
        run("rebuild_directional_history.py")
        run("enrich_directional_history_context.py")
        run("compare_directional_models_v11.py")
        run("build_latest_directional_decisions.py")
        run("align_observed_release_price.py")
        run("price_execution_adapter.py")
        run("macro_actionability_guard.py")
        run("inject_model_comparison_report.py")
        run("inject_directional_dashboard.py")
        run("validate_directional_outputs.py")
    except Exception as exc:
        write_status("failed", str(exc), refresh_ok)
        raise

    message = "Directional report and integrated macro dashboard rebuilt and validated successfully."
    if refresh_ok is False:
        message += " Public-data refresh failed, so cached inputs were used; release and source-freshness guards remain active."
    write_status("ok", message, refresh_ok)
    print(message)
    if args.open:
        webbrowser.open(DIRECTIONAL_HTML.resolve().as_uri())


if __name__ == "__main__":
    main()
