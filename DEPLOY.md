# Deploying the COT Dashboard

The COT dashboard is a **self-contained HTML file** (~13 MB) with all historical data
embedded as JSON. Deployment is simply a matter of hosting this static file.

---

## Option A: GitHub Pages (Recommended, Free)

The included GitHub Actions workflow automatically refreshes data and deploys
every week.

1. **Push** the repository to GitHub.
2. Go to **Settings → Secrets and variables → Actions** and add:
   | Secret | Description |
   |---|---|
   | `FRED_API_KEY` | Your [FRED API key](https://fred.stlouisfed.org/docs/api/api_key.html) *(optional – fallback data exists)* |
3. Go to **Settings → Pages** and set **Source** to **"GitHub Actions"**.
4. The workflow triggers automatically on:
   - Push to `main`
   - **Every Saturday at 08:00 UTC** (COT data releases Friday)
   - Manual dispatch from the **Actions** tab
5. To trigger manually: **Actions → "Refresh and Deploy" → Run workflow**.

> [!TIP]
> If the refresh step fails (API downtime, rate limits), the workflow still
> deploys the last successfully built HTML so the site stays up.

---

## Option B: Vercel (Static, Free)

A `vercel.json` is included for quick static deploys.

```bash
# 1. Install Vercel CLI
npm i -g vercel

# 2. Rebuild the dashboard locally
python analysis/serve_interactive_cot_dashboard.py --refresh-only

# 3. Deploy
vercel --prod
```

> [!NOTE]
> Vercel free tier has no cron/build support. You must rebuild locally and
> redeploy whenever you want fresh data. Combine with GitHub Actions for
> automation.

---

## Option C: Cloudflare Pages (Static, Free)

1. Connect your GitHub repository in the Cloudflare Pages dashboard.
2. **Build command**: leave empty (the HTML is pre-built).
3. **Output directory**: `analysis`
4. Deploy. Cloudflare will serve the static files with its global CDN.

---

## Local Development

```bash
# Full refresh + open in browser
python analysis/serve_interactive_cot_dashboard.py --open

# Refresh data only (no server)
python analysis/serve_interactive_cot_dashboard.py --refresh-only

# Serve existing HTML without re-fetching data
python analysis/serve_interactive_cot_dashboard.py --skip-refresh

# Refresh without legacy analysis (faster)
python analysis/serve_interactive_cot_dashboard.py --refresh-only --no-legacy
```

### FRED API Key

Provide your key via **either**:
- Environment variable: `export FRED_API_KEY=your_key`
- File: `analysis/config/fred_api_key.txt`

Get a free key at <https://fred.stlouisfed.org/docs/api/api_key.html>.

---

## Important Notes

| Topic | Detail |
|---|---|
| **File size** | The dashboard HTML is ~13 MB because it embeds all historical data as inline JSON. |
| **Plotly.js** | The template includes a CDN fallback, so the dashboard works even without the local `plotly-2.35.2.min.js`. |
| **FRED key** | Optional – the pipeline has fallback data sources for most series. |
| **Update cadence** | COT data updates weekly (Friday release). Daily rebuilds are unnecessary. |
| **Fear & Greed** | The sub-project `fear-greed-data-main/` fetches CNN Fear & Greed data. It runs automatically during refresh. |
