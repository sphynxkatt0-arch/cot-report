# COT Direction Report and Macro Liquidity Dashboard

This project has two connected surfaces:

1. **Directional COT Report** — the priority decision layer for S&P 500 and Nasdaq-100.
2. **COT Macro Monitor** — the advanced workbench for raw TFF/Legacy positioning, macro liquidity, funding stress, rates, credit, dollar, volatility, calendars, backtests, and source detail.

The directional report does not replace the research dashboard. It imposes one hierarchy so parallel research scores cannot compete to define the headline trade.

## Recommended workflow

From the `analysis` directory, double-click either:

```text
start_directional_cot_report.cmd
start_cot_dashboard.cmd
```

Both launchers route through the same governed refresh. To refresh without opening a page:

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

The run status is written to:

```text
model_output\directional_refresh_status.json
```

## Mandatory decision hierarchy

The integrated refresh applies these layers in order:

1. **Legacy Non-commercials set structural direction.** Equity-index calibration is contrarian: historically low positioning is bullish support; historically high positioning is a long-crowding warning.
2. **TFF modifies conviction only.** Other Reportables and Nonreportables use 13-week trend ranks; Legacy Non-commercial four-week flow provides additional tactical context.
3. **Asset Managers modify size only.** They cannot reverse the Legacy structural sign.
4. **Macro modifies size or blocks execution.** Stale inputs are excluded rather than treated as neutral.
5. **Price controls execution.** Post-release response, 20-business-day trend, and 65-day context determine confirmation, waiting, contradiction, or invalidation.
6. **Historical evidence caps exposure.** Evidence grades never create or reverse direction.
7. **CFTC release completeness has final actionability priority.** Delayed, awaiting, and catch-up reports cannot create new exposure.
8. **Weekly position changes explain the result.** This descriptive layer shows what changed but never casts another directional vote.

Commercials are not counted as independent directional confirmation because their positioning is mechanically related to other participant categories. Dealer / Intermediary remains excluded from directional scoring as structural offset inventory.

Nonreportables are labelled **Retail proxy (Nonreportables)** or **small-trader/retail proxy**. CFTC does not identify this residual category as verified pure retail.

## What changed this week

The final JSON, standalone report, and integrated dashboard compare the latest two common Legacy/TFF report dates and show:

- Legacy Non-commercial net-contract change and net/open-interest change;
- Asset Manager change;
- Leveraged Money change;
- Other Reportables change;
- Retail proxy / Nonreportables change;
- structural-score change;
- tactical-modifier change;
- adjusted COT-score change;
- whether the COT signal strengthened, weakened, neutralized, flipped, or remained little changed.

This section is descriptive. It does not alter `final_action` or `exposure_multiplier`.

## Publication timing and delays

COT observations are Tuesday as-of positions but normally become public Friday at 15:30 New York time. The decision layer begins at the first eligible market close on or after the effective release date, never from Tuesday.

The release tracker stores:

- scheduled release in UTC and Stockholm time;
- expected latest report date;
- the first local observation of a genuinely current report;
- the expected report gap;
- `current`, `awaiting_release`, `delayed`, and `catch_up_delayed` states.

A first-observed timestamp is local evidence, not an asserted official CFTC publication timestamp.

Delayed states have final priority:

```text
Hold Prior Signal — CFTC Report Delayed
Hold Prior Signal — Awaiting Friday Release
Wait — CFTC Catch-Up Still Behind
```

A multi-week catch-up report may be displayed for positioning context, but it remains non-actionable while a newer expected CFTC report is missing.

Historical audit rows always use deterministic scheduled-Friday alignment and never read the live release ledger.

## Macro structure and freshness

The directional adapter groups the existing macro evidence into:

- **Liquidity plumbing:** net liquidity, bank reserves, SOFR–IORB funding pressure, and SLR/balance-sheet load.
- **Market transmission:** real yields, credit spreads, dollar, and VIX.
- **Supply pressure:** Treasury issuance-calendar pressure.

Daily and weekly inputs that breach their configured freshness limits are removed from available weight. The final JSON lists every stale or missing factor.

New exposure is blocked when reliable macro coverage is below 60%. Severe macro overrides are suppressed when their supporting sources are stale.

Macro changes exposure or blocks execution; it does not manufacture the opposite COT thesis.

## Historical evidence governance

Five models are compared on identical Friday-aligned dates and outcomes:

1. old TFF regime;
2. old Legacy regime;
3. new Non-commercial structure;
4. new structure plus TFF tactical layer;
5. new full release-time decision model.

The comparison reports:

- Pearson and Spearman association;
- Newey–West HAC slope and p-value with horizon-matched lags;
- positive-minus-negative edge and HAC p-value;
- three chronological subperiod sign stability;
- drift-adjusted accuracy;
- directional coverage and hit rate;
- average and worst adverse movement;
- path utility;
- pairwise directional agreement.

Evidence is explicitly graded:

```text
Supported
Tentative
Weak/Mixed
Contradictory
Not estimable
```

Historical evidence only caps exposure:

- Supported: maximum 1.25x;
- Tentative: maximum 0.75x;
- Not validated: maximum 0.35x;
- Contradictory: 0.00x and wait on the existing structural side.

## Price execution

The execution layer uses daily cash-index closes:

- **Confirmed:** release response and trend structure align with the COT side.
- **Waiting:** movement remains inside the configured band.
- **Contradicted:** release response or trend structure opposes the COT side.
- **Invalidated:** an adverse move breaches the configured market threshold.
- **Unavailable:** required price history is missing.

This is not futures VWAP or intraday order flow. The existing post-report anchor remains an anchored mean unless a volume-bearing futures source is added.

## Generated outputs

```text
model_output\cot_direction_latest.json
model_output\cot_direction_latest.csv
model_output\cot_position_changes_latest.csv
model_output\cot_direction_history.csv
model_output\cot_direction_validation_summary.csv
model_output\directional_model_comparison_aligned.csv
model_output\directional_model_comparison_summary.csv
model_output\directional_model_agreement.csv
model_output\macro_direction_context.json
model_output\cftc_release_observations.json
model_output\directional_refresh_status.json
directional_cot_report.html
interactive_cot_dashboard.html
```

The macro dashboard receives an injected top decision panel and a decision-quality panel containing historical evidence and weekly participant changes. Older TFF/Legacy regime surfaces remain available but are explicitly labelled as research-only.

## Validation

Every integrated refresh validates raw inputs and discovers every test automatically:

```powershell
py -m unittest discover -s tests -p "test_*.py" -v
```

The test suite covers:

- Friday release alignment and Stockholm release time;
- pre-release rejection, delayed reports, and multi-week catch-ups;
- contrarian Non-commercial direction;
- weak-structure and tactical sign protection;
- Asset Manager sizing-only behavior;
- macro decomposition, stale-source exclusion, and reliable overrides;
- price confirmation and delayed-release price alignment;
- deterministic historical alignment and no-look-ahead macro context;
- five-model HAC, stability, path, and evidence grading;
- evidence, macro, and release actionability guards;
- weekly participant-change calculations;
- idempotent standalone-report and dashboard injection;
- generated JSON, CSV, comparison, and HTML contracts.

The repository's GitHub Actions environment currently fails before any workflow steps or logs are produced. The integrated local refresh therefore remains the required execution path until that repository-level Actions problem is repaired.

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
config\fred_api_key.txt
```

or the `FRED_API_KEY` environment variable.

## Methodology and configuration

```text
docs\cot_direction_model_v1.md
config\cot_direction_model_v1.json
```

Current model version: `cot-direction-v1.1`.

## Remaining limitations

- Historical exact official CFTC publication timestamps are unavailable.
- Public COT data cannot isolate verified retail positioning.
- Treasury and agency calendars do not perfectly estimate settlement drain, dealer balance-sheet usage, or auction demand.
- The SLR layer is a public H.8 proxy, not bank-level regulatory filing data.
- Intraday repo, cross-currency basis, CDX, options gamma, Treasury depth, and bank-level constraints require separate sources.
- Model weights are transparent versioned starting values, not a claim of sealed out-of-sample optimization.
