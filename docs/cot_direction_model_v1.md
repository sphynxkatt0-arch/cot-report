# COT Direction Model v1.1

## Purpose

This is the priority decision layer for S&P 500 and Nasdaq-100. It preserves the existing macro-liquidity dashboard as the advanced evidence surface while producing one explicit market posture.

## Decision hierarchy

1. **Legacy Non-commercials set structural direction.** Equity-index calibration is contrarian: historically low Non-commercial positioning is bullish support; historically high positioning is a crowding warning.
2. **TFF data modifies conviction only.** Other Reportables and Nonreportables use 13-week trend ranks; Legacy Non-commercial four-week flow identifies confirmation versus continued accumulation or liquidation.
3. **Asset Managers modify size only.** Above the 90th percentile, the default exposure multiplier is 0.75. Asset Managers cannot reverse the structural sign.
4. **Macro modifies size or blocks execution.** The existing macro payload is decomposed into liquidity plumbing, market transmission, and supply pressure. Two or more severe red alerts produce a hard-risk override.
5. **Price controls execution.** Confirmation requires both the post-release move and the 20-business-day trend to agree with the COT side. The 65-business-day trend remains context.
6. **Confidence controls actionability.** Missing or stale data lowers availability and confidence rather than being silently filled as neutral evidence.

## Release timing

COT positions are Tuesday as-of observations but normally become public Friday at 15:30 New York time. That is normally 21:30 Stockholm during the summer and 21:30 or 20:30 around daylight-saving transition periods depending on the U.S./European clock-change mismatch.

The system records:

- scheduled release timestamp;
- expected latest report date;
- first local observation time for genuinely current reports;
- delayed and awaiting-release states.

A first-observed timestamp is local evidence, not an official CFTC timestamp. During a delayed week the system preserves the prior signal and emits no new recommendation.

Historical model rows always use deterministic scheduled Friday alignment. They never inherit the live first-observed ledger.

## Macro decomposition

The adapter groups existing macro factors into:

- **Liquidity plumbing:** net liquidity, reserves, repo spread, and SLR/balance-sheet load.
- **Market transmission:** real yields, credit, dollar, and VIX.
- **Supply pressure:** Treasury issuance calendar pressure.

Daily sources older than five days and weekly sources older than twelve days are excluded from available weight. Stale and missing factor names are written to the macro context output.

## Price execution states

- **Confirmed:** post-release move and 20-day trend align with structural direction.
- **Waiting:** movement remains inside the configured band.
- **Contradicted:** release response or 20-day trend opposes the structural side.
- **Invalidated:** the adverse move breaches the market-specific invalidation threshold.
- **Unavailable:** required price history is missing.

## Main outputs

- `model_output/cot_direction_latest.json`
- `model_output/cot_direction_latest.csv`
- `model_output/cot_direction_history.csv`
- `model_output/cot_direction_validation_summary.csv`
- `model_output/macro_direction_context.json`
- `model_output/cftc_release_observations.json`
- `model_output/directional_refresh_status.json`
- `directional_cot_report.html`
- injected decision summary inside `interactive_cot_dashboard.html`

## Run

Recommended full workflow:

```powershell
py refresh_directional_cot_system.py --strict-refresh --open
```

Day-to-day Windows launchers:

```text
start_directional_cot_report.cmd
start_cot_dashboard.cmd
refresh_cot_dashboard.cmd
```

All three launch paths route through the integrated directional workflow.

## Validation

The refresh command compiles the runtime through import/execution and runs:

```powershell
py -m unittest \
  tests.test_cot_direction_model \
  tests.test_release_and_macro \
  tests.test_directional_system \
  tests.test_price_execution_adapter \
  tests.test_deterministic_history -v
```

The historical summary is explicitly labelled exploratory and release-aligned. It is not described as sealed out-of-sample evidence.

## Important limitations

- Historical exact CFTC publication timestamps are not available in the repository.
- Nonreportables are a small-trader/retail proxy, not verified pure retail.
- Price execution uses daily cash-index closes. It is not futures VWAP or intraday order flow.
- The model is designed for S&P 500 and Nasdaq-100. Do not transfer its directional sign to commodities or FX without separate calibration.
- The repository's GitHub Actions runner failed before producing steps or logs. Automated local tests remain mandatory in the integrated refresh until repository Actions infrastructure is repaired.
