# Extended COT predictivity backtest

Run locally from the repository root:

```bash
python -m pip install numpy pandas
python analysis/cot_extended_predictivity.py
```

The script writes its results to `analysis/cot_extended_predictivity_output/`.

The GitHub Actions workflow `.github/workflows/extended-cot-backtest.yml` runs the same analysis for pull requests and can also be started manually. The workflow uploads the complete result directory as the `cot-extended-predictivity-results` artifact.

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
