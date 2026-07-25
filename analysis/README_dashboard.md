# Interactive COT And Macro Liquidity Dashboard

This dashboard combines COT positioning with macro-liquidity, funding-stress, rates, credit, and event-calendar inputs. The COT report itself does not contain SOFR, IORB, EFFR, reverse repo, Treasury cash, Fed balance sheet, bank H.8 data, Treasury auctions, agency issuance calendars, real yields, credit spreads, or equity forward returns. Those are separate public data feeds cached under `..\data`.

## Run

From `A:\work\trading\cot report\analysis`:

```powershell
py serve_interactive_cot_dashboard.py --open
```

For day-to-day use, double-click:

```text
start_cot_dashboard.cmd
```

That refreshes the public data feeds, rebuilds both current TFF and legacy COT outputs, rebuilds the dashboard, and opens localhost. To run only the refresh without opening the dashboard, double-click:

```text
refresh_cot_dashboard.cmd
```

Useful modes:

```powershell
py serve_interactive_cot_dashboard.py --refresh-only
py serve_interactive_cot_dashboard.py --skip-refresh --open
py build_interactive_cot_dashboard.py
```

`start_cot_dashboard.cmd` runs a full refresh first (`--refresh-only`), then opens the localhost dashboard. This keeps daily price, VIX, CNN Fear & Greed, macro, TFF COT, legacy COT, position-effect, and regime-backtest data current. The refresh validates every COT-derived output against the latest official CFTC source date and stops if a dependent output is behind. Optional non-COT feed failures reuse the existing local cache; a full rebuild failure opens the existing dashboard file and prints a warning.

The Signal Regime Panel and Regime Backtest Evidence follow the active dataset selector. TFF Detailed uses the asset-manager, dealer, leveraged-fund, other-reportable, and non-reportable model. Legacy uses non-commercial, commercial, and non-reportable classifications; total reportable is displayed elsewhere but excluded from scoring because it aggregates the underlying reportable categories. Both backtests use expanding percentile ranks and returns beginning at the first market close on or after Friday publication.

The **Cross-Market Player Bias** panel aligns the same report date across S&P 500, NASDAQ-100, and VIX for the selected classification. It reports futures-equivalent notional using the contract units printed by CFTC in the selected rows:

- S&P 500 Consolidated: index x $50.
- NASDAQ-100 Consolidated: index x $20.
- VIX Futures: index x $1,000.

Equity notional is S&P 500 plus NASDAQ-100. VIX is counted as an inverse risk leg in the total-risk read: buying VIX subtracts from risk appetite, while selling VIX adds to it. Raw VIX notional is still shown separately because a dollar of VIX notional is not a clean dollar-for-dollar equity beta. The short-term bias score standardizes each player's one-week and four-week net-position changes against up to 156 prior reports, averages S&P and NQ with inverse VIX direction, and weights one-week flow 60% and four-week flow 40%. Treat it as a flow classifier, not a portfolio delta or VaR estimate.

The player table separates current net exposure from the latest one-week net change for both SP and NQ. The latest net change is dated from the previous common COT report date to the newest common COT report date across S&P 500, NASDAQ-100, and VIX. A market leg is Bullish above +0.10% of open interest, Bearish below -0.10%, and Neutral inside that band. The combined SP+NQ direction uses summed futures-equivalent notional and is Mixed when opposing legs leave less than 15% of gross flow after netting. The total-risk direction uses SP+NQ minus VIX flow, so VIX buying is bearish and VIX selling is bullish; it is also Mixed when the signed total is less than 15% of gross absolute flow. The table intentionally uses separate columns for latest total-risk delta and long-term total-risk trend so one-week flow is not confused with standing net exposure or 13-week/26-week drift. The comparison chart plots latest one-week total-risk delta against the 13-week total-risk net change, while the long-term total-risk chart plots historical net notional using the same SP+NQ-VIX definition. Direction is evaluated per player; adding all players together is not a market signal because futures longs and shorts offset by construction.

Legacy and TFF are parallel classifications, not interchangeable mappings. Legacy Noncommercial is not the same player as TFF Asset Managers or Leveraged Funds. The backtest comparison therefore evaluates each taxonomy separately.

Backtest evidence now separates headline returns from statistical support:

- `Score r` measures association between the regime score and the forward return.
- `HAC p` uses Newey-West errors with lags tied to the forecast horizon, reducing false confidence from overlapping weekly forecasts.
- `Risk-On - Caution` is the average return spread between the two directional buckets.
- `Drift-adjusted hit` tests whether the score predicted returns above or below the prior expanding average, rather than rewarding ordinary positive equity drift.
- Evidence grades require at least 20 observations in the smaller directional bucket. `Supported` requires a positive edge with HAC p <= 0.05; `Tentative` uses p <= 0.10.

The percentile calculation is walk-forward. The rule thresholds and weights are fixed research choices, so the result is not a sealed out-of-sample model-selection test.

## Setup

```powershell
py -m pip install -r requirements.txt
```

The dashboard uses Plotly from the HTML bundle/CDN and does not require a separate JavaScript build step.

For FRED series, the refresher uses the official St. Louis Fed API when a key is available. Put the key in either:

```text
analysis\config\fred_api_key.txt
```

or the `FRED_API_KEY` environment variable. The key is not printed in the command window.

## Automatic Updates

`serve_interactive_cot_dashboard.py` refreshes the public CSV feeds, reruns the COT builders and dependent backtests, validates their report dates against the official CFTC feeds, rebuilds `interactive_cot_dashboard.html`, and then serves it. A non-COT feed failure falls back to the existing cached file when one exists, so one stale optional source does not block the full dashboard.

For Windows Task Scheduler, create a task that runs:

```powershell
py A:\work\trading\cot report\analysis\serve_interactive_cot_dashboard.py --refresh-only
```

Set the working directory to:

```text
A:\work\trading\cot report\analysis
```

## Added Macro-Liquidity Inputs

- Core liquidity: Fed balance sheet, TGA, reverse repo, bank reserves, net liquidity.
- Price overlays: Yahoo `^GSPC`, `^NDX`, and `^VIX` for daily market top-ups, with FRED-compatible local CSVs preserved for downstream analysis.
- Funding stress: SOFR, EFFR, IORB, SOFR-IORB, EFFR-IORB.
- Bank balance-sheet/SLR proxies: bank Treasury and agency securities, total bank assets, reserves as a share of bank assets.
- Rates and credit: 10Y real yield, optional 5Y real yield, optional 10Y/2Y/3M/30Y nominal yields, high-yield OAS, investment-grade OAS.
- Supply calendars: Treasury issuance, Fannie/Freddie scheduled agency funding, Fannie/Freddie mortgage cash-flow dates.
- Retirement-flow proxy: FRTIB/TSP monthly allocation data where available.

## Regime Overview Versus Liquidity Detail

The **Composite Market Regime Overview** is the decision layer. It combines all seven score blocks (positioning, liquidity, funding, rates, credit, dollar, and volatility) into the full risk-regime read.

The **Liquidity Plumbing Detail** is a diagnostic subsystem. It displays the underlying Fed balance sheet, TGA, reverse repo, reserves, bank balance-sheet, and funding inputs. It explains the liquidity contribution to the composite regime but is not a second independent regime call.

The dashboard summarizes:

- Macro regime score on a -2 to +2 scale.
- Confidence score based on source availability, freshness, and alert conflict.
- Component scores for positioning, liquidity, funding stress, rates, credit, dollar, and volatility.
- Biggest positive and negative drivers.
- Forward path expectations for 5D, 20D, and 60D horizons.
- Historical analog rows from similar past macro setups.
- Data freshness by source.

Treat the score as a structured risk backdrop, not as a standalone trading signal. COT positioning, price trend, volatility regime, and event risk still matter.

## Current Data Limitations

- The SLR view is a proxy. It uses public Fed H.8 balance-sheet categories, not bank-level regulatory SLR filings.
- Treasury and agency calendars identify scheduled liquidity events; they do not perfectly model settlement cash drain, dealer balance-sheet usage, or demand at auction.
- FRED can time out from this machine. S&P 500 and Nasdaq-100 prices use Yahoo chart data as a supplement/fallback. Treasury nominal and real yield series use Treasury.gov XML as the primary fallback, including the 30Y nominal yield.
- Intraday repo data, dealer inventory, cross-currency basis, CDX, options gamma, Treasury market depth, and bank-level regulatory constraints are not included unless separate data sources are added.
