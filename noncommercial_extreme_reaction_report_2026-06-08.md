# Non-Commercial Short Extreme Reaction Report

Date prepared: 2026-06-08

## Scope

This report checks whether current legacy COT non-commercial short positioning is extreme, and how NASDAQ-100 and S&P 500 prices have historically reacted after similar conditions.

Data used:

- Legacy COT consolidated rows from `analysis/cot_legacy_output`.
- NASDAQ-100 prices from `data/NASDAQ100.csv`.
- S&P 500 prices from `data/SP500.csv`.
- Latest COT report date in the local files: 2026-06-02, released 2026-06-05.

The CFTC states that COT reports generally use Tuesday position data and are released Friday afternoon. The event-study returns therefore separate same-week Tuesday-to-Friday reaction from post-release forward returns.

## Executive View

Non-commercial shorts are extreme right now, but the historical reaction is not straightforward bearish.

For NASDAQ-100 legacy non-commercials, the latest raw short position is the highest in the 2016-2026 sample. The raw net-short position is second-most bearish, behind 2020-09-22. On a net/OI basis, 2020 was much more extreme than today because open interest was far smaller then. However, when similar short extremes occurred historically, forward NQ returns were usually positive over 1-13 weeks, especially when measured by short percentage of open interest or bearish net/OI percentile.

For S&P 500 legacy non-commercials, the latest short position is also high, but not the absolute highest. It ranks around the 97th percentile by both raw short count and short/OI. Similar S&P 500 non-commercial short extremes historically produced mixed short-term returns but tended to be positive over 2-13 weeks, including for NQ cross-market reaction.

Interpretation: the current setup is a stress/crowding signal, but historically it has more often behaved like a potential short-covering fuel signal than a clean continuation-bearish signal. The latest Friday price drop was severe, but the post-release Monday rebound is consistent with the historical tendency for extreme shorts to create snapback risk.

## Latest NASDAQ-100 Legacy Non-Commercial Position

Latest report date: 2026-06-02.

| Metric | Latest | Rank / Sample | Percentile / Comment |
|---|---:|---:|---:|
| Open interest | 345,837 | 6 / 544 high | 99.1 percentile |
| Non-commercial short | 90,634 | 1 / 544 high | 100.0 percentile |
| Non-commercial short / OI | 26.21% | 132 / 544 high | 75.9 percentile |
| Non-commercial net | -22,085 | 2 / 544 most bearish | 0.4 percentile |
| Non-commercial net / OI | -6.39% | 29 / 544 most bearish | 5.3 percentile |
| 1-week short change | +10,115 | elevated | not a 40k-style change |
| 2-week short change | +11,328 | elevated | not a 40k-style change |

Key point: by raw count, NQ non-commercial shorts are absolutely extreme. By short/OI they are elevated, but not top-decile extreme. The difference matters because open interest is also very high.

The most bearish raw net-short row in the sample was 2020-09-22:

| Date | Open Interest | Non-Commercial Long | Non-Commercial Short | Non-Commercial Net | Net / OI | Short / OI | NQ 1W | NQ 2W | NQ 4W | NQ 13W |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2020-09-22 | 66,403 | 16,676 | 43,538 | -26,862 | -40.45% | 65.57% | +1.22% | +0.94% | +4.39% | +13.44% |
| 2026-06-02 | 345,837 | 68,549 | 90,634 | -22,085 | -6.39% | 26.21% | n/a | n/a | n/a | n/a |

This makes 2020 the cleaner net-short analog by intensity. It also shows why the latest row is different: today's raw net short is large, but it is spread across much higher open interest.

## Latest S&P 500 Legacy Non-Commercial Position

Latest report date: 2026-06-02.

| Metric | Latest | Rank / Sample | Percentile / Comment |
|---|---:|---:|---:|
| Open interest | 2,183,680 | 64 / 523 high | 88.0 percentile |
| Non-commercial short | 485,041 | 15 / 523 high | 97.3 percentile |
| Non-commercial short / OI | 22.21% | 17 / 523 high | 96.9 percentile |
| Non-commercial net | -214,309 | 17 / 523 most bearish | 3.3 percentile |
| Non-commercial net / OI | -9.81% | 35 / 523 most bearish | 6.7 percentile |
| 1-week short change | +70,891 | very large | larger than the leveraged-fund +40k threshold |
| 2-week short change | +79,736 | very large | sustained short build |

Key point: the S&P 500 non-commercial setup is more extreme on short/OI than NQ. This supports the idea that broad-index speculators are crowded short.

## NASDAQ-100 Historical Reaction After NQ Non-Commercial Extremes

### NQ Raw Short Top 10

This condition compares historical rows where NQ non-commercial raw short count ranked in the top 10, excluding the latest row.

| Horizon | N | Mean | Median | Positive Rate | Negative Rate |
|---|---:|---:|---:|---:|---:|
| Same-week Tue-Fri | 10 | +0.38% | +0.66% | 60.0% | 40.0% |
| Post-release 1D | 10 | +0.68% | +0.73% | 70.0% | 30.0% |
| Post-release 1W | 10 | +0.19% | -0.60% | 40.0% | 60.0% |
| Post-release 2W | 9 | +0.87% | +0.83% | 55.6% | 44.4% |
| Post-release 4W | 7 | +3.75% | +4.07% | 85.7% | 14.3% |
| Post-release 13W | 5 | +2.56% | +3.03% | 60.0% | 40.0% |

Read: raw top-10 shorts are not immediately clean bullish or bearish. One-week reaction is mixed. Four-week reaction has historically leaned bullish.

### NQ Short/OI Top Decile

This condition compares rows where NQ non-commercial short/OI was in the top decile.

| Horizon | N | Mean | Median | Positive Rate | Negative Rate |
|---|---:|---:|---:|---:|---:|
| Same-week Tue-Fri | 55 | +0.56% | +0.52% | 70.9% | 29.1% |
| Post-release 1D | 55 | +0.24% | +0.16% | 63.6% | 36.4% |
| Post-release 1W | 55 | +0.90% | +0.94% | 63.6% | 36.4% |
| Post-release 2W | 55 | +1.22% | +1.43% | 69.1% | 30.9% |
| Post-release 4W | 55 | +1.42% | +3.10% | 69.1% | 30.9% |
| Post-release 13W | 55 | +6.72% | +5.77% | 89.1% | 10.9% |

Read: when shorts were extreme relative to open interest, forward returns skewed positive, especially past the first week.

### NQ Most Bearish Net/OI Decile

This condition compares rows where NQ non-commercial net/OI was in the lowest decile.

| Horizon | N | Mean | Median | Positive Rate | Negative Rate |
|---|---:|---:|---:|---:|---:|
| Same-week Tue-Fri | 55 | +0.16% | +0.40% | 60.0% | 40.0% |
| Post-release 1D | 55 | +0.34% | +0.35% | 69.1% | 30.9% |
| Post-release 1W | 55 | +1.07% | +1.00% | 69.1% | 30.9% |
| Post-release 2W | 55 | +1.77% | +1.86% | 74.6% | 25.5% |
| Post-release 4W | 54 | +3.35% | +3.99% | 79.6% | 20.4% |
| Post-release 13W | 54 | +8.71% | +9.32% | 92.6% | 7.4% |

Read: bearish non-commercial net/OI extremes historically leaned bullish as a contrarian setup.

## NQ Reaction After S&P 500 Non-Commercial Extremes

Because S&P 500 positioning often reflects broad equity futures risk, this section tests NQ reaction after S&P 500 legacy non-commercial extremes.

### S&P 500 Raw Short Top 10, NQ Reaction

| Horizon | N | Mean | Median | Positive Rate | Negative Rate |
|---|---:|---:|---:|---:|---:|
| Same-week Tue-Fri | 10 | +1.69% | +1.28% | 90.0% | 10.0% |
| Post-release 1D | 10 | +0.22% | +0.16% | 60.0% | 40.0% |
| Post-release 1W | 10 | +0.93% | +1.21% | 60.0% | 40.0% |
| Post-release 2W | 10 | +2.31% | +2.25% | 80.0% | 20.0% |
| Post-release 4W | 10 | +5.11% | +4.54% | 80.0% | 20.0% |
| Post-release 13W | 10 | +6.03% | +5.66% | 90.0% | 10.0% |

### S&P 500 Short/OI Top Decile, NQ Reaction

| Horizon | N | Mean | Median | Positive Rate | Negative Rate |
|---|---:|---:|---:|---:|---:|
| Same-week Tue-Fri | 53 | +0.63% | +0.67% | 60.4% | 39.6% |
| Post-release 1D | 53 | -0.00% | +0.04% | 52.8% | 47.2% |
| Post-release 1W | 53 | +0.57% | +0.90% | 58.5% | 41.5% |
| Post-release 2W | 53 | +0.84% | +1.04% | 60.4% | 39.6% |
| Post-release 4W | 53 | +2.01% | +2.86% | 67.9% | 32.1% |
| Post-release 13W | 53 | +6.33% | +7.70% | 79.3% | 20.8% |

Read: broad-index non-commercial short extremes also skewed positive for NQ beyond the immediate post-release window.

## Latest Price Reaction

Latest report date: 2026-06-02. Release reference date: 2026-06-05.

NQ fell sharply into the release:

- NQ 2026-06-02 close: 30,660.6.
- NQ 2026-06-05 close: 28,957.6.
- Same-week Tuesday-to-Friday return: -5.55%.

Then NQ rebounded on the next cached trading day:

- NQ 2026-06-08: 29,410.254.
- Post-release 1D return from 2026-06-05: +1.56%.

This is important: the latest row shows price weakness before/into the Friday release, but the first post-release response is already a bounce.

## Trading Interpretation

### What Supports A Bearish View

- NQ raw non-commercial shorts are at a 2016-2026 high.
- NQ raw non-commercial net is second-most bearish in the sample.
- S&P 500 non-commercial shorts are in the 97th percentile by raw count and short/OI.
- S&P 500 non-commercial short change was very large: +70,891 contracts in one week.
- Price fell hard into the 2026-06-05 release, so the market already expressed stress.

### What Pushes Against A Clean Bearish View

- NQ short/OI is only 75.9 percentile, because open interest is also extreme.
- Historical NQ short/OI top-decile cases had positive average forward returns.
- Historical NQ most-bearish net/OI decile cases were strongly positive over 1-13 weeks.
- S&P 500 non-commercial short extremes also tended to precede positive NQ forward returns over 2-13 weeks.
- Large short positioning can become fuel for short-covering if price stabilizes.

## Practical Conclusion

The best read is not "non-commercial shorts are extreme, therefore price must drop."

The better read is:

1. Positioning confirms stress and crowding.
2. The latest Friday drop may have been part of that stress being priced.
3. If NQ cannot reclaim momentum and liquidity/risk factors deteriorate, the short crowd can press the move lower.
4. If NQ stabilizes above the Friday low, the extreme short base increases short-covering rebound risk.

Historically, current-style non-commercial short extremes have been more contrarian bullish than continuation bearish, especially on 2-week to 13-week horizons. For a bearish continuation thesis, price confirmation matters more than the COT extreme itself: renewed weakness below the 2026-06-05 low would matter; a hold and rebound would make the short extreme a squeeze-risk signal.
