# Vercel COT dashboard

This repository root is a Vercel-native COT dashboard.

- `/` serves the S&P 500 and Nasdaq-100 consolidated futures report.
- `/api/cot` queries the official CFTC Public Reporting Environment.
- `vercel.json` calls `/api/cot` every day at 20:35 UTC.
- `/api/cot` is the runtime freshness authority for the S&P 500 and Nasdaq-100 dashboard.
- API responses use a short 5-minute shared cache with 1 minute of stale-while-revalidate so a Friday release cannot be pinned behind a near-day cache entry.
- The validated GitHub refresh sync commit must not contain `[skip ci]`, because that commit is also the Vercel production deployment trigger.

## Data

- TFF Futures Only: `gpe5-46if`
- Legacy Futures Only: `6dca-aqww`
- S&P 500 Consolidated: `13874+`
- Nasdaq-100 Consolidated: `20974+`

Net position is long minus short. The 3-year percentile uses up to 156 weekly observations.
