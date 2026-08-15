import { test, expect } from '@playwright/test';

async function openToday(page, viewport = { width: 1440, height: 960 }, query = '?market=nq&view=today') {
  await page.setViewportSize(viewport);
  await page.goto(`/worldclass_dashboard.html${query}`);
  await page.waitForFunction(() => document.documentElement.classList.contains('cot-worldclass-ux-ready'));
  await page.waitForFunction(() => document.documentElement.classList.contains('cot-ux-hardening-ready'));
  await expect(page.locator('#currentEdgeCommand')).toBeVisible();
}

test('latest COT changes expose complete table semantics', async ({ page }) => {
  await openToday(page);

  const table = page.locator('.decision-cot-change-table');
  await expect(table).toHaveAttribute('role', 'table');
  await expect(table).toHaveAttribute('aria-colcount', '7');
  const headers = table.locator('.decision-cot-change-head > *');
  await expect(headers).toHaveCount(7);
  for (let index = 0; index < 7; index += 1) {
    await expect(headers.nth(index)).toHaveAttribute('role', 'columnheader');
  }

  const firstRow = table.locator('.decision-cot-change-row').first();
  await expect(firstRow.locator(':scope > *').first()).toHaveAttribute('role', 'rowheader');
  await expect(firstRow.locator(':scope > *').nth(1)).toHaveAttribute('role', 'cell');
  const rowCount = Number(await table.getAttribute('aria-rowcount'));
  expect(rowCount).toBeGreaterThanOrEqual(2);
});

test('financial futures switch TFF and Legacy as one coherent report taxonomy', async ({ page }) => {
  await openToday(page);

  const control = page.locator('#reportTaxonomyControl');
  await expect(control).toBeVisible();
  await expect(control.locator('[data-report-dataset="tff"]')).toHaveClass(/active/);

  const tffState = await page.evaluate(async () => {
    const model = window.__COT_CURRENT_EDGE_MODEL__;
    const rows = model.currentRows('nq');
    const active = model.activeRows('nq');
    const regime = await (await fetch('worldclass/regime_backtest.json')).json();
    const detail = await (await fetch('worldclass/cot-edge-details/nq.json')).json();
    return {
      datasets: [...new Set(rows.map(row => row.dataset))],
      actors: rows.map(row => row.actor_label),
      activeSeries: active.map(row => row.series),
      regimeDataset: regime.markets?.nq?.presentation_dataset,
      detailDatasets: [...new Set((detail.actors || []).map(row => String(row.series).split(':')[0]))]
    };
  });
  expect(tffState.datasets).toEqual(['tff']);
  expect(tffState.actors.join(' ')).toMatch(/Asset Manager|Institutional/i);
  expect(tffState.activeSeries.every(series => String(series).startsWith('tff:'))).toBeTruthy();
  expect(tffState.regimeDataset).toBe('tff');
  expect(tffState.detailDatasets).toEqual(['tff']);

  await control.locator('[data-report-dataset="legacy"]').click();
  await page.waitForURL(/report=legacy/);
  await page.waitForFunction(() => document.documentElement.classList.contains('cot-worldclass-ux-ready'));
  await expect(page.locator('#reportTaxonomyControl [data-report-dataset="legacy"]')).toHaveClass(/active/);

  const legacyState = await page.evaluate(async () => {
    const model = window.__COT_CURRENT_EDGE_MODEL__;
    const rows = model.currentRows('nq');
    const active = model.activeRows('nq');
    const regime = await (await fetch('worldclass/regime_backtest.json')).json();
    const detail = await (await fetch('worldclass/cot-edge-details/nq.json')).json();
    return {
      datasets: [...new Set(rows.map(row => row.dataset))],
      actors: rows.map(row => row.actor_label),
      activeSeries: active.map(row => row.series),
      regimeDataset: regime.markets?.nq?.presentation_dataset,
      detailDatasets: [...new Set((detail.actors || []).map(row => String(row.series).split(':')[0]))],
      livePredictions: (model.state.live?.current_predictions || []).filter(row => row.market === 'nq').length
    };
  });
  expect(legacyState.datasets).toEqual(['legacy']);
  expect(legacyState.actors.join(' ')).toMatch(/Non-Commercial/i);
  expect(legacyState.activeSeries.every(series => String(series).startsWith('legacy:'))).toBeTruthy();
  expect(legacyState.regimeDataset).toBe('legacy');
  expect(legacyState.detailDatasets).toEqual(['legacy']);
  expect(legacyState.livePredictions).toBe(0);

  await page.locator('#instrumentTabs [data-market="gold"]').click();
  await expect(page.locator('#reportTaxonomyControl')).toContainText('Disaggregated');
  const goldDatasets = await page.evaluate(() => [...new Set(window.__COT_CURRENT_EDGE_MODEL__.currentRows('gold').map(row => row.dataset))]);
  expect(goldDatasets).toEqual(['disaggregated']);
});

test('important expiries are generated from the calendar instead of a frozen date list', async ({ page }) => {
  await openToday(page);

  const strip = page.locator('.decision-expiries');
  await expect(strip).toContainText('Next index OPEX');
  await expect(strip).toContainText('Next quarterly OPEX');
  await expect(strip).toContainText('Next VIX settlement');
  await expect(strip).toContainText('Calendar-standard dates');
  await expect(strip.locator('.ux-expiry-item')).toHaveCount(3);

  const key = await strip.getAttribute('data-ux-expiry-key');
  expect(key).toMatch(/^\d{4}-\d{2}-\d{2}\|\d{4}-\d{2}-\d{2}\|\d{4}-\d{2}-\d{2}$/);
});

test('mobile decision controls provide touch-sized targets and visible keyboard focus', async ({ page }) => {
  await openToday(page, { width: 390, height: 844 });

  const selectors = [
    '#instrumentTabs [data-market="nq"]',
    '[data-decision-view="today"]',
    '[data-decision-horizon="1w"]',
    '[data-model-family="combined"]',
    '[data-report-dataset="tff"]',
    '[data-report-dataset="legacy"]'
  ];

  for (const selector of selectors) {
    const control = page.locator(selector);
    await expect(control).toBeVisible();
    const box = await control.boundingBox();
    expect(box?.height ?? 0).toBeGreaterThanOrEqual(44);
  }

  const today = page.locator('[data-decision-view="today"]');
  await today.focus();
  const outline = await today.evaluate(node => {
    const style = getComputedStyle(node);
    return { style: style.outlineStyle, width: parseFloat(style.outlineWidth) || 0 };
  });
  expect(outline.style).not.toBe('none');
  expect(outline.width).toBeGreaterThanOrEqual(2);
});
