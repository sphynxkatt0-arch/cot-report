# Directional COT and Macro Liquidity Dashboard

The project has two connected surfaces:

1. **Directional COT Report** — the governed decision layer for S&P 500 and Nasdaq-100.
2. **COT Macro Monitor** — the advanced workbench for positioning, liquidity plumbing, funding stress, Treasury cash flows, auction absorption, rates, credit, dollar, volatility, calendars, and historical evidence.

The dashboard is decision-first. Research-only scores remain available but are hidden by default so they cannot compete with the governed output.

## Start the system

From the `analysis` directory, double-click:

```text
start_directional_cot_report.cmd
start_cot_dashboard.cmd
```

Both launchers use the same refresh pipeline. Manual commands:

```powershell
py refresh_directional_cot_system.py --skip-public-refresh --open
py refresh_directional_cot_system.py --strict-refresh --open
```

The strict command stops when the core public-data refresh fails. The cached command may continue only with validated local inputs and explicit freshness warnings.

Run status:

```text
model_output\directional_refresh_status.json
```

## Governed decision hierarchy

1. **Legacy Non-commercials set structural direction.**
2. **TFF categories modify conviction but cannot create or reverse direction.**
3. **Asset Manager crowding changes position size only.**
4. **Fresh macro conditions change size or block execution.**
5. **Price action controls execution.**
6. **Historical evidence caps exposure.**
7. **CFTC release completeness has final actionability priority.**
8. **Weekly participant changes explain movement without casting another vote.**

Commercials are not counted as independent confirmation because they are mechanically related to the other Legacy categories. Dealer/Intermediary is treated as structural inventory rather than a directional player. Nonreportables are labelled as a **small-trader/retail proxy**, not verified retail.

## Dashboard reading order

The integrated dashboard is ordered:

1. **Directional COT Decision**
2. **Market Playbook**
3. **Macro Liquidity Control Room**
4. **Daily Treasury Cash Flow**
5. **Treasury Auction Demand Quality**
6. **Positioning Changes and Evidence Quality**
7. **Research Workbench**

A sticky navigator links to each governed section. Research panels are hidden by default and restored with **Show research**.

## Macro liquidity architecture

Macro liquidity is not one score. The control room separates:

### Current state

- Federal Reserve total assets
- Treasury General Account
- overnight reverse repo
- bank reserves
- SOFR, EFFR, and IORB
- real yields
- credit spreads
- dollar
- VIX

### Funding capacity

Official Office of Financial Research Short-term Funding Monitor inputs:

- DVP overnight/open repo rate
- GCF overnight/open repo rate
- tri-party overnight/open repo rate
- DVP transaction volume
- primary-dealer Treasury positions
- primary-dealer Treasury repo financing
- primary-dealer Treasury settlement fails
- money-market-fund assets
- MMF Treasury holdings
- MMF repo holdings

Configured OFR mnemonics are verified by a usable data response. Metadata search is the fallback. The original 30+ day term-repo configuration has been corrected to overnight/open series.

### Forward cash path

Official Daily Treasury Statement inputs:

- daily TGA / operating cash
- deposits into operating cash
- withdrawals from operating cash
- tax deposits
- largest cash-flow categories

Sign convention:

```text
Treasury withdrawal = positive private-sector cash effect
Treasury deposit     = negative private-sector cash effect
Rising TGA           = private-sector liquidity drain
Falling TGA          = private-sector liquidity injection
```

The dashboard displays five-day and twenty-day private cash effect, five-day TGA change, taxes, total deposits, total withdrawals, and category detail.

### Supply absorption

Official Treasury auction results provide:

- bid-to-cover ratio
- primary-dealer accepted amount
- indirect-bidder accepted amount
- direct-bidder accepted amount
- total accepted amount
- security type and term

Each coupon auction is compared with prior auctions of the same tenor. Lower bid-to-cover, higher dealer share, and lower indirect share reduce relative absorption quality. The system does not claim an auction tail because it does not have a reviewed when-issued benchmark.

## Publication timing

COT observations are Tuesday positions normally released Friday at 15:30 New York time. The actionable price base begins at the first valid close on or after the effective release date, never Tuesday.

Release states:

```text
current
awaiting_release
delayed
catch_up_delayed
```

A delayed or incomplete report cannot create new exposure. A local first-seen timestamp is not represented as an official CFTC timestamp.

## Price execution

The execution layer uses cash-index closes:

- **Confirmed:** post-release response and 20-day trend align with the structural side.
- **Waiting:** movement remains inside the configured band.
- **Contradicted:** price or trend opposes the structural side.
- **Invalidated:** the adverse move exceeds the configured market threshold.
- **Unavailable:** required price history is missing.

The post-report anchor is an anchored mean, not futures VWAP, because the cash-index series does not contain futures volume.

## Historical governance

Five models are evaluated on identical Friday-aligned dates:

1. old TFF regime
2. old Legacy regime
3. new Non-commercial structural model
4. new structural plus TFF tactical model
5. new full release-time decision model

Outputs include:

- Pearson and Spearman association
- Newey–West HAC slope and p-value
- directional edge and HAC p-value
- three-subperiod sign stability
- drift-adjusted accuracy
- directional coverage and hit rate
- average and worst adverse movement
- path utility
- pairwise directional agreement

Evidence grades:

```text
Supported
Tentative
Weak/Mixed
Contradictory
Not estimable
```

Historical evidence can cap exposure but cannot reverse direction.

## Generated outputs

```text
model_output\cot_direction_latest.json
model_output\cot_direction_latest.csv
model_output\cot_direction_history.csv
model_output\cot_direction_validation_summary.csv
model_output\directional_model_comparison_summary.csv
model_output\cot_position_changes_latest.csv
model_output\macro_direction_context.json
model_output\macro_liquidity_expansion.json
model_output\macro_liquidity_source_status.csv
model_output\treasury_cash_source_status.csv
model_output\cftc_release_observations.json
model_output\directional_refresh_status.json
directional_cot_report.html
interactive_cot_dashboard.html
```

Every new macro source is classified:

```text
fresh
stale
unavailable
```

Missing data lowers coverage. It is never replaced with a neutral score.

## Validation

Every test module is discovered automatically:

```powershell
py -m unittest discover -s tests -p "test_*.py" -v
```

The integrated refresh additionally validates:

- raw CFTC contracts and dates
- Friday release alignment
- COT structural-sign invariants
- macro freshness and overrides
- Daily Treasury cash-flow sign convention
- same-tenor auction comparison
- weekly positioning-change completeness
- JSON and CSV schemas
- idempotent dashboard/report injection
- focused default UX and section navigation

GitHub Actions currently fails before producing any steps or logs. Repository issue #4 tracks that platform-level problem. Until it is repaired, the two local refresh commands remain the required end-to-end validation gate.

## Configuration and methodology

```text
config\cot_direction_model_v1.json
config\macro_liquidity_sources_v1.json
docs\cot_direction_model_v1.md
docs\macro_liquidity_control_room_v12.md
docs\directional_cot_validation_runbook.md
```

Current versions:

```text
cot-direction-v1.1
macro-liquidity-control-room-v1.2
```

## Limitations

- Exact historical CFTC publication timestamps are unavailable; historical audit uses scheduled Friday availability.
- Daily Treasury data is not intraday.
- Modified-cash Treasury flows are not direct equity-purchase estimates.
- OFR rate series are informational and not contract reference rates.
- Dealer data is aggregate rather than dealer-specific.
- MMF data is lower frequency than repo data.
- Cross-currency basis, Treasury market depth, SFOS reserve-comfort estimates, and bank-level regulatory capacity require future source modules.
- Model weights are transparent starting values, not sealed out-of-sample optimization.
