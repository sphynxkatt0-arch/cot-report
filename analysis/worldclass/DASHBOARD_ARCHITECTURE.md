# Dashboard architecture

This is the runtime ownership contract for `worldclass_dashboard.html`. The goal is to keep one stable application shell while allowing deep analytical modules to remain independently maintainable.

## Canonical page hierarchy

`topbar` and `instrument-bar` are persistent global chrome. `#currentEdgeCommand` is the only top-level decision shell and owns the primary navigation (`Today`, `Charts & data`, `Research`, `Live Record`) plus URL state for market, horizon, view and model family.

Specialist content lives in exactly one explicit workspace below that shell:

- `#dataWorkspace`: chart controls, holdings history, weekly changes, positioning, macro, methodology, taxonomy, sentiment and other analytical enhancements.
- `#researchWorkspace`: `#cotIntelligence` plus `#wcCrossActorPanel`.
- `#liveWorkspace`: `#liveTrackRecordPanel`.

Today is rendered entirely by `#currentEdgeCommand` and does not unhide unrelated legacy sections.

## State ownership

The URL is the durable navigation contract: `market`, `horizon`, `view`, `model` and report-family parameters must survive top-level view changes. `current-edge-command.js` applies URL state first and synchronizes the instrument bar through explicit selection events. Rendering must never infer a default active DOM tab and overwrite a valid requested market during asynchronous startup.

## Mounting rules

No feature module may `prepend()` a new application to `<main>` or insert a competing top-level dashboard after the instrument bar. Research and live modules mount directly into their named workspaces. Data enhancements mount relative to anchors already inside `#dataWorkspace`, which keeps their DOM ownership contained automatically.

`terminal-v3.js` is a retired UI owner and is intentionally not booted. Its cross-market actor analysis remains available through the standalone `cross-actor.js` module.

## Styling rules

Route visibility is controlled only at workspace level. Do not reintroduce CSS routing that individually toggles a long list of `main > ...` components with `!important`; that was the main source of visual diffusion and tab-specific page identities.

Module CSS must remain scoped beneath the module root. Research overrides in `current-edge-command.css` normalize specialist panel geometry to the shared shell without changing statistical calculations.

## Regression contract

`analysis/e2e/worldclass-cot-ux-order.spec.mjs` verifies that specialist modules have the correct parent workspace, the primary shell remains above Research, only one workspace is visible at a time, and market/horizon/model state survives tab switches. `worldclass-command-center.spec.mjs` verifies that the retired duplicate command center is not mounted. The remaining Worldclass suites cover taxonomy, cross-actor research, accessibility, mobile overflow and data functionality.
