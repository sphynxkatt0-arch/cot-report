# BSS COT Dashboard Comparison

Date reviewed: 2026-06-24

Sources inspected:
- https://130-162-209-238-sslip-io.guruflix.biz/bss-cot/#desk
- https://130-162-209-238-sslip-io.guruflix.biz/bss-cot/#nq
- https://130-162-209-238-sslip-io.guruflix.biz/bss-cot/api/data
- https://130-162-209-238-sslip-io.guruflix.biz/bss-cot/api/chart?key=nq

Important caveat: use BSS as a product and workflow reference, not as a direct data replacement. Its NQ Non-Commercial net differs from the local Legacy NQ consolidated record, so any copied idea should be rebuilt from the local CFTC pipeline and existing predictivity outputs.

## Useful BSS Patterns

1. Scanner-first workflow
   - BSS opens with a Setup Finder that ranks instruments by a composite 0-100 score.
   - Components are positioning, smart-vs-retail disagreement, price divergence, statistical extreme, and conviction/gas.
   - This creates an immediate answer to: "What is worth looking at this week?"

2. Desk overview before deep charts
   - The Positioning Desk summarizes top setups, then groups market tables.
   - The user can scan bias, net, weekly change, percentiles, z-score, and signal label before opening a full chart.

3. Instrument brief is decision-shaped
   - NQ example as of 2026-06-16: Non-Commercial net -8,908, weekly change -7,559, 10.6 percentile, gas 63.7/100, strong institution-vs-retail divergence, price confirmed the bearish read by moving -0.63% since report, and 2 of 3 index peers confirmed.
   - The flow is verdict -> key numbers -> what changed -> who drove it -> crowding -> price confirmation -> peers -> playbook -> chart.

4. Chart payload is compact and task-specific
   - NQ chart payload lazy-loads only 25 daily price bars, 16 anchored VWAP points, and 104 COT points.
   - The full dashboard avoids loading heavy Plotly by default; larger charting is lazy-loaded only when needed.

5. Methodology is visible near the signal
   - The score explanation sits directly under the scanner.
   - Full "what this is not" and 5-step routine are collapsible, so education is available without dominating the default view.

## Current Local Dashboard Strengths

1. Stronger source/freshness layer
   - The generated dashboard exposes COT, price, factor, liquidity, funding, macro, and source freshness metadata.
   - Current generated artifact shows COT latest 2026-06-16 and macro inputs through 2026-06-23 where available.

2. Better evidence layer
   - The local project has a reusable predictivity script and CSV outputs for player-level forward-return tests.
   - This is more defensible than a pure heuristic scanner if surfaced correctly.

3. Better market-specific control surface
   - The current workbench has report selection, market selection, metric selection, factor overlays, threshold scanner, axis zoom, drag mode, line styling, range slider, and Plotly controls.

4. Better cross-market equity risk lens
   - The current dashboard already compares S&P 500, NASDAQ-100, and VIX with explicit VIX inversion logic.

## Gaps To Improve

1. Add a scanner/desk view above the workbench
   - Current default view starts with the full workbench and many sections. Add a compact "This week's actionable setups" panel before the chart.
   - Rank rows with a local score using existing fields: percentile distance from 50, 26w z-score, 1w/4w flow z-score, price divergence, peer confirmation, and backtested edge.

2. Turn predictivity into a visible signal badge
   - The current local evidence says Legacy Commercial/Noncommercial net_z has the strongest forward-return edge for NQ 13w/26w.
   - Add "Backtested edge" to the snapshot and scanner rows instead of leaving it buried in CSV/report panels.

3. Create an instrument brief mode for NQ/SP/VIX
   - For the selected market, show: verdict, key numbers, long-vs-short decomposition, crowding, price confirmation since report, peer confirmation, and playbook.
   - Keep the existing Market Workbench as the deep chart section below the brief.

4. Rename "risk" surface text where possible
   - Keep the formula if desired, but display it as "equity-beta positioning" or "SP+NQ-VIX risk-on exposure".
   - This reduces confusion because the value is positioning exposure, not realized/portfolio risk.

5. Add BSS-style peer confirmation
   - For local scope, start with ES/SP500, NQ, and VIX.
   - Display "confirmed / mixed / divergent" using direction, flow, and cross-market total-risk contribution.

6. Add anchored price response panel
   - A compact panel should answer: price since COT report, did it confirm the positioning read, and where is price relative to an anchored VWAP/mean from a prior COT release.
   - Use lazy loading or optional rendering to avoid making the main dashboard heavier.

7. Separate default and advanced workflows
   - Default: Desk -> brief -> chart -> evidence.
   - Advanced: liquidity model, macro monitor, backtests, research findings, source tables.
   - This keeps the current dashboard powerful without making first use feel like a research archive.

## Suggested Build Order

1. Build a local scanner dataset from current COT records plus predictivity CSVs.
2. Add a top "Weekly Desk" panel to the existing template.
3. Add instrument brief cards below the summary strip and above the current Market Workbench.
4. Add peer confirmation and price-since-report cards.
5. Add optional anchored VWAP/anchored mean panel for selected market.
6. Move advanced macro/research sections behind clearer tabs or collapsed groups.

## Implementation Status

Updated: 2026-06-25

- Done: local weekly scanner payload and top Weekly Desk section.
- Done: visible backtested-edge badges from the local predictivity CSVs.
- Done: selected-market instrument brief with dominant read, driver, evidence, and price check.
- Done: peer confirmation and price-since-report confirmation.
- Done: anchored price response using post-report mean, high, low, and latest distance from that anchor. This is an anchored mean, not VWAP, because the local FRED price series do not carry volume.
- Done: visible "total risk" wording changed to "risk-on exposure" while preserving the SP+NQ-VIX calculation.
- Done: Dealer / Intermediary is excluded from directional setup ranking and cross-market risk-on reads because it is treated as structural offset inventory, not standalone demand.
- Done: lower-level Factor Predictivity, Regime Backtest Evidence, and Research Findings cards now start collapsed so the default workflow stays desk-first.
