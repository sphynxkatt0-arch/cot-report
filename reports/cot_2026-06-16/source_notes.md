# Source and QA Notes

## Controlling sources

- Official CFTC current report page: https://www.cftc.gov/MarketReports/CommitmentsofTraders/index.htm
- TFF Futures Only weekly feed: https://www.cftc.gov/dea/newcot/FinFutWk.txt
- Legacy Futures Only weekly feed: https://www.cftc.gov/dea/newcot/deafut.txt
- Local refreshed TFF extracts: `analysis/cot_exact_output/*_exact_consolidated_data_2016_2026.csv`
- Local refreshed Legacy extracts: `analysis/cot_legacy_output/*_legacy_data_2016_2026.csv`
- Local regime histories: `analysis/cot_regime_backtest_output/regime_score_history.csv` and `analysis/cot_legacy_regime_backtest_output/regime_score_history.csv`

## Validation checks

- Dashboard metadata and all four source extracts end on 2026-06-16.
- Official CFTC viewable TFF and Legacy pages show the same open interest and participant positions used here.
- Latest rows were compared with 2026-06-09 by direct subtraction of long, short, and net contracts.
- Open-interest changes were checked independently because quarterly rollover makes net/OI deltas less reliable.
- TFF and Legacy totals were not added together because classifications overlap.

## Chart map

1. `current_net_oi.png`: Comparison & Ranking / faceted diverging horizontal bars; current net/OI by report, market, and participant; two-root signed palette.
2. `positioning_percentiles.png`: Uncertainty & Benchmark / faceted horizontal bars; current expanding-window percentile with 10th/90th reference lines; single-root palette plus neutral/orange references.

## Report structure mapping

- Title: report header.
- Executive summary: visible answer-first summary.
- Key findings with visual evidence: S&P section, Nasdaq section, net/OI chart, percentile chart.
- Recommended next steps: trading read and next confirmation points.
- Further questions: what would change the call.
- Caveats and assumptions: rollover, reporting lag, classification overlap, and non-causal backtest caveat.

## QA result

Ready to share with caveats. The material caveat is quarterly rollover: absolute contract changes are emphasized over net/OI percentage changes.

The HTML structure, required section order, table row counts, image references, and executed notebook were validated programmatically. Both PNG charts were visually inspected at full resolution. A full-page browser render of the local HTML was not available because the in-app browser blocked the local `file://` URL under its security policy.
