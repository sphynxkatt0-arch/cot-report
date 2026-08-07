#!/usr/bin/env python3
"""
Refresh and open or serve the interactive COT dashboard.

This is the preferred way to open the dashboard when you want fresh data.
It downloads the latest FRED price CSVs, reruns the COT scripts, rebuilds
interactive_cot_dashboard.html, and can either open the HTML directly or
serve it from localhost.

Run:
  py serve_interactive_cot_dashboard.py --open-html
  py serve_interactive_cot_dashboard.py --open
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
import socket
import subprocess
import sys
import urllib.parse
import urllib.request
import webbrowser
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parent
HTML = ROOT / "interactive_cot_dashboard.html"
REFRESH_STATUS = ROOT / "dashboard_refresh_status.json"
FRED_SERIES = {
    "SP500": PROJECT / "data" / "SP500.csv",
    "NASDAQ100": PROJECT / "data" / "NASDAQ100.csv",
    "VIXCLS": PROJECT / "data" / "VIXCLS.csv",
    "WALCL": PROJECT / "data" / "WALCL.csv",
    "WDTGAL": PROJECT / "data" / "WDTGAL.csv",
    "RRPONTSYD": PROJECT / "data" / "RRPONTSYD.csv",
    "WRESBAL": PROJECT / "data" / "WRESBAL.csv",
    "SOFR": PROJECT / "data" / "SOFR.csv",
    "EFFR": PROJECT / "data" / "EFFR.csv",
    "IORB": PROJECT / "data" / "IORB.csv",
    "USGSEC": PROJECT / "data" / "USGSEC.csv",
    "BANKASSETS": PROJECT / "data" / "BANKASSETS.csv",
    "DFII5": PROJECT / "data" / "DFII5.csv",
    "DFII10": PROJECT / "data" / "DFII10.csv",
    "DGS10": PROJECT / "data" / "DGS10.csv",
    "DGS2": PROJECT / "data" / "DGS2.csv",
    "DGS3MO": PROJECT / "data" / "DGS3MO.csv",
    "DGS30": PROJECT / "data" / "DGS30.csv",
    "BAMLH0A0HYM2": PROJECT / "data" / "BAMLH0A0HYM2.csv",
    "BAMLC0A0CM": PROJECT / "data" / "BAMLC0A0CM.csv",
    "DTWEXBGS": PROJECT / "data" / "DTWEXBGS.csv",
    "RUT": PROJECT / "data" / "RUT.csv",
    "DJIA": PROJECT / "data" / "DJIA.csv",
    "GOLD": PROJECT / "data" / "GOLD.csv",
}
FEAR_GREED_ROOT = PROJECT / "fear-greed-data-main" / "fear-greed-data-main"
FRED_FETCH_TIMEOUT = 20
FRED_API_KEY_FILE = ROOT / "config" / "fred_api_key.txt"
YAHOO_INDEX_PRICE_SERIES = {
    "SP500": "^GSPC",
    "NASDAQ100": "^NDX",
    "VIXCLS": "^VIX",
    "RUT": "^RUT",
    "DJIA": "^DJI",
    "GOLD": "GC=F",
}
TREASURY_XML_URL = "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/pages/xml"
TREASURY_XML_YEAR_LOOKBACK = 4
TREASURY_XML_SERIES = {
    "DGS3MO": ("daily_treasury_yield_curve", "BC_3MONTH"),
    "DGS2": ("daily_treasury_yield_curve", "BC_2YEAR"),
    "DGS10": ("daily_treasury_yield_curve", "BC_10YEAR"),
    "DGS30": ("daily_treasury_yield_curve", "BC_30YEAR"),
    "DFII5": ("daily_treasury_real_yield_curve", "TC_5YEAR"),
    "DFII10": ("daily_treasury_real_yield_curve", "TC_10YEAR"),
}
TREASURY_XML_CACHE: dict[tuple[str, int], bytes] = {}
OFR_SOFR_URL = "https://data.financialresearch.gov/v1/series/timeseries?mnemonic=FNYR-SOFR-A&remove_nulls=true"
OFR_EFFR_URL = "https://data.financialresearch.gov/v1/series/timeseries?mnemonic=FNYR-EFFR-A&remove_nulls=true"
FED_IORB_URL = (
    "https://www.federalreserve.gov/datadownload/Output.aspx"
    "?rel=PRATES&series=c27939ee810cb2e929a920a6bd77d9f6&lastObs=&from=&to="
    "&filetype=csv&label=include&layout=seriescolumn&type=package"
)
FED_H8_BANK_TREASURY_AGENCY_URL = (
    "https://www.federalreserve.gov/datadownload/Output.aspx"
    "?rel=H8&series=fce2318909bacbc8ce268096deddd180&lastObs=&from=&to="
    "&filetype=csv&label=include&layout=seriescolumn&type=package"
)
FED_H8_BANK_ASSETS_URL = FED_H8_BANK_TREASURY_AGENCY_URL


def local_timestamp() -> str:
    return datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %z")


def log(message: str, *, file=sys.stdout) -> None:
    print(f"[{local_timestamp()}] {message}", file=file, flush=True)


def write_refresh_status(status: str, message: str = "") -> None:
    payload = {
        "status": status,
        "message": message,
        "updated_at": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "dashboard_mtime": (
            datetime.fromtimestamp(HTML.stat().st_mtime, UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
            if HTML.exists() else None
        ),
    }
    REFRESH_STATUS.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def cached_csv_latest_date(path: Path) -> str:
    try:
        last_data_line = ""
        with path.open("r", encoding="utf-8-sig", errors="replace") as fh:
            next(fh, None)
            for line in fh:
                if line.strip():
                    last_data_line = line
        if not last_data_line:
            return "n/a"
        return last_data_line.split(",", 1)[0].strip() or "n/a"
    except OSError:
        return "n/a"


def fetch_url_bytes(url: str, timeout: int) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 COT dashboard updater"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def fetch_url_json(url: str, timeout: int):
    return json.loads(fetch_url_bytes(url, timeout).decode("utf-8"))


def load_fred_api_key() -> str | None:
    env_key = os.environ.get("FRED_API_KEY", "").strip()
    if env_key:
        return env_key
    try:
        file_key = FRED_API_KEY_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return file_key or None


def write_series_csv(dest: Path, series_id: str, rows: list[tuple[str, str]]) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["observation_date", series_id])
        writer.writerows(rows)


def merge_series_csv(dest: Path, series_id: str, rows: list[tuple[str, str]]) -> None:
    merged: dict[str, str] = {}
    if dest.exists():
        with dest.open("r", newline="", encoding="utf-8-sig", errors="replace") as fh:
            reader = csv.DictReader(fh)
            if reader.fieldnames:
                date_col = "observation_date" if "observation_date" in reader.fieldnames else "date"
                value_col = series_id if series_id in reader.fieldnames else next(
                    (field for field in reader.fieldnames if field != date_col),
                    None,
                )
                if value_col:
                    for row in reader:
                        observation_date = str(row.get(date_col, "")).strip()
                        value = str(row.get(value_col, "")).strip()
                        if observation_date and value and value != ".":
                            merged[observation_date] = value
    for observation_date, value in rows:
        if observation_date and value:
            merged[str(observation_date)] = str(value)
    write_series_csv(dest, series_id, sorted(merged.items()))


def fetch_fred_api_csv(series_id: str, dest: Path, timeout: int = FRED_FETCH_TIMEOUT) -> bool:
    api_key = load_fred_api_key()
    if not api_key:
        return False
    params = {
        "series_id": series_id,
        "api_key": api_key,
        "file_type": "json",
    }
    latest = cached_csv_latest_date(dest)
    if latest != "n/a":
        params["observation_start"] = latest
    url = f"https://api.stlouisfed.org/fred/series/observations?{urllib.parse.urlencode(params)}"
    observations = fetch_url_json(url, timeout).get("observations") or []
    rows = [
        (str(item.get("date", "")).strip(), str(item.get("value", "")).strip())
        for item in observations
        if str(item.get("date", "")).strip() and str(item.get("value", "")).strip() not in {"", "."}
    ]
    if not rows:
        return False
    merge_series_csv(dest, series_id, rows)
    return True


def fetch_yahoo_index_price_csv(dest: Path, series_id: str) -> None:
    symbol = YAHOO_INDEX_PRICE_SERIES[series_id]
    encoded_symbol = urllib.parse.quote(symbol, safe="")
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{encoded_symbol}?range=10y&interval=1d"
    result = (fetch_url_json(url, 20).get("chart", {}).get("result") or [None])[0]
    if not result:
        raise RuntimeError(f"Yahoo chart returned no data for {symbol}.")
    timestamps = result.get("timestamp") or []
    quote = ((result.get("indicators") or {}).get("quote") or [{}])[0]
    closes = quote.get("close") or []
    rows: list[tuple[str, str]] = []
    for timestamp, close_value in zip(timestamps, closes):
        if close_value is None:
            continue
        observation_date = datetime.fromtimestamp(int(timestamp), UTC).date().isoformat()
        rows.append((observation_date, f"{float(close_value):.3f}"))
    meta = result.get("meta") or {}
    current_price = meta.get("regularMarketPrice")
    current_time = meta.get("regularMarketTime")
    if current_price is not None and current_time is not None:
        observation_date = datetime.fromtimestamp(int(current_time), UTC).date().isoformat()
        rows.append((observation_date, f"{float(current_price):.3f}"))
    if not rows:
        raise RuntimeError(f"Yahoo chart returned no usable close values for {symbol}.")
    merge_series_csv(dest, series_id, rows)


def xml_local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def fetch_treasury_xml_bytes(data_key: str, year: int) -> bytes:
    cache_key = (data_key, year)
    if cache_key in TREASURY_XML_CACHE:
        return TREASURY_XML_CACHE[cache_key]
    query = urllib.parse.urlencode({"data": data_key, "field_tdr_date_value": str(year)})
    url = f"{TREASURY_XML_URL}?{query}"
    content = fetch_url_bytes(url, 30)
    TREASURY_XML_CACHE[cache_key] = content
    return content


def parse_treasury_xml_series(data_key: str, value_field: str) -> list[tuple[str, str]]:
    current_year = datetime.now(UTC).year
    rows: dict[str, str] = {}
    for year in range(current_year - TREASURY_XML_YEAR_LOOKBACK + 1, current_year + 1):
        root = ET.fromstring(fetch_treasury_xml_bytes(data_key, year))
        for entry in root.iter():
            if xml_local_name(entry.tag) != "entry":
                continue
            properties = next((node for node in entry.iter() if xml_local_name(node.tag) == "properties"), None)
            if properties is None:
                continue
            values = {xml_local_name(child.tag): (child.text or "").strip() for child in list(properties)}
            observation_date = values.get("NEW_DATE", "").split("T", 1)[0]
            value = values.get(value_field)
            if observation_date and value:
                rows[observation_date] = value
    return sorted(rows.items())


def fetch_treasury_yield_csv(dest: Path, series_id: str) -> None:
    data_key, value_field = TREASURY_XML_SERIES[series_id]
    rows = parse_treasury_xml_series(data_key, value_field)
    if not rows:
        raise RuntimeError(f"Treasury XML returned no usable rows for {series_id}.")
    merge_series_csv(dest, series_id, rows)


def fetch_ofr_rate_csv(dest: Path, series_id: str, source_url: str) -> None:
    rows = [
        (str(item[0]), str(item[1]))
        for item in fetch_url_json(source_url, 60)
        if isinstance(item, list) and len(item) >= 2 and item[1] is not None
    ]
    write_series_csv(dest, series_id, rows)


def fetch_ofr_sofr_csv(dest: Path) -> None:
    fetch_ofr_rate_csv(dest, "SOFR", OFR_SOFR_URL)


def fetch_ofr_effr_csv(dest: Path) -> None:
    fetch_ofr_rate_csv(dest, "EFFR", OFR_EFFR_URL)


def fetch_fed_ddp_series_csv(dest: Path, series_id: str, source_url: str, value_column: str) -> None:
    content = fetch_url_bytes(source_url, 60).decode("utf-8-sig", errors="replace")
    reader = csv.reader(io.StringIO(content))
    rows: list[tuple[str, str]] = []
    header: list[str] | None = None
    value_index: int | None = None
    for row in reader:
        if not row:
            continue
        if row[0].strip().lower() == "time period":
            header = [item.strip() for item in row]
            if value_column not in header:
                raise KeyError(f"{value_column} was not found in Federal Reserve DDP output.")
            value_index = header.index(value_column)
            continue
        if header is None or value_index is None or len(row) <= value_index:
            continue
        value = row[value_index].strip()
        if value:
            rows.append((row[0].strip(), value))
    write_series_csv(dest, series_id, rows)


def fetch_fed_iorb_csv(dest: Path) -> None:
    fetch_fed_ddp_series_csv(dest, "IORB", FED_IORB_URL, "RESBM_N.D")


def fetch_fed_h8_bank_treasury_agency_csv(dest: Path) -> None:
    fetch_fed_ddp_series_csv(dest, "USGSEC", FED_H8_BANK_TREASURY_AGENCY_URL, "B1003NCBA")


def fetch_fed_h8_bank_assets_csv(dest: Path) -> None:
    fetch_fed_ddp_series_csv(dest, "BANKASSETS", FED_H8_BANK_ASSETS_URL, "B1058NCBA")


SPECIAL_SERIES_FETCHERS = {
    "SOFR": fetch_ofr_sofr_csv,
    "EFFR": fetch_ofr_effr_csv,
    "IORB": fetch_fed_iorb_csv,
    "USGSEC": fetch_fed_h8_bank_treasury_agency_csv,
    "BANKASSETS": fetch_fed_h8_bank_assets_csv,
}


def fetch_fred_csv(series_id: str, dest: Path, timeout: int = FRED_FETCH_TIMEOUT) -> None:
    special_fetcher = SPECIAL_SERIES_FETCHERS.get(series_id)
    if special_fetcher is not None:
        special_fetcher(dest)
        log(f"Updated {series_id}: {dest}")
        return
    if series_id in TREASURY_XML_SERIES:
        fetch_treasury_yield_csv(dest, series_id)
        log(f"Updated {series_id} from Treasury XML: {dest}")
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    if series_id in YAHOO_INDEX_PRICE_SERIES:
        fetch_yahoo_index_price_csv(dest, series_id)
        log(f"Updated {series_id} from Yahoo fallback/top-up: {dest}")
        return

    try:
        if fetch_fred_api_csv(series_id, dest, timeout=timeout):
            log(f"Updated FRED API {series_id}: {dest}")
            return
    except Exception as exc:
        log(f"WARNING: FRED API {series_id} refresh failed; trying CSV endpoint: {exc}")

    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
    try:
        dest.write_bytes(fetch_url_bytes(url, timeout))
    except Exception:
        raise
    log(f"Updated FRED {series_id}: {dest}")


def run_python(script: str, *args: str) -> None:
    cmd = [sys.executable, str(ROOT / script), *args]
    log(f"$ {' '.join(cmd)}")
    logs = ROOT / "dashboard_refresh_logs"
    logs.mkdir(exist_ok=True)
    log_path = logs / f"{Path(script).stem}.log"
    result = subprocess.run(cmd, cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    log_path.write_text(result.stdout, encoding="utf-8", errors="replace")
    if result.returncode != 0:
        tail = "\n".join(result.stdout.splitlines()[-80:])
        raise RuntimeError(f"{script} failed with exit code {result.returncode}. Log: {log_path}\n{tail}")
    log(f"Completed {script}. Log: {log_path}")


def run_python_file(path: Path, *args: str, timeout: int | None = None) -> None:
    cmd = [sys.executable, str(path), *args]
    log(f"$ {' '.join(cmd)}")
    logs = ROOT / "dashboard_refresh_logs"
    logs.mkdir(exist_ok=True)
    log_path = logs / f"{path.stem}.log"
    try:
        result = subprocess.run(
            cmd,
            cwd=path.parent.parent,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        partial = exc.stdout or ""
        log_path.write_text(str(partial), encoding="utf-8", errors="replace")
        raise RuntimeError(f"{path.name} timed out after {timeout}s. Log: {log_path}") from exc
    log_path.write_text(result.stdout, encoding="utf-8", errors="replace")
    if result.returncode != 0:
        tail = "\n".join(result.stdout.splitlines()[-80:])
        raise RuntimeError(f"{path.name} failed with exit code {result.returncode}. Log: {log_path}\n{tail}")
    log(f"Completed {path.name}. Log: {log_path}")


def csv_max_date(path: Path, column: str, *, market: str | None = None) -> str:
    maximum = ""
    with path.open("r", encoding="utf-8-sig", errors="replace", newline="") as fh:
        for row in csv.DictReader(fh):
            if market is not None and row.get("market") != market:
                continue
            value = (row.get(column) or "").strip()
            if value and value > maximum:
                maximum = value
    return maximum


def summary_cutoffs(path: Path) -> dict[str, dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", errors="replace", newline="") as fh:
        return {
            row["market"]: {
                "latest": (row.get("latest_date") or "")[:10],
                "source": (row.get("source_latest_date") or "")[:10],
            }
            for row in csv.DictReader(fh)
        }


def validate_refresh_outputs(start: int, end: int, include_legacy: bool) -> None:
    exact = summary_cutoffs(ROOT / "cot_exact_output" / f"cot_exact_summary_{start}_{end}.csv")
    legacy = summary_cutoffs(ROOT / "cot_legacy_output" / f"cot_legacy_summary_{start}_{end}.csv") if include_legacy else {}
    failures: list[str] = []
    for market, dates in exact.items():
        if dates["latest"] != dates["source"]:
            failures.append(f"TFF {market}: output {dates['latest']} != source {dates['source']}")
    for market, dates in legacy.items():
        if dates["latest"] != dates["source"]:
            failures.append(f"Legacy {market}: output {dates['latest']} != source {dates['source']}")

    cross_market_latest = csv_max_date(
        ROOT / "cot_cross_market_predictivity_output" / "latest_risk_exposure_signals.csv",
        "date",
    )
    expected_cross_market_latest = min(dates["latest"] for dates in exact.values() if dates["latest"])
    if cross_market_latest != expected_cross_market_latest:
        failures.append(
            f"Cross-market predictivity: {cross_market_latest} != TFF common latest {expected_cross_market_latest}"
        )

    history = ROOT / "cot_regime_backtest_output" / "regime_score_history.csv"
    legacy_history = ROOT / "cot_legacy_regime_backtest_output" / "regime_score_history.csv"
    for market in ("sp500", "nq"):
        backtest_latest = csv_max_date(history, "report_date", market=market)
        if backtest_latest != exact[market]["latest"]:
            failures.append(f"Regime backtest {market}: {backtest_latest} != TFF {exact[market]['latest']}")

        if include_legacy:
            legacy_backtest_latest = csv_max_date(legacy_history, "report_date", market=market)
            if legacy_backtest_latest != legacy[market]["latest"]:
                failures.append(
                    f"Legacy regime backtest {market}: {legacy_backtest_latest} != Legacy {legacy[market]['latest']}"
                )

        tff_effects = ROOT / "cot_position_effects_output" / f"{market}_tff_disaggregated_post_release_data.csv"
        effects_latest = csv_max_date(tff_effects, "date")
        if effects_latest != exact[market]["latest"]:
            failures.append(f"Position effects {market}: {effects_latest} != TFF {exact[market]['latest']}")

    if failures:
        raise RuntimeError("Refresh freshness validation failed:\n- " + "\n- ".join(failures))
    log(
        "Freshness validated: "
        + ", ".join(f"TFF {market} {dates['latest']}" for market, dates in exact.items())
        + ("; " + ", ".join(f"Legacy {market} {dates['latest']}" for market, dates in legacy.items()) if legacy else "")
        + "; regime backtest and position-effect outputs reconciled."
    )


def refresh_cnn_factors() -> None:
    fetch_script = FEAR_GREED_ROOT / "scripts" / "fetch_cnn.py"
    build_script = FEAR_GREED_ROOT / "scripts" / "build_combined.py"
    if not fetch_script.exists() or not build_script.exists():
        log(f"WARNING: CNN factor scripts not found under {FEAR_GREED_ROOT}; using existing local factor files.")
        return
    try:
        run_python_file(fetch_script, timeout=45)
        run_python_file(build_script, timeout=45)
    except Exception as exc:
        log(f"WARNING: CNN factor refresh failed: {exc}")
        log("Continuing with existing local CNN factor files.")


def refresh_data(start: int, end: int, include_legacy: bool = True) -> None:
    log(f"Refresh started. start={start}, end={end}, legacy={'yes' if include_legacy else 'no'}")
    write_refresh_status("running", "Refresh is in progress.")
    for series_id, dest in FRED_SERIES.items():
        try:
            fetch_fred_csv(series_id, dest)
        except Exception as exc:
            if dest.exists():
                log(
                    f"WARNING: {series_id} refresh failed; using existing {dest} "
                    f"(latest cached date: {cached_csv_latest_date(dest)}): {exc}"
                )
                continue
            raise

    refresh_cnn_factors()
    run_python("cot_overlay_exact.py", "--market", "all", "--start", str(start), "--end", str(end))
    if include_legacy:
        run_python("cot_legacy_correlations.py", "--market", "all", "--start", str(start), "--end", str(end))
    run_python("cot_cross_market_predictivity.py")
    run_python("cot_weekly_position_effects.py")
    run_python("cot_regime_score_backtest.py")
    if include_legacy:
        run_python("cot_legacy_regime_score_backtest.py")
    validate_refresh_outputs(start, end, include_legacy)
    run_python("build_interactive_cot_dashboard.py")
    run_python("verify_findings.py")
    write_refresh_status("ok", "Last refresh completed successfully.")
    log(f"Refresh completed. Dashboard rebuilt: {HTML}")


class DashboardHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store, max-age=0")
        super().end_headers()

    def do_GET(self) -> None:
        if self.path in {"/", ""}:
            self.path = "/interactive_cot_dashboard.html"
        super().do_GET()


def find_port(host: str, preferred: int) -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        if s.connect_ex((host, preferred)) != 0:
            return preferred
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((host, 0))
        return int(s.getsockname()[1])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--start", type=int, default=2016)
    parser.add_argument("--end", type=int, default=datetime.now(UTC).year)
    parser.add_argument("--skip-refresh", action="store_true")
    parser.add_argument("--no-legacy", action="store_true")
    parser.add_argument("--refresh-only", action="store_true")
    parser.add_argument("--open-html", action="store_true", help="Open interactive_cot_dashboard.html directly and exit after refresh.")
    parser.add_argument("--open", action="store_true")
    args = parser.parse_args()

    refresh_failed = False
    if not args.skip_refresh:
        try:
            refresh_data(args.start, args.end, include_legacy=not args.no_legacy)
        except Exception as e:
            refresh_failed = True
            write_refresh_status("failed", str(e))
            log(f"WARNING: refresh failed: {e}", file=sys.stderr)
            if not HTML.exists():
                raise
            fallback = "Opening" if args.open_html else "Serving"
            log(f"{fallback} the existing dashboard file instead.", file=sys.stderr)

    if args.refresh_only:
        if refresh_failed:
            sys.exit(1)
        return

    if not HTML.exists():
        raise FileNotFoundError(f"{HTML} does not exist. Run build_interactive_cot_dashboard.py first.")

    if args.open_html:
        url = HTML.resolve().as_uri()
        webbrowser.open(url)
        log(f"Opened dashboard HTML: {url}")
        log("Refresh completed; Python process is stopping now.")
        return

    port = find_port(args.host, args.port)
    url = f"http://{args.host}:{port}/"
    server = ThreadingHTTPServer((args.host, port), DashboardHandler)
    log(f"Serving COT dashboard: {url}")
    log("Press Ctrl+C to stop.")
    if args.open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log("Stopped.")


if __name__ == "__main__":
    main()
