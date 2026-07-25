# COT Direction Report And Macro Liquidity Dashboard

This project has two connected surfaces:

1. **Directional COT Report** — the priority decision layer for S&P 500 and Nasdaq-100.
2. **COT Macro Monitor** — the advanced workbench for raw TFF/Legacy positioning, macro liquidity, funding stress, rates, credit, dollar, volatility, calendars, backtests, and source detail.

The directional report does not replace the macro component. It imposes one hierarchy so multiple research panels no longer compete to define direction.

## Recommended workflow

From `A:\work\trading\cot report\analysis`, double-click either:

```text
start_directional_cot_report.cmd
start_cot_dashboard.cmd
```

Both launchers route through the same integrated refresh. To refresh without opening a page:

```text
refresh_cot_dashboard.cmd
```

Manual equivalent:

```powershell
py refresh_directional_cot_system.py --strict-refresh --open
```

A non-strict run may use existing validated cached files when a public source fails:

```powershell
py refresh_directional_cot_system.py --open
```

The system records whether public-data refresh succeeded in:

```text
model_output\directional_refresh_status.json
```

## Decision hierarchy

1. **Legacy Non-commercials set structural direction.** Equity-index calibration is contrarian: historically low positioning is bullish support and historically high positioning is a crowding warning.
2. **TFF modifies conviction only.** Other Reportables and Nonreportables use 13-week trend ranks; Legacy Non-commercial four-week flow provides additional tactical context.
3. **Asset Managers modify position size only.** They cannot reverse the structural sign.
4. **Macro modifies size or blocks execution.** The model separates liquidity plumbing, market transmission, and Treasury supply pressure.
5. **Price controls execution.** Post-release response and the 20-business-day trend must agree for confirmation; the 65-day trend remains context.
6. **Confidence controls actionability.** Missing or stale data lowers availability and confidence instead of being silently treated as neutral.

Commercials are not counted as independent directional confirmation because their positioning is mechanically related to other participant categories. Dealer / Intermediary remains excluded from directional scoring as structural offset inventory. Nonreportables are labelled as a **small-trader/retail proxy**, not verified pure retail.

## Publication timing and delays

COT observations are Tuesday as-of positions but normally become public Friday at 15:30 New York time. The decision layer starts at the first market close on or after the effective release date, never from Tuesday.

The release tracker stores:

- scheduled release in UTC and Stockholm time;
- expected latest report date;
- the first time a genuinely current report was observed locally;
- current, awaiting-release, and delayed states.

A first-observed timestamp is not claimed as an official CFTC timestamp. When a report is delayed, the system preserves the prior signal and emits:

```text
Hold Prior Signal — CFTC Report Delayed
```

No new recommendation is produced from stale COT data.

Historical audit rows always use deterministic scheduled-Friday alignment and never read the live release ledger.

## Macro structure and freshness

The existing macro dashboard remains the evidence source. The directional adapter groups its factors into:

- **Liquidity plumbing:** net liquidity, bank reserves, SOFR–IORB funding pressure, and SLR/balance-sheet load.
- **Market transmission:** real yields, credit spreads, dollar, and VIX.
- **Supply pressure:** Treasury issuance-calendar pressure.

Daily inputs older than five calendar days and weekly inputs older than twelve days are excluded from the available macro weight. The final JSON lists every stale or missing factor. Two or more active severe red macro alerts trigger a hard-risk override.

Macro changes exposure or blocks execution; it does not manufacture the opposite COT thesis.

## Price execution

The execution layer uses daily cash-index closes:

- **Confirmed:** post-release response and 20-day trend align with the structural side.
- **Waiting:** movement remains inside the configured band.
- **Contradicted:** the release response or 20-day trend opposes the structural side.
- **Invalidated:** an adverse move breaches the configured S&P 500 or Nasdaq threshold.
- **Unavailable:** required price history is missing.

This is not futures VWAP or intraday order flow. The existing dashboard's post-report anchor remains an anchored mean unless a volume-bearing futures source is added.

## Generated outputs

```text
model_output\cot_direction_latest.json
model_output\cot_direction_latest.csv
model_output\cot_direction_history.csv
model_output\cot_direction_validation_summary.csv
model_output\macro_direction_context.json
model_output\cftc_release_observations.json
model_output\directional_refresh_status.json
directional_cot_report.html
interactive_cot_dashboard.html
```

The macro dashboard receives an injected top decision panel. The older Weekly Desk, selected-report regime, and TFF/Legacy selector remain available but are explicitly labelled as research-only surfaces.

## Historical audit

`cot_direction_history.csv` contains release-aligned features and subsequent 1-, 4-, 13-, and 26-week outcomes. `cot_direction_validation_summary.csv` reports exploratory correlations and bullish-versus-bearish bucket differences.

These outputs are audit aids. They are not described as sealed out-of-sample proof.

## Validation

The integrated refresh runs all model suites automatically:

```powershell
py -m unittest \
  tests.test_cot_direction_model \
  tests.test_release_and_macro \
  tests.test_directional_system \
  tests.test_price_execution_adapter \
  tests.test_deterministic_history -v
```

They cover:

- Friday release alignment and Stockholm release time;
- stale-report rejection and delayed-report behavior;
- contrarian Non-commercial direction;
- tactical sign protection;
- Asset Manager sizing-only behavior;
- macro decomposition, stale-source exclusion, and overrides;
- trend-aware price confirmation;
- deterministic historical alignment;
- idempotent dashboard injection and research-only relabelling.

The repository's GitHub Actions runner currently fails before any steps or logs are produced. The local integrated refresh therefore remains the required validation path until Actions infrastructure is repaired.

## Full research dashboard

To serve the already-built integrated dashboard without refreshing:

```powershell
py serve_interactive_cot_dashboard.py --skip-refresh --open
```

Raw data contracts remain official CFTC Futures Only consolidated rows:

- S&P 500 Consolidated, code `13874+`, index × $50.
- Nasdaq-100 Consolidated, code `20974+`, index × $20.
- VIX Futures, code `1170E1`, index × $1,000.

Legacy and TFF are parallel classifications, not interchangeable mappings.

## Setup

```powershell
py -m pip install -r requirements.txt
```

Provide a FRED API key through either:

```text
analysis\config\fred_api_key.txt
```

or the `FRED_API_KEY` environment variable.

## Methodology and configuration

```text
docs\cot_direction_model_v1.md
config\cot_direction_model_v1.json
```

Current model version: `cot-direction-v1.1`.

## Remaining limitations

- Historical exact official CFTC publication timestamps are not available.
- Treasury and agency calendars do not perfectly estimate settlement drain, dealer balance-sheet usage, or auction demand.
- The SLR layer is a public H.8 proxy, not bank-level regulatory filing data.
- Intraday repo, cross-currency basis, CDX, options gamma, Treasury depth, and bank-level constraints require separate sources.
- Weights are transparent versioned starting values, not a claim of sealed out-of-sample optimization.
