import { test, expect } from '@playwright/test';

test('metal taxonomy copy is driven by v1.3 governed weights', async ({ page }) => {
  await page.route('**/worldclass/market-sentiment.json*', route => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({ schema_version: 1, provider: 'Adanos', sources: ['reddit', 'x', 'news', 'polymarket'], history_count: 0, latest: null, history: [] })
  }));
  await page.route('**/worldclass/live-track-record.json*', route => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({ schema_version: 1, forecast_count: 0, entry_count: 0, outcome_count: 0, weekly_vintage_count: 0, matured_signal_count: 0, complete_signal_count: 0, open_signal_count: 0, current_predictions: [], model_comparison: [], model_versions: [], ledger: { integrity: 'PASS', latest_manifest_hash: 'GENESIS' } })
  }));

  await page.goto('/worldclass_dashboard.html');
  await page.waitForFunction(() => window.__COT_WORLDCLASS_BASE__?.MODEL_SPEC?.model_version === '1.3.0');
  await page.locator('#instrumentTabs [data-market="gold"]').click();

  const banner = page.locator('#wcTaxonomyBanner');
  await expect(banner).toBeVisible();
  await expect(banner).not.toContainText('modeled inversely');
  await expect(banner).not.toContainText('modeled inversely/contrarian');

  const managed = banner.locator('.wc-role', { hasText: 'Managed Money' });
  await expect(managed).toContainText('DIRECTIONAL INPUT');
  await expect(managed).toContainText('score weight +1.00');

  const other = banner.locator('.wc-role', { hasText: 'Other Reportables' });
  await expect(other).toContainText('CONTEXT ONLY');
  await expect(other).toContainText('score weight 0.00');

  const nonreportable = banner.locator('.wc-role', { hasText: 'Non-reportable' });
  await expect(nonreportable).toContainText('CONTEXT ONLY');
  await expect(nonreportable).toContainText('score weight 0.00');
});
