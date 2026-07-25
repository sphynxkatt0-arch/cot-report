# COT Regime Score Backtest Report

Generated: 2026-07-24T22:41:49Z

This report is regenerated from the same current TFF Detailed inputs used by the dashboard. COT observations are Tuesday report dates; signals start at the first available close on or after Friday publication.

## Data Cutoffs

| Market | Latest COT report | Latest signal close | Latest price | Scored rows |
| --- | --- | --- | --- | --- |
| S&P 500 | 2026-07-21 | 2026-07-24 | 2026-07-24 | 426 |
| NASDAQ-100 | 2026-07-21 | 2026-07-24 | 2026-07-24 | 448 |

## Current Tradable COT Signals

| Market | Report date | Signal date | Score | Bucket | Active triggers |
| --- | --- | --- | --- | --- | --- |
| S&P 500 | 2026-07-21 | 2026-07-24 | -3.50 | Caution | asset_mgr 92.4% -2.00 Asset Manager crowding; non_reportable 97.4% -1.50 Non-reportable crowding |
| NASDAQ-100 | 2026-07-21 | 2026-07-24 | +0.50 | Mixed | lev_money 0.4% +1.50 Leveraged Money underexposed; non_reportable 90.4% -1.00 Non-reportable elevated |

## Forward Returns by Regime Bucket

| Market | Horizon | Bucket | N | Average return | Hit rate | Average drawdown |
| --- | --- | --- | --- | --- | --- | --- |
| S&P 500 | 4w | Mixed | 198 | +1.42% | 71.2% | -2.74% |
| S&P 500 | 4w | Caution | 174 | +0.30% | 64.9% | -2.87% |
| S&P 500 | 4w | Risk-On | 49 | +2.73% | 71.4% | -2.93% |
| S&P 500 | 13w | Mixed | 191 | +4.50% | 77.0% | -4.62% |
| S&P 500 | 13w | Caution | 172 | +1.82% | 66.9% | -6.49% |
| S&P 500 | 13w | Risk-On | 49 | +5.90% | 75.5% | -4.45% |
| S&P 500 | 26w | Mixed | 184 | +7.79% | 76.1% | -7.20% |
| S&P 500 | 26w | Caution | 165 | +4.89% | 72.1% | -9.32% |
| S&P 500 | 26w | Risk-On | 49 | +11.70% | 83.7% | -4.59% |
| NASDAQ-100 | 4w | Mixed | 333 | +1.67% | 66.1% | -3.53% |
| NASDAQ-100 | 4w | Risk-On | 78 | +2.11% | 65.4% | -2.92% |
| NASDAQ-100 | 4w | Caution | 32 | -0.22% | 56.2% | -4.26% |
| NASDAQ-100 | 13w | Mixed | 327 | +4.98% | 70.9% | -6.39% |
| NASDAQ-100 | 13w | Risk-On | 75 | +7.42% | 85.3% | -4.53% |
| NASDAQ-100 | 13w | Caution | 32 | +1.97% | 59.4% | -9.21% |
| NASDAQ-100 | 26w | Mixed | 313 | +8.88% | 71.6% | -8.80% |
| NASDAQ-100 | 26w | Risk-On | 75 | +15.86% | 93.3% | -5.80% |
| NASDAQ-100 | 26w | Caution | 32 | +10.03% | 100.0% | -12.75% |

## Predictivity Diagnostics

| Market | Horizon | N | Score/return r | HAC p | Risk-On minus Caution | Edge HAC p | Drift-adjusted accuracy | Evidence |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| S&P 500 | 4w | 421 | +0.125 | 0.079 | +2.43% | 0.078 | 50.8% | Tentative |
| S&P 500 | 13w | 412 | +0.155 | 0.211 | +4.08% | 0.240 | 56.3% | Unclear |
| S&P 500 | 26w | 398 | +0.168 | 0.250 | +6.81% | 0.184 | 55.2% | Unclear |
| NASDAQ-100 | 4w | 443 | +0.067 | 0.231 | +2.32% | 0.164 | 59.1% | Unclear |
| NASDAQ-100 | 13w | 434 | +0.116 | 0.126 | +5.44% | 0.143 | 54.7% | Unclear |
| NASDAQ-100 | 26w | 420 | +0.150 | 0.028 | +5.83% | 0.052 | 63.2% | Tentative |

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
