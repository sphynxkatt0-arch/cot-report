# COT Regime Score Backtest Report

Generated: 2026-08-29T00:47:39Z

This report is regenerated from the same current Legacy COT inputs used by the dashboard. COT observations are Tuesday report dates; signals start at the first available close on or after Friday publication.

## Data Cutoffs

| Market | Latest COT report | Latest signal close | Latest price | Scored rows |
| --- | --- | --- | --- | --- |
| S&P 500 | 2026-08-25 | 2026-08-28 | 2026-08-28 | 431 |
| NASDAQ-100 | 2026-08-25 | 2026-08-28 | 2026-08-28 | 453 |
| VIX Futures | 2026-08-25 | 2026-08-28 | 2026-08-28 | 453 |
| Russell 2000 | 2026-08-25 | 2026-08-28 | 2026-08-28 | 135 |
| Dow Jones | 2026-08-25 | 2026-08-28 | 2026-08-28 | 453 |
| Gold | 2026-08-25 | 2026-08-28 | 2026-08-28 | 453 |

## Current Tradable COT Signals

| Market | Report date | Signal date | Score | Bucket | Active triggers |
| --- | --- | --- | --- | --- | --- |
| S&P 500 | 2026-08-25 | 2026-08-28 | -1.00 | Mixed | nonreportable 97.2% -1.00 Non-reportable contrarian (retail long) |
| NASDAQ-100 | 2026-08-25 | 2026-08-28 | -1.00 | Mixed | nonreportable 97.8% -1.00 Non-reportable contrarian (retail long) |
| VIX Futures | 2026-08-25 | 2026-08-28 | +0.00 | Mixed | No active extreme trigger |
| Russell 2000 | 2026-08-25 | 2026-08-28 | +0.00 | Mixed | No active extreme trigger |
| Dow Jones | 2026-08-25 | 2026-08-28 | +0.00 | Mixed | No active extreme trigger |
| Gold | 2026-08-25 | 2026-08-28 | +0.00 | Mixed | No active extreme trigger |

## Forward Returns by Regime Bucket

| Market | Horizon | Bucket | N | Average return | Hit rate | Average drawdown |
| --- | --- | --- | --- | --- | --- | --- |
| S&P 500 | 4w | Mixed | 313 | +1.08% | 69.6% | -2.78% |
| S&P 500 | 4w | Caution | 21 | -0.35% | 61.9% | -3.66% |
| S&P 500 | 4w | Risk-On | 93 | +1.61% | 68.8% | -2.65% |
| S&P 500 | 13w | Mixed | 304 | +4.13% | 77.0% | -5.27% |
| S&P 500 | 13w | Caution | 21 | -3.58% | 23.8% | -9.41% |
| S&P 500 | 13w | Risk-On | 92 | +3.27% | 70.7% | -4.62% |
| S&P 500 | 26w | Mixed | 291 | +7.60% | 76.3% | -7.84% |
| S&P 500 | 26w | Caution | 21 | -3.71% | 28.6% | -15.81% |
| S&P 500 | 26w | Risk-On | 92 | +8.07% | 84.8% | -5.69% |
| NASDAQ-100 | 4w | Mixed | 398 | +1.51% | 64.1% | -3.58% |
| NASDAQ-100 | 4w | Risk-On | 51 | +2.35% | 72.5% | -2.82% |
| NASDAQ-100 | 13w | Mixed | 391 | +4.76% | 69.6% | -6.53% |
| NASDAQ-100 | 13w | Risk-On | 48 | +8.28% | 95.8% | -4.07% |
| NASDAQ-100 | 26w | Mixed | 379 | +10.06% | 76.5% | -9.08% |
| NASDAQ-100 | 26w | Risk-On | 47 | +12.12% | 89.4% | -4.44% |
| VIX Futures | 4w | Mixed | 449 | +6.17% | 50.1% | -13.20% |
| VIX Futures | 13w | Mixed | 439 | +10.21% | 46.9% | -19.71% |
| VIX Futures | 26w | Mixed | 426 | +10.57% | 47.2% | -23.19% |
| Russell 2000 | 4w | Mixed | 131 | +1.57% | 64.9% | -3.08% |
| Russell 2000 | 13w | Mixed | 121 | +4.76% | 76.0% | -5.60% |
| Russell 2000 | 26w | Mixed | 108 | +8.81% | 78.7% | -8.27% |
| Dow Jones | 4w | Mixed | 449 | +0.78% | 65.0% | -2.77% |
| Dow Jones | 13w | Mixed | 439 | +2.51% | 68.1% | -5.16% |
| Dow Jones | 26w | Mixed | 426 | +5.00% | 73.7% | -7.43% |
| Gold | 4w | Mixed | 449 | +1.21% | 58.4% | -2.29% |
| Gold | 13w | Mixed | 439 | +3.93% | 66.7% | -3.77% |
| Gold | 26w | Mixed | 426 | +8.71% | 74.6% | -4.58% |

## Predictivity Diagnostics

| Market | Horizon | N | Score/return r | HAC p | Risk-On minus Caution | Edge HAC p | Drift-adjusted accuracy | Evidence |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| S&P 500 | 4w | 427 | +0.086 | 0.227 | +1.96% | 0.137 | 52.1% | Unclear |
| S&P 500 | 13w | 417 | +0.103 | 0.368 | +6.85% | 0.003 | 55.8% | Supported |
| S&P 500 | 26w | 404 | +0.141 | 0.264 | +11.78% | 0.002 | 55.6% | Supported |
| NASDAQ-100 | 4w | 449 | +0.030 | 0.574 | n/a | n/a | 54.7% | Insufficient |
| NASDAQ-100 | 13w | 439 | +0.071 | 0.271 | n/a | n/a | 54.1% | Insufficient |
| NASDAQ-100 | 26w | 426 | -0.013 | 0.857 | n/a | n/a | 52.6% | Insufficient |
| VIX Futures | 4w | 449 | n/a | n/a | n/a | n/a | n/a | Insufficient |
| VIX Futures | 13w | 439 | n/a | n/a | n/a | n/a | n/a | Insufficient |
| VIX Futures | 26w | 426 | n/a | n/a | n/a | n/a | n/a | Insufficient |
| Russell 2000 | 4w | 131 | n/a | n/a | n/a | n/a | n/a | Insufficient |
| Russell 2000 | 13w | 121 | n/a | n/a | n/a | n/a | n/a | Insufficient |
| Russell 2000 | 26w | 108 | n/a | n/a | n/a | n/a | n/a | Insufficient |
| Dow Jones | 4w | 449 | n/a | n/a | n/a | n/a | n/a | Insufficient |
| Dow Jones | 13w | 439 | n/a | n/a | n/a | n/a | n/a | Insufficient |
| Dow Jones | 26w | 426 | n/a | n/a | n/a | n/a | n/a | Insufficient |
| Gold | 4w | 449 | n/a | n/a | n/a | n/a | n/a | Insufficient |
| Gold | 13w | 439 | n/a | n/a | n/a | n/a | n/a | Insufficient |
| Gold | 26w | 426 | n/a | n/a | n/a | n/a | n/a | Insufficient |

## Interpretation

- Risk-On means the configured COT extremes historically aligned with better forward reward/risk; it is not a guaranteed long signal.
- Caution is primarily an exposure and position-sizing warning, not an automatic short.
- Mixed means the active COT extremes conflict or lack enough conviction for a directional call.
- The backtest is COT-only. Price, volatility, and the unified macro-liquidity score are excluded from the regime score.
- `Supported` requires a positive Risk-On-minus-Caution edge with an overlap-adjusted HAC p-value at or below 0.05 and at least 20 observations in the smaller directional bucket.
- Drift-adjusted accuracy asks whether the score sign predicted a return above or below the prior expanding average, rather than rewarding the model for the equity market's long-run positive drift.

## Caveats

1. The expanding-percentile warmup requires at least 104 prior weekly reports.
2. Equity-index drift can keep average returns positive even in Caution buckets.
3. Long-horizon observations overlap. The main evidence table therefore uses Newey-West HAC statistics with lags tied to the forecast horizon; conventional permutation and Welch statistics remain in the CSV only as secondary diagnostics.
4. Publication timing is approximated using the first available market close on or after Friday release.
5. Latest rows may lack longer-horizon returns until enough future price history exists.
6. Percentile ranks are walk-forward, but the rule thresholds and weights are fixed researcher choices rather than rules selected in a sealed out-of-sample training process.
