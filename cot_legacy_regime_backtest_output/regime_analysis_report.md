# COT Regime Score Backtest Report

Generated: 2026-08-07T19:47:34Z

This report is regenerated from the same current Legacy COT inputs used by the dashboard. COT observations are Tuesday report dates; signals start at the first available close on or after Friday publication.

## Data Cutoffs

| Market | Latest COT report | Latest signal close | Latest price | Scored rows |
| --- | --- | --- | --- | --- |
| S&P 500 | 2026-08-04 | 2026-08-07 | 2026-08-07 | 428 |
| NASDAQ-100 | 2026-08-04 | 2026-08-07 | 2026-08-07 | 450 |
| VIX Futures | 2026-08-04 | 2026-08-07 | 2026-08-07 | 450 |
| Russell 2000 | 2026-08-04 | 2026-08-07 | 2026-08-07 | 132 |
| Dow Jones | 2026-08-04 | 2026-08-07 | 2026-08-07 | 450 |
| Gold | 2026-08-04 | 2026-08-07 | 2026-08-07 | 450 |

## Current Tradable COT Signals

| Market | Report date | Signal date | Score | Bucket | Active triggers |
| --- | --- | --- | --- | --- | --- |
| S&P 500 | 2026-08-04 | 2026-08-07 | -1.50 | Mixed | nonreportable 90.6% -1.50 Non-reportable crowding |
| NASDAQ-100 | 2026-08-04 | 2026-08-07 | +4.00 | Risk-On | noncommercial 1.4% +2.50 Non-commercial short crowding; commercial 90.6% +1.50 Commercial contrarian support |
| VIX Futures | 2026-08-04 | 2026-08-07 | +0.00 | Mixed | No active extreme trigger |
| Russell 2000 | 2026-08-04 | 2026-08-07 | +0.00 | Mixed | No active extreme trigger |
| Dow Jones | 2026-08-04 | 2026-08-07 | +0.00 | Mixed | No active extreme trigger |
| Gold | 2026-08-04 | 2026-08-07 | +0.00 | Mixed | No active extreme trigger |

## Forward Returns by Regime Bucket

| Market | Horizon | Bucket | N | Average return | Hit rate | Average drawdown |
| --- | --- | --- | --- | --- | --- | --- |
| S&P 500 | 4w | Mixed | 292 | +1.03% | 69.2% | -2.72% |
| S&P 500 | 4w | Caution | 33 | +0.04% | 63.6% | -3.85% |
| S&P 500 | 4w | Risk-On | 99 | +1.69% | 69.7% | -2.74% |
| S&P 500 | 13w | Mixed | 283 | +4.05% | 76.3% | -5.34% |
| S&P 500 | 13w | Caution | 33 | -0.43% | 42.4% | -7.70% |
| S&P 500 | 13w | Risk-On | 98 | +3.45% | 72.4% | -4.63% |
| S&P 500 | 26w | Mixed | 270 | +7.27% | 75.6% | -7.84% |
| S&P 500 | 26w | Caution | 33 | +1.30% | 48.5% | -13.37% |
| S&P 500 | 26w | Risk-On | 98 | +8.52% | 84.7% | -5.66% |
| NASDAQ-100 | 4w | Mixed | 290 | +1.62% | 64.5% | -3.52% |
| NASDAQ-100 | 4w | Caution | 84 | +1.11% | 61.9% | -3.92% |
| NASDAQ-100 | 4w | Risk-On | 72 | +1.98% | 69.4% | -2.91% |
| NASDAQ-100 | 13w | Mixed | 285 | +4.80% | 68.1% | -6.54% |
| NASDAQ-100 | 13w | Caution | 83 | +4.85% | 75.9% | -6.82% |
| NASDAQ-100 | 13w | Risk-On | 68 | +7.13% | 86.8% | -4.40% |
| NASDAQ-100 | 26w | Mixed | 273 | +9.51% | 71.8% | -9.26% |
| NASDAQ-100 | 26w | Caution | 82 | +11.79% | 90.2% | -9.35% |
| NASDAQ-100 | 26w | Risk-On | 68 | +11.21% | 86.8% | -4.92% |
| VIX Futures | 4w | Mixed | 446 | +6.33% | 50.4% | -13.16% |
| VIX Futures | 13w | Mixed | 436 | +10.36% | 47.2% | -19.73% |
| VIX Futures | 26w | Mixed | 423 | +10.80% | 47.5% | -23.16% |
| Russell 2000 | 4w | Mixed | 128 | +1.54% | 64.1% | -3.13% |
| Russell 2000 | 13w | Mixed | 118 | +4.72% | 75.4% | -5.68% |
| Russell 2000 | 26w | Mixed | 105 | +8.66% | 78.1% | -8.24% |
| Dow Jones | 4w | Mixed | 446 | +0.77% | 64.8% | -2.79% |
| Dow Jones | 13w | Mixed | 436 | +2.48% | 67.9% | -5.19% |
| Dow Jones | 26w | Mixed | 423 | +4.98% | 73.5% | -7.41% |
| Gold | 4w | Mixed | 446 | +1.14% | 58.1% | -2.30% |
| Gold | 13w | Mixed | 436 | +3.97% | 67.0% | -3.71% |
| Gold | 26w | Mixed | 423 | +8.84% | 75.2% | -4.46% |

## Predictivity Diagnostics

| Market | Horizon | N | Score/return r | HAC p | Risk-On minus Caution | Edge HAC p | Drift-adjusted accuracy | Evidence |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| S&P 500 | 4w | 424 | +0.101 | 0.171 | +1.65% | 0.202 | 53.1% | Unclear |
| S&P 500 | 13w | 414 | +0.107 | 0.347 | +3.89% | 0.146 | 56.0% | Unclear |
| S&P 500 | 26w | 401 | +0.151 | 0.244 | +7.22% | 0.097 | 56.7% | Tentative |
| NASDAQ-100 | 4w | 446 | +0.028 | 0.622 | +0.87% | 0.431 | 56.0% | Unclear |
| NASDAQ-100 | 13w | 436 | +0.061 | 0.378 | +2.29% | 0.285 | 55.1% | Unclear |
| NASDAQ-100 | 26w | 423 | -0.021 | 0.784 | -0.58% | 0.854 | 53.7% | Unclear |
| VIX Futures | 4w | 446 | n/a | n/a | n/a | n/a | n/a | Insufficient |
| VIX Futures | 13w | 436 | n/a | n/a | n/a | n/a | n/a | Insufficient |
| VIX Futures | 26w | 423 | n/a | n/a | n/a | n/a | n/a | Insufficient |
| Russell 2000 | 4w | 128 | n/a | n/a | n/a | n/a | n/a | Insufficient |
| Russell 2000 | 13w | 118 | n/a | n/a | n/a | n/a | n/a | Insufficient |
| Russell 2000 | 26w | 105 | n/a | n/a | n/a | n/a | n/a | Insufficient |
| Dow Jones | 4w | 446 | n/a | n/a | n/a | n/a | n/a | Insufficient |
| Dow Jones | 13w | 436 | n/a | n/a | n/a | n/a | n/a | Insufficient |
| Dow Jones | 26w | 423 | n/a | n/a | n/a | n/a | n/a | Insufficient |
| Gold | 4w | 446 | n/a | n/a | n/a | n/a | n/a | Insufficient |
| Gold | 13w | 436 | n/a | n/a | n/a | n/a | n/a | Insufficient |
| Gold | 26w | 423 | n/a | n/a | n/a | n/a | n/a | Insufficient |

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
