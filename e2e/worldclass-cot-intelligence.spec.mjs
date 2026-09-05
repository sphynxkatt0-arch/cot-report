import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

async function open(page, query = '?market=sp500&view=overview') {
  await page.goto(`/worldclass_dashboard.html${query}`);
  await page.waitForFunction(() => document.documentElement.classList.contains('decision-first-ready'));
  await expect(page.locator('#currentEdgeCommand')).toBeVisible();
  await expect(page.locator('#loadingOverlay')).toBeHidden();
}

async function selectMarketWithActiveEdge(page) {
  const market = await page.evaluate(() => {
    const byMarket = window.__COT_CURRENT_EDGE_MODEL__?.state?.active?.by_market || {};
    return Object.entries(byMarket).find(([, block]) => (block?.active_thresholds || []).length > 0)?.[0] || null;
  });
  if (market) {
    await page.locator(`#instrumentTabs [data-market="${market}"]`).click();
    await expect(page).toHaveURL(new RegExp(`market=${market}`));
  }
  return market;
}

test('decision layer separates current estimate, prospective record and historical edge', async ({ page }) => {
  await open(page);
  const panel = page.locator('#currentEdgeCommand');
  await expect(panel).toContainText('CURRENT MODEL ESTIMATE');
  await expect(panel).toContainText('LIVE PROSPECTIVE');
  await expect(panel).toContainText('ACTIVE HISTORICAL EDGE');
  await expect(page.locator('#cotIntelligence')).toBeHidden();
  await expect(page.locator('#wcCommandCenter')).toBeHidden();
});

test('active edge view preserves conditional, normal, uplift and independent sample evidence', async ({ page }) => {
  await open(page);
  const market = await selectMarketWithActiveEdge(page);
  if (!market) return;

  await page.locator('[data-decision-view="edges"]').click();
  const panel = page.locator('.decision-view-panel[data-decision-surface="edges"]');
  await expect(panel).toContainText('Ranked current actor conditions');
  const rows = panel.locator('.decision-edge-row');
  if (await rows.count()) {
    await expect(rows.first()).toContainText('Historical result');
    await expect(rows.first()).toContainText('Normal');
    await expect(rows.first()).toContainText('Uplift');
    await expect(rows.first()).toContainText(/N \d+/);
    await expect(rows.first()).toContainText(/pp/);
  }
});

test('research matrix exposes all 15 horizons and can switch evidence metric', async ({ page }) => {
  await open(page, '?market=nq&view=research');
  const panel = page.locator('.decision-view-panel[data-decision-surface="research"]');
  const matrix = panel.locator('.decision-matrix');
  await expect(matrix.locator('thead th')).toHaveCount(16);
  await expect(matrix).toContainText('52W');
  await panel.locator('#researchMetricSelector').selectOption('n');
  expect(await matrix.locator('tbody tr').count()).toBeGreaterThan(0);
});

test('research view exposes cross-market evidence only on demand', async ({ page }) => {
  await open(page, '?market=nq&view=overview');
  await expect(page.locator('#wcCrossActorPanel')).toBeHidden();
  await page.locator('[data-decision-view="research"]').click();
  await expect(page.locator('#wcCrossActorPanel')).toBeHidden();
  await page.locator('[data-research-section="positioning"]').click();
  await expect(page.locator('#wcCrossActorPanel')).toBeVisible();
  await expect(page.locator('#wcCrossActorPanel')).toContainText('CROSS-INSTRUMENT ACTOR TREND');
});

test('mobile decision surface stays within viewport and uses final mobile cascade', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await open(page);
  await page.waitForFunction(() => document.documentElement.dataset.mobileUxReady === 'true');
  await expect(page.locator('.hero')).toBeHidden();
  const layout = await page.evaluate(() => ({
    viewport: document.documentElement.clientWidth,
    scroll: document.documentElement.scrollWidth,
    edge: document.querySelector('#currentEdgeCommand')?.getBoundingClientRect().width || 0
  }));
  expect(layout.scroll).toBeLessThanOrEqual(layout.viewport + 2);
  expect(layout.edge).toBeGreaterThan(layout.viewport - 30);
});

test('decision surface passes WCAG A/AA without page-level mobile overflow', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await open(page);
  await page.waitForFunction(() => document.documentElement.dataset.mobileUxReady === 'true');
  const widths = await page.evaluate(() => ({ client: document.documentElement.clientWidth, scroll: document.documentElement.scrollWidth }));
  expect(widths.scroll).toBeLessThanOrEqual(widths.client + 2);
  const results = await new AxeBuilder({ page })
    .include('#currentEdgeCommand')
    .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
    .analyze();
  expect(results.violations).toEqual([]);
});

test('mobile day mode renders a readable light decision surface', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.addInitScript(() => localStorage.setItem('cot-worldclass-theme', 'light'));
  await open(page);
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'light');
  const surface = page.locator('.decision-current');
  const colors = await surface.evaluate(el => ({ background: getComputedStyle(el).backgroundColor, color: getComputedStyle(el).color }));
  expect(colors.background).not.toBe('rgba(0, 0, 0, 0)');
  expect(colors.color).not.toBe(colors.background);
});

test('live view never relabels historical research as prospective proof', async ({ page }) => {
  await open(page);
  await page.locator('[data-decision-view="live"]').click();
  const panel = page.locator('.decision-view-panel[data-decision-surface="live"]');
  await expect(panel).toContainText('Historical backtests and future live forecasts remain strictly decoupled');
  await expect(panel).toContainText('Past reports are never retroactively backfilled as live proof');
  await expect(panel).toContainText('DISALLOWED');
  await expect(panel).toContainText('Governance Review');
});
