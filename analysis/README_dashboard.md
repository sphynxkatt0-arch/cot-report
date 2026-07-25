# COT Direction Report And Macro Liquidity Dashboard

This project now has two connected surfaces:

1. **Directional COT Report** — the priority decision layer for S&P 500 and Nasdaq-100.
2. **COT Macro Monitor** — the advanced workbench for raw TFF/Legacy positioning, macro liquidity, funding stress, rates, credit, dollar, volatility, calendars, backtests, and source detail.

The directional report does not replace the macro component. It gives the project one explicit hierarchy so multiple panels no longer compete to define direction.

## Recommended day-to-day run

From `A:\work\trading\cot report\analysis`, double-click:

```text
start_directional_cot_report.cmd
```

This performs the existing full refresh, rebuilds the macro dashboard, builds the directional model outputs, and opens:

```text
directional_cot_report.html
```

Manual equivalent:

```powershell
py serve_interactive_cot_dashboard.py --refresh-only
py build_directional_cot_report.py
```

Generated directional outputs:

```text
model_output\cot_direction_latest.json
model_output\cot_direction_latest.csv
directional_cot_report.html
```

## Decision hierarchy

The directional model is deliberately ordered:

1. **Legacy Non-commercials set structural direction.**
2. **TFF Other Reportables, Nonreportables, and Non-commercial flow modify conviction.**
3. **Asset Manager crowding modifies position size only.**
4. **Macro regime modifies size or activates a hard-risk override.**
5. **Post-release price action controls execution.**
6. **Confidence controls whether the result is actionable or context only.**

TFF categories cannot reverse the Legacy Non-commercial structural sign. Commercials are not counted as an independent directional confirmation because their positioning mechanically offsets other participant groups. Dealer / Intermediary remains excluded from directional scoring because it is primarily structural offset inventory.

For equity indices, the current historical calibration is contrarian:

- historically low Legacy Non-commercial positioning is bullish structural support;
- historically high Legacy Non-commercial positioning is a long-crowding warning;
- the direction sign must not be copied to commodities or FX without separate calibration.

Nonreportables are labelled as a **small-trader/retail proxy**, not verified pure retail.

Full methodology and current limitations:

```text
docs\cot_direction_model_v1.md
```

Model thresholds and weights:

```text
config\cot_direction_model_v1.json
```

## Publication timing

COT observations are Tuesday as-of positions but normally become public on Friday. The directional model anchors price execution to the first market close on or after Friday rather than using Tuesday-to-Friday movement as tradable information.

The current repository does not contain a complete historical archive of actual CFTC publication timestamps. The first model version therefore records Friday as a `scheduled_assumption` and applies a confidence penalty. Delayed-release detection and an actual publication-time archive remain follow-up work.

## Run the full research dashboard

To open the existing COT Macro Monitor:

```powershell
py serve_interactive_cot_dashboard.py --open
```

Or double-click:

```text
start_cot_dashboard.cmd
```

Useful modes:

```powershell
py serve_interactive_cot_dashboard.py --refresh-only
py serve_interactive_cot_dashboard.py --skip-refresh --open
py build_interactive_cot_dashboard.py
py build_directional_cot_report.py
```

The refresher downloads or updates public price and macro feeds, rebuilds TFF and Legacy COT outputs, regenerates dependent analyses, validates source freshness, and rebuilds `interactive_cot_dashboard.html`. Optional non-COT source failures use the latest local cache when available.

## COT data contracts

The pipeline uses official CFTC Futures Only consolidated rows:

- S&P 500 Consolidated, code `13874+`, index × $50.
- Nasdaq-100 Consolidated, code `20974+`, index × $20.
- VIX Futures, code `1170E1`, index × $1,000.

Legacy and TFF are parallel classifications, not interchangeable mappings. Legacy Non-commercial is not the same category as TFF Asset Managers or Leveraged Funds.

The full dashboard preserves raw category charts, weekly changes, cross-market SP + NQ − VIX exposure, historical percentile tables, backtests, and research findings. The dataset selector is an analytical control; it should not be interpreted as changing the directional model's structural anchor.

## Macro-liquidity inputs

The macro system includes:

- Core liquidity: Fed balance sheet, TGA, reverse repo, bank reserves, and net liquidity.
- Funding stress: SOFR, EFFR, IORB, SOFR–IORB, and EFFR–IORB.
- Bank balance-sheet proxies: Treasury/agency holdings, total assets, reserves relative to bank assets, and SLR-related load.
- Rates and credit: real yields, nominal yields, high-yield OAS, and investment-grade OAS.
- Transmission: broad dollar index and VIX.
- Supply calendars: Treasury issuance, agency issuance, and rule-based GSE cash-flow dates.
- Retirement-flow proxy: FRTIB/TSP monthly allocation data where available.

The broad existing `liquidity_score` contains liquidity, supply, funding, rates, credit, dollar, and volatility. In the directional model it is treated as a macro risk-regime input that modifies size; it does not independently manufacture the opposite COT direction.

Two or more active severe red macro alerts trigger a hard-risk override in the first implementation.

## Price execution

The directional report uses daily index closes to measure price response from the scheduled Friday release date. It does not claim to calculate futures VWAP. The full dashboard's post-report anchor is an anchored mean unless a separate volume-bearing futures feed is added.

## Validation

Run the model invariants with:

```powershell
py -m unittest tests.test_cot_direction_model -v
```

The tests verify:

- Tuesday COT rows align to Friday publication timing.
- Low Non-commercial percentile is bullish for the equity-index calibration.
- High Non-commercial percentile is bearish/crowded.
- Tactical TFF inputs cannot reverse the structural sign.
- Asset Manager extremes reduce size instead of defining direction.
- Macro overrides block execution without rewriting the structural COT bias.

The existing `verify_findings.py` remains a reproducibility check for saved research constants. It is not a sealed out-of-sample validation framework.

## Setup

```powershell
py -m pip install -r requirements.txt
```

For FRED series, provide an API key through either:

```text
analysis\config\fred_api_key.txt
```

or the `FRED_API_KEY` environment variable.

## Current limitations

- Historical actual CFTC release timestamps and delays are not fully archived.
- The macro model still uses the broad existing score rather than fully separated plumbing, transmission, and supply submodels.
- Treasury and agency calendars identify scheduled events but do not perfectly estimate settlement drain, dealer balance-sheet usage, or auction demand.
- The SLR layer is a proxy built from public H.8 data, not bank-level regulatory filings.
- Intraday repo, cross-currency basis, CDX, options gamma, Treasury depth, and bank-level constraints require separate data sources.
- The first directional model is transparent and rule-based. Its weights are versioned starting values, not a claim of sealed out-of-sample optimization.
