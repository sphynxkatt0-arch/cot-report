# COT Direction Model v1

## Decision hierarchy

1. **Legacy Non-commercials set structural direction.** Equity-index calibration is contrarian: historically low Non-commercial positioning is bullish support; historically high positioning is a crowding warning.
2. **TFF data modifies conviction only.** Other Reportables and Nonreportables use 13-week trend ranks; Legacy Non-commercial four-week flow identifies confirmation versus continued accumulation/liquidation.
3. **Asset Managers modify size only.** Above the 90th percentile, the default exposure multiplier is 0.75. Asset Managers cannot reverse the structural sign.
4. **Macro modifies size or blocks execution.** The existing macro score is used as a risk multiplier. Multiple severe red alerts produce a hard-risk override.
5. **Price controls execution.** Returns and confirmation start from the scheduled Friday release date, not Tuesday's COT as-of date.

## Important limitations

- Historical actual CFTC publication timestamps are not available in the current repository. The first implementation records Friday as a `scheduled_assumption` and reduces confidence accordingly.
- Nonreportables are a small-trader/retail proxy, not verified pure retail.
- The current post-release price source is a daily index close. It is not futures VWAP.
- The model is designed for S&P 500 and Nasdaq-100. Do not transfer the direction sign to commodities or FX without separate calibration.

## Outputs

- `model_output/cot_direction_latest.json`
- `model_output/cot_direction_latest.csv`
- `directional_cot_report.html`

## Run

```powershell
py build_directional_cot_report.py
```

For a full refresh and build, double-click `start_directional_cot_report.cmd`.
