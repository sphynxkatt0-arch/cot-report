# Directional COT and Macro Liquidity Dashboard

The project has two connected surfaces:

1. **Directional COT Report** — the governed decision layer for S&P 500 and Nasdaq-100.
2. **COT Macro Monitor** — the advanced workbench for positioning, liquidity plumbing, Treasury cash flows, auction absorption, rates, credit, volatility, and historical evidence.

The dashboard is decision-first. Research-only panels remain available but are hidden by default so parallel scores cannot compete with the governed output.

## Start the system

From the `analysis` directory:

```text
start_directional_cot_report.cmd
start_cot_dashboard.cmd
```

Manual validation and refresh:

```powershell
py refresh_directional_cot_system.py --skip-public-refresh --open
py refresh_directional_cot_system.py --strict-refresh --open
```

The strict run stops if the core public-data refresh fails. The cached run may continue only with validated local inputs and explicit freshness warnings.

Run status:

```text
model_output\directional_refresh_status.json
```

## Governed decision hierarchy

1. **Legacy Non-commercials set structural direction.**
2. **TFF categories modify conviction but cannot create or reverse direction.**
3. **Asset Manager crowding changes size only.**
4. **Fresh macro conditions change size or block execution.**
5. **Price action controls execution.**
6. **Expanded liquidity plumbing can block exposure only when severe stress is independently corroborated.**
7. **Historical evidence caps exposure.**
8. **CFTC release completeness has final actionability priority.**
9. **Weekly participant changes explain movement without casting another vote.**

Commercials are not counted as independent confirmation. Dealer/Intermediary is treated as structural inventory rather than a directional player. Nonreportables are labelled as a **small-trader/retail proxy**, not verified retail.

## Dashboard reading order

1. **Directional COT Decision**
2. **Market Playbook**
3. **Macro Liquidity Control Room**
4. **Daily Treasury Cash Flow**
5. **Treasury Auction Demand Quality**
6. **Positioning Changes and Evidence Quality**
7. **Research Workbench**

A sticky navigator links to each governed section. Research panels are hidden by default and restored with **Show research**.

## Macro liquidity architecture

Macro liquidity is separated into distinct channels rather than compressed into one score.

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
- DVP overnight/open transaction volume
- primary-dealer Treasury positions
- primary-dealer Treasury repo financing
- primary-dealer Treasury settlement fails
- money-market-fund assets
- MMF Treasury holdings
- MMF repo holdings

Configured OFR mnemonics are verified by a usable series response. Metadata search is the fallback. The original 30+ day term-repo configuration was corrected to overnight/open series.

### Forward Treasury cash path

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

### Treasury supply absorption

Official Treasury auction results provide:

- bid-to-cover ratio
- primary-dealer accepted amount
- indirect-bidder accepted amount
- direct-bidder accepted amount
- total accepted amount
- security type and term

Each coupon auction is compared with prior auctions of the same tenor. Lower bid-to-cover, higher dealer share, and lower indirect share reduce relative absorption quality. The system does not claim an auction tail because it does not contain a reviewed when-issued benchmark.

## Conservative liquidity-plumbing guard

The expanded indicators remain descriptive unless multiple fresh, independent sources confirm severe stress.

Current requirements:

```text
overall expanded-source coverage >= 60%
at least two reliable eligible pillars
at least two reliable pillar scores <= 25
```

Eligible pillars:

```text
funding_microstructure
dealer_absorption
fiscal_cash_flow
auction_absorption
```

Freshness rules:

- Funding requires at least two independent fresh repo-rate venues. DVP volume cannot substitute for a second rate venue.
- Dealer absorption requires at least two fresh dealer sources.
- Fiscal cash flow requires both daily TGA and daily deposits/withdrawals to be fresh.
- Auction absorption requires fresh official auction data.

When active:

```text
final action: Wait — Liquidity Plumbing Stress
exposure:     0.00x
COT direction: unchanged
```

One severe pillar, stale data, or low overall coverage cannot activate the guard. The CFTC release-state guard retains final priority.

## Publication timing

COT observations are Tuesday positions normally released Friday at 15:30 New York time. The actionable price base begins at the first valid close on or after the effective release date, never Tuesday.

Release states:

```text
current
awaiting_release
delayed
catch_up_delayed
```

Delayed or incomplete reports cannot create new exposure. A local first-seen timestamp is not represented as an official CFTC timestamp.

## Price execution

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

Diagnostics include Newey–West HAC statistics, directional edge, chronological stability, drift-adjusted accuracy, adverse movement, path utility, and model agreement.

Evidence grades:

```text
Supported
Tentative
Weak/Mixed
Contradictory
Not estimable
```

Historical evidence can cap exposure but cannot reverse direction or replace a higher-priority plumbing or release block.

## Generated outputs

```text
model_output\cot_direction_latest.json
model_output\cot_direction_latest.csv
model_output\cot_direction_history.csv
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
- macro freshness and override priority
- independent repo-venue requirements
- Daily Treasury cash-flow sign convention
- same-tenor auction comparison
- multi-pillar plumbing-guard activation
- weekly positioning-change completeness
- JSON and CSV schemas
- idempotent dashboard/report injection
- focused default UX and section navigation

GitHub Actions currently fails before producing any steps or logs. Repository issue #4 tracks that platform-level problem. Until it is repaired, the two local refresh commands remain the required end-to-end validation gate.

## Configuration and methodology

```text
config\cot_direction_model_v1.json
config\macro_liquidity_sources_v1.json
config\macro_liquidity_guard_v1.json
docs\cot_direction_model_v1.md
docs\macro_liquidity_control_room_v12.md
docs\macro_liquidity_guard_v1.md
docs\directional_cot_validation_runbook.md
```

Current versions:

```text
cot-direction-v1.1
macro-liquidity-control-room-v1.2
macro-liquidity-guard-v1.0
```

## Limitations

- Exact historical CFTC publication timestamps are unavailable; historical audit uses scheduled Friday availability.
- Daily Treasury data is not intraday.
- Modified-cash Treasury flows are not direct equity-purchase estimates.
- OFR rate series are informational and not contract reference rates.
- Dealer data is aggregate rather than dealer-specific.
- MMF data is lower frequency than repo data.
- Cross-currency basis, Treasury market depth, SFOS reserve-comfort estimates, and bank-level regulatory capacity remain future source modules.
- Model weights and guard thresholds are transparent conservative starting values, not sealed out-of-sample optimization.
