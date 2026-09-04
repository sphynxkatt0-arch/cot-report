# COT Regime Score Backtest Report

Generated: 2026-08-29T00:47:29Z

This report is regenerated from the same current TFF Detailed inputs used by the dashboard. COT observations are Tuesday report dates; signals start at the first available close on or after Friday publication.

## Data Cutoffs

| Market | Latest COT report | Latest signal close | Latest price | Scored rows |
| --- | --- | --- | --- | --- |
| S&P 500 | 2026-08-25 | 2026-08-28 | 2026-08-28 | 431 |
| NASDAQ-100 | 2026-08-25 | 2026-08-28 | 2026-08-28 | 453 |
| Russell 2000 | 2026-08-25 | 2026-08-28 | 2026-08-28 | 135 |
| Dow Jones | 2026-08-25 | 2026-08-28 | 2026-08-28 | 453 |

## Current Tradable COT Signals

| Market | Report date | Signal date | Score | Bucket | Active triggers |
| --- | --- | --- | --- | --- | --- |
| S&P 500 | 2026-08-25 | 2026-08-28 | -1.00 | Mixed | non_reportable 97.2% -1.00 Non-reportable contrarian (retail long) |
| NASDAQ-100 | 2026-08-25 | 2026-08-28 | -0.75 | Mixed | non_reportable 97.8% -0.75 Non-reportable contrarian (retail long) |
| Russell 2000 | 2026-08-25 | 2026-08-28 | +0.00 | Mixed | No active extreme trigger |
| Dow Jones | 2026-08-25 | 2026-08-28 | +0.00 | Mixed | No active extreme trigger |

## Forward Returns by Regime Bucket

| Market | Horizon | Bucket | N | Average return | Hit rate | Average drawdown |
| --- | --- | --- | --- | --- | --- | --- |
| S&P 500 | 4w | Mixed | 246 | +1.56% | 71.1% | -2.61% |
| S&P 500 | 4w | Caution | 172 | +0.37% | 65.1% | -3.14% |
| S&P 500 | 4w | Risk-On | 9 | +3.74% | 88.9% | -1.33% |
| S&P 500 | 13w | Mixed | 243 | +4.27% | 75.3% | -4.41% |
| S&P 500 | 13w | Caution | 165 | +2.29% | 67.9% | -6.88% |
| S&P 500 | 13w | Risk-On | 9 | +7.21% | 100.0% | -1.97% |
| S&P 500 | 26w | Mixed | 237 | +6.91% | 73.0% | -7.09% |
| S&P 500 | 26w | Caution | 158 | +6.86% | 78.5% | -9.10% |
| S&P 500 | 26w | Risk-On | 9 | +17.20% | 100.0% | -1.97% |
| NASDAQ-100 | 4w | Mixed | 337 | +1.72% | 65.9% | -3.54% |
| NASDAQ-100 | 4w | Risk-On | 88 | +1.62% | 63.6% | -3.21% |
| NASDAQ-100 | 4w | Caution | 24 | -0.03% | 58.3% | -3.86% |
| NASDAQ-100 | 13w | Mixed | 327 | +5.19% | 71.9% | -6.25% |
| NASDAQ-100 | 13w | Risk-On | 88 | +6.07% | 80.7% | -5.28% |
| NASDAQ-100 | 13w | Caution | 24 | +1.01% | 50.0% | -10.06% |
| NASDAQ-100 | 26w | Mixed | 317 | +9.53% | 74.1% | -8.62% |
| NASDAQ-100 | 26w | Risk-On | 85 | +13.17% | 85.9% | -6.63% |
| NASDAQ-100 | 26w | Caution | 24 | +10.13% | 100.0% | -14.79% |
| Russell 2000 | 4w | Mixed | 131 | +1.57% | 64.9% | -3.08% |
| Russell 2000 | 13w | Mixed | 121 | +4.76% | 76.0% | -5.60% |
| Russell 2000 | 26w | Mixed | 108 | +8.81% | 78.7% | -8.27% |
| Dow Jones | 4w | Mixed | 449 | +0.78% | 65.0% | -2.77% |
| Dow Jones | 13w | Mixed | 439 | +2.51% | 68.1% | -5.16% |
| Dow Jones | 26w | Mixed | 426 | +5.00% | 73.7% | -7.43% |

## Predictivity Diagnostics

| Market | Horizon | N | Score/return r | HAC p | Risk-On minus Caution | Edge HAC p | Drift-adjusted accuracy | Evidence |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| S&P 500 | 4w | 427 | +0.077 | 0.234 | +3.36% | 0.037 | 46.0% | Insufficient |
| S&P 500 | 13w | 417 | +0.085 | 0.368 | +4.92% | 0.001 | 49.7% | Insufficient |
| S&P 500 | 26w | 404 | +0.059 | 0.642 | +10.33% | 0.000 | 48.2% | Insufficient |
| NASDAQ-100 | 4w | 449 | +0.049 | 0.391 | +1.65% | 0.400 | 57.4% | Unclear |
| NASDAQ-100 | 13w | 439 | +0.096 | 0.233 | +5.07% | 0.277 | 52.5% | Unclear |
| NASDAQ-100 | 26w | 426 | +0.131 | 0.065 | +3.03% | 0.515 | 58.9% | Weak |
| Russell 2000 | 4w | 131 | n/a | n/a | n/a | n/a | n/a | Insufficient |
| Russell 2000 | 13w | 121 | n/a | n/a | n/a | n/a | n/a | Insufficient |
| Russell 2000 | 26w | 108 | n/a | n/a | n/a | n/a | n/a | Insufficient |
| Dow Jones | 4w | 449 | n/a | n/a | n/a | n/a | n/a | Insufficient |
| Dow Jones | 13w | 439 | n/a | n/a | n/a | n/a | n/a | Insufficient |
| Dow Jones | 26w | 426 | n/a | n/a | n/a | n/a | n/a | Insufficient |

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
