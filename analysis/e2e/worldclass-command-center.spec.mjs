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
  await page.goto('/worldclass_dashboard.html');
  await expect(page.getByRole('heading', { name: 'COT Intelligence' })).toBeVisible();
  await page.waitForFunction(() => Boolean(window.__COT_WORLDCLASS_BASE__?.MODEL_SPEC));
  await expect(page.locator('#wcCommandCenter')).toBeVisible();
  await expect(page.locator('#wcCommandCenter .wc-v3-integrity')).toBeVisible();
}

test('command center renders every market and follows the canonical model spec', async ({ page }) => {
  await openDashboard(page);

  const commandCenter = page.locator('#wcCommandCenter');
  await expect(commandCenter.locator('.wc-v3-market-grid [data-wc-v3-market]')).toHaveCount(7);
  await expect(commandCenter).toContainText('GLOBAL POSITIONING COMMAND CENTER');
  await expect(commandCenter).toContainText('PRODUCTION HEALTH');
  await expect(commandCenter).toContainText('DISLOCATION RADAR');
  await expect(commandCenter).toContainText('WHY NOW');
  await expect(commandCenter).toContainText('CONFIRMATION');
  await expect(commandCenter).toContainText('INVALIDATION');
  await expect(commandCenter).toContainText('FORWARD TESTING');

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

  await page.locator('#wcCommandCenter .wc-v3-market-grid [data-wc-v3-market="nq"]').click();
  await expect(page.locator('#instrumentTabs [data-market="nq"]')).toHaveClass(/active/);
  await expect(page.locator('#wcCommandCenter .wc-v3-verdict h3')).toContainText('Nasdaq-100');

  await page.keyboard.press('6');
  await expect(page.locator('#instrumentTabs [data-market="gold"]')).toHaveClass(/active/);
  await expect(page.locator('#wcCommandCenter .wc-v3-verdict h3')).toContainText('Gold');
});

test('command center never hides delayed release health behind a neutral score', async ({ page }) => {
  const delayed = {
    ...liveRelease,
    state: 'DELAYED',
    latest_cot_report_date: '2026-07-28',
    expected_cot_report_date: '2026-08-04',
    delayed_markets: ['nq'],
    market_states: { ...liveRelease.market_states, nq: { state: 'DELAYED', latest_cot_report_date: '2026-07-28', expected_cot_report_date: '2026-08-04' } }
  };
  await openDashboard(page, delayed, healthyTrack);

  const commandCenter = page.locator('#wcCommandCenter');
  const nqCard = commandCenter.locator('.wc-v3-market-grid [data-wc-v3-market="nq"]');
  await expect(commandCenter.locator('.wc-v3-integrity')).toContainText('DELAYED');
  await expect(nqCard).toContainText('DELAYED');
  await nqCard.click();
  await expect(commandCenter.locator('.wc-v3-verdict-meta')).toContainText('Evidence quality');
});

test('command center passes automated WCAG A/AA checks', async ({ page }) => {
  await openDashboard(page);
  const results = await new AxeBuilder({ page })
    .include('#wcCommandCenter')
    .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
    .analyze();
  expect(results.violations).toEqual([]);
});