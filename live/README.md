# COT live forecast ledger

This branch is the authoritative prospective record for live COT forecasts and realized outcomes.

## Invariants

- Forecast files are append-only and immutable after first publication.
- Entry and outcome files are separate from forecasts.
- Re-running automation may not overwrite or alter an existing forecast, entry, outcome, or manifest entry.
- Every forecast is identified deterministically from report date, market, dataset, model family, model version, and model-spec hash.
- Every forecast is covered by the application-level SHA-256 manifest chain.
- Historical research may be rebuilt; this prospective ledger may not be rewritten to match a later model version.
- A new model version starts a new prospective series and never rewrites older forecasts.

## Layout

```text
live/
  forecasts/<year>/<release-date>/...
  entries/...
  outcomes/<signal-id>/<horizon>.json
  manifests/...
```

The `gh-pages` branch is presentation output only and is not an authoritative live-history store.
