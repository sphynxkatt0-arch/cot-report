# Deploying COT Intelligence

Production is built as a validated static release from the `analysis/` tree and published to `gh-pages`. The large full-history research artifacts remain build/research inputs; the production root is `analysis/index.html`, generated from the validated world-class dashboard shell.

## Authoritative production pipeline

`.github/workflows/refresh-and-deploy.yml` is the only authoritative build/deploy workflow. It runs on:

- every push to `main`;
- manual `workflow_dispatch`;
- the DST-safe Friday 15:35 New York scheduled refresh.

A separate `.github/workflows/cot-refresh-dispatch.yml` exists only as the Friday 16:35 New York retry/manual dispatcher. It no longer dispatches on `main` pushes, avoiding duplicate refresh jobs racing or cancelling one another.

Every authoritative run performs the following sequence:

1. Validate Python/JavaScript syntax and governed research/model contracts.
2. Refresh the raw normalized CFTC source layer. **A `main` push now refreshes CFTC data too**; it is not allowed to rebuild production from an intentionally stale normalized snapshot.
3. Refresh the metals and macro inputs, retaining last-valid caches only where the source layer explicitly permits it.
4. Build current context plus the frozen release-corrected-v2 historical research artifacts.
5. Validate the current CFTC report date against the report that should already be public. A stale week therefore blocks deployment instead of being published as `LIVE`.
6. Build prospective live-ledger forecasts and the presentation track record.
7. Copy the validated dashboard shell to `analysis/index.html`.
8. Generate `analysis/worldclass/release-manifest.json`, containing the source commit, release ID, file sizes, and SHA-256 hashes for the production runtime surface.
9. Verify every manifest hash before deployment.
10. Publish the whole validated `analysis/` tree to `gh-pages` as one force-orphan release commit.
11. Fetch the published `gh-pages` tree back and verify the research contract and every release-manifest hash again.

This makes the static publish unit the **entire validated release tree**, not individual files. A new JavaScript shell cannot be intentionally paired with an older COT JSON payload, and a partial/mixed-version runtime fails release verification.

## Production URL

`https://sphynxkatt0-arch.github.io/cot-report/`

The public site should always represent the same release recorded by `worldclass/release-manifest.json` and the current report status recorded by `worldclass/release-status.json`.

## CFTC timing

The normal CFTC refresh is scheduled for **Friday at 21:35 Europe/Stockholm during CEST** / the equivalent 15:35 New York release-follow-up time. The workflow uses two UTC cron candidates and an America/New_York timezone gate so DST changes do not shift the intended New York execution time.

A second dispatcher checks at **16:35 New York time** as a retry. If the expected CFTC release is genuinely delayed, the validator preserves the last valid observation but marks the release as delayed; it must not fabricate a new neutral report or label stale data as current.

## Governed model contract

Production decisions follow the tri-partite contract:

- **COT = directional thesis.** Legacy Non-commercial positioning defines structural direction; tactical TFF evidence may strengthen or weaken an already actionable thesis without reversing it.
- **Price = execution.** Price determines waiting, confirmation, contradiction, and invalidation.
- **Macro = context / risk budget.** Aggregate macro is calendar-aligned but not proven point-in-time vintage safe, so its production directional weight is `0.0` and its production multiplier is fixed at `1.0`. Independent hard-risk overrides remain active.

The macro adapter uses one canonical weighting pass:

- Plumbing: **48%**
- Transmission: **42%**
- Supply: **10%**

Missing or stale macro evidence is shrunk toward neutral using:

`effective_score = 50 + availability_confidence * (observed_score - 50)`

The adapter emits `macro_context`, `macro_risk_budget`, and `macro_directional_edges` so the UI/research layer can show the context without quietly turning it into unsupported directional sizing.

## Backtest independence contract

The regime backtest continues to report raw weekly observations, but raw N is not treated as independent evidence for multi-week horizons. Each horizon now reports:

- `observations`: raw realized weekly signals;
- `non_overlapping_n`: signals spaced by at least that forward horizon in trading days;
- `regime_episode_n`: contiguous weekly matches to the same regime collapsed into episodes;
- `effective_n = min(non_overlapping_n, regime_episode_n)`.

Confidence labels use `effective_n`. Historical macro evidence remains explicitly tagged `macro_vintage_safe: false` until genuine vintage-safe replication is available.

## Release manifest

`analysis/build_release_manifest.py` is part of the production contract. The generated manifest records:

- `release_id`;
- `source_commit`;
- aggregate release-content SHA-256;
- every included runtime path, byte size, and SHA-256;
- `mixed_version_runtime_allowed: false`;
- required pre-deploy and post-deploy verification.

Manual verification against an already built tree:

```bash
python analysis/build_release_manifest.py --root analysis --verify
```

## Required / optional secrets

| Secret | Purpose |
|---|---|
| `FRED_API_KEY` | Optional FRED API access. The pipeline retains governed last-valid/fallback paths when this feed is unavailable. |

GitHub's automatically supplied `GITHUB_TOKEN` handles the release publish, retry dispatcher, live-ledger writes, and branch verification using the workflow permissions declared in the repository.

## Local validation

```bash
# Governed regression tests added for macro weighting/shrinkage and sample independence
python analysis/tests/test_governed_cot_contract.py

# Release-corrected production validator
python analysis/validate_worldclass_release_v2.py

# Build/verify a release manifest after production outputs exist
cp analysis/worldclass_dashboard.html analysis/index.html
python analysis/build_release_manifest.py --root analysis
python analysis/build_release_manifest.py --root analysis --verify
```

The production validator is expected to fail rather than deploy when the currently public CFTC report has not been incorporated correctly.
