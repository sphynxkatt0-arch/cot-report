# COT Regime Score Backtest Report

Generated: 2026-08-07T19:47:17Z

This report is regenerated from the same current TFF Detailed inputs used by the dashboard. COT observations are Tuesday report dates; signals start at the first available close on or after Friday publication.

## Data Cutoffs

| Market | Latest COT report | Latest signal close | Latest price | Scored rows |
| --- | --- | --- | --- | --- |
| S&P 500 | 2026-08-04 | 2026-08-07 | 2026-08-07 | 428 |
| NASDAQ-100 | 2026-08-04 | 2026-08-07 | 2026-08-07 | 450 |
| Russell 2000 | 2026-08-04 | 2026-08-07 | 2026-08-07 | 132 |
| Dow Jones | 2026-08-04 | 2026-08-07 | 2026-08-07 | 450 |

## Current Tradable COT Signals

| Market | Report date | Signal date | Score | Bucket | Active triggers |
| --- | --- | --- | --- | --- | --- |
| S&P 500 | 2026-08-04 | 2026-08-07 | -1.50 | Mixed | non_reportable 90.6% -1.50 Non-reportable crowding |
| NASDAQ-100 | 2026-08-04 | 2026-08-07 | +1.50 | Mixed | lev_money 0.4% +1.50 Leveraged Money underexposed |
| Russell 2000 | 2026-08-04 | 2026-08-07 | +0.00 | Mixed | No active extreme trigger |
| Dow Jones | 2026-08-04 | 2026-08-07 | +0.00 | Mixed | No active extreme trigger |

## Forward Returns by Regime Bucket

| Market | Horizon | Bucket | N | Average return | Hit rate | Average drawdown |
| --- | --- | --- | --- | --- | --- | --- |
| S&P 500 | 4w | Mixed | 198 | +1.42% | 71.2% | -2.74% |
| S&P 500 | 4w | Caution | 177 | +0.31% | 65.5% | -2.86% |
| S&P 500 | 4w | Risk-On | 49 | +2.73% | 71.4% | -2.93% |
| S&P 500 | 13w | Mixed | 193 | +4.50% | 77.2% | -4.58% |
| S&P 500 | 13w | Caution | 172 | +1.82% | 66.9% | -6.49% |
| S&P 500 | 13w | Risk-On | 49 | +5.90% | 75.5% | -4.45% |
| S&P 500 | 26w | Mixed | 184 | +7.79% | 76.1% | -7.20% |
| S&P 500 | 26w | Caution | 168 | +4.96% | 72.6% | -9.31% |
| S&P 500 | 26w | Risk-On | 49 | +11.70% | 83.7% | -4.59% |
| NASDAQ-100 | 4w | Mixed | 336 | +1.64% | 65.5% | -3.56% |
| NASDAQ-100 | 4w | Risk-On | 78 | +2.11% | 65.4% | -2.92% |
| NASDAQ-100 | 4w | Caution | 32 | -0.22% | 56.2% | -4.26% |
| NASDAQ-100 | 13w | Mixed | 328 | +4.99% | 71.0% | -6.38% |
| NASDAQ-100 | 13w | Risk-On | 76 | +7.31% | 84.2% | -4.49% |
| NASDAQ-100 | 13w | Caution | 32 | +1.97% | 59.4% | -9.21% |
| NASDAQ-100 | 26w | Mixed | 316 | +8.91% | 71.8% | -8.81% |
| NASDAQ-100 | 26w | Risk-On | 75 | +15.86% | 93.3% | -5.80% |
| NASDAQ-100 | 26w | Caution | 32 | +10.03% | 100.0% | -12.75% |
| Russell 2000 | 4w | Mixed | 128 | +1.54% | 64.1% | -3.13% |
| Russell 2000 | 13w | Mixed | 118 | +4.72% | 75.4% | -5.68% |
| Russell 2000 | 26w | Mixed | 105 | +8.66% | 78.1% | -8.24% |
| Dow Jones | 4w | Mixed | 446 | +0.77% | 64.8% | -2.79% |
| Dow Jones | 13w | Mixed | 436 | +2.48% | 67.9% | -5.19% |
| Dow Jones | 26w | Mixed | 423 | +4.98% | 73.5% | -7.41% |

## Predictivity Diagnostics

| Market | Horizon | N | Score/return r | HAC p | Risk-On minus Caution | Edge HAC p | Drift-adjusted accuracy | Evidence |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| S&P 500 | 4w | 424 | +0.124 | 0.081 | +2.42% | 0.079 | 51.0% | Tentative |
| S&P 500 | 13w | 414 | +0.155 | 0.211 | +4.08% | 0.240 | 56.2% | Unclear |
| S&P 500 | 26w | 401 | +0.167 | 0.253 | +6.74% | 0.188 | 54.9% | Unclear |
| NASDAQ-100 | 4w | 446 | +0.065 | 0.243 | +2.32% | 0.164 | 58.4% | Unclear |
| NASDAQ-100 | 13w | 436 | +0.115 | 0.131 | +5.34% | 0.154 | 54.7% | Unclear |
| NASDAQ-100 | 26w | 423 | +0.149 | 0.029 | +5.83% | 0.052 | 62.8% | Tentative |
| Russell 2000 | 4w | 128 | n/a | n/a | n/a | n/a | n/a | Insufficient |
| Russell 2000 | 13w | 118 | n/a | n/a | n/a | n/a | n/a | Insufficient |
| Russell 2000 | 26w | 105 | n/a | n/a | n/a | n/a | n/a | Insufficient |
| Dow Jones | 4w | 446 | n/a | n/a | n/a | n/a | n/a | Insufficient |
| Dow Jones | 13w | 436 | n/a | n/a | n/a | n/a | n/a | Insufficient |
| Dow Jones | 26w | 423 | n/a | n/a | n/a | n/a | n/a | Insufficient |

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
