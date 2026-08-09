import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

const emptySentiment = {
  schema_version: 1,
  generated_at_utc: '2026-08-09T00:00:00Z',
  provider: 'Adanos',
  sources: ['reddit', 'x', 'news', 'polymarket'],
  history_count: 0,
  latest: null,
  history: []
};

const emptyTrack = {
  schema_version: 1,
  generated_at_utc: '2026-08-09T00:00:00Z',
  forecast_count: 0,
  entry_count: 0,
  outcome_count: 0,
  weekly_vintage_count: 0,
  matured_signal_count: 0,
  complete_signal_count: 0,
  open_signal_count: 0,
  latest_forecast_vintage: null,
  model_versions: [],
  current_predictions: [],
  statistics: [],
  model_comparison: [],
  signal_history: [],
  ledger: {
    integrity: 'PASS',
    latest_manifest_hash: 'GENESIS',
    forecast_count: 0,
    entry_count: 0,
    outcome_count: 0
  }
};

const liveSentiment = {
  schema_version: 1,
  generated_at_utc: '2026-08-09T00:00:00Z',
  latest: {
    observation_date: '2026-08-09',
    composite: {
      state: 'LIVE',
      available_sources: 4,
      required_sources: 4,
      sentiment_index: 64,
      regime: 'BULLISH',
      bullish_pct: 61,
      bearish_pct: 25,
      buzz_score: 78,
      source_disagreement: 0.08
    },
    sources: {
      reddit: { status: 'LIVE', sentiment_index: 62, sentiment_score: 0.24, bullish_pct: 58, bearish_pct: 26, buzz_score: 75, drivers: [] },
      x: { status: 'LIVE', sentiment_index: 67, sentiment_score: 0.34, bullish_pct: 64, bearish_pct: 23, buzz_score: 88, drivers: [] },
      news: { status: 'LIVE', sentiment_index: 60, sentiment_score: 0.20, bullish_pct: 55, bearish_pct: 29, buzz_score: 66, drivers: [] },
      polymarket: { status: 'LIVE', sentiment_index: 66, sentiment_score: 0.32, bullish_pct: 67, bearish_pct: 22, buzz_score: 82, drivers: [] }
    }
  }
};

const liveTrack = {
  schema_version: 1,
  generated_at_utc: '2026-08-14T19:35:10Z',
  forecast_count: 3,
  entry_count: 0,
  outcome_count: 0,
  weekly_vintage_count: 1,
  matured_signal_count: 0,
  complete_signal_count: 0,
  open_signal_count: 3,
  latest_forecast_vintage: '2026-08-14',
  model_versions: ['1.3.0'],
  ledger: { integrity: 'PASS', latest_manifest_hash: 'abc123', forecast_count: 3, entry_count: 0, outcome_count: 0 },
  current_predictions: [
    { signal_id: '1', market: 'nq', dataset: 'tff', model_family: 'combined', signal: 'BULLISH', expected_4w_return_pct: 2.4, probability_positive_4w: 0.68, confidence: 'High', status: 'awaiting close' },
    { signal_id: '2', market: 'sp500', dataset: 'tff', model_family: 'combined', signal: 'NEUTRAL', expected_4w_return_pct: 1.1, probability_positive_4w: 0.57, confidence: 'Medium', status: 'awaiting close' }
  ],
  model_comparison: [{
    model_version: '1.3.0',
    horizon: '4w',
    champion: 'combined',
    challengers: ['cot', 'macro'],
    families: {
      combined: { directional_hit_rate_pct: null, average_realized_return_pct: null, live_edge_vs_unconditional_pct: null, sample_stage: 'INSUFFICIENT SAMPLE', drift: { state: 'INSUFFICIENT SAMPLE' } },
      cot: { directional_hit_rate_pct: null, average_realized_return_pct: null, live_edge_vs_unconditional_pct: null, sample_stage: 'INSUFFICIENT SAMPLE', drift: { state: 'INSUFFICIENT SAMPLE' } },
      macro: { directional_hit_rate_pct: null, average_realized_return_pct: null, live_edge_vs_unconditional_pct: null, sample_stage: 'INSUFFICIENT SAMPLE', drift: { state: 'INSUFFICIENT SAMPLE' } }
    }
  }]
};

async function mockEvidence(page, sentiment = emptySentiment, track = emptyTrack) {
  await page.route('**/worldclass/market-sentiment.json*', route => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(sentiment) }));
  await page.route('**/worldclass/live-track-record.json*', route => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(track) }));
}

async function openDashboard(page) {
  await page.goto('/worldclass_dashboard.html');
  await expect(page.getByRole('heading', { name: 'COT Intelligence' })).toBeVisible();
  await page.waitForFunction(() => Boolean(window.__COT_WORLDCLASS_BASE__?.MODEL_SPEC));
  await expect(page.locator('#headlineCards')).not.toBeEmpty();
}

test('renders model v1.3 and explicit empty evidence states', async ({ page }) => {
  await mockEvidence(page);
  await openDashboard(page);

  const model = await page.evaluate(() => window.__COT_WORLDCLASS_BASE__.MODEL_SPEC);
  expect(model.model_version).toBe('1.3.0');
  expect(model.score_models.tff.category_weights).toEqual({ dealer: 0, asset_mgr: 1.25, lev_money: 0.75, other_reportable: 0, non_reportable: 0 });
  expect(model.score_models.legacy.category_weights).toEqual({ noncommercial: 1, commercial: 0, total_reportable: 0, nonreportable: 0 });
  expect(model.score_models.disaggregated.category_weights).toEqual({ producer_merchant: 0, swap_dealer: 0, managed_money: 1, other_reportable: 0, non_reportable: 0 });

  await expect(page.locator('#marketSentimentPanel')).toContainText('AWAITING COLLECTION');
  await expect(page.locator('#marketSentimentPanel')).toContainText('ADANOS_API_KEY');
  await expect(page.locator('#liveTrackRecordPanel')).toContainText('LEDGER READY');
  await expect(page.locator('#liveTrackRecordPanel')).toContainText('intentionally empty');
});

test('renders live sentiment and prospective forecast evidence', async ({ page }) => {
  await mockEvidence(page, liveSentiment, liveTrack);
  await openDashboard(page);

  await expect(page.locator('#marketSentimentPanel')).toContainText('64');
  await expect(page.locator('#marketSentimentPanel')).toContainText('X / FinTwit');
  await expect(page.locator('#marketSentimentPanel')).toContainText('Polymarket');

  await expect(page.locator('#liveTrackRecordPanel')).toContainText('FORWARD TESTING');
  await expect(page.locator('#liveTrackRecordPanel')).toContainText('Nasdaq-100');
  await expect(page.locator('#liveTrackRecordPanel')).toContainText('+2.40%');
  await expect(page.locator('#liveTrackRecordPanel')).toContainText('CHAMPION');
});

test('new evidence panels have no automated WCAG A/AA violations', async ({ page }) => {
  await mockEvidence(page, liveSentiment, liveTrack);
  await openDashboard(page);
  await expect(page.locator('#marketSentimentPanel')).toBeVisible();
  await expect(page.locator('#liveTrackRecordPanel')).toBeVisible();

  for (const selector of ['#marketSentimentPanel', '#liveTrackRecordPanel']) {
    const results = await new AxeBuilder({ page })
      .include(selector)
      .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
      .analyze();
    expect(results.violations, `${selector} accessibility violations`).toEqual([]);
  }
});
