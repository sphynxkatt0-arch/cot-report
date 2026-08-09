import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

async function openDashboard(page) {
  await page.goto('/worldclass_dashboard.html');
  await expect(page.getByRole('heading', { name: 'COT Intelligence' })).toBeVisible();
  await page.waitForFunction(() => Boolean(window.__COT_WORLDCLASS_BASE__?.MODEL_SPEC));
  await expect(page.locator('#wcCommandCenter')).toBeVisible();
}

test('command center renders every market and follows the canonical model spec', async ({ page }) => {
  await openDashboard(page);

  const commandCenter = page.locator('#wcCommandCenter');
  await expect(commandCenter.locator('.wc-v2-market-grid [data-wc-v2-market]')).toHaveCount(7);
  await expect(commandCenter).toContainText('GLOBAL POSITIONING COMMAND CENTER');
  await expect(commandCenter).toContainText('DISLOCATION RADAR');

  const weights = await page.evaluate(() => window.__COT_WORLDCLASS_BASE__.MODEL_SPEC.score_models);
  expect(weights.tff.category_weights.other_reportable).toBe(0);
  expect(weights.tff.category_weights.non_reportable).toBe(0);
  expect(weights.legacy.category_weights.commercial).toBe(0);
  expect(weights.disaggregated.category_weights.producer_merchant).toBe(0);

  const oldDecision = page.locator('#wcDecisionLayer');
  if (await oldDecision.count()) await expect(oldDecision).toBeHidden();
});

test('command center market selection synchronizes with the research workbench', async ({ page }) => {
  await openDashboard(page);

  await page.locator('#wcCommandCenter .wc-v2-market-grid [data-wc-v2-market="nq"]').click();
  await expect(page.locator('#instrumentTabs [data-market="nq"]')).toHaveClass(/active/);
  await expect(page.locator('#wcCommandCenter .wc-v2-verdict h3')).toContainText('Nasdaq-100');

  await page.keyboard.press('6');
  await expect(page.locator('#instrumentTabs [data-market="gold"]')).toHaveClass(/active/);
  await expect(page.locator('#wcCommandCenter .wc-v2-verdict h3')).toContainText('Gold');
});

test('shared metals payload performs one physical request during initial render', async ({ page }) => {
  let metalsRequests = 0;
  page.on('request', request => {
    if (/\/worldclass\/metals\.json(?:\?|$)/.test(request.url())) metalsRequests += 1;
  });

  await openDashboard(page);
  expect(metalsRequests).toBe(1);
});

test('command center passes automated WCAG A/AA checks', async ({ page }) => {
  await openDashboard(page);
  const results = await new AxeBuilder({ page })
    .include('#wcCommandCenter')
    .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
    .analyze();
  expect(results.violations).toEqual([]);
});
