# COT Regime Score Backtest Report

Generated: 2026-07-24T22:41:56Z

This report is regenerated from the same current Legacy COT inputs used by the dashboard. COT observations are Tuesday report dates; signals start at the first available close on or after Friday publication.

## Data Cutoffs

| Market | Latest COT report | Latest signal close | Latest price | Scored rows |
| --- | --- | --- | --- | --- |
| S&P 500 | 2026-07-21 | 2026-07-24 | 2026-07-24 | 426 |
| NASDAQ-100 | 2026-07-21 | 2026-07-24 | 2026-07-24 | 448 |

## Current Tradable COT Signals

| Market | Report date | Signal date | Score | Bucket | Active triggers |
| --- | --- | --- | --- | --- | --- |
| S&P 500 | 2026-07-21 | 2026-07-24 | -1.50 | Mixed | nonreportable 97.4% -1.50 Non-reportable crowding |
| NASDAQ-100 | 2026-07-21 | 2026-07-24 | -2.00 | Caution | nonreportable 90.4% -2.00 Non-reportable crowding |

## Forward Returns by Regime Bucket

| Market | Horizon | Bucket | N | Average return | Hit rate | Average drawdown |
| --- | --- | --- | --- | --- | --- | --- |
| S&P 500 | 4w | Mixed | 289 | +1.03% | 68.9% | -2.72% |
| S&P 500 | 4w | Caution | 33 | +0.04% | 63.6% | -3.85% |
| S&P 500 | 4w | Risk-On | 99 | +1.69% | 69.7% | -2.74% |
| S&P 500 | 13w | Mixed | 281 | +4.04% | 76.2% | -5.37% |
| S&P 500 | 13w | Caution | 33 | -0.43% | 42.4% | -7.70% |
| S&P 500 | 13w | Risk-On | 98 | +3.45% | 72.4% | -4.63% |
| S&P 500 | 26w | Mixed | 267 | +7.25% | 75.3% | -7.83% |
| S&P 500 | 26w | Caution | 33 | +1.30% | 48.5% | -13.37% |
| S&P 500 | 26w | Risk-On | 98 | +8.52% | 84.7% | -5.66% |
| NASDAQ-100 | 4w | Mixed | 289 | +1.64% | 64.7% | -3.52% |
| NASDAQ-100 | 4w | Caution | 83 | +1.13% | 62.7% | -3.86% |
| NASDAQ-100 | 4w | Risk-On | 71 | +2.06% | 70.4% | -2.83% |
| NASDAQ-100 | 13w | Mixed | 283 | +4.81% | 68.2% | -6.57% |
| NASDAQ-100 | 13w | Caution | 83 | +4.85% | 75.9% | -6.82% |
| NASDAQ-100 | 13w | Risk-On | 68 | +7.13% | 86.8% | -4.40% |
| NASDAQ-100 | 26w | Mixed | 273 | +9.51% | 71.8% | -9.26% |
| NASDAQ-100 | 26w | Caution | 79 | +11.78% | 89.9% | -9.32% |
| NASDAQ-100 | 26w | Risk-On | 68 | +11.21% | 86.8% | -4.92% |

## Predictivity Diagnostics

| Market | Horizon | N | Score/return r | HAC p | Risk-On minus Caution | Edge HAC p | Drift-adjusted accuracy | Evidence |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| S&P 500 | 4w | 421 | +0.102 | 0.169 | +1.65% | 0.202 | 52.9% | Unclear |
| S&P 500 | 13w | 412 | +0.108 | 0.347 | +3.89% | 0.146 | 56.0% | Unclear |
| S&P 500 | 26w | 398 | +0.153 | 0.240 | +7.22% | 0.097 | 57.0% | Tentative |
| NASDAQ-100 | 4w | 443 | +0.029 | 0.605 | +0.93% | 0.408 | 56.4% | Unclear |
| NASDAQ-100 | 13w | 434 | +0.061 | 0.380 | +2.29% | 0.285 | 55.1% | Unclear |
| NASDAQ-100 | 26w | 420 | -0.020 | 0.796 | -0.57% | 0.861 | 54.0% | Unclear |

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
