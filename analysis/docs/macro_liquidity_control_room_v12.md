# Macro Liquidity Control Room v1.2

## Purpose

The control room answers four separate questions:

1. **Current state:** Is system liquidity presently supportive, neutral, or defensive?
2. **Funding capacity:** Can dealers and money markets fund collateral without visible stress?
3. **Forward cash path:** Are Treasury cash operations injecting money into, or withdrawing money from, the private sector?
4. **Supply absorption:** Are coupon auctions clearing with normal demand, or are primary dealers absorbing unusually large shares?

It is a risk and sizing layer. It does **not** create or reverse the Legacy Non-commercial COT structural direction.

## Dashboard order

The integrated dashboard is intentionally ordered:

1. Directional COT decision
2. Market playbook
3. Macro liquidity control room
4. Daily Treasury cash path
5. Treasury auction demand quality
6. Weekly positioning changes and evidence quality
7. Research-only TFF, Legacy, macro, and backtest surfaces

A sticky section navigator links to each governed panel. Research-only surfaces are hidden by default and can be restored with **Show research**.

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

These are separated into liquidity plumbing, market transmission, and supply pressure rather than being described as one undifferentiated liquidity measure.

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

Configured mnemonics are accepted only after a usable series response. If a configured series is unavailable, metadata search is attempted and the selected mnemonic is recorded in `macro_liquidity_source_status.csv`.

The original 30+ day term-repo configuration was corrected to official overnight/open series. The control room never substitutes a neutral score for a missing or stale source.

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

The dashboard reports the five-day and twenty-day private cash effect, five-day TGA change, tax deposits, total deposits, total withdrawals, and the largest cash-flow categories.

### Treasury Securities Auctions Data

The Fiscal Data auction endpoint supplies:

- bid-to-cover ratio;
- primary-dealer accepted amount;
- indirect-bidder accepted amount;
- direct-bidder accepted amount;
- total accepted amount;
- security type and original term.

Auction quality is evaluated relative to prior auctions of the **same tenor**. Lower bid-to-cover, higher dealer share, and lower indirect share reduce the score. This avoids applying one universal threshold to bills, notes, bonds, and TIPS.

## Pillars

### Macro risk regime

Broad transmission backdrop from rates, credit, dollar, volatility, and the existing liquidity score.

### Net liquidity impulse

Four-week change in:

```text
Fed assets - TGA - overnight reverse repo
```

This is a useful balance-sheet approximation, not a complete measure of market liquidity.

### Funding microstructure

Uses overnight/open repo rates and DVP volume. The diagnostic penalizes:

- widening rate dispersion across DVP, GCF, and tri-party markets;
- large short-term repo-rate changes;
- unusually weak DVP transaction volume.

### Dealer absorption

Uses Treasury dealer positions, repo financing, and settlement fails. High inventory, financing, or fails relative to history can indicate weaker absorption or balance-sheet strain.

### Money-market allocation

Shows whether cash is accumulating in MMFs and whether holdings are directed toward Treasury securities or repo. This remains context until its historical relationship with equities is separately validated.

### Daily fiscal cash flow

Combines the Daily Treasury Statement flow with the daily TGA path. A supportive reading means withdrawals injected cash and/or the TGA fell. A defensive reading means deposits, tax receipts, or TGA rebuilding drained private cash.

### Treasury auction absorption

Uses recent coupon auctions and their same-tenor history. The panel displays:

- latest bid-to-cover;
- bid-to-cover change from the prior same-tenor average;
- indirect-bidder share;
- primary-dealer share;
- relative quality score.

Auction quality is descriptive supply-absorption evidence. It cannot cast an independent equity-direction vote.

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

Coverage is displayed in the dashboard. Missing data lowers coverage; it is not converted to a neutral 50.

## Model governance

The extension is descriptive. It may support future exposure caps or hard-risk guards only after release-aligned historical validation. In v1.2:

- COT direction remains authoritative;
- the existing governed macro layer may reduce size or block execution;
- OFR, Daily Treasury, and auction diagnostics explain state and forward pressure;
- none of the new diagnostics creates or reverses direction.

## Refresh

From the `analysis` directory:

```powershell
py refresh_directional_cot_system.py --skip-public-refresh
py refresh_directional_cot_system.py --strict-refresh --open
```

The refresh runs test discovery, builds the OFR and Treasury source contracts, reconstructs the governed COT decision, injects the control-room UX, and validates all generated JSON, CSV, and HTML contracts.

## Limitations

- Daily Treasury Statement data is published after the relevant business day and is not intraday liquidity information.
- Deposits and withdrawals are modified-cash accounting flows; they are not a direct estimate of equity purchases.
- OFR repo rate series are informational and should not be treated as contract reference rates.
- Dealer aggregates do not reveal individual dealer constraints.
- MMF data is lower frequency than repo data.
- Auction results do not include a reliable when-issued yield benchmark, so the system does not claim to calculate an auction tail.
- Cross-currency basis, Treasury market depth, Senior Financial Officer Survey reserve-comfort estimates, and bank-level regulatory capacity remain future source modules.
