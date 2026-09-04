import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

async function open(page, query = '?market=nq&view=overview') {
  await page.goto(`/worldclass_dashboard.html${query}`);
  await page.waitForFunction(() => document.documentElement.classList.contains('decision-first-ready'));
  await expect(page.locator('#currentEdgeCommand')).toBeVisible();
  await expect(page.locator('.instrument-bar')).toBeVisible();
  await expect(page.locator('#loadingOverlay')).toBeHidden();
}

test('desktop first viewport is decision-first and defaults to governed 1W read', async ({ page }) => {
  await page.setViewportSize({ width: 1600, height: 1000 });
  await open(page);

  await expect(page.locator('.hero')).toBeHidden();
  await expect(page.locator('.decision-title-row')).toBeVisible();
  await expect(page.locator('.decision-strongest')).toBeVisible();
  await expect(page.locator('.decision-horizons [data-decision-horizon="1w"]')).toHaveClass(/active/);
  await expect(page).toHaveURL(/horizon=1w/);
  await expect(page.locator('.decision-title-row h2')).toContainText('COT POSITIONING');
  await expect(page.locator('.decision-title-row')).toContainText(/Governed COT score/i);
  await expect(page.locator('.decision-driver-strip > div')).toHaveCount(4);
  await expect(page.locator('.decision-driver-strip')).toContainText('COT SCORE');
  await expect(page.locator('.decision-driver-strip')).toContainText('MACRO');
  await expect(page.locator('.decision-driver-strip')).toContainText('SENTIMENT');

  const bounds = await page.evaluate(() => {
    const bottom = selector => document.querySelector(selector)?.getBoundingClientRect().bottom ?? Infinity;
    return {
      selector: bottom('.instrument-bar'),
      read: bottom('.decision-title-row'),
      strongest: bottom('.decision-strongest')
    };
  });
  expect(bounds.selector).toBeLessThan(1000);
  expect(bounds.read).toBeLessThan(1000);
  expect(bounds.strongest).toBeLessThan(1000);

  await expect(page.locator('#cotIntelligence')).toBeHidden();
  await expect(page.locator('.workbench-panel')).toBeHidden();
});

test('score, current model estimate, live prospective record and historical edge are distinct', async ({ page }) => {
  await open(page, '?market=sp500&view=overview');

  await expect(page.locator('.decision-title-row')).toContainText(/Governed COT score/i);
  const semantics = page.locator('.decision-semantics');
  await expect(semantics).toContainText('CURRENT MODEL ESTIMATE');
  await expect(semantics).toContainText('LIVE PROSPECTIVE');
  await expect(semantics).toContainText('ACTIVE HISTORICAL EDGE');

  const estimate = semantics.locator('.decision-semantic').filter({ hasText: 'CURRENT MODEL ESTIMATE' });
  await expect(estimate).not.toContainText(/^n\/a$/);
  await expect(estimate).toContainText(/P\(positive\)/i);
  await expect(estimate).toContainText(/baseline/i);
  await expect(estimate).toContainText(/excess/i);

  const live = semantics.locator('.decision-semantic').filter({ hasText: /LIVE PROSPECTIVE/ });
  const liveText = await live.innerText();
  expect(liveText).toMatch(/FROZEN|NOT YET FROZEN/);

  const historical = semantics.locator('.decision-semantic.historical');
  const historicalText = await historical.innerText();
  expect(historicalText).toMatch(/normal|NO ACTIVE DIRECTIONAL/i);
  if (historicalText.includes('pp')) expect(historicalText).toMatch(/ACTIVE HISTORICAL EDGE/i);
});

test('macro affects the Combined model estimate but never rewrites the raw COT score', async ({ page }) => {
  await open(page, '?market=sp500&horizon=1w&view=overview&model=combined');

  const scoreBefore = await page.locator('.decision-title-row').innerText();
  const combined = page.locator('.decision-semantic').filter({ hasText: 'CURRENT MODEL ESTIMATE' });
  const combinedText = await combined.innerText();
  await expect(combined).toContainText('COMBINED');

  await page.locator('[data-model-family="macro"]').click();
  await expect(page).toHaveURL(/model=macro/);
  const macroText = await page.locator('.decision-semantic').filter({ hasText: 'CURRENT MODEL ESTIMATE' }).innerText();
  expect(macroText).not.toBe(combinedText);

  const scoreAfter = await page.locator('.decision-title-row').innerText();
  expect(scoreAfter.match(/Governed COT score[^.]+/)?.[0]).toBe(scoreBefore.match(/Governed COT score[^.]+/)?.[0]);

  await page.locator('[data-model-family="cot"]').click();
  await expect(page).toHaveURL(/model=cot/);
  await expect(page.locator('.decision-semantic').filter({ hasText: 'CURRENT MODEL ESTIMATE' })).toContainText('COT');
});

test('context-only actors cannot drive headline, scanner, coming edge or week path', async ({ page }) => {
  await open(page, '?market=sp500&horizon=1w&view=overview');
  await expect(page.locator('.decision-title-row h2')).toContainText('COT POSITIONING');
  await expect(page.locator('.decision-title-row h2')).not.toContainText(/Dealer|Intermediary/i);
  await expect(page.locator('.decision-strongest')).not.toContainText(/Dealer\/Intermediary/i);

  await page.locator('[data-decision-view="edges"]').click();
  await expect(page.locator('.decision-view-panel')).toContainText(/Primary\/secondary actors drive the decision layer/i);
  await expect(page.locator('.decision-watch-section')).toContainText('Conditional watch — not a prediction');
});

test('market, horizon, model family and view persist in URL and synchronize the dashboard', async ({ page }) => {
  await open(page, '?market=sp500&horizon=1w&view=overview&model=combined');

  await page.locator('.decision-scanner [data-decision-market="gold"]').click();
  await expect(page.locator('#instrumentTabs [data-market="gold"]')).toHaveClass(/active/);
  await expect(page).toHaveURL(/market=gold/);
  await expect(page.locator('.decision-title-row')).toContainText('Gold');

  await page.locator('[data-decision-horizon="2w"]').click();
  await expect(page.locator('[data-decision-horizon="2w"]')).toHaveClass(/active/);
  await expect(page).toHaveURL(/horizon=2w/);

  await page.locator('[data-model-family="macro"]').click();
  await expect(page).toHaveURL(/model=macro/);

  await page.locator('[data-decision-view="research"]').click();
  await expect(page).toHaveURL(/view=research/);
  await expect(page).toHaveURL(/research=matrix/);
  await expect(page.locator('#cotIntelligence')).toBeHidden();
  await expect(page.locator('.workbench-panel')).toBeHidden();
  await expect(page.locator('.controls-surface')).toBeHidden();
  const research = page.locator('.decision-view-panel[data-decision-surface="research"]');
  await expect(research).toBeVisible();
  await expect(research).toContainText(/DEEP RESEARCH MATRIX · Gold/i);

  await page.locator('[data-research-section="positioning"]').click();
  await expect(page).toHaveURL(/research=positioning/);
  await expect(page.locator('#cotIntelligence')).toBeHidden();
  await expect(page.locator('#weeklyChangePanel')).toBeVisible();
  await expect(page.locator('.workbench-panel')).toBeHidden();
  await expect(page.locator('.instrument-bar')).toBeVisible();
  await expect(page.locator('.decision-research-shell')).toBeVisible();

  await page.locator('[data-research-section="chart"]').click();
  await expect(page).toHaveURL(/research=chart/);
  await expect(page.locator('.workbench-panel')).toBeVisible();
  await expect(page.locator('.controls-surface')).toBeVisible();
  await expect(page.locator('#cotIntelligence')).toBeHidden();
});

test('macro research separates current liquidity state from predictive effectiveness', async ({ page }) => {
  await page.setViewportSize({ width: 1600, height: 1000 });
  await open(page, '?market=sp500&view=research&research=macro&dataset=tff');

  const panel = page.locator('.macro-research');
  await expect(panel).toBeVisible();
  await expect(panel).toContainText('CURRENT LIQUIDITY SCORE');
  await expect(panel).toContainText('SOURCE COVERAGE');
  await expect(panel).toContainText('PREDICTIVE VALIDITY');
  await expect(panel).toContainText('NOT_VALIDATED');
  await expect(panel).toContainText('PRODUCTION DIRECTIONAL WEIGHT');
  await expect(panel).toContainText('0%');
  await expect(panel).toContainText('Does a higher liquidity score predict higher future returns?');
  await expect(panel.locator('.macro-effectiveness-table').first().locator('tbody tr')).toHaveCount(5);
  await expect(panel).toContainText('FACTOR-LEVEL RESEARCH');
  await expect(panel).toContainText(/VIX|HY OAS|Net liquidity/i);
  await expect(page.locator('#wcMacroControl')).toBeHidden();

  const accessibility = await new AxeBuilder({ page })
    .include('.macro-research')
    .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
    .analyze();
  expect(accessibility.violations).toEqual([]);

  await page.locator('[data-decision-view="overview"]').click();
  await expect(page.locator('.decision-driver-strip')).toContainText('0% directional weight');
});

test('active edges prioritize directional actors and coming edges remain explicitly conditional', async ({ page }) => {
  await open(page);
  await page.locator('[data-decision-view="edges"]').click();
  await expect(page.locator('.decision-view-panel')).toContainText('Ranked current actor conditions');
  await expect(page.locator('.decision-watch-section')).toContainText('Conditional watch — not a prediction');

  const rows = page.locator('.decision-edge-row');
  if (await rows.count()) {
    await expect(rows.first()).toContainText(/Historical result/i);
    await expect(rows.first()).toContainText(/Uplift/i);
    await expect(rows.first().locator('.decision-why')).toHaveCount(1);
  }

  const watches = page.locator('.decision-watch');
  if (await watches.count()) {
    await expect(watches.first()).toContainText('If triggered');
    await expect(watches.first()).toContainText(/percentile points away/i);
    await expect(watches.first().locator('.decision-progress')).toBeVisible();
  }
});

test('weekday view reads as a cumulative directional path and preserves release timing language', async ({ page }) => {
  await open(page);
  await page.locator('[data-decision-view="week"]').click();
  const panel = page.locator('.decision-view-panel');
  await expect(panel).toContainText('THIS WEEK — CUMULATIVE HISTORICAL PATH');
  if (await panel.locator('.decision-week-path article').count()) {
    await expect(panel).toContainText('previous Tuesday COT positioning');
    await expect(panel).toContainText('publicly available Friday');
    await expect(panel.locator('.decision-week-path article')).toHaveCount(5);
  }
});

test('important index and VIX option expiries are visible in overview', async ({ page }) => {
  await open(page, '?market=nq&horizon=1w&view=overview');
  const overview = page.locator('.decision-current');
  await expect(overview).toContainText('Important expiries');
  await expect(overview).toContainText('Next index OPEX');
  await expect(overview).toContainText('Next VIX expiry');
});

test('mobile has no page-level horizontal overflow and strongest edge needs no table scroll', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await open(page);
  await page.waitForFunction(() => document.documentElement.dataset.mobileUxReady === 'true');
  await expect(page.locator('.hero')).toBeHidden();
  let overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow).toBeLessThanOrEqual(1);

  const touchHeights = await page.locator('.decision-nav button, #themeToggle, .instrument-tab').evaluateAll(nodes => nodes
    .map(node => node.getBoundingClientRect())
    .filter(rect => rect.width > 0 && rect.height > 0)
    .map(rect => rect.height));
  expect(touchHeights.length).toBeGreaterThan(0);
  expect(Math.min(...touchHeights)).toBeGreaterThanOrEqual(44);

  await page.locator('[data-decision-view="edges"]').click();
  overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow).toBeLessThanOrEqual(1);

  const firstRow = page.locator('.decision-edge-row').first();
  if (await firstRow.count()) {
    const box = await firstRow.boundingBox();
    expect(box.width).toBeLessThanOrEqual(390);
  }
});

test('desktop makes the primary COT taxonomy explicit and keeps actor tables taxonomy-pure', async ({ page }) => {
  await page.setViewportSize({ width: 1600, height: 1000 });
  await open(page, '?market=sp500&view=overview');

  await expect(page.locator('#instrumentTabs [data-market="sp500"]')).toContainText('TFF');
  await expect(page.locator('#instrumentTabs [data-market="gold"]')).toContainText('DISAGG');
  await expect(page.locator('.decision-title-row')).toContainText('TFF');
  await expect(page.locator('.decision-title-row')).toContainText(/Asset Manager \+ Leveraged Funds|Financial-futures taxonomy/i);

  const actorRows = page.locator('.decision-actor-table tbody tr');
  expect(await actorRows.count()).toBeGreaterThan(0);
  const actorTaxonomies = await actorRows.locator('td:first-child small').allTextContents();
  expect(actorTaxonomies.every(text => text.includes('TFF'))).toBeTruthy();

  const strongest = page.locator('.decision-strongest');
  if ((await strongest.innerText()).includes('Non-Commercial')) {
    await expect(strongest).toContainText('LEGACY');
    await expect(page.locator('.decision-taxonomy-note')).toContainText(/supplemental edge/i);
  }

  await page.locator('#instrumentTabs [data-market="gold"]').click();
  await expect(page.locator('.decision-title-row')).toContainText('DISAGG');
  const goldTaxonomies = await page.locator('.decision-actor-table tbody tr td:first-child small').allTextContents();
  expect(goldTaxonomies.length).toBeGreaterThan(0);
  expect(goldTaxonomies.every(text => text.includes('DISAGGREGATED'))).toBeTruthy();
});

test('desktop taxonomy control switches S&P between TFF and Legacy without repeating report dates in every asset tab', async ({ page }) => {
  await page.setViewportSize({ width: 1600, height: 1000 });
  await open(page, '?market=sp500&view=overview&dataset=tff');

  const tabsText = await page.locator('#instrumentTabs').innerText();
  expect(tabsText).not.toMatch(/2026-\d{2}-\d{2}/);
  await expect(page.locator('#freshnessPill')).toBeHidden();

  const legacy = page.locator('[data-decision-dataset="legacy"]');
  await expect(legacy).toBeVisible();
  await legacy.click();
  await expect(page).toHaveURL(/dataset=legacy/);
  await expect(page.locator('.decision-title-row')).toContainText('LEGACY');
  await expect(page.locator('#instrumentTabs [data-market="sp500"]')).toContainText('LEGACY');

  const legacyRows = await page.locator('.decision-actor-table tbody tr td:first-child small').allTextContents();
  expect(legacyRows.length).toBeGreaterThan(0);
  expect(legacyRows.every(text => text.includes('LEGACY'))).toBeTruthy();

  await page.locator('[data-decision-dataset="tff"]').click();
  await expect(page).toHaveURL(/dataset=tff/);
  await expect(page.locator('.decision-title-row')).toContainText('TFF');

  await open(page, '?market=sp500&view=overview&dataset=legacy');
  await expect(page.locator('[data-decision-dataset="legacy"]')).toHaveClass(/active/);
  await expect(page.locator('#instrumentTabs [data-market="sp500"]')).toContainText('LEGACY');
});

test('decision-first surface passes automated WCAG A/AA checks', async ({ page }) => {
  await open(page, '?market=nq&horizon=1w&view=overview');
  const results = await new AxeBuilder({ page })
    .include('#currentEdgeCommand')
    .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
    .analyze();
  expect(results.violations).toEqual([]);
});

test('light and dark themes retain readable decision surfaces', async ({ page }) => {
  await open(page);
  for (const theme of ['dark', 'light']) {
    const current = await page.locator('html').getAttribute('data-theme');
    if (current !== theme) await page.locator('#themeToggle').click();
    await expect(page.locator('html')).toHaveAttribute('data-theme', theme);
    const contrastSanity = await page.locator('.decision-current').evaluate(node => {
      const style = getComputedStyle(node);
      return { color: style.color, background: style.backgroundColor };
    });
    expect(contrastSanity.color).not.toBe(contrastSanity.background);
  }
});
