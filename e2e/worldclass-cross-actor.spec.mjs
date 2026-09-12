import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

async function openDashboard(page) {
  await page.goto('/worldclass_dashboard.html?view=research&research=positioning');
  await expect(page.getByRole('heading', { name: 'COT Intelligence' })).toBeVisible();
  await page.waitForFunction(() => Boolean(window.__COT_WORLDCLASS_BASE__?.MODEL_SPEC));
  await page.waitForFunction(() => document.documentElement.dataset.cotDecisionView === 'research');
  await expect(page.locator('#wcCrossActorPanel')).toBeVisible();
}

test('restores same-actor S&P + NQ - VIX aggregation', async ({ page }) => {
  await openDashboard(page);

  const panel = page.locator('#wcCrossActorPanel');
  await expect(panel).toContainText('CROSS-INSTRUMENT ACTOR TREND');
  await expect(panel).toContainText('Same participant, combined across equity-risk futures');
  await expect(panel.locator('[data-cross-actor]')).toHaveCount(4);
  await expect(panel.locator('[data-cross-actor="asset_mgr"]')).toBeVisible();
  await expect(panel.locator('[data-cross-actor="lev_money"]')).toBeVisible();
  await expect(panel.locator('[data-cross-actor="other_reportable"]')).toBeVisible();
  await expect(panel.locator('[data-cross-actor="non_reportable"]')).toBeVisible();

  const headers = await panel.locator('thead th').allTextContents();
  expect(headers).toEqual(expect.arrayContaining([
    'S&P $bn', 'NQ $bn', 'VIX inverse $bn', 'Combined $bn',
    '1W Δ', '4W Δ', '13W trend', '26W trend', '13W rank'
  ]));

  const rows = await panel.locator('[data-cross-actor]').evaluateAll(elements => elements.map(row => row.textContent));
  expect(rows.every(text => text && !text.includes('NaN'))).toBeTruthy();
});

test('keeps instrument-specific bottom-decile evidence separate from cross-market trend', async ({ page }) => {
  await openDashboard(page);

  const baseResearch = await page.evaluate(() => window.__COT_WORLDCLASS_BASE__.RESEARCH);
  expect(baseResearch?.sp500?.extremes).toBeTruthy();
  expect(baseResearch?.nq?.extremes).toBeTruthy();

  const panel = page.locator('#wcCrossActorPanel');
  await expect(panel).toContainText('S&P · Non-reportable bottom 10%');
  await expect(panel).toContainText('13W +5.82% · 26W +10.98% · 52W +26.46%');
  await expect(panel).toContainText('NQ · Non-reportable bottom 10%');
  await expect(panel).toContainText('13W +2.25% · 26W +6.22% · 52W +21.03%');
  await expect(panel).toContainText('NQ · Other Reportable bottom 10%');
  await expect(panel).toContainText('13W +8.43% · 26W +16.45% · 52W +31.89%');

  // Current readings are not bottom-decile triggers. The exact percentile is
  // live data, so assert the semantic state rather than freezing an old week.
  const resetCards = panel.locator('.wc-cross-research-card');
  await expect(resetCards).toHaveCount(3);
  for (let i = 0; i < 3; i += 1) {
    await expect(resetCards.nth(i)).toContainText(/Not active · current percentile \d+(?:\.\d+)?/);
  }
});

test('cross-actor panel passes automated WCAG A/AA checks', async ({ page }) => {
  await openDashboard(page);
  const results = await new AxeBuilder({ page })
    .include('#wcCrossActorPanel')
    .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
    .analyze();
  expect(results.violations).toEqual([]);
});
