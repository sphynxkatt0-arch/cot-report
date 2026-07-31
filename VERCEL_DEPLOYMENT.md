# Vercel COT dashboard

This repository root is a Vercel-native COT dashboard.

- `/` serves the S&P 500 and Nasdaq-100 consolidated futures report.
- `/api/cot` queries the official CFTC Public Reporting Environment.
- `vercel.json` calls `/api/cot` every day at 20:35 UTC.
- Responses are cached at the Vercel edge for 23 hours with one hour of stale-while-revalidate.
- `/full-report` opens the existing research dashboard in `analysis/interactive_cot_dashboard.html`.

## Data

- TFF Futures Only: `gpe5-46if`
- Legacy Futures Only: `6dca-aqww`
- S&P 500 Consolidated: `13874+`
- Nasdaq-100 Consolidated: `20974+`

Net position is long minus short. The 3-year percentile uses up to 156 weekly observations.
