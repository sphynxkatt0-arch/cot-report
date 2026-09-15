import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

const liveRelease = {
  schema_version: 2,
  state: 'LIVE',
  generated_at_utc: '2026-08-09T05:26:37Z',
  latest_cot_report_date: '2026-08-04',
  expected_cot_report_date: '2026-08-04',
  model: { model_version: '1.3.0', model_spec_hash: 'a'.repeat(64) },
  market_states: Object.fromEntries(['sp500', 'nq', 'vix', 'rty', 'dow', 'gold', 'silver'].map(market => [market, { state: 'LIVE', latest_cot_report_date: '2026-08-04', expected_cot_report_date: '2026-08-04' }])),
  delayed_markets: [],
  data_contracts: 'PASS',
  actor_taxonomy: 'PASS',
  lookahead_safety: 'PASS',
  macro_plumbing: { state: 'LIVE', source_coverage_ratio: 0.846, source_coverage_label: 'Good' }
};

const healthyTrack = {
  schema_version: 1,
  forecast_count: 3,
  matured_signal_count: 0,
  ledger: { integrity: 'PASS' }
};

async function mockCommandEvidence(page, release = liveRelease, track = healthyTrack) {
  await page.route('**/worldclass/release-status.json*', route => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(release) }));
  await page.route('**/worldclass/live-track-record.json*', route => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(track) }));
}

async function openDashboard(page, release = liveRelease, track = healthyTrack) {
  await mockCommandEvidence(page, release, track);
  await page.goto('/worldclass_dashboard.html?market=sp500&view=overview');
  await page.waitForFunction(() => Boolean(window.__COT_WORLDCLASS_BASE__?.MODEL_SPEC));
  await page.waitForFunction(() => document.documentElement.classList.contains('decision-first-ready'));
  await expect(page.locator('#currentEdgeCommand')).toBeVisible();
}

test('decision-first scanner renders every market and follows the canonical model spec', async ({ page }) => {
  await openDashboard(page);

  await expect(page.locator('.decision-scanner-list [data-decision-market]')).toHaveCount(7);
  await expect(page.locator('#wcCommandCenter')).toBeHidden();

  const weights = await page.evaluate(() => window.__COT_WORLDCLASS_BASE__.MODEL_SPEC.score_models);
  expect(weights.tff.category_weights.other_reportable).toBe(0);
  expect(weights.tff.category_weights.non_reportable).toBe(0);
  expect(weights.legacy.category_weights.commercial).toBe(0);
  expect(weights.disaggregated.category_weights.producer_merchant).toBe(0);
});

test('decision-layer market selection synchronizes with instrument tabs and deep links', async ({ page }) => {
  await openDashboard(page);

  await page.locator('[data-decision-market="nq"]').click();
  await expect(page.locator('#instrumentTabs [data-market="nq"]')).toHaveClass(/active/);
  await expect(page).toHaveURL(/market=nq/);
  await expect(page.locator('.decision-current')).toContainText(/NASDAQ-100/i);

  await page.locator('#instrumentTabs [data-market="gold"]').click();
  await expect(page).toHaveURL(/market=gold/);
  await expect(page.locator('.decision-current')).toContainText(/GOLD/i);
});

test('delayed CFTC health is preserved in diagnostics and surfaced as a check state', async ({ page }) => {
  const delayed = {
    ...liveRelease,
    state: 'DELAYED',
    latest_cot_report_date: '2026-07-28',
    expected_cot_report_date: '2026-08-04',
    delayed_markets: ['nq'],
    market_states: { ...liveRelease.market_states, nq: { state: 'DELAYED', latest_cot_report_date: '2026-07-28', expected_cot_report_date: '2026-08-04' } }
  };
  await openDashboard(page, delayed, healthyTrack);

  await expect(page.locator('#wcCommandCenter .wc-v3-integrity')).toContainText('DELAYED');
  await expect(page.locator('#wcCommandCenter')).toBeHidden();
  await expect(page.locator('#wcDataHealthButton')).toContainText(/CHECK|FRESH/, { timeout: 10000 });
});

test('shared metals payload performs one physical request during initial render', async ({ page }) => {
  let metalsRequests = 0;
  page.on('request', request => {
    if (/\/worldclass\/metals\.json(?:\?|$)/.test(request.url())) metalsRequests += 1;
  });

  await openDashboard(page);
  expect(metalsRequests).toBe(1);
});

test('decision-first command surface passes automated WCAG A/AA checks', async ({ page }) => {
  await openDashboard(page);
  const results = await new AxeBuilder({ page })
    .include('#currentEdgeCommand')
    .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
    .analyze();
  expect(results.violations).toEqual([]);
});
