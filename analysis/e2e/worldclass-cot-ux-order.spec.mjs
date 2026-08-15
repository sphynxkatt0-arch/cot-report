import { test, expect } from '@playwright/test';

async function open(page, query = '?market=nq&view=today') {
  await page.goto(`/worldclass_dashboard.html${query}`);
  await page.waitForFunction(() => document.documentElement.classList.contains('cot-worldclass-ux-ready'));
  await expect(page.locator('#currentEdgeCommand')).toBeVisible();
  await expect(page.locator('.instrument-bar')).toBeVisible();
}

test('Today is the default decision surface and newest COT changes are immediately visible', async ({ page }) => {
  await page.setViewportSize({ width: 1600, height: 1000 });
  await open(page);

  await expect(page.locator('.hero')).toBeHidden();
  await expect(page.locator('[data-decision-view]')).toHaveCount(3);
  await expect(page.locator('[data-decision-view="today"]')).toHaveClass(/active/);
  await expect(page.locator('.decision-title-row')).toBeVisible();
  await expect(page.locator('[data-decision-surface="latest-cot-changes"]')).toBeVisible();
  await expect(page.locator('[data-decision-surface="latest-cot-changes"]')).toContainText('LATEST COT POSITION CHANGES');
  await expect(page.locator('[data-decision-surface="latest-cot-changes"]')).toContainText(/Positions as of/i);
  await expect(page.locator('[data-decision-surface="latest-cot-changes"]')).toContainText(/released/i);
  await expect(page.locator('[data-decision-surface="latest-cot-changes"]')).toContainText(/versus the prior COT report/i);
  await expect(page.locator('.decision-cot-change-row').first()).toContainText(/Long|Short|Primary|Secondary|Context|Hedger|Intermediary|Aggregate/i);
  await expect(page.locator('.decision-cot-score-bridge')).toContainText('Governed COT score');
  await expect(page.locator('.decision-cot-score-bridge')).toContainText('4W score change');

  const currentRows = await page.evaluate(() => window.__COT_CURRENT_EDGE_MODEL__.currentRows('nq').length);
  await expect(page.locator('.decision-cot-change-row')).toHaveCount(currentRows);

  const bounds = await page.evaluate(() => {
    const bottom = selector => document.querySelector(selector)?.getBoundingClientRect().bottom ?? Infinity;
    return { selector: bottom('.instrument-bar'), read: bottom('.decision-title-row'), latest: bottom('.decision-latest-cot') };
  });
  expect(bounds.selector).toBeLessThan(1000);
  expect(bounds.read).toBeLessThan(1000);
  expect(bounds.latest).toBeLessThan(1000);

  await expect(page.locator('#cotIntelligence')).toBeHidden();
  await expect(page.locator('.workbench-panel')).toBeHidden();
});

test('latest COT rows expose canonical net, long and short weekly deltas for the selected market', async ({ page }) => {
  await open(page, '?market=nq&view=today');

  const expected = await page.evaluate(() => {
    const model = window.__COT_CURRENT_EDGE_MODEL__;
    const rows = [...model.currentRows('nq')].sort((a, b) => {
      const role = (model.ROLE_ORDER?.[a.actor_role] ?? 9) - (model.ROLE_ORDER?.[b.actor_role] ?? 9);
      if (role) return role;
      return Math.abs(Number(b.delta_net_contracts) || 0) - Math.abs(Number(a.delta_net_contracts) || 0);
    });
    return rows.map(row => ({
      actor: row.actor_label,
      net: row.net_contracts,
      deltaNet: row.delta_net_contracts,
      deltaLong: row.delta_long_contracts,
      deltaShort: row.delta_short_contracts,
      positionPercentile: row.position_percentile,
      weeklyPercentile: row.change_magnitude_percentile,
      report: row.report_date_tuesday,
      release: row.release_date_friday
    }));
  });

  expect(expected.length).toBeGreaterThan(0);
  for (const [index, row] of expected.entries()) {
    const card = page.locator('.decision-cot-change-row').nth(index);
    await expect(card).toContainText(row.actor);
    const text = await card.innerText();
    for (const value of [row.net, row.deltaNet, row.deltaLong, row.deltaShort]) {
      if (value === null || value === undefined) continue;
      expect(text.replaceAll(',', '').replaceAll('−', '-')).toContain(String(Math.round(Number(value))));
    }
  }

  const releaseBlock = await page.locator('.decision-latest-cot .decision-block-head').innerText();
  expect(releaseBlock).toContain(expected[0].report);
  expect(releaseBlock).toContain(expected[0].release);
});

test('financial and metals markets keep their correct actor taxonomies', async ({ page }) => {
  await open(page, '?market=nq&view=today');
  const nq = await page.locator('.decision-latest-cot').innerText();
  expect(nq).toMatch(/Asset Manager|Institutional/i);
  expect(nq).toMatch(/Leveraged/i);

  await page.locator('#instrumentTabs [data-market="gold"]').click();
  await expect(page).toHaveURL(/market=gold/);
  const gold = await page.locator('.decision-latest-cot').innerText();
  expect(gold).toMatch(/Managed Money/i);
  expect(gold).toMatch(/Producer|Merchant|Processor|User/i);
  expect(gold).toMatch(/Swap/i);
});

test('score, current model estimate, live prospective record and historical edge remain distinct', async ({ page }) => {
  await open(page, '?market=sp500&view=today');

  await expect(page.locator('.decision-title-row')).toContainText(/Governed COT score/i);
  const semantics = page.locator('.decision-semantics');
  await expect(semantics).toContainText('CURRENT MODEL ESTIMATE');
  await expect(semantics).toContainText('LIVE PROSPECTIVE');
  await expect(semantics).toContainText('ACTIVE HISTORICAL EDGE');

  const estimate = semantics.locator('.decision-semantic').filter({ hasText: 'CURRENT MODEL ESTIMATE' });
  await expect(estimate).toContainText(/P\(positive\)|No .* regime estimate/i);
  const live = semantics.locator('.decision-semantic').filter({ hasText: /LIVE PROSPECTIVE/ });
  expect(await live.innerText()).toMatch(/FROZEN|NOT YET FROZEN/);
});

test('macro changes model family view but never rewrites the raw COT score or actor deltas', async ({ page }) => {
  await open(page, '?market=sp500&horizon=1w&view=today&model=combined');

  const scoreBefore = await page.locator('.decision-title-row').innerText();
  const deltasBefore = await page.locator('.decision-latest-cot').innerText();
  const combined = page.locator('.decision-semantic').filter({ hasText: 'CURRENT MODEL ESTIMATE' });
  const combinedText = await combined.innerText();

  await page.locator('[data-model-family="macro"]').click();
  await expect(page).toHaveURL(/model=macro/);
  const macroText = await page.locator('.decision-semantic').filter({ hasText: 'CURRENT MODEL ESTIMATE' }).innerText();
  expect(macroText).not.toBe(combinedText);

  const scoreAfter = await page.locator('.decision-title-row').innerText();
  expect(scoreAfter.match(/Governed COT score[^.]+/)?.[0]).toBe(scoreBefore.match(/Governed COT score[^.]+/)?.[0]);
  expect(await page.locator('.decision-latest-cot').innerText()).toBe(deltasBefore);
});

test('Today contains strongest edge, week path and coming edge without separate top-level tabs', async ({ page }) => {
  await open(page, '?market=sp500&horizon=1w&view=today');

  await expect(page.locator('[data-decision-view="edges"]')).toHaveCount(0);
  await expect(page.locator('[data-decision-view="week"]')).toHaveCount(0);
  await expect(page.locator('.decision-strongest')).toBeVisible();
  await expect(page.locator('[data-decision-surface="week-path"]')).toBeVisible();
  await expect(page.locator('[data-decision-surface="coming-edge"]')).toBeVisible();
  await expect(page.locator('[data-decision-surface="coming-edge"]')).toContainText('Conditional watch — not a prediction');
  await expect(page.locator('.decision-strongest')).toHaveCount(1);
});

test('old overview, edges and week URLs normalize safely to Today', async ({ page }) => {
  for (const oldView of ['overview', 'edges', 'week']) {
    await open(page, `?market=nq&view=${oldView}`);
    await expect(page).toHaveURL(/view=today/);
    await expect(page.locator('[data-decision-view="today"]')).toHaveClass(/active/);
  }
});

test('market, horizon and model family persist in URL and synchronize Today', async ({ page }) => {
  await open(page, '?market=sp500&horizon=1w&view=today&model=combined');

  await page.locator('.decision-scanner [data-decision-market="gold"]').click();
  await expect(page.locator('#instrumentTabs [data-market="gold"]')).toHaveClass(/active/);
  await expect(page).toHaveURL(/market=gold/);
  await expect(page.locator('.decision-title-row')).toContainText('Gold');

  await page.locator('[data-decision-horizon="2w"]').click();
  await expect(page.locator('[data-decision-horizon="2w"]')).toHaveClass(/active/);
  await expect(page).toHaveURL(/horizon=2w/);

  await page.locator('[data-model-family="macro"]').click();
  await expect(page).toHaveURL(/model=macro/);
});

test('Research is self-contained and never exposes the legacy dashboard', async ({ page }) => {
  await open(page, '?market=gold&view=research');

  await expect(page.locator('[data-decision-view="research"]')).toHaveClass(/active/);
  await expect(page.locator('[data-decision-surface="research"]')).toBeVisible();
  await expect(page.locator('.decision-research-group')).toHaveCount(4);
  await expect(page.locator('[data-decision-surface="research"]')).toContainText('Positioning & actors');
  await expect(page.locator('[data-decision-surface="research"]')).toContainText('Backtests & regimes');
  await expect(page.locator('[data-decision-surface="research"]')).toContainText('Macro evidence');
  await expect(page.locator('[data-decision-surface="research"]')).toContainText('Methodology & provenance');

  await expect(page.locator('#cotIntelligence')).toBeHidden();
  await expect(page.locator('.controls-surface')).toBeHidden();
  await expect(page.locator('.workbench-panel')).toBeHidden();
  await expect(page.locator('.methodology')).toBeHidden();
  await expect(page.locator('[data-decision-view]')).toHaveCount(3);
});

test('weekday path preserves release timing language on Today', async ({ page }) => {
  await open(page, '?market=nq&view=today');
  const panel = page.locator('[data-decision-surface="week-path"]');
  await expect(panel).toContainText('THIS WEEK — CUMULATIVE HISTORICAL PATH');
  if (await panel.locator('.decision-week-path article').count()) {
    await expect(panel).toContainText('previous Tuesday COT positioning');
    await expect(panel).toContainText('publicly available Friday');
    await expect(panel.locator('.decision-week-path article')).toHaveCount(5);
  }
});

test('important index and VIX option expiries remain visible on Today', async ({ page }) => {
  await open(page, '?market=nq&horizon=1w&view=today');
  const overview = page.locator('.decision-current');
  await expect(overview).toContainText('Important expiries');
  await expect(overview).toContainText('Next index OPEX');
  await expect(overview).toContainText('Next VIX expiry');
});

test('mobile has no page-level horizontal overflow and latest COT changes become cards', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await open(page);

  let overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow).toBeLessThanOrEqual(1);

  const firstChange = page.locator('.decision-cot-change-row').first();
  await expect(firstChange).toBeVisible();
  await expect(firstChange).toContainText(/Net position|Weekly Δ/i);
  const box = await firstChange.boundingBox();
  expect(box.width).toBeLessThanOrEqual(390);

  await page.locator('[data-decision-view="research"]').click();
  overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow).toBeLessThanOrEqual(1);
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
