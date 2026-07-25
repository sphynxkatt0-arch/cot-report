# Macro Liquidity Control Room v1.2

## Purpose

The control room answers four separate questions:

1. **Current state:** Is system liquidity supportive, neutral, or defensive?
2. **Funding capacity:** Can dealers and money markets fund Treasury collateral without visible stress?
3. **Forward cash path:** Are Treasury cash operations injecting money into, or withdrawing money from, the private sector?
4. **Supply absorption:** Are coupon auctions clearing with normal demand, or are primary dealers absorbing unusually large shares?

The control room is subordinate to the governed COT hierarchy. Its indicators cannot create or reverse the Legacy Non-commercial structural direction.

## Dashboard order

The integrated dashboard is intentionally ordered:

1. Directional COT decision
2. Market playbook
3. Macro liquidity control room
4. Daily Treasury cash path
5. Treasury auction demand quality
6. Weekly positioning changes and evidence quality
7. Research-only TFF, Legacy, macro, and backtest surfaces

A sticky navigator links to each governed panel. Research-only surfaces are hidden by default and restored with **Show research**.

## Existing macro evidence

The existing dashboard remains the source for:

- Federal Reserve total assets;
- Treasury General Account;
- overnight reverse repo;
- bank reserves;
- bank Treasury and agency holdings;
- bank total assets / SLR proxy;
- SOFR, EFFR, and IORB;
- real and nominal yields;
- high-yield and investment-grade spreads;
- broad dollar index;
- VIX;
- Treasury auction and settlement calendar;
- TSP retirement-allocation context.

These inputs are separated into liquidity plumbing, market transmission, and supply pressure rather than being described as one undifferentiated liquidity measure.

## New official sources

### Office of Financial Research Short-term Funding Monitor

The OFR public API supplies:

- DVP overnight/open repo rate;
- GCF overnight/open repo rate;
- tri-party overnight/open repo rate;
- DVP overnight/open transaction volume;
- primary-dealer Treasury positions;
- primary-dealer Treasury repo financing;
- primary-dealer Treasury settlement fails;
- money-market-fund assets;
- MMF Treasury holdings;
- MMF repo holdings.

Configured mnemonics are accepted only after a usable series response. Metadata search is the fallback. The selected mnemonic and resolution method are written to the source-status output.

The original 30+ day term-repo configuration was corrected to official overnight/open series. Missing or stale OFR data is never replaced with a neutral score.

### U.S. Treasury Daily Treasury Statement

The Treasury Fiscal Data API supplies:

- daily operating cash / TGA balance;
- deposits into operating cash;
- withdrawals from operating cash;
- tax deposits;
- largest daily cash-flow categories.

Sign convention:

```text
Treasury withdrawal = positive private-sector cash effect
Treasury deposit     = negative private-sector cash effect
Rising TGA           = private-sector liquidity drain
Falling TGA          = private-sector liquidity injection
```

The dashboard reports five-day and twenty-day private cash effect, five-day TGA change, tax deposits, total deposits, total withdrawals, and the largest cash-flow categories.

### Treasury Securities Auctions Data

The Fiscal Data auction endpoint supplies:

- bid-to-cover ratio;
- primary-dealer accepted amount;
- indirect-bidder accepted amount;
- direct-bidder accepted amount;
- total accepted amount;
- security type and original term.

Auction quality is evaluated relative to prior auctions of the **same tenor**. Lower bid-to-cover, higher dealer share, and lower indirect share reduce the relative absorption score. The system does not claim an auction tail because it does not contain a reviewed when-issued benchmark.

## Pillars

### Macro risk regime

Broad transmission backdrop from rates, credit, dollar, volatility, and the existing macro score.

### Net liquidity impulse

Four-week change in:

```text
Fed assets - TGA - overnight reverse repo
```

This is a balance-sheet approximation, not a complete measure of market liquidity.

### Funding microstructure

Uses overnight/open repo rates and DVP volume. The diagnostic responds to:

- widening rate dispersion across DVP, GCF, and tri-party markets;
- large short-term repo-rate changes;
- weak DVP transaction volume.

### Dealer absorption

Uses Treasury dealer positions, repo financing, and settlement fails. High inventory, financing, or fails relative to history can indicate weaker absorption or balance-sheet strain.

### Money-market allocation

Shows whether cash is accumulating in MMFs and whether holdings are directed toward Treasury securities or repo. This remains descriptive context until separately validated against equity outcomes.

### Daily fiscal cash flow

Combines Daily Treasury Statement flows with the daily TGA path. A supportive reading means withdrawals injected cash and/or the TGA fell. A defensive reading means deposits, tax receipts, or TGA rebuilding drained private cash.

### Treasury auction absorption

Uses recent coupon auctions and same-tenor history. The panel displays:

- latest bid-to-cover;
- bid-to-cover change from prior same-tenor average;
- indirect-bidder share;
- primary-dealer share;
- relative quality score.

## Conservative plumbing-stress guard

The new indicators are descriptive by default. A separate conservative guard can block new exposure only when severe stress is independently corroborated.

Current activation requirements:

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

Pillar freshness requirements are stricter than overall coverage:

- Funding requires at least two independent fresh repo-rate venues. DVP volume cannot substitute for a second rate venue.
- Dealer absorption requires at least two fresh dealer sources.
- Fiscal cash flow requires both Daily Treasury operating cash and deposits/withdrawals to be fresh.
- Auction absorption requires fresh official auction data.

When active:

```text
final action: Wait — Liquidity Plumbing Stress
exposure:     0.00x
COT direction: unchanged
```

One severe pillar, stale data, or low total source coverage cannot activate the guard. The CFTC release-state guard retains final priority.

Detailed rules:

```text
docs/macro_liquidity_guard_v1.md
config/macro_liquidity_guard_v1.json
```

## Source and freshness governance

Generated contracts:

```text
model_output/macro_liquidity_expansion.json
model_output/macro_liquidity_source_status.csv
model_output/treasury_cash_source_status.csv
```

Every source is marked:

```text
fresh
stale
unavailable
```

The payload records:

- selected mnemonic or API endpoint;
- resolution method;
- latest date and value;
- short- and medium-window change;
- latest z-score where estimable;
- age in days;
- error detail when unavailable.

Missing data lowers coverage. It is never converted into a neutral score.

## Governance hierarchy

The live actionability sequence is:

1. Existing macro availability and severe-risk override
2. Expanded multi-pillar plumbing-stress guard
3. Historical-evidence exposure cap
4. CFTC release-state guard

The expanded guard may block exposure but cannot create direction, reverse direction, or increase size. Historical evidence remains recorded but cannot replace a higher-priority plumbing-stress action. Delayed or incomplete CFTC data has final priority.

## Refresh

From the `analysis` directory:

```powershell
py refresh_directional_cot_system.py --skip-public-refresh
py refresh_directional_cot_system.py --strict-refresh --open
```

The refresh discovers all tests, builds OFR and Treasury source contracts, reconstructs the governed COT decision, applies actionability guards, injects the control-room UX, and validates generated JSON, CSV, and HTML contracts.

## Limitations

- Daily Treasury Statement data is published after the relevant business day and is not intraday liquidity information.
- Modified-cash Treasury flows are not direct estimates of equity purchases.
- OFR repo rates are informational and should not be treated as contract reference rates.
- Dealer data is aggregate rather than dealer-specific.
- MMF data is lower frequency than repo data.
- Auction results do not include a reviewed when-issued benchmark, so the system does not calculate an auction tail.
- Cross-currency basis, Treasury market depth, SFOS reserve-comfort estimates, and bank-level regulatory capacity remain future source modules.
