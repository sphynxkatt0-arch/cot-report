# COT Regime Score Backtest Report

Generated: 2026-09-04T21:12:32Z

This report is regenerated from the same current Legacy COT inputs used by the dashboard. COT observations are Tuesday report dates; signals start at the first available close on or after Friday publication.

## Data Cutoffs

| Market | Latest COT report | Latest signal close | Latest price | Scored rows |
| --- | --- | --- | --- | --- |
| S&P 500 | 2026-09-01 | 2026-09-04 | 2026-09-04 | 432 |
| NASDAQ-100 | 2026-09-01 | 2026-09-04 | 2026-09-04 | 454 |
| VIX Futures | 2026-09-01 | 2026-09-04 | 2026-09-04 | 454 |
| Russell 2000 | 2026-09-01 | 2026-09-04 | 2026-09-04 | 136 |
| Dow Jones | 2026-09-01 | 2026-09-04 | 2026-09-04 | 454 |
| Gold | 2026-09-01 | 2026-09-04 | 2026-09-04 | 454 |

## Current Tradable COT Signals

| Market | Report date | Signal date | Score | Bucket | Active triggers |
| --- | --- | --- | --- | --- | --- |
| S&P 500 | 2026-09-01 | 2026-09-04 | -1.00 | Mixed | nonreportable 91.2% -1.00 Non-reportable contrarian (retail long) |
| NASDAQ-100 | 2026-09-01 | 2026-09-04 | +0.00 | Mixed | No active extreme trigger |
| VIX Futures | 2026-09-01 | 2026-09-04 | +0.00 | Mixed | No active extreme trigger |
| Russell 2000 | 2026-09-01 | 2026-09-04 | +0.00 | Mixed | No active extreme trigger |
| Dow Jones | 2026-09-01 | 2026-09-04 | +0.00 | Mixed | No active extreme trigger |
| Gold | 2026-09-01 | 2026-09-04 | +0.00 | Mixed | No active extreme trigger |

## Forward Returns by Regime Bucket

| Market | Horizon | Bucket | N | Average return | Hit rate | Average drawdown |
| --- | --- | --- | --- | --- | --- | --- |
| S&P 500 | 4w | Mixed | 314 | +1.08% | 69.4% | -2.78% |
| S&P 500 | 4w | Caution | 21 | -0.35% | 61.9% | -3.66% |
| S&P 500 | 4w | Risk-On | 93 | +1.61% | 68.8% | -2.65% |
| S&P 500 | 13w | Mixed | 305 | +4.12% | 77.0% | -5.27% |
| S&P 500 | 13w | Caution | 21 | -3.58% | 23.8% | -9.41% |
| S&P 500 | 13w | Risk-On | 92 | +3.27% | 70.7% | -4.62% |
| S&P 500 | 26w | Mixed | 292 | +7.62% | 76.4% | -7.84% |
| S&P 500 | 26w | Caution | 21 | -3.71% | 28.6% | -15.81% |
| S&P 500 | 26w | Risk-On | 92 | +8.07% | 84.8% | -5.69% |
| NASDAQ-100 | 4w | Mixed | 398 | +1.51% | 64.1% | -3.58% |
| NASDAQ-100 | 4w | Risk-On | 52 | +2.30% | 71.2% | -2.81% |
| NASDAQ-100 | 13w | Mixed | 392 | +4.73% | 69.4% | -6.54% |
| NASDAQ-100 | 13w | Risk-On | 48 | +8.28% | 95.8% | -4.07% |
| NASDAQ-100 | 26w | Mixed | 380 | +10.08% | 76.6% | -9.08% |
| NASDAQ-100 | 26w | Risk-On | 47 | +12.12% | 89.4% | -4.44% |
| VIX Futures | 4w | Mixed | 450 | +6.15% | 50.0% | -13.18% |
| VIX Futures | 13w | Mixed | 440 | +10.18% | 46.8% | -19.68% |
| VIX Futures | 26w | Mixed | 427 | +10.50% | 47.1% | -23.20% |
| Russell 2000 | 4w | Mixed | 132 | +1.54% | 64.4% | -3.09% |
| Russell 2000 | 13w | Mixed | 122 | +4.73% | 76.2% | -5.58% |
| Russell 2000 | 26w | Mixed | 109 | +8.84% | 78.9% | -8.27% |
| Dow Jones | 4w | Mixed | 450 | +0.78% | 64.9% | -2.77% |
| Dow Jones | 13w | Mixed | 440 | +2.51% | 68.2% | -5.15% |
| Dow Jones | 26w | Mixed | 427 | +5.01% | 73.8% | -7.43% |
| Gold | 4w | Mixed | 450 | +1.21% | 58.4% | -2.28% |
| Gold | 13w | Mixed | 440 | +3.91% | 66.6% | -3.79% |
| Gold | 26w | Mixed | 427 | +8.65% | 74.5% | -4.62% |

## Predictivity Diagnostics

| Market | Horizon | N | Score/return r | HAC p | Risk-On minus Caution | Edge HAC p | Drift-adjusted accuracy | Evidence |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| S&P 500 | 4w | 428 | +0.086 | 0.223 | +1.96% | 0.137 | 52.3% | Unclear |
| S&P 500 | 13w | 418 | +0.103 | 0.364 | +6.85% | 0.003 | 56.0% | Supported |
| S&P 500 | 26w | 405 | +0.141 | 0.261 | +11.78% | 0.002 | 55.8% | Supported |
| NASDAQ-100 | 4w | 450 | +0.028 | 0.597 | n/a | n/a | 54.4% | Insufficient |
| NASDAQ-100 | 13w | 440 | +0.072 | 0.267 | n/a | n/a | 54.1% | Insufficient |
| NASDAQ-100 | 26w | 427 | -0.013 | 0.853 | n/a | n/a | 52.6% | Insufficient |
| VIX Futures | 4w | 450 | n/a | n/a | n/a | n/a | n/a | Insufficient |
| VIX Futures | 13w | 440 | n/a | n/a | n/a | n/a | n/a | Insufficient |
| VIX Futures | 26w | 427 | n/a | n/a | n/a | n/a | n/a | Insufficient |
| Russell 2000 | 4w | 132 | n/a | n/a | n/a | n/a | n/a | Insufficient |
| Russell 2000 | 13w | 122 | n/a | n/a | n/a | n/a | n/a | Insufficient |
| Russell 2000 | 26w | 109 | n/a | n/a | n/a | n/a | n/a | Insufficient |
| Dow Jones | 4w | 450 | n/a | n/a | n/a | n/a | n/a | Insufficient |
| Dow Jones | 13w | 440 | n/a | n/a | n/a | n/a | n/a | Insufficient |
| Dow Jones | 26w | 427 | n/a | n/a | n/a | n/a | n/a | Insufficient |
| Gold | 4w | 450 | n/a | n/a | n/a | n/a | n/a | Insufficient |
| Gold | 13w | 440 | n/a | n/a | n/a | n/a | n/a | Insufficient |
| Gold | 26w | 427 | n/a | n/a | n/a | n/a | n/a | Insufficient |

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
