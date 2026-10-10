import RELEASE_CALENDAR from '../analysis/reference/cftc_release_calendar.json' with { type: 'json' };
const TFF_DATASET = 'gpe5-46if';
const LEGACY_DATASET = '6dca-aqww';
const API_ROOT = 'https://publicreporting.cftc.gov/resource';

const MARKETS = {
  sp500: {
    code: '13874+',
    name: 'S&P 500 Consolidated',
    symbol: 'ES',
    exactName: 'S&P 500 Consolidated - CHICAGO MERCANTILE EXCHANGE',
  },
  nq: {
    code: '20974+',
    name: 'NASDAQ-100 Consolidated',
    symbol: 'NQ',
    exactName: 'NASDAQ-100 Consolidated - CHICAGO MERCANTILE EXCHANGE',
  },
};

const TFF_FIELDS = [
  'market_and_exchange_names',
  'report_date_as_yyyy_mm_dd',
  'cftc_contract_market_code',
  'open_interest_all',
  'change_in_open_interest_all',
  'dealer_positions_long_all',
  'dealer_positions_short_all',
  'change_in_dealer_long_all',
  'change_in_dealer_short_all',
  'asset_mgr_positions_long',
  'asset_mgr_positions_short',
  'change_in_asset_mgr_long',
  'change_in_asset_mgr_short',
  'lev_money_positions_long',
  'lev_money_positions_short',
  'change_in_lev_money_long',
  'change_in_lev_money_short',
  'other_rept_positions_long',
  'other_rept_positions_short',
  'change_in_other_rept_long',
  'change_in_other_rept_short',
  'nonrept_positions_long_all',
  'nonrept_positions_short_all',
  'change_in_nonrept_long_all',
  'change_in_nonrept_short_all',
].join(',');

const LEGACY_FIELDS = [
  'market_and_exchange_names',
  'report_date_as_yyyy_mm_dd',
  'cftc_contract_market_code',
  'open_interest_all',
  'change_in_open_interest_all',
  'noncomm_positions_long_all',
  'noncomm_positions_short_all',
  'change_in_noncomm_long_all',
  'change_in_noncomm_short_all',
  'comm_positions_long_all',
  'comm_positions_short_all',
  'change_in_comm_long_all',
  'change_in_comm_short_all',
  'tot_rept_positions_long_all',
  'tot_rept_positions_short',
  'change_in_tot_rept_long_all',
  'change_in_tot_rept_short',
  'nonrept_positions_long_all',
  'nonrept_positions_short_all',
  'change_in_nonrept_long_all',
  'change_in_nonrept_short_all',
].join(',');

function asNumber(value) {
  if (value === null || value === undefined || value === '') return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function net(longValue, shortValue) {
  const long = asNumber(longValue);
  const short = asNumber(shortValue);
  return long === null || short === null ? null : long - short;
}

function changeNet(longValue, shortValue) {
  return net(longValue, shortValue);
}

function percentileRank(values, current) {
  const clean = values.filter(Number.isFinite).sort((a, b) => a - b);
  if (!clean.length || !Number.isFinite(current)) return null;
  const atOrBelow = clean.filter((value) => value <= current).length;
  return Math.round((atOrBelow / clean.length) * 1000) / 10;
}

function percentOfOpenInterest(value, openInterest) {
  if (!Number.isFinite(value) || !Number.isFinite(openInterest) || openInterest === 0) return null;
  return Math.round((value / openInterest) * 10000) / 100;
}

function category(row, longField, shortField, changeLongField, changeShortField, historyRows) {
  const long = asNumber(row?.[longField]);
  const short = asNumber(row?.[shortField]);
  const currentNet = net(long, short);
  const weeklyChange = changeNet(row?.[changeLongField], row?.[changeShortField]);
  const openInterest = asNumber(row?.open_interest_all);
  const history = historyRows.slice(0, 156).map((item) => net(item[longField], item[shortField]));

  return {
    long,
    short,
    net: currentNet,
    weeklyChange,
    changeLong: asNumber(row?.[changeLongField]),
    changeShort: asNumber(row?.[changeShortField]),
    netPctOpenInterest: percentOfOpenInterest(currentNet, openInterest),
    percentile3y: percentileRank(history, currentNet),
  };
}

function exactRows(rows, market) {
  return rows
    .filter((row) => row.cftc_contract_market_code === market.code)
    .filter((row) => row.market_and_exchange_names?.trim() === market.exactName)
    .sort((a, b) => new Date(b.report_date_as_yyyy_mm_dd) - new Date(a.report_date_as_yyyy_mm_dd));
}

async function fetchDataset(dataset, select) {
  const codes = Object.values(MARKETS).map((market) => `'${market.code}'`).join(',');
  const url = new URL(`${API_ROOT}/${dataset}.json`);
  // Full history is needed for the governed expanding percentiles. The API
  // returns a bounded chart tail, plus full-history metrics for recent reports.
  url.searchParams.set('$limit', '10000');
  url.searchParams.set('$select', select);
  url.searchParams.set('$where', `cftc_contract_market_code in (${codes})`);
  url.searchParams.set('$order', 'report_date_as_yyyy_mm_dd DESC');

  const response = await fetch(url, {
    headers: {
      Accept: 'application/json',
      'User-Agent': 'cot-report-vercel/1.0',
    },
    cache: 'no-store',
  });

  if (!response.ok) {
    throw new Error(`CFTC ${dataset} request failed with ${response.status}`);
  }

  return response.json();
}

function releaseState(reportDate) {
  if (!reportDate) return { state: 'unavailable', ageDays: null };
  const ageMs = Date.now() - new Date(reportDate).getTime();
  const ageDays = Math.max(0, Math.floor(ageMs / 86_400_000));
  if (ageDays <= 10) return { state: 'current', ageDays };
  if (ageDays <= 17) return { state: 'delayed', ageDays };
  return { state: 'stale', ageDays };
}

const ACTOR_FIELDS = {
  tff: {
    dealer: ['dealer_positions_long_all', 'dealer_positions_short_all', 'change_in_dealer_long_all', 'change_in_dealer_short_all'],
    asset_mgr: ['asset_mgr_positions_long', 'asset_mgr_positions_short', 'change_in_asset_mgr_long', 'change_in_asset_mgr_short'],
    lev_money: ['lev_money_positions_long', 'lev_money_positions_short', 'change_in_lev_money_long', 'change_in_lev_money_short'],
    other_reportable: ['other_rept_positions_long', 'other_rept_positions_short', 'change_in_other_rept_long', 'change_in_other_rept_short'],
    non_reportable: ['nonrept_positions_long_all', 'nonrept_positions_short_all', 'change_in_nonrept_long_all', 'change_in_nonrept_short_all'],
  },
  legacy: {
    noncommercial: ['noncomm_positions_long_all', 'noncomm_positions_short_all', 'change_in_noncomm_long_all', 'change_in_noncomm_short_all'],
    commercial: ['comm_positions_long_all', 'comm_positions_short_all', 'change_in_comm_long_all', 'change_in_comm_short_all'],
    total_reportable: ['tot_rept_positions_long_all', 'tot_rept_positions_short', 'change_in_tot_rept_long_all', 'change_in_tot_rept_short'],
    nonreportable: ['nonrept_positions_long_all', 'nonrept_positions_short_all', 'change_in_nonrept_long_all', 'change_in_nonrept_short_all'],
  },
};

const day = value => String(value || '').slice(0, 10);
const dateAt = value => new Date(`${day(value)}T12:00:00Z`);
function observed(date) {
  const copy = new Date(date);
  if (copy.getUTCDay() === 6) copy.setUTCDate(copy.getUTCDate() - 1);
  if (copy.getUTCDay() === 0) copy.setUTCDate(copy.getUTCDate() + 1);
  return day(copy.toISOString());
}
function nthWeekday(year, month, weekday, nth) {
  const date = new Date(Date.UTC(year, month, 1, 12));
  date.setUTCDate(1 + (weekday - date.getUTCDay() + 7) % 7 + 7 * (nth - 1));
  return day(date.toISOString());
}
function holidays(year) {
  const lastMonday = new Date(Date.UTC(year, 5, 0, 12));
  lastMonday.setUTCDate(lastMonday.getUTCDate() - (lastMonday.getUTCDay() + 6) % 7);
  return new Set([
    observed(new Date(Date.UTC(year, 0, 1, 12))), observed(new Date(Date.UTC(year + 1, 0, 1, 12))),
    nthWeekday(year, 0, 1, 3), nthWeekday(year, 1, 1, 3), day(lastMonday.toISOString()),
    ...(year >= 2021 ? [observed(new Date(Date.UTC(year, 5, 19, 12)))] : []),
    observed(new Date(Date.UTC(year, 6, 4, 12))), nthWeekday(year, 8, 1, 1), nthWeekday(year, 9, 1, 2),
    observed(new Date(Date.UTC(year, 10, 11, 12))), nthWeekday(year, 10, 4, 4), observed(new Date(Date.UTC(year, 11, 25, 12))),
  ]);
}
export function releaseDate(reportDate) {
  const exception = RELEASE_CALENDAR.exceptions?.[day(reportDate)];
  if (exception) return { date: exception.release_date, source: exception.source_type || 'CFTC_ACTUAL_EXCEPTION' };
  const cursor = dateAt(reportDate);
  let businessDays = 0;
  while (businessDays < 3) {
    cursor.setUTCDate(cursor.getUTCDate() + 1);
    if (![0, 6].includes(cursor.getUTCDay()) && !holidays(cursor.getUTCFullYear()).has(day(cursor.toISOString()))) businessDays++;
  }
  return { date: day(cursor.toISOString()), source: 'NORMAL_BUSINESS_DAY_SCHEDULE_ASSUMPTION' };
}
function midrank(values, current) {
  const clean = values.filter(Number.isFinite);
  if (!clean.length || !Number.isFinite(current)) return null;
  const less = clean.filter(value => value < current).length;
  const equal = clean.filter(value => value === current).length;
  return (less + equal / 2) / clean.length * 100;
}
export function reportHistory(rows, dataset) {
  const records = [...rows].reverse().map((row, index, ascending) => {
    const release = releaseDate(row.report_date_as_yyyy_mm_dd);
    const oi = asNumber(row.open_interest_all);
    const record = { date: day(row.report_date_as_yyyy_mm_dd), open_interest: oi,
      change_open_interest: asNumber(row.change_in_open_interest_all),
      prior_report_date: index ? day(ascending[index - 1].report_date_as_yyyy_mm_dd) : null,
      release_date: release.date, release_source: release.source, runtime_authority: '/api/cot' };
    for (const [actor, fields] of Object.entries(ACTOR_FIELDS[dataset])) {
      const [long, short, dl, ds] = fields.map(field => asNumber(row[field]));
      const n = net(long, short);
      record[`${actor}_long`] = long; record[`${actor}_short`] = short; record[`${actor}_net`] = n;
      record[`${actor}_net_oi_pct`] = oi && n !== null ? n / oi * 100 : null;
      record[`${actor}_short_oi_pct`] = oi && short !== null ? short / oi * 100 : null;
      record[`${actor}_delta_long`] = dl; record[`${actor}_delta_short`] = ds;
      record[`${actor}_delta_net`] = net(dl, ds);
    }
    return record;
  });
  // Recent current/4W scores use expanding FULL history, not the chart tail.
  for (const actor of Object.keys(ACTOR_FIELDS[dataset])) {
    const levels = records.map(record => record[`${actor}_net_oi_pct`]);
    const magnitudes = records.map((record, i) => i && Number.isFinite(levels[i]) && Number.isFinite(levels[i - 1])
      ? Math.abs(levels[i] - levels[i - 1]) : null);
    for (let i = Math.max(0, records.length - 6); i < records.length; i++) {
      records[i][`${actor}_position_percentile`] = midrank(levels.slice(0, i + 1), levels[i]);
      records[i][`${actor}_change_percentile`] = midrank(magnitudes.slice(0, i + 1), magnitudes[i]);
    }
  }
  return records.slice(-312);
}

export function buildMarket(market, tffRows, legacyRows) {
  const tff = exactRows(tffRows, market);
  const legacy = exactRows(legacyRows, market);
  const latestTff = tff[0];
  const latestLegacy = legacy[0];

  if (!latestTff || !latestLegacy) {
    throw new Error(`Missing consolidated CFTC rows for ${market.symbol}`);
  }

  const openInterest = asNumber(latestTff.open_interest_all);
  const assetManager = category(
    latestTff,
    'asset_mgr_positions_long',
    'asset_mgr_positions_short',
    'change_in_asset_mgr_long',
    'change_in_asset_mgr_short',
    tff,
  );
  const leveragedFunds = category(
    latestTff,
    'lev_money_positions_long',
    'lev_money_positions_short',
    'change_in_lev_money_long',
    'change_in_lev_money_short',
    tff,
  );

  return {
    key: market.symbol.toLowerCase(),
    symbol: market.symbol,
    name: market.name,
    code: market.code,
    reportDate: latestTff.report_date_as_yyyy_mm_dd,
    release: releaseState(latestTff.report_date_as_yyyy_mm_dd),
    openInterest,
    changeOpenInterest: asNumber(latestTff.change_in_open_interest_all),
    tff: {
      assetManager,
      leveragedFunds,
      dealer: category(
        latestTff,
        'dealer_positions_long_all',
        'dealer_positions_short_all',
        'change_in_dealer_long_all',
        'change_in_dealer_short_all',
        tff,
      ),
      otherReportables: category(
        latestTff,
        'other_rept_positions_long',
        'other_rept_positions_short',
        'change_in_other_rept_long',
        'change_in_other_rept_short',
        tff,
      ),
      nonReportable: category(
        latestTff,
        'nonrept_positions_long_all',
        'nonrept_positions_short_all',
        'change_in_nonrept_long_all',
        'change_in_nonrept_short_all',
        tff,
      ),
      amVsLeveragedDivergence: Number.isFinite(assetManager.net) && Number.isFinite(leveragedFunds.net)
        ? assetManager.net - leveragedFunds.net
        : null,
      amVsLeveragedDivergencePctOi: Number.isFinite(assetManager.net) && Number.isFinite(leveragedFunds.net)
        ? percentOfOpenInterest(assetManager.net - leveragedFunds.net, openInterest)
        : null,
    },
    legacy: {
      reportDate: latestLegacy.report_date_as_yyyy_mm_dd,
      nonCommercial: category(
        latestLegacy,
        'noncomm_positions_long_all',
        'noncomm_positions_short_all',
        'change_in_noncomm_long_all',
        'change_in_noncomm_short_all',
        legacy,
      ),
      nonReportable: category(
        latestLegacy,
        'nonrept_positions_long_all',
        'nonrept_positions_short_all',
        'change_in_nonrept_long_all',
        'change_in_nonrept_short_all',
        legacy,
      ),
      commercial: category(
        latestLegacy,
        'comm_positions_long_all',
        'comm_positions_short_all',
        'change_in_comm_long_all',
        'change_in_comm_short_all',
        legacy,
      ),
    },
    historyPoints: Math.min(tff.length, 156),
    history: { tff: reportHistory(tff, 'tff'), legacy: reportHistory(legacy, 'legacy') },
  };
}

export default async function handler(request, response) {
  if (request.method !== 'GET') {
    response.setHeader('Allow', 'GET');
    return response.status(405).json({ error: 'Method not allowed' });
  }

  try {
    const [tffRows, legacyRows] = await Promise.all([
      fetchDataset(TFF_DATASET, TFF_FIELDS),
      fetchDataset(LEGACY_DATASET, LEGACY_FIELDS),
    ]);

    const markets = Object.fromEntries(
      Object.entries(MARKETS).map(([key, market]) => [key, buildMarket(market, tffRows, legacyRows)]),
    );
    const reportDates = Object.values(markets).map((market) => market.reportDate).filter(Boolean);
    const latestReportDate = reportDates.sort().at(-1) ?? null;

    // This endpoint is the runtime freshness authority for the dashboard. A
    // near-day edge cache can pin the previous Tuesday report across Friday's
    // CFTC release, so keep the shared cache deliberately short.
    response.setHeader('Cache-Control', 'public, s-maxage=300, stale-while-revalidate=60');
    response.setHeader('Access-Control-Allow-Origin', '*');
    return response.status(200).json({
      source: {
        publisher: 'U.S. Commodity Futures Trading Commission',
        tffDataset: TFF_DATASET,
        legacyDataset: LEGACY_DATASET,
        methodology: 'Consolidated futures-only rows, exact CFTC contract codes 13874+ and 20974+.',
      },
      latestReportDate,
      fetchedAt: new Date().toISOString(),
      markets,
    });
  } catch (error) {
    console.error('COT refresh failed', error);
    response.setHeader('Cache-Control', 'no-store');
    return response.status(502).json({
      error: 'Unable to refresh CFTC data',
      detail: error instanceof Error ? error.message : String(error),
      fetchedAt: new Date().toISOString(),
    });
  }
}
