# Deploying COT Intelligence

The production dashboard now uses a **lightweight application shell + compact runtime data**, while the large full-history research HTML remains a build/research artifact. The public site should not serve the multi-megabyte research document as its root page.

## GitHub Pages production setup

In **Settings → Pages**, keep **Source = GitHub Actions**.

The `Refresh and Deploy` workflow is the authoritative production pipeline. It:

1. Validates Python/JavaScript syntax, the canonical model specification, macro parsers, live-ledger integrity, data contracts and lookahead safety.
2. Refreshes CFTC/FRED/Treasury/OFR inputs on scheduled/manual refreshes.
3. Builds the compact `worldclass/base.json`, research/backtest artifacts, model identity and macro-control-room payload.
4. Builds a lightweight Pages artifact containing the production shell, `worldclass/` runtime assets, macro payload and chart runtime. The multi-megabyte `interactive_cot_dashboard.html` research artifact is intentionally excluded from the public Pages artifact.
5. Uploads the artifact with one-day retention and deploys it using the official `actions/deploy-pages` path required by the repository's **GitHub Actions** Pages source.
6. Publishes the full `analysis/` directory to `gh-pages` as a **last-valid cache/mirror** used by refresh recovery and integrity tooling. `gh-pages` is not the configured public Pages source.
7. Runs public production-contract checks against the actual `github.io` URL. The checks require a lightweight root shell, the canonical model identity, guarded runtime bootstrap and populated macro-control-room pillars.

### Why both Pages Actions and `gh-pages` exist

The repository previously switched from Pages artifacts to direct `gh-pages` publishing because accumulated deployment artifacts hit storage limits. That left the repository's Pages setting (`GitHub Actions`) inconsistent with the deployment method. The current workflow solves both problems:

- old `github-pages` deployment artifacts are removed before upload;
- the new Pages artifact has one-day retention;
- the public artifact excludes the large research HTML;
- `gh-pages` remains available for last-valid data/cache recovery without being mistaken for the active Pages source.

## Production URL

`https://sphynxkatt0-arch.github.io/cot-report/`

A healthy deployment must serve the lightweight `index.html` shell from this URL. The production contract fails if the root grows above 200 KB or if it contains the embedded `const COT_DATA = ...` research payload.

## Automated schedule

CFTC refresh is scheduled for **Friday at 21:35 Europe/Stockholm**. Two UTC cron expressions are used and a timezone gate selects the one that maps to 21:35, so CET/CEST changes do not move the intended local refresh time.

If the expected CFTC release is delayed, the dashboard keeps the last valid observations and exposes the delayed state instead of fabricating a neutral update.

## Required / optional secrets

| Secret | Purpose |
|---|---|
| `FRED_API_KEY` | Optional FRED API access. The pipeline retains last-valid data/fallback paths when the key/feed is unavailable. |

GitHub's automatically supplied `GITHUB_TOKEN` handles branch mirrors, artifact cleanup and Pages deployment using the workflow permissions declared in `.github/workflows/refresh-and-deploy.yml`.

## Production data safeguards

The deployment is blocked or repaired when any of these contracts fail:

- required index/metal COT coverage and valid dates;
- price history availability;
- canonical `MODEL_SPEC` version/hash;
- lookahead-safe backtests;
- compact runtime bundle integrity;
- macro core fields (net-liquidity impulse, reserve impulse/level, funding spread);
- server macro-control-room pillars;
- public Pages lightweight-shell and macro rendering contract.

The hourly `Runtime Bundle Integrity` workflow independently checks the published compact bundle and repairs the `gh-pages` mirror from canonical source data when needed.

## Local development

```bash
# Full refresh + local server
python analysis/serve_interactive_cot_dashboard.py --open

# Refresh data only
python analysis/serve_interactive_cot_dashboard.py --refresh-only

# Serve existing data without refreshing
python analysis/serve_interactive_cot_dashboard.py --skip-refresh
```

The research HTML is intentionally large because it embeds historical data. That size is acceptable for research/build use; it is no longer the intended public root document.
