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
  'nonrept_positions_long_all',
  'nonrept_positions_short_all',
  'change_in_nonrept_long_all',
  'change_in_nonrept_short_all',
].join(',');

function asNumber(value) {
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
  url.searchParams.set('$limit', '1000');
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

function buildMarket(market, tffRows, legacyRows) {
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

    response.setHeader('Cache-Control', 'public, s-maxage=82800, stale-while-revalidate=3600');
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
