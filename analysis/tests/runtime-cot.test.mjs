import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import { reportHistory, releaseDate } from '../../api/cot.js';

const sourceRow = (date, overrides = {}) => ({
  report_date_as_yyyy_mm_dd: date, open_interest_all: '297655', change_in_open_interest_all: '13704',
  noncomm_positions_long_all: '84033', noncomm_positions_short_all: '29922',
  change_in_noncomm_long_all: '5381', change_in_noncomm_short_all: '-3334', ...overrides,
});

test('uses published weekly changes and backfills the actual previous report', () => {
  const rows = reportHistory([
    sourceRow('2026-10-06'),
    sourceRow('2026-09-29', { open_interest_all: '283950', noncomm_positions_long_all: '78652', noncomm_positions_short_all: '33256' }),
    sourceRow('2026-09-01', { noncomm_positions_long_all: '84710', noncomm_positions_short_all: '57633' }),
  ], 'legacy');
  assert.equal(rows.at(-1).prior_report_date, '2026-09-29');
  assert.equal(rows.at(-1).noncommercial_delta_net, 8715);
  // Consolidated report levels can differ by one contract from published
  // changes; use the CFTC's change, not subtraction of rounded levels.
  assert.equal(rows.at(-1).change_open_interest, 13704);
  assert.equal(rows.at(-1).open_interest - rows.at(-2).open_interest, 13705);
  assert.equal(rows.at(-1).release_date, '2026-10-09');
  assert.equal(rows.at(-1).commercial_net, null);
  assert.equal(rows.at(-1).commercial_position_percentile, null);
});

test('release date uses the canonical holiday and exception calendar', () => {
  assert.equal(releaseDate('2026-10-06').date, '2026-10-09');
  assert.equal(releaseDate('2021-06-15').date, '2021-06-21');
  assert.equal(releaseDate('2026-11-24').date, '2026-11-30');
});

test('recent percentile uses full expanding history before the bounded chart tail', () => {
  const rows = [];
  for (let i = 0; i < 400; i++) {
    const date = new Date('2018-01-02T12:00:00Z'); date.setUTCDate(date.getUTCDate() + i * 7);
    rows.unshift(sourceRow(date.toISOString().slice(0, 10), { open_interest_all: '1000',
      noncomm_positions_long_all: String(i < 88 ? 900 : i === 399 ? 500 : 100), noncomm_positions_short_all: '0' }));
  }
  const history = reportHistory(rows, 'legacy');
  assert.equal(history.length, 312);
  assert.equal(history.at(-1).noncommercial_position_percentile, (311 + .5) / 400 * 100);
});

function coherence(base) {
  // Evaluate the canonical data owner, not a copied implementation.
  const source = readFileSync(new URL('../worldclass/bootstrap.js', import.meta.url), 'utf8');
  const body = source.slice(source.indexOf('  function applyCurrent('), source.indexOf('  function buildRuntimeReleaseOverride('));
  const context = { window: { __COT_WORLDCLASS_BASE__: base, __COT_LIVE_API__: { markets: { nq: {} }, fetchedAt: '2026-10-10T12:00:00Z' } },
    finiteNumber: value => value === null || value === undefined || value === '' || !Number.isFinite(Number(value)) ? null : Number(value),
    pct: (v, total) => Number.isFinite(v) && total ? v / total * 100 : null };
  vm.runInNewContext(body, context);
  return context.window.__COT_RUNTIME_COHERENCE__;
}

test('current data keeps report filtering, release date and score coherent', () => {
  const records = reportHistory([sourceRow('2026-10-06'), sourceRow('2026-09-29')], 'legacy');
  const base = { COT_DATA: { legacy: { nq: { categories: { noncommercial: 'Noncommercial' }, records } } },
    MODEL_SPEC: { score_models: { legacy: { category_weights: { noncommercial: 1 } } } } };
  const owner = coherence(base);
  const current = owner.applyCurrent({ presentation_selection: { financial_report: 'legacy' }, actor_states: {
    'legacy:nq:noncommercial': { dataset: 'legacy', actor_role: 'PRIMARY_DIRECTIONAL' },
    'tff:nq:dealer': { dataset: 'tff', market: 'nq' } } });
  assert.deepEqual(Object.keys(current.actor_states), ['legacy:nq:noncommercial']);
  assert.equal(current.actor_states['legacy:nq:noncommercial'].delta_net_contracts, 8715);
  assert.equal(current.actor_states['legacy:nq:noncommercial'].release_date_friday, '2026-10-09');
  const regime = owner.regimeCurrent('legacy', 'nq', { report_date: '2026-09-01', cot_score: 61 });
  assert.equal(regime.report_date, '2026-10-06');
  assert.equal(regime.cot_score, records.at(-1).noncommercial_position_percentile);
  assert.equal(regime.cot_score_delta_4w, null);
});

function edgeModel() {
  const context = { window: {} };
  vm.runInNewContext(readFileSync(new URL('../worldclass/current-edge-model.js', import.meta.url), 'utf8'), context);
  return context.window.__COT_CURRENT_EDGE_MODEL__;
}

test('reselects frozen thresholds for the current flow and each horizon', () => {
  const model = edgeModel();
  const actor = { series: 'legacy:nq:noncommercial', market: 'nq', dataset: 'legacy',
    direction: 'ADD', change_magnitude_percentile: 68, actor_role: 'PRIMARY_DIRECTIONAL', report_date_tuesday: '2026-10-06' };
  model.state.current = { actor_states: { [actor.series]: actor } };
  const candidates = { historical_research_frozen: true, candidates: [{ ...actor, threshold_profiles: {
    60: [{ horizon: '1w', evidence_status: 'NONOVERLAP_CONFIRMED', independent_n: 30 },
         { horizon: '4w', evidence_status: 'DISCOVERY_ONLY', independent_n: 20 }],
    65: [{ horizon: '1w', evidence_status: 'DISCOVERY_ONLY', independent_n: 20 },
         { horizon: '4w', evidence_status: 'NONOVERLAP_CONFIRMED', independent_n: 20 }],
    75: [{ horizon: '1w', evidence_status: 'GLOBAL_FDR', independent_n: 30 }],
  } }] };
  model.state.active = model.rebuildActive(candidates, {});
  const selected = model.state.active.all_taxonomy_by_market.nq.active_thresholds[0];
  assert.equal(selected.horizon_selections['1w'].selected_threshold, 60);
  assert.equal(selected.horizon_selections['4w'].selected_threshold, 65);
  assert.equal(selected.current_change_percentile, 68);
  actor.change_magnitude_percentile = 43;
  assert.deepEqual(Object.keys(model.rebuildActive(candidates, {}).all_taxonomy_by_market), []);
});

test('withholds older and unidentified forecasts instead of attaching them to a new release', () => {
  const model = edgeModel();
  model.state.current = { actor_states: { x: { market: 'nq', report_date_tuesday: '2026-10-06' } } };
  const valid = { market: 'nq', report_date: '2026-10-06', created_at_utc: '2026-10-09T20:00:00Z',
    forecast_hash: 'verified-hash', model_family: 'cot', expected_1w_return_pct: .5 };
  model.state.live = { current_predictions: [{ ...valid, report_date: '2026-09-01', expected_1w_return_pct: 2.34 }] };
  assert.equal(model.liveForecast('nq', '1w', 'cot'), null);
  model.state.live.current_predictions = [{ ...valid, report_date: undefined }];
  assert.equal(model.liveForecast('nq', '1w', 'cot'), null);
  model.state.live.current_predictions = [valid];
  assert.equal(model.liveForecast('nq', '1w', 'cot').expected, .5);
  assert.equal(model.liveForecast('nq', '1w', 'combined'), null);
});
