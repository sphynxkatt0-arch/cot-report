import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

async function open(page) {
  await page.goto('/worldclass_dashboard.html');
  await page.waitForFunction(() => Boolean(window.__COT_EDGE_REGISTRY__));
  await expect(page.locator('#cotIntelligence')).toBeVisible();
}

test('COT Intelligence separates current state from statistical evidence', async ({ page }) => {
  await open(page); const panel=page.locator('#cotIntelligence');
  for (const label of ['NOW','EDGES','HORIZONS','ACTORS','CROSS','LIVE']) await expect(panel.getByRole('button',{name:label})).toBeVisible();
  await expect(panel).toContainText('pp = percentage points'); expect(await panel.locator('.cot-now-table tbody tr').count()).toBeGreaterThan(0); await expect(page.locator('#wcCommandCenter')).toContainText('Data / decision quality');
});

test('edge tab distinguishes threshold conditions from continuous correlations', async ({ page }) => {
  await open(page); const panel=page.locator('#cotIntelligence'); await panel.getByRole('button',{name:'EDGES'}).click(); await expect(panel).toContainText('ACTIVE THRESHOLD CONDITIONS'); await expect(panel).toContainText('CONTINUOUS HISTORICAL EVIDENCE'); await expect(panel).toContainText('Continuous association is context, not a discrete trigger.');
});

test('horizon matrix exposes all 15 horizons and sample warnings', async ({ page }) => {
  await open(page); const panel=page.locator('#cotIntelligence'); await panel.getByRole('button',{name:'HORIZONS'}).click(); const matrix=panel.locator('.cot-matrix'); await expect(matrix.locator('thead th')).toHaveCount(16); await expect(matrix).toContainText('52W'); await panel.locator('#cotMatrixMetric').selectOption('n'); expect(await matrix.locator('tbody tr').count()).toBeGreaterThan(0);
});

test('actor drilldown lazy-loads predictor comparison, percentile bands and OI interactions', async ({ page }) => {
  await open(page); const panel=page.locator('#cotIntelligence'); await panel.getByRole('button',{name:'ACTORS'}).click(); await expect(panel).toContainText('PREDICTOR COMPARISON'); await expect(panel).toContainText('PERCENTILE CURVES'); await expect(panel).toContainText('P0–10'); await expect(panel).toContainText('P90–100'); await expect(panel).toContainText('Actor flow × Open Interest direction'); await expect(panel).toContainText('ADD OI CUT');
});

test('cross view shows current same-actor markets but keeps combinations discovery-only', async ({ page }) => {
  await open(page); const panel=page.locator('#cotIntelligence'); await panel.getByRole('button',{name:'CROSS'}).click(); await expect(panel).toContainText('Same actor across markets'); await expect(panel).toContainText('DISCOVERY ONLY'); await expect(panel).toContainText('SAME ACTOR · CROSS INSTRUMENT'); await expect(panel).toContainText('RISK BREADTH');
});

test('COT Intelligence passes WCAG A/AA and does not cause mobile page overflow', async ({ page }) => {
  await page.setViewportSize({width:390,height:844}); await open(page); const panel=page.locator('#cotIntelligence'); await expect(panel.locator('.cot-now-cards')).toBeVisible(); const widths=await page.evaluate(()=>({client:document.documentElement.clientWidth,scroll:document.documentElement.scrollWidth})); expect(widths.scroll).toBeLessThanOrEqual(widths.client+2); const results=await new AxeBuilder({page}).include('#cotIntelligence').withTags(['wcag2a','wcag2aa','wcag21a','wcag21aa']).analyze(); expect(results.violations).toEqual([]);
});

test('live tab never relabels historical research as live evidence', async ({ page }) => {
  await open(page); const panel=page.locator('#cotIntelligence'); await panel.getByRole('button',{name:'LIVE'}).click(); await expect(panel).toContainText('Prospective edge validation'); await expect(panel).toContainText('No past week is backfilled as live'); await expect(panel).toContainText('ELIGIBLE FOR GOVERNANCE REVIEW');
});
