# COT Dashboard Score Improvement Prompt And Plan

## Working Prompt

You are improving the local COT dashboard in `A:\work\trading\cot report` as a mathematician, data scientist, and pragmatic trading-system engineer.

Goal: rebuild the dashboard scoring layer so it is evidence-weighted, horizon-aware, robust to noisy COT data, and visually clear for trading decisions. Do not simply add more indicators. Make the score more defensible.

Primary files:
- `analysis/build_interactive_cot_dashboard.py`
- `analysis/cot_cross_market_predictivity.py`
- `analysis/cot_regime_score_backtest.py`
- `analysis/cot_legacy_regime_score_backtest.py`
- `analysis/dashboard_template/dashboard.js`
- `analysis/dashboard_template/dashboard.css`
- `analysis/config/regime_rules.json`
- `analysis/config/regime_rules_legacy.json`
- generated output: `analysis/interactive_cot_dashboard.html`

Current known behavior:
- Cross-market short-term bias is built from clipped trailing z-scores using fixed `0.60 * flow_1w_z + 0.40 * flow_4w_z`, with SP500 and NQ positive and VIX inverted.
- Current position score is calculated but not part of the visible short-term bias score.
- Regime score rules are hand-authored threshold/weight JSON rules.
- Backtest evidence shows weak short-horizon predictive power in many places, with stronger evidence at medium/long horizons. The dashboard must not imply high confidence where the statistics do not support it.
- Dealer / Intermediary should remain treated as structural offset inventory, not as a standalone directional player.

Core redesign:
1. Build separate scores by horizon:
   - `flow_timing_score`: 1w/4w, explicitly low confidence unless backtest edge is positive and stable.
   - `positioning_regime_score`: 13w/26w, based on current net/OI, percentile extremes, and historical forward-return evidence.
   - `risk_on_exposure_score`: cross-market SP+NQ-VIX notional score, with VIX inverted and gross-offset penalty.
   - `confidence_score`: sample size, edge stability, data freshness, signal agreement, and model drawdown penalty.
2. Replace fixed weights with evidence-weighted contributions:
   - estimate each feature's sign, effect size, and uncertainty from local backtests;
   - shrink weak/noisy estimates toward zero;
   - cap single-feature contribution so one unstable signal cannot dominate;
   - keep human-readable reason rows showing exactly why the score changed.
3. Use walk-forward validation:
   - expanding percentile ranks only;
   - no use of future data in thresholds or normalization;
   - returns must start after the COT publication delay;
   - compare against simple baselines: always-long, old score, percentile-only, and flow-only.
4. Use robust statistics:
   - prefer percentile/rank transforms and rolling median/MAD or winsorized z-scores over plain mean/std z-scores where outliers distort the score;
   - handle contract-roll/open-interest distortions by comparing absolute contract change, net/OI change, and notional change separately;
   - show when the signal is mostly short-covering, long accumulation, or hedge-pressure change.
5. Improve the UI:
   - show one top decision panel: `Timing`, `Regime`, `Risk-on exposure`, and `Confidence`;
   - separate 1w/4w timing from 13w/26w regime;
   - add evidence badges: observations, edge, HAC p-value/permutation p-value where available, drawdown, and current analog count;
   - show `No edge / weak edge` explicitly instead of forcing Bullish/Bearish labels.

Non-negotiable guardrails:
- Do not reintroduce Dealer / Intermediary as a directional score driver.
- Do not call short-covering long accumulation unless long contracts actually increased.
- Do not promote a score if its backtest edge is negative, unstable, or sample size is too low.
- Do not use combined SP+NQ-VIX exposure as automatically superior; test combined versus single-instrument evidence and display the winner.
- Verify generated HTML and rendered dashboard, not only Python compilation.

Acceptance criteria:
- The new score outputs include feature contribution rows, confidence, horizon, sample size, and evidence source.
- Old and new scores are backtested side by side for S&P 500 and Nasdaq-100 on TFF and Legacy datasets.
- The dashboard defaults to a decision-first view while preserving advanced research sections.
- The dashboard clearly states whether a signal is short-term timing, medium-term regime, or structural positioning context.
- `analysis/interactive_cot_dashboard.html` rebuilds successfully, freshness metadata is current, and the browser render shows the new score blocks without layout overlap.

## Execution Plan

1. Audit current scoring and data contracts.
   - Map every score field currently created in `build_interactive_cot_dashboard.py`.
   - Map every score field rendered in `dashboard.js`.
   - List all generated CSVs used as evidence, especially `risk_exposure_predictivity_*`, `net_position_*`, and `regime_*`.
   - Flag stale or conflicting rules, including any directional Dealer / Intermediary rule.

2. Build a scoring research table.
   - One row per date, dataset, market, player, signal, horizon.
   - Candidate features: net/OI percentile, net z/rank, 1w flow, 4w flow, 13w trend, 26w trend, long change, short change, notional exposure, SP+NQ-VIX exposure, price confirmation since report, peer confirmation.
   - Outcomes: forward returns for 1w, 4w, 13w, 26w, 52w, plus max adverse move/drawdown.
   - Include publication lag and prevent forward leakage.

3. Calibrate evidence weights.
   - Compute effect size, sign, sample size, HAC t/p, permutation p, hit rate edge, average return edge, and drawdown penalty.
   - Apply shrinkage: `effective_weight = signed_effect * confidence_multiplier`.
   - Confidence multiplier should penalize low observations, weak p-values, unstable rolling signs, high drawdown, and stale source data.
   - Keep a transparent rule table so the final score is auditable.

4. Design the new score formula.
   - Use horizon-specific formulas:
     - timing score: flow and price confirmation, heavily confidence-gated;
     - regime score: current position percentile/rank and medium-term edge;
     - exposure score: SP+NQ-VIX notional direction with offset/gross-flow penalty;
     - final actionable score: weighted blend only when confidence passes a minimum threshold.
   - Output `score`, `label`, `confidence`, `horizon`, `evidence_grade`, and `top_contributors`.
   - If evidence is weak, label as `Context only`, not Bullish/Bearish.

5. Backtest old versus new.
   - Compare old regime score, old cross-market bias, new timing score, new regime score, and new final score.
   - Metrics: correlation, HAC slope/t, permutation p, bucket forward returns, win rate edge, average drawdown, worst drawdown, turnover/trigger count.
   - Require improvement versus baseline on at least the target horizon being claimed.

6. Wire into the dashboard.
   - Add top score cards for Timing, Regime, Risk-on Exposure, Confidence.
   - Add a contribution table with signed feature contributions and evidence strength.
   - Add a model comparison panel: old score versus new score.
   - Keep advanced factor/research sections collapsed by default.

7. Validate.
   - Run Python compile checks.
   - Rebuild COT predictivity outputs, regime backtests, and the dashboard.
   - Verify `interactive_cot_dashboard.html` freshness metadata.
   - Open/render the dashboard and check desktop/mobile layouts.
   - Confirm no directional Dealer / Intermediary labels appear.

## First Mathematical Improvements To Try

1. Replace mean/std z-score with robust rank score:
   - `rank_score = 2 * percentile / 100 - 1`
   - Winsorize at the 2.5th/97.5th percentile.
   - This makes extreme COT prints comparable across regimes without one outlier defining the scale.

2. Add evidence shrinkage:
   - `shrunk_edge = raw_edge * n / (n + k)`
   - Start with `k = 75` weekly observations.
   - Then multiply by stability: share of rolling windows where signal sign agrees with full-sample sign.

3. Add drawdown-aware utility:
   - `utility = avg_forward_return - lambda * avg_adverse_move`
   - Use this to avoid scores that predict upside but carry unacceptable adverse path.

4. Add gross-offset penalty to cross-market exposure:
   - `direction_strength = abs(sp + nq - vix) / (abs(sp) + abs(nq) + abs(vix))`
   - If strength is below 0.15, force `Mixed`.
   - Between 0.15 and 0.35, reduce contribution rather than giving full bullish/bearish credit.

5. Split long accumulation from short-covering:
   - bullish accumulation: longs up and net up;
   - short-covering: shorts down and net up;
   - bearish accumulation: shorts up and net down;
   - long liquidation: longs down and net down.
   - Display these as different signal reasons because their forward implications can differ.

6. Score horizon honestly.
   - If 1w/4w evidence is weak but 26w evidence is strong, the UI should say: `Medium-term supportive, short-term timing weak`.
   - Never compress that into one generic bullish score.
