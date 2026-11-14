# Macro → Price Action Backtest — 2026-08-14

## Governance decision

**Aggregate `liquidity_score` has 0 directional weight in the command center.**

The production aggregate score showed no statistically robust standalone predictive relationship with subsequent SPX or Nasdaq-100 returns at 1W, 2W, 4W, 13W, or 26W horizons. It remains useful as descriptive macro context, but it must not be counted as a bullish/bearish vote, confirmation layer, or disagreement layer until a point-in-time/vintage-safe rebuild validates a directional model.

## Data and sample

- Source: deployed GitHub Pages runtime artifact, `model_output/macro_history.csv`.
- Source artifact id: `9202356162` (`github-pages`, head `gh-pages@d455e938554947fb15c50aa17e25c614d973e3c0`).
- Date range: `2023-06-07` through `2026-08-13`.
- Daily rows: 1,164.
- Primary sample: one observation per week (`W-FRI`) to reduce pseudo-replication from forward-filled daily macro values.
- Weekly rows before horizon truncation: 167.
- Markets: S&P 500 and Nasdaq-100.
- Horizons: 1W, 2W, 4W, 13W, 26W.

## Aggregate score result

| Horizon | Pearson SPX | Spearman SPX | HAC p SPX | Pearson NQ | Spearman NQ | HAC p NQ |
|---|---:|---:|---:|---:|---:|---:|
| 1W | -0.032 | -0.016 | 0.651 | -0.023 | -0.008 | 0.740 |
| 2W | -0.048 | -0.046 | 0.542 | -0.048 | -0.044 | 0.535 |
| 4W | -0.053 | -0.037 | 0.605 | -0.015 | -0.022 | 0.878 |
| 13W | +0.001 | +0.023 | 0.993 | +0.005 | +0.031 | 0.957 |
| 26W | +0.058 | +0.092 | 0.562 | +0.065 | +0.119 | 0.506 |

Levels, 1W/4W/8W changes, acceleration, and plumbing-score variants also failed family-level robustness.

## Strong factor-level findings

The aggregate failure does **not** mean every macro variable is useless. Several factor-level relationships deserve further point-in-time validation:

- **VIX:** contrarian/rebound association, strongest at 13W. NQ 13W Spearman `+0.441`, HAC `p < 1e-6`, chronological OOS R² `+34.7%`.
- **HY OAS:** strong 13W/26W rebound relationship. SPX 26W Spearman `+0.652`, HAC `p = 0.00061`, OOS R² `+11.0%`.
- **Net liquidity 13W change:** positive 13W/26W association. SPX 13W Spearman `+0.374`, NQ 13W `+0.370`.
- **TGA 4W change:** weak/moderate 2W candidate only; it does not survive the same multiple-testing standard.
- **10Y real yield:** SPX 26W candidate; requires more history and vintage-safe replication.

These are not yet promoted to production directional weights because the current historical macro layer is calendar-aligned rather than fully release/vintage-safe.

## Dashboard integration

`analysis/worldclass/terminal-v3.js` is updated with this governance rule:

1. Macro remains visible as **Macro context**.
2. Aggregate macro score contributes **0 directional weight**.
3. Macro no longer participates in risk-on/risk-off alignment.
4. Macro no longer creates a positioning-vs-macro tension.
5. Confirmation/invalidation logic uses COT positioning and price, not the aggregate macro score.
6. Future factor-level macro edges must be added horizon-by-horizon only after point-in-time validation.

## Saved evidence

- `aggregate_score_summary.csv` — the ten production `liquidity_score` horizon tests used for the zero-weight decision.
- `top_factor_findings.csv` — curated factor/horizon rows discussed in the research verdict.
- `net_liquidity_incremental_controls.csv` — 13W-change incremental tests controlling for price state and VIX.
- `methodology_and_formula.json` — inferred production score weights and reconstruction diagnostics.
- `manifest.json` — provenance and hashes for the saved research evidence.

The larger exploratory matrices were generated from the same deployed source and remain research-only; the repository persists the decision-critical rows rather than treating every exploratory test as a production artifact.

## Production score reconstruction

Inferred aggregate weights:

- net liquidity: 26%
- bank reserves: 10%
- Treasury supply: 10%
- repo spread: 8%
- SLR load: 4%
- real yields: 14%
- credit: 14%
- dollar: 8%
- VIX: 6%

`score_market_trend` is not part of the inferred aggregate score.

## Caveat / promotion rule

This backtest is **research evidence**, not final causal proof. The historical macro dataset is not fully vintage/release-safe. Before any factor receives non-zero production directional weight, rebuild the macro history with point-in-time vintages and actual publication lags, rerun HAC/non-overlap/era/OOS tests, and require stability across those checks.
