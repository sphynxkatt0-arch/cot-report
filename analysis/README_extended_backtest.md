# Extended COT predictivity backtest

## Run on Windows

From the repository root:

```powershell
powershell -ExecutionPolicy Bypass -File analysis/run_extended_backtest.ps1
```

## Run with Python directly

```bash
python -m pip install numpy pandas
python analysis/cot_extended_predictivity.py
```

The script writes all reports and CSVs to:

```text
analysis/cot_extended_predictivity_output/
```

## Run through GitHub Actions

The workflow `.github/workflows/extended-cot-backtest.yml` is manual. Open the Actions tab, select **Extended COT predictivity backtest**, choose the branch to run, and start the workflow. When GitHub-hosted runner capacity is available, the workflow executes the same analysis and commits the generated result directory back to the selected branch.

The workflow is intentionally manual because unavailable GitHub-hosted runner capacity can otherwise leave a permanently failing pull-request check. Three attempted runs on July 25, 2026 terminated before exposing ordinary workflow steps or logs; no statistical output was produced by those runner attempts.

## What is tested

- TFF Detailed: Asset Manager/Institutional, Dealer/Intermediary, Leveraged Funds, Other Reportables, and Nonreportable.
- Legacy: Non-Commercial, Commercial, and Nonreportable.
- Market-specific signals for S&P 500 and Nasdaq-100.
- Net position, long/short exposure, changes over 1–26 weeks, flow acceleration, and selected category divergences.
- Forward horizons from 1 trading day through 52 weeks.
- Fixed Non-Commercial-anchored combinations and a purged expanding walk-forward ridge model.

## Safeguards

- Tuesday COT observations are not treated as tradable until the first close on or after normal Friday publication.
- Z-scores and percentiles use prior observations only.
- Overlapping returns use Newey-West HAC inference.
- P-values receive Benjamini-Hochberg false-discovery-rate adjustment.
- Signals must survive chronological out-of-sample and stability checks to receive a strong evidence label.
- The walk-forward model only trains on forward returns that would already have been observable at each prediction date.

`Nonreportable` is described as a small-trader/retail proxy, not as a verified pure-retail category.
