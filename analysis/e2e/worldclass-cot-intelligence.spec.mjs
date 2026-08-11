import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

async function open(page) {
  await page.goto('/worldclass_dashboard.html');
  await page.waitForFunction(() => Boolean(window.__COT_EDGE_REGISTRY__));
  await expect(page.locator('#cotIntelligence')).toBeVisible();
  await expect(page.locator('#currentEdgeCommand')).toBeVisible();
}

async function selectMarketWithActiveEdge(page) {
  const market = await page.evaluate(() => {
    const byMarket = window.__COT_CURRENT_EDGE_MODEL__?.state?.active?.by_market || {};
    return Object.entries(byMarket).find(([, block]) => (block?.active_thresholds || []).length > 0)?.[0] || null;
  });
  if (market) {
    await page.locator(`#instrumentTabs [data-market="${market}"]`).click();
    await page.waitForTimeout(50);
  }
  return market;
}

test('COT Intelligence separates current state from statistical evidence', async ({ page }) => {
  await open(page); const panel=page.locator('#cotIntelligence');
  for (const label of ['NOW','EDGES','HORIZONS','ACTORS','CROSS','LIVE']) await expect(panel.getByRole('button',{name:label})).toBeVisible();
  await expect(panel).toContainText('pp = percentage points'); expect(await panel.locator('.cot-now-table tbody tr').count()).toBeGreaterThan(0); await expect(page.locator('#wcCommandCenter')).toContainText('Data / decision quality');
});

test('current edge command ranks active conditions without summing correlated edges', async ({ page }) => {
  await open(page); const panel=page.locator('#currentEdgeCommand');
  expect(await page.evaluate(() => document.querySelector('.instrument-bar')?.nextElementSibling?.id)).toBe('currentEdgeCommand');
  await expect(panel).toContainText('Current edge stack');
  await expect(panel).toContainText('ranked, never summed');
  await expect(panel).toContainText('Rank; do not sum');
  await expect(panel).toContainText('Historical backtests remain research evidence');
  const market=await selectMarketWithActiveEdge(page);
  if (market) {
    expect(await panel.locator('.current-edge-table tbody tr').count()).toBeGreaterThan(0);
    await expect(panel.locator('.current-edge-weekdays article')).toHaveCount(5);
    await expect(panel).toContainText('MON–FRI');
    await expect(panel).toContainText('Returns are cumulative to each weekday');
  }
});

test('current edge horizon controls preserve exact pp and sample evidence', async ({ page }) => {
  await open(page); const panel=page.locator('#currentEdgeCommand');
  const market=await selectMarketWithActiveEdge(page);
  if (!market) return;
  await panel.getByRole('button',{name:'4W'}).click();
  await expect(panel.getByRole('button',{name:'4W'})).toHaveAttribute('aria-pressed','true');
  await expect(panel).toContainText('Conditional');
  await expect(panel).toContainText('Normal');
  await expect(panel).toContainText('Edge');
  await expect(panel).toContainText('pp');
  await expect(panel).toContainText('N');
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

test('mobile decision surfaces use full width, compact health tiles and visible market tabs', async ({ page }) => {
  await page.setViewportSize({width:390,height:844});
  await open(page);
  await expect(page.locator('link[data-cot-intelligence-asset="mobile-ux-css"]')).toHaveCount(1);
  const layout = await page.evaluate(() => {
    const viewport = document.documentElement.clientWidth;
    const rect = sel => document.querySelector(sel)?.getBoundingClientRect();
    const command = rect('#wcCommandCenter');
    const edge = rect('#currentEdgeCommand');
    const tabs = [...document.querySelectorAll('#instrumentTabs [data-market]')].map(el => el.getBoundingClientRect());
    const health = [...document.querySelectorAll('.wc-v3-integrity-item')].map(el => el.getBoundingClientRect());
    const marketCards = [...document.querySelectorAll('.wc-v3-market')].map(el => el.getBoundingClientRect());
    const liveCards = [...document.querySelectorAll('.current-edge-live-grid article')].map(el => el.getBoundingClientRect());
    return {viewport,command,edge,tabs,health,marketCards,liveCards,scroll:document.documentElement.scrollWidth};
  });
  expect(layout.scroll).toBeLessThanOrEqual(layout.viewport+2);
  expect(layout.command.width).toBeGreaterThan(layout.viewport-30);
  expect(layout.edge.width).toBeGreaterThan(layout.viewport-30);
  expect(layout.tabs).toHaveLength(7);
  expect(Math.max(...layout.tabs.map(r=>r.right))).toBeLessThanOrEqual(layout.viewport+1);
  expect(layout.health.length).toBeGreaterThanOrEqual(5);
  expect(new Set(layout.health.map(r=>Math.round(r.top))).size).toBeLessThan(layout.health.length);
  expect(layout.marketCards).toHaveLength(7);
  expect(new Set(layout.marketCards.map(r=>Math.round(r.top))).size).toBeLessThanOrEqual(2);
  if(layout.liveCards.length>=2) expect(Math.round(layout.liveCards[0].top)).toBe(Math.round(layout.liveCards[1].top));
});

test('COT Intelligence and Current Edge pass WCAG A/AA and do not cause mobile page overflow', async ({ page }) => {
  await page.setViewportSize({width:390,height:844}); await open(page); const panel=page.locator('#cotIntelligence'); const edge=page.locator('#currentEdgeCommand'); await expect(panel.locator('.cot-now-cards')).toBeVisible(); await expect(edge).toBeVisible(); const widths=await page.evaluate(()=>({client:document.documentElement.clientWidth,scroll:document.documentElement.scrollWidth})); expect(widths.scroll).toBeLessThanOrEqual(widths.client+2); const cotResults=await new AxeBuilder({page}).include('#cotIntelligence').withTags(['wcag2a','wcag2aa','wcag21a','wcag21aa']).analyze(); expect(cotResults.violations).toEqual([]); const edgeResults=await new AxeBuilder({page}).include('#currentEdgeCommand').withTags(['wcag2a','wcag2aa','wcag21a','wcag21aa']).analyze(); expect(edgeResults.violations).toEqual([]);
});

test('mobile day mode loads light decision surfaces without dark overlays', async ({ page }) => {
  await page.setViewportSize({width:390,height:844});
  await page.addInitScript(() => localStorage.setItem('cot-worldclass-theme','light'));
  await open(page);
  await expect(page.locator('html')).toHaveAttribute('data-theme','light');
  await expect(page.locator('link[data-cot-intelligence-asset="light-css"]')).toHaveCount(1);
  await expect(page.locator('link[data-cot-intelligence-asset="current-edge-css"]')).toHaveCount(1);
  await expect(page.locator('link[data-cot-intelligence-asset="mobile-ux-css"]')).toHaveCount(1);
  const panel=page.locator('#cotIntelligence');
  const edge=page.locator('#currentEdgeCommand');
  await expect(panel.locator('.cot-now-cards')).toBeVisible();
  const colors=await panel.evaluate(el=>({background:getComputedStyle(el).backgroundColor,color:getComputedStyle(el).color}));
  expect(colors.background).toBe('rgb(255, 255, 255)');
  expect(colors.color).not.toBe('rgb(243, 247, 251)');
  const cardBackground=await panel.locator('.cot-now-card').first().evaluate(el=>getComputedStyle(el).backgroundColor);
  expect(cardBackground).toMatch(/^rgba?\(255,\s*255,\s*255/);
  const edgeBackground=await edge.locator('.current-edge-hero').evaluate(el=>getComputedStyle(el).backgroundColor);
  expect(edgeBackground).toBe('rgb(255, 255, 255)');
});

test('live tab never relabels historical research as live evidence', async ({ page }) => {
  await open(page); const panel=page.locator('#cotIntelligence'); await panel.getByRole('button',{name:'LIVE'}).click(); await expect(panel).toContainText('Prospective edge validation'); await expect(panel).toContainText('No past week is backfilled as live'); await expect(panel).toContainText('ELIGIBLE FOR GOVERNANCE REVIEW');
});
