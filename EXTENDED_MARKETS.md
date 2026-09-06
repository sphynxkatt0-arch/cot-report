# Five-market governed COT pipeline

The directional pipeline now covers five markets with one release-aligned decision hierarchy:

| Market | Legacy futures-only | Tactical / crowding report | Exact CFTC row | Price series |
|---|---|---|---|---|
| S&P 500 | Legacy | TFF | `13874+` — S&P 500 Consolidated | `SP500` |
| Nasdaq-100 | Legacy | TFF | `20974+` — NASDAQ-100 Consolidated | `NASDAQ100` |
| Russell 2000 | Legacy | TFF | `239742` — RUSSELL E-MINI | `RUSSELL2000` / Yahoo `^RUT` |
| Dow Jones | Legacy | TFF | `12460+` — DJIA Consolidated | `DJIA` / Yahoo `^DJI` |
| Gold | Legacy | Disaggregated | `088691` — GOLD, COMEX | `GOLD` / Yahoo `GC=F` |

## Contract integrity

Dow, S&P 500, and Nasdaq-100 use exact CFTC consolidated parent rows. Gold uses the exact primary COMEX Gold row and excludes Micro Gold. CFTC currently does **not** publish a Russell 2000 consolidated parent row in the financial futures-only file, so Russell uses the exact primary E-mini row `239742`; Micro Russell, annual-dividend, and Russell 1000 rows are excluded. The selection mode and note are exposed in every decision and validated through `model_output/cot_market_refresh_manifest.json`.

## Report-family mapping

Financial indices retain the existing hierarchy:

1. Legacy Non-commercial percentile sets structural direction.
2. TFF Other Reportables, Nonreportables, and Non-commercial flow modify conviction without reversing the structural sign.
3. Asset Manager crowding changes size.
4. Macro, release, evidence, liquidity-plumbing, and price-execution guards remain downstream.

Gold uses the same hierarchy, but the secondary report is CFTC Disaggregated Futures Only:

1. Legacy Non-commercial percentile sets structural direction.
2. Disaggregated Other Reportables, Nonreportables, and Legacy Non-commercial flow modify conviction.
3. Managed Money crowding changes size.
4. Macro, release, evidence, liquidity-plumbing, and price-execution guards remain downstream.

## Refresh

`refresh_directional_cot_system.py` first runs the existing public dashboard refresh and then `refresh_extended_cot_markets.py`. The extended refresher downloads exact CFTC data, refreshes Russell/Dow/Gold prices, writes the contract manifest, and feeds all five markets through input validation, historical comparison, latest decisions, weekly participant changes, report/dashboard injection, and v1.2 output validation.
