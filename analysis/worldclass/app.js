(() => {
  "use strict";

  const MARKET_META = {
    sp500: { label: "S&P 500", short: "S&P", type: "index" },
    nq: { label: "Nasdaq-100", short: "NQ", type: "index" },
    vix: { label: "VIX Futures", short: "VIX", type: "vol" },
    rty: { label: "Russell 2000", short: "Russell", type: "index" },
    dow: { label: "Dow Jones", short: "Dow", type: "index" },
    gold: { label: "Gold", short: "Gold", type: "metal" },
    silver: { label: "Silver", short: "Silver", type: "metal" }
  };

  const DATASET_LABELS = {
    tff: "TFF Detailed",
    legacy: "Legacy",
    disaggregated: "Disaggregated"
  };

  const CATEGORY_COLORS = {
    dealer: "#77869a",
    asset_mgr: "#35baf2",
    lev_money: "#31d27c",
    other_reportable: "#a876ff",
    non_reportable: "#ff6675",
    noncommercial: "#35baf2",
    commercial: "#31d27c",
    total_reportable: "#a876ff",
    nonreportable: "#ff8a4c",
    producer_merchant: "#f4b64e",
    swap_dealer: "#5d8df7",
    managed_money: "#31d27c"
  };

  const PRICE_COLORS = {
    sp500: "#ff7d87",
    nq: "#f4f7fb",
    vix: "#a876ff",
    rty: "#f4b64e",
    dow: "#5d8df7",
    gold: "#e8b84a",
    silver: "#b9c7d8"
  };

  // The score is intentionally separate from the older regime-rule engine.
  // It is normalized, visible and auditable. Positive weights mean a high
  // historical percentile is supportive; negative weights are contrarian.
  const SCORE_WEIGHTS = {
    tff: {
      dealer: 0,
      asset_mgr: 1.25,
      lev_money: 0.75,
      other_reportable: -1.0,
      non_reportable: -1.0
    },
    legacy: {
      noncommercial: 1.0,
      commercial: -0.75,
      total_reportable: 0,
      nonreportable: -0.75
    },
    disaggregated: {
      producer_merchant: -0.75,
      swap_dealer: -0.35,
      managed_money: 1.25,
      other_reportable: -0.75,
      non_reportable: -0.75
    }
  };

  const METRIC_LABELS = {
    net_oi_pct: "Net / open interest (%)",
    net: "Net contracts",
    long: "Long contracts",
    short: "Short contracts",
    short_oi_pct: "Short / open interest (%)"
  };

  const state = {
    market: "sp500",
    dataset: "tff",
    metric: "net_oi_pct",
    range: "all",
    activeCategories: new Set(),
    priceOverlays: new Set(["sp500"]),
    factorOverlays: new Set(["macro_score"]),
    theme: localStorage.getItem("cot-worldclass-theme") === "light" ? "light" : "dark"
  };

  const db = {
    COT_DATA: {},
    PRICE_DATA: {},
    FACTOR_DATA: {},
    LIQUIDITY_DATA: {},
    MACRO_MONITOR: {},
    MACRO_LENS: {},
    METADATA: {},
    metals: null
  };

  const $ = (selector) => document.querySelector(selector);
  const $$ = (selector) => [...document.querySelectorAll(selector)];

  function finite(value) {
    const number = Number(value);
    return Number.isFinite(number) ? number : null;
  }

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function extractEmbeddedJson(text, name) {
    const marker = `const ${name} = `;
    let cursor = text.indexOf(marker);
    if (cursor < 0) return null;
    cursor += marker.length;
    while (/\s/.test(text[cursor] || "")) cursor += 1;

    const start = cursor;
    let depth = 0;
    let started = false;
    let inString = false;
    let escaped = false;

    for (; cursor < text.length; cursor += 1) {
      const char = text[cursor];
      if (inString) {
        if (escaped) escaped = false;
        else if (char === "\\") escaped = true;
        else if (char === '"') inString = false;
        continue;
      }
      if (char === '"') {
        inString = true;
        continue;
      }
      if (char === "{" || char === "[") {
        depth += 1;
        started = true;
      } else if (char === "}" || char === "]") {
        depth -= 1;
        if (started && depth === 0) {
          try {
            return JSON.parse(text.slice(start, cursor + 1));
          } catch (error) {
            console.warn(`Unable to parse ${name}`, error);
            return null;
          }
        }
      }
    }
    return null;
  }

  async function loadData() {
    const response = await fetch("interactive_cot_dashboard.html", { cache: "no-store" });
    if (!response.ok) throw new Error(`Base dashboard data returned HTTP ${response.status}`);
    const html = await response.text();
    for (const name of [
      "COT_DATA", "PRICE_DATA", "FACTOR_DATA", "LIQUIDITY_DATA",
      "MACRO_MONITOR", "MACRO_LENS", "METADATA"
    ]) {
      db[name] = extractEmbeddedJson(html, name) || {};
    }

    try {
      const metalResponse = await fetch(`worldclass/metals.json?v=${Date.now()}`, { cache: "no-store" });
      if (metalResponse.ok) {
        db.metals = await metalResponse.json();
        db.COT_DATA.disaggregated = db.metals.markets || {};
        for (const [market, payload] of Object.entries(db.metals.prices || {})) {
          db.PRICE_DATA[market] = payload;
        }
      }
    } catch (error) {
      console.warn("Gold/Silver disaggregated data unavailable", error);
    }
  }

  function datasetPayload(dataset = state.dataset, market = state.market) {
    return db.COT_DATA?.[dataset]?.[market] || null;
  }

  function payloadRecords(payload = datasetPayload()) {
    const records = payload?.records;
    return Array.isArray(records) ? records.filter(row => row?.date) : [];
  }

  function availableDatasets(market) {
    const priority = market === "gold" || market === "silver"
      ? ["disaggregated", "legacy", "tff"]
      : ["tff", "legacy", "disaggregated"];
    return priority.filter(key => payloadRecords(db.COT_DATA?.[key]?.[market]).length > 1);
  }

  function chooseDatasetForMarket(market, requested = null) {
    const available = availableDatasets(market);
    if (requested && available.includes(requested)) return requested;
    return available[0] || "tff";
  }

  function marketAvailable(market) {
    return availableDatasets(market).length > 0 || priceRecords(market).length > 0;
  }

  function categoryMap() {
    return datasetPayload()?.categories || {};
  }

  function categoryKeys() {
    return Object.keys(categoryMap());
  }

  function fieldFor(category, metric = state.metric) {
    return `${category}_${metric}`;
  }

  function priceRecords(market) {
    const payload = db.PRICE_DATA?.[market];
    if (Array.isArray(payload)) return payload.filter(row => row?.date && finite(row?.price) !== null);
    if (Array.isArray(payload?.records)) return payload.records.filter(row => row?.date && finite(row?.price) !== null);
    return [];
  }

  function currentRows() {
    return payloadRecords();
  }

  function currentLatest() {
    const rows = currentRows();
    return rows.at(-1) || {};
  }

  function currentPrior() {
    const rows = currentRows();
    return rows.at(-2) || {};
  }

  function signed(value, digits = 0, suffix = "") {
    const number = finite(value);
    if (number === null) return "n/a";
    const formatted = Math.abs(number).toLocaleString(undefined, {
      minimumFractionDigits: digits,
      maximumFractionDigits: digits
    });
    return `${number > 0 ? "+" : number < 0 ? "−" : ""}${formatted}${suffix}`;
  }

  function number(value, digits = 0) {
    const n = finite(value);
    if (n === null) return "n/a";
    return n.toLocaleString(undefined, { minimumFractionDigits: digits, maximumFractionDigits: digits });
  }

  function pct(value, digits = 2) {
    const n = finite(value);
    return n === null ? "n/a" : `${n.toFixed(digits)}%`;
  }

  function signedClass(value, neutral = 0) {
    const n = finite(value);
    if (n === null || Math.abs(n) <= neutral) return "value-muted";
    return n > 0 ? "value-positive" : "value-negative";
  }

  function toneClass(score) {
    const n = finite(score);
    if (n === null) return "";
    if (n >= 58) return "positive";
    if (n <= 42) return "negative";
    return "warning";
  }

  function percentile(history, value) {
    const current = finite(value);
    const clean = history.map(finite).filter(v => v !== null).sort((a, b) => a - b);
    if (current === null || !clean.length) return null;
    let less = 0;
    let equal = 0;
    for (const item of clean) {
      if (item < current) less += 1;
      else if (item === current) equal += 1;
    }
    return ((less + Math.max(equal, 1) / 2) / clean.length) * 100;
  }

  function cotScore() {
    const rows = currentRows();
    const latest = rows.at(-1) || {};
    const weights = SCORE_WEIGHTS[state.dataset] || {};
    let numerator = 0;
    let denominator = 0;
    const components = [];

    for (const key of categoryKeys()) {
      const weight = finite(weights[key]) ?? 0;
      const field = fieldFor(key, "net_oi_pct");
      const value = finite(latest[field]);
      const rank = percentile(rows.map(row => row[field]), value);
      const centered = rank === null ? null : (rank - 50) / 50;
      const contribution = centered === null ? 0 : weight * centered;
      if (weight !== 0 && centered !== null) {
        numerator += contribution;
        denominator += Math.abs(weight);
      }
      components.push({
        key,
        label: categoryMap()[key] || key,
        value,
        percentile: rank,
        weight,
        contribution
      });
    }

    const normalized = denominator ? 50 + 50 * (numerator / denominator) : 50;
    const score = Math.max(0, Math.min(100, normalized));
    let label = "Balanced";
    if (score >= 65) label = "Bullish positioning";
    else if (score >= 56) label = "Constructive";
    else if (score <= 35) label = "Bearish positioning";
    else if (score <= 44) label = "Cautious";
    return { score, label, components };
  }

  function flowClassification(longDelta, shortDelta, netDelta) {
    const l = finite(longDelta);
    const s = finite(shortDelta);
    const n = finite(netDelta);
    if (l === null || s === null || n === null) return { text: "n/a", tone: "" };
    if (Math.abs(n) < 1e-9) return { text: "Net unchanged", tone: "" };
    if (n > 0) {
      if (l > 0 && s < 0) return { text: "Long add + short cover", tone: "positive" };
      if (l > 0 && s >= 0) return { text: "Long accumulation", tone: "positive" };
      if (s < 0 && l <= 0) return { text: "Short covering", tone: "positive" };
      return { text: "Net bullish rotation", tone: "positive" };
    }
    if (l < 0 && s > 0) return { text: "Long liquidate + shorts add", tone: "negative" };
    if (s > 0 && l <= 0) return { text: "Short accumulation", tone: "negative" };
    if (l < 0 && s >= 0) return { text: "Long liquidation", tone: "negative" };
    return { text: "Net bearish rotation", tone: "negative" };
  }

  function daysBetween(left, right = new Date()) {
    if (!left) return null;
    const parsed = new Date(`${left}T12:00:00Z`);
    if (Number.isNaN(parsed.getTime())) return null;
    return Math.floor((right.getTime() - parsed.getTime()) / 86400000);
  }

  function findSeries(root, valueKeys) {
    const aliases = Array.isArray(valueKeys) ? valueKeys : [valueKeys];
    const seen = new Set();
    let best = null;
    let bestScore = -Infinity;

    function inspect(node, depth = 0) {
      if (!node || depth > 6 || typeof node !== "object" || seen.has(node)) return;
      seen.add(node);
      if (Array.isArray(node)) {
        const sample = node.find(row => row && typeof row === "object" && row.date);
        if (sample) {
          for (const key of aliases) {
            const validCount = node.reduce((count, row) => count + (row?.date && finite(row?.[key]) !== null ? 1 : 0), 0);
            const score = validCount + (validCount >= 20 ? 100 : 0);
            if (score > bestScore) {
              bestScore = score;
              best = { rows: node, key };
            }
          }
        }
        for (const child of node.slice(0, 5)) inspect(child, depth + 1);
        return;
      }
      for (const value of Object.values(node)) inspect(value, depth + 1);
    }
    inspect(root);
    if (!best || bestScore <= 0) return [];
    return best.rows
      .filter(row => row?.date && finite(row?.[best.key]) !== null)
      .map(row => ({ date: String(row.date).slice(0, 10), value: finite(row[best.key]), raw: row }));
  }

  function findLatestObject(root, preferredKeys) {
    if (root?.latest && typeof root.latest === "object") return root.latest;
    const series = findSeries(root, preferredKeys);
    return series.at(-1)?.raw || {};
  }

  function macroScoreSeries() {
    return findSeries(db.MACRO_MONITOR, ["liquidity_score", "macro_score", "unified_score", "score"]);
  }

  function macroLatest() {
    return findLatestObject(db.MACRO_MONITOR, ["liquidity_score", "macro_score", "unified_score", "score"]);
  }

  function macroScoreValue() {
    const latest = macroLatest();
    for (const key of ["liquidity_score", "macro_score", "unified_score", "score"]) {
      const value = finite(latest?.[key]);
      if (value !== null && value >= 0 && value <= 100) return value;
    }
    const row = macroScoreSeries().at(-1);
    return row?.value ?? null;
  }

  function genericSeriesForFactor(key) {
    const direct = db.FACTOR_DATA?.[key];
    const candidate = findSeries(direct || db.FACTOR_DATA, ["value", key, "score"]);
    if (candidate.length) return candidate;
    const aliases = {
      fred_vix: ["vix", "fred_vix"],
      real_yield_10y: ["real_yield_10y", "dfii10"],
      hy_oas: ["hy_oas", "high_yield_oas"],
      dollar_index: ["dollar_index", "broad_dollar"]
    };
    return findSeries(db.MACRO_MONITOR, aliases[key] || [key]);
  }

  function rangeStart(latestDate) {
    if (state.range === "all" || !latestDate) return null;
    const years = state.range === "1y" ? 1 : state.range === "3y" ? 3 : 5;
    const date = new Date(`${latestDate}T00:00:00Z`);
    date.setUTCFullYear(date.getUTCFullYear() - years);
    return date.toISOString().slice(0, 10);
  }

  function filteredByRange(rows, latestDate) {
    const start = rangeStart(latestDate);
    return start ? rows.filter(row => row.date >= start) : rows;
  }

  function applyTheme() {
    document.documentElement.dataset.theme = state.theme;
    localStorage.setItem("cot-worldclass-theme", state.theme);
    $("#themeToggle").textContent = state.theme === "dark" ? "☾" : "☀";
  }

  function setMarket(market) {
    if (!MARKET_META[market]) return;
    state.market = market;
    state.dataset = chooseDatasetForMarket(market, state.dataset);
    state.activeCategories = new Set(categoryKeys());
    state.priceOverlays.add(market);
    renderAll();
  }

  function setDataset(dataset) {
    if (!availableDatasets(state.market).includes(dataset)) return;
    state.dataset = dataset;
    state.activeCategories = new Set(categoryKeys());
    renderAll();
  }

  function renderInstrumentTabs() {
    $("#instrumentTabs").innerHTML = Object.entries(MARKET_META).map(([key, meta]) => {
      const available = marketAvailable(key);
      const latestDates = availableDatasets(key)
        .map(dataset => payloadRecords(db.COT_DATA?.[dataset]?.[key]).at(-1)?.date)
        .filter(Boolean)
        .sort();
      const latest = latestDates.at(-1) || "data pending";
      return `<button class="instrument-tab ${state.market === key ? "active" : ""}" data-market="${key}" type="button" ${available ? "" : "disabled"}>
        ${escapeHtml(meta.short)}<small>${escapeHtml(latest)}</small>
      </button>`;
    }).join("");
  }

  function controlMarkup() {
    const datasets = availableDatasets(state.market);
    const categories = categoryMap();
    const prices = Object.entries(MARKET_META).filter(([key]) => priceRecords(key).length);
    const factorDefs = [
      ["macro_score", "Macro score", "#f4b64e"],
      ["fred_vix", "VIX", "#a876ff"],
      ["real_yield_10y", "10Y real yield", "#35baf2"],
      ["hy_oas", "HY OAS", "#ff6675"],
      ["dollar_index", "Dollar", "#31d27c"]
    ];
    return `
      <div class="control-block">
        <label class="control-label">COT report</label>
        <select class="control-select" data-control="dataset">
          ${datasets.map(key => `<option value="${key}" ${state.dataset === key ? "selected" : ""}>${DATASET_LABELS[key] || key}</option>`).join("")}
        </select>
      </div>
      <div class="control-block">
        <label class="control-label">Position metric</label>
        <select class="control-select" data-control="metric">
          ${Object.entries(METRIC_LABELS).map(([key, label]) => `<option value="${key}" ${state.metric === key ? "selected" : ""}>${label}</option>`).join("")}
        </select>
      </div>
      <div class="control-block">
        <label class="control-label">Trader groups</label>
        <div class="chip-row">
          ${Object.entries(categories).map(([key, label]) => `<button class="toggle-chip ${state.activeCategories.has(key) ? "active" : ""}" data-category="${key}" type="button" title="${escapeHtml(label)}"><span class="swatch" style="--chip-color:${CATEGORY_COLORS[key] || "#91a2b8"}"></span>${escapeHtml(shortCategory(label))}</button>`).join("")}
        </div>
      </div>
      <div class="control-block">
        <label class="control-label">Price & factor overlays</label>
        <div class="chip-row">
          ${prices.map(([key, meta]) => `<button class="toggle-chip ${state.priceOverlays.has(key) ? "active" : ""}" data-price-overlay="${key}" type="button"><span class="swatch" style="--chip-color:${PRICE_COLORS[key]}"></span>${escapeHtml(meta.short)}</button>`).join("")}
          ${factorDefs.map(([key, label, color]) => `<button class="toggle-chip ${state.factorOverlays.has(key) ? "active" : ""}" data-factor-overlay="${key}" type="button"><span class="swatch" style="--chip-color:${color}"></span>${label}</button>`).join("")}
        </div>
      </div>`;
  }

  function shortCategory(label) {
    return String(label)
      .replace("Asset Manager / Institutional", "Asset Manager")
      .replace("Dealer / Intermediary", "Dealer")
      .replace("Producer / Merchant / Processor / User", "Producer/Merchant")
      .replace("Total Reportable", "Reportable");
  }

  function renderControls() {
    const markup = controlMarkup();
    $("#desktopControls").innerHTML = markup;
    $("#mobileControlBody").innerHTML = markup;
    $("#mobileControlSummary").textContent = `${DATASET_LABELS[state.dataset] || state.dataset} · ${METRIC_LABELS[state.metric]}`;
  }

  function renderFreshness() {
    const latest = currentLatest();
    const age = daysBetween(latest.date);
    const pill = $("#freshnessPill");
    pill.classList.remove("live", "stale");
    let label = latest.date ? `COT ${latest.date}` : "COT unavailable";
    if (age !== null && age <= 10) pill.classList.add("live");
    else if (age !== null && age > 14) {
      pill.classList.add("stale");
      label += " · stale";
    }
    pill.querySelector("span:last-child").textContent = label;
    $("#heroAsOf").innerHTML = `<strong>${escapeHtml(MARKET_META[state.market].label)}</strong>${escapeHtml(DATASET_LABELS[state.dataset] || state.dataset)}<br>Report date ${escapeHtml(latest.date || "n/a")}`;
    $("#footerFreshness").textContent = `Selected COT: ${latest.date || "n/a"} · Dashboard build: ${String(db.METADATA?.generated_at_utc || db.METADATA?.generated_at || "n/a").replace("T", " ").replace("Z", " UTC")}`;

    const alert = $("#alertStrip");
    if (age !== null && age > 14) {
      alert.hidden = false;
      alert.className = "alert-strip danger";
      alert.textContent = `${MARKET_META[state.market].label} COT data is ${age} days old. Treat the positioning signal as stale until the next successful CFTC refresh.`;
    } else if (state.market === "silver" && !datasetPayload()) {
      alert.hidden = false;
      alert.className = "alert-strip";
      alert.textContent = "Silver is configured but the first Disaggregated CFTC refresh has not completed yet.";
    } else {
      alert.hidden = true;
    }
  }

  function weeklyDeltas() {
    const latest = currentLatest();
    const prior = currentPrior();
    return categoryKeys().map(key => {
      const latestNet = finite(latest[fieldFor(key, "net")]);
      const priorNet = finite(prior[fieldFor(key, "net")]);
      const latestLong = finite(latest[fieldFor(key, "long")]);
      const priorLong = finite(prior[fieldFor(key, "long")]);
      const latestShort = finite(latest[fieldFor(key, "short")]);
      const priorShort = finite(prior[fieldFor(key, "short")]);
      const latestPct = finite(latest[fieldFor(key, "net_oi_pct")]);
      const priorPct = finite(prior[fieldFor(key, "net_oi_pct")]);
      const longDelta = latestLong !== null && priorLong !== null ? latestLong - priorLong : null;
      const shortDelta = latestShort !== null && priorShort !== null ? latestShort - priorShort : null;
      const netDelta = latestNet !== null && priorNet !== null ? latestNet - priorNet : null;
      const pctDelta = latestPct !== null && priorPct !== null ? latestPct - priorPct : null;
      return {
        key,
        label: categoryMap()[key] || key,
        latestPct,
        pctDelta,
        longDelta,
        shortDelta,
        netDelta,
        flow: flowClassification(longDelta, shortDelta, netDelta)
      };
    });
  }

  function renderHeadlineCards() {
    const latest = currentLatest();
    const prior = currentPrior();
    const score = cotScore();
    const macro = macroScoreValue();
    const oiDelta = finite(latest.open_interest) !== null && finite(prior.open_interest) !== null
      ? finite(latest.open_interest) - finite(prior.open_interest) : null;
    const weekly = weeklyDeltas().filter(row => row.netDelta !== null);
    const largest = weekly.sort((a, b) => Math.abs(b.netDelta) - Math.abs(a.netDelta))[0];
    const currentPrice = finite(latest.price);
    const priorPrice = finite(prior.price);
    const priceDeltaPct = currentPrice !== null && priorPrice !== null && priorPrice !== 0
      ? (currentPrice / priorPrice - 1) * 100 : null;

    const cards = [
      {
        label: "Directional COT score",
        value: score.score.toFixed(0),
        sub: `${score.label} · 0–100`,
        tone: toneClass(score.score)
      },
      {
        label: "Macro liquidity",
        value: macro === null ? "n/a" : macro.toFixed(0),
        sub: macro === null ? "Macro series unavailable" : "Unified liquidity score",
        tone: toneClass(macro)
      },
      {
        label: "Open interest Δ",
        value: signed(oiDelta),
        sub: `${number(latest.open_interest)} contracts latest`,
        tone: oiDelta > 0 ? "positive" : oiDelta < 0 ? "negative" : ""
      },
      {
        label: "COT-aligned price Δ",
        value: signed(priceDeltaPct, 2, "%"),
        sub: `${number(currentPrice, 2)} latest aligned close`,
        tone: priceDeltaPct > 0 ? "positive" : priceDeltaPct < 0 ? "negative" : ""
      },
      {
        label: "Largest weekly player move",
        value: largest ? signed(largest.netDelta) : "n/a",
        sub: largest ? shortCategory(largest.label) : "No comparable prior row",
        tone: largest?.netDelta > 0 ? "positive" : largest?.netDelta < 0 ? "negative" : ""
      }
    ];

    $("#headlineCards").innerHTML = cards.map(card => `<article class="metric-card ${card.tone || ""}">
      <div class="metric-label">${escapeHtml(card.label)}</div>
      <div class="metric-value">${escapeHtml(card.value)}</div>
      <div class="metric-sub">${escapeHtml(card.sub)}</div>
    </article>`).join("");
  }

  function plotTokens() {
    const light = state.theme === "light";
    return {
      paper: "rgba(0,0,0,0)",
      plot: "rgba(0,0,0,0)",
      grid: light ? "rgba(91,108,130,.13)" : "rgba(128,154,185,.10)",
      text: light ? "#0f1b2d" : "#f3f7fb",
      muted: light ? "#657991" : "#91a2b8",
      zero: light ? "#a7b2c2" : "#40526a"
    };
  }

  function indexedPriceRows(rows, startDate) {
    const visible = startDate ? rows.filter(row => row.date >= startDate) : rows;
    const base = finite(visible[0]?.price);
    return visible.map(row => ({
      date: row.date,
      raw: finite(row.price),
      value: base && finite(row.price) !== null ? finite(row.price) / base * 100 : null
    })).filter(row => row.value !== null);
  }

  function rawPriceRows(rows, startDate) {
    return (startDate ? rows.filter(row => row.date >= startDate) : rows)
      .map(row => ({ date: row.date, raw: finite(row.price), value: finite(row.price) }))
      .filter(row => row.value !== null);
  }

  function renderMainChart() {
    if (!window.Plotly) return;
    const rows = currentRows();
    const latestDate = rows.at(-1)?.date || priceRecords(state.market).at(-1)?.date;
    const startDate = rangeStart(latestDate);
    const cotRows = startDate ? rows.filter(row => row.date >= startDate) : rows;
    const traces = [];

    for (const key of categoryKeys()) {
      if (!state.activeCategories.has(key)) continue;
      const field = fieldFor(key);
      const points = cotRows.filter(row => finite(row[field]) !== null);
      traces.push({
        type: "scatter",
        mode: "lines",
        name: shortCategory(categoryMap()[key] || key),
        x: points.map(row => row.date),
        y: points.map(row => finite(row[field])),
        line: { width: 2.1, color: CATEGORY_COLORS[key] || "#91a2b8" },
        yaxis: "y",
        hovertemplate: `<b>${escapeHtml(categoryMap()[key] || key)}</b><br>%{x}<br>${escapeHtml(METRIC_LABELS[state.metric])}: %{y:,.2f}<extra></extra>`
      });
    }

    const selectedPrices = [...state.priceOverlays].filter(key => priceRecords(key).length);
    const indexPrices = selectedPrices.length > 1;
    for (const market of selectedPrices) {
      const source = priceRecords(market);
      const points = indexPrices ? indexedPriceRows(source, startDate) : rawPriceRows(source, startDate);
      traces.push({
        type: "scatter",
        mode: "lines",
        name: `${MARKET_META[market]?.short || market} price`,
        x: points.map(row => row.date),
        y: points.map(row => row.value),
        customdata: points.map(row => row.raw),
        line: { width: market === state.market ? 2.5 : 1.6, color: PRICE_COLORS[market] || "#ffffff" },
        opacity: market === state.market ? .98 : .74,
        yaxis: "y2",
        hovertemplate: indexPrices
          ? `<b>${escapeHtml(MARKET_META[market]?.label || market)}</b><br>%{x}<br>Indexed: %{y:,.2f}<br>Raw: %{customdata:,.2f}<extra></extra>`
          : `<b>${escapeHtml(MARKET_META[market]?.label || market)}</b><br>%{x}<br>Price: %{y:,.2f}<extra></extra>`
      });
    }

    const factorDefs = {
      macro_score: { label: "Macro liquidity score", color: "#f4b64e", series: macroScoreSeries(), fixed: true },
      fred_vix: { label: "VIX", color: "#a876ff", series: genericSeriesForFactor("fred_vix") },
      real_yield_10y: { label: "10Y real yield", color: "#35baf2", series: genericSeriesForFactor("real_yield_10y") },
      hy_oas: { label: "HY OAS", color: "#ff6675", series: genericSeriesForFactor("hy_oas") },
      dollar_index: { label: "Broad dollar", color: "#31d27c", series: genericSeriesForFactor("dollar_index") }
    };
    for (const key of state.factorOverlays) {
      const def = factorDefs[key];
      if (!def?.series?.length) continue;
      const points = startDate ? def.series.filter(row => row.date >= startDate) : def.series;
      traces.push({
        type: "scatter",
        mode: "lines",
        name: def.label,
        x: points.map(row => row.date),
        y: points.map(row => row.value),
        line: { width: 1.7, dash: "dot", color: def.color },
        opacity: .82,
        yaxis: "y3",
        hovertemplate: `<b>${def.label}</b><br>%{x}<br>%{y:,.2f}<extra></extra>`
      });
    }

    const t = plotTokens();
    const yTitle = METRIC_LABELS[state.metric];
    const y2Title = indexPrices ? "Price (indexed = 100)" : "Price";
    $("#workbenchTitle").textContent = `${MARKET_META[state.market].label} · ${DATASET_LABELS[state.dataset]} positioning`;
    $("#legendHint").textContent = selectedPrices.length > 1 ? "Multiple price overlays are indexed to 100 for comparability" : "Hover any line for exact values";

    Plotly.react("mainChart", traces, {
      paper_bgcolor: t.paper,
      plot_bgcolor: t.plot,
      margin: { l: 64, r: 82, t: 24, b: 54 },
      font: { family: "Inter, ui-sans-serif, sans-serif", color: t.text, size: 11 },
      hovermode: "x unified",
      hoverlabel: { bgcolor: state.theme === "light" ? "#fff" : "#101d30", bordercolor: t.zero, font: { color: t.text } },
      legend: { orientation: "h", x: 0, y: 1.06, xanchor: "left", yanchor: "bottom", font: { size: 10, color: t.muted } },
      xaxis: {
        type: "date",
        gridcolor: t.grid,
        linecolor: t.zero,
        tickfont: { color: t.muted, size: 10 },
        rangeslider: { visible: false },
        fixedrange: false
      },
      yaxis: {
        title: { text: yTitle, font: { size: 10, color: t.muted } },
        gridcolor: t.grid,
        zerolinecolor: t.zero,
        tickfont: { color: t.muted, size: 10 },
        side: "left"
      },
      yaxis2: {
        title: { text: y2Title, font: { size: 10, color: t.muted } },
        overlaying: "y",
        side: "right",
        showgrid: false,
        tickfont: { color: t.muted, size: 10 },
        position: 1
      },
      yaxis3: {
        overlaying: "y",
        side: "right",
        anchor: "free",
        position: .94,
        showgrid: false,
        showticklabels: false,
        range: state.factorOverlays.size === 1 && state.factorOverlays.has("macro_score") ? [0, 100] : undefined
      },
      dragmode: "pan",
      modebar: { orientation: "v" }
    }, {
      responsive: true,
      displaylogo: false,
      scrollZoom: true,
      modeBarButtonsToRemove: ["lasso2d", "select2d"]
    });
  }

  function renderWeeklyChanges() {
    const latest = currentLatest();
    const prior = currentPrior();
    const marketLabel = MARKET_META[state.market].label;
    $("#weeklyChangeHeading").textContent = `${marketLabel} — What changed since last update`;
    $("#weeklyChangeSub").textContent = `${DATASET_LABELS[state.dataset]} · ${latest.date || "n/a"} versus ${prior.date || "n/a"} · exact weekly long/short/net deltas`;

    const oiLatest = finite(latest.open_interest);
    const oiPrior = finite(prior.open_interest);
    const oiDelta = oiLatest !== null && oiPrior !== null ? oiLatest - oiPrior : null;
    const pxLatest = finite(latest.price);
    const pxPrior = finite(prior.price);
    const pxDelta = pxLatest !== null && pxPrior !== null ? pxLatest - pxPrior : null;
    const pxPct = pxLatest !== null && pxPrior !== null && pxPrior !== 0 ? (pxLatest / pxPrior - 1) * 100 : null;
    const totalAbsFlow = weeklyDeltas().reduce((sum, row) => sum + Math.abs(row.netDelta || 0), 0);

    const stats = [
      ["Report comparison", `${latest.date || "n/a"} →`, `Prior: ${prior.date || "n/a"}`, ""],
      ["Open interest", signed(oiDelta), `${number(oiLatest)} latest`, signedClass(oiDelta)],
      ["COT-aligned price", signed(pxDelta, 2), `${signed(pxPct, 2, "%")} week/week`, signedClass(pxDelta)],
      ["Gross category net-flow", number(totalAbsFlow), "Sum of absolute Δ net contracts", ""]
    ];
    $("#weeklyOverview").innerHTML = stats.map(([label, value, sub, cls]) => `<div class="weekly-stat">
      <div class="weekly-stat-label">${escapeHtml(label)}</div>
      <div class="weekly-stat-value ${cls || ""}">${escapeHtml(value)}</div>
      <div class="weekly-stat-sub">${escapeHtml(sub)}</div>
    </div>`).join("");

    $("#weeklyChangeRows").innerHTML = weeklyDeltas().map(row => `<tr>
      <td><span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${CATEGORY_COLORS[row.key] || "#91a2b8"};margin-right:9px"></span>${escapeHtml(row.label)}</td>
      <td>${pct(row.latestPct)}</td>
      <td class="${signedClass(row.pctDelta)}">${signed(row.pctDelta, 2, " pts")}</td>
      <td class="${signedClass(row.longDelta)}">${signed(row.longDelta)}</td>
      <td class="${signedClass(row.shortDelta)}">${signed(row.shortDelta)}</td>
      <td class="${signedClass(row.netDelta)}"><strong>${signed(row.netDelta)}</strong></td>
      <td><span class="flow-badge ${row.flow.tone}">${escapeHtml(row.flow.text)}</span></td>
    </tr>`).join("");
  }

  function renderPositioning() {
    const rows = currentRows();
    const latest = currentLatest();
    const score = cotScore();
    const byKey = Object.fromEntries(score.components.map(item => [item.key, item]));

    $("#positioningPanel").innerHTML = categoryKeys().map(key => {
      const field = fieldFor(key, "net_oi_pct");
      const value = finite(latest[field]);
      const rank = percentile(rows.map(row => row[field]), value);
      const component = byKey[key];
      const zone = rank === null ? "n/a" : rank >= 90 ? "Top 10%" : rank <= 10 ? "Bottom 10%" : rank >= 75 ? "Upper quartile" : rank <= 25 ? "Lower quartile" : "Middle";
      return `<div class="position-row">
        <div class="position-label">${escapeHtml(categoryMap()[key] || key)}<small>${escapeHtml(zone)} · weight ${component?.weight > 0 ? "+" : ""}${number(component?.weight, 2)}</small></div>
        <div class="position-number ${signedClass(value)}">${pct(value)}</div>
        <div class="percentile-track"><div class="percentile-fill" style="width:${rank === null ? 0 : Math.max(1, Math.min(100, rank))}%"></div></div>
        <div class="percentile-label">${rank === null ? "n/a" : `${rank.toFixed(0)}th`}</div>
      </div>`;
    }).join("");
  }

  function renderCotScore() {
    const result = cotScore();
    const tone = result.score >= 58 ? "#31d27c" : result.score <= 42 ? "#ff6675" : "#f4b64e";
    const inverseNames = result.components.filter(item => item.weight < 0).map(item => shortCategory(item.label));
    $("#cotScorePanel").innerHTML = `<div class="score-hero">
      <div class="score-ring" style="--score-angle:${(result.score / 100 * 360).toFixed(1)}deg;--score-color:${tone}">
        <div class="score-ring-inner"><div class="score-ring-value">${result.score.toFixed(0)}</div><div class="score-ring-label">COT score</div></div>
      </div>
      <div class="score-copy">
        <h4>${escapeHtml(result.label)}</h4>
        <p>Historical percentile signal normalized to 0–100. ${inverseNames.length ? `${escapeHtml(inverseNames.join(", "))} contribute inversely.` : "Weights are shown below."}</p>
      </div>
    </div>
    <div class="score-components">
      ${result.components.map(item => {
        const contribution = item.contribution;
        const direction = contribution > .001 ? "value-positive" : contribution < -.001 ? "value-negative" : "value-muted";
        const relationship = item.weight < 0 ? "inverse" : item.weight > 0 ? "positive" : "excluded";
        return `<div class="score-component">
          <div class="score-component-name">${escapeHtml(item.label)}<small>${relationship} association · ${item.percentile === null ? "n/a" : `${item.percentile.toFixed(0)}th percentile`} · weight ${item.weight > 0 ? "+" : ""}${number(item.weight, 2)}</small></div>
          <div class="score-component-value ${direction}">${contribution > 0 ? "+" : ""}${contribution.toFixed(2)}</div>
        </div>`;
      }).join("")}
    </div>`;
  }

  function latestMacroValue(keys) {
    const latest = macroLatest();
    for (const key of keys) {
      const value = finite(latest?.[key]);
      if (value !== null) return { value, key };
    }
    const series = findSeries(db.MACRO_MONITOR, keys);
    if (series.length) return { value: series.at(-1).value, key: keys[0] };
    return { value: null, key: keys[0] };
  }

  function renderMacroCards() {
    const score = macroScoreValue();
    const definitions = [
      { label: "Unified liquidity", keys: ["liquidity_score", "macro_score", "unified_score", "score"], format: v => v === null ? "n/a" : `${v.toFixed(0)}/100`, sub: "Composite macro regime" },
      { label: "Net liquidity 4W", keys: ["net_liquidity_4w_change"], format: v => signed(v, 1, " bn"), sub: "Fed assets − TGA − RRP impulse" },
      { label: "Bank reserves", keys: ["bank_reserves", "reserves"], format: v => v === null ? "n/a" : number(v, 0), sub: "Banking-system liquidity" },
      { label: "SOFR − IORB", keys: ["sofr_iorb_spread"], format: v => signed(v, 3, " pp"), sub: "Secured funding pressure" },
      { label: "10Y real yield", keys: ["real_yield_10y"], format: v => v === null ? "n/a" : `${v.toFixed(2)}%`, sub: "Growth discount-rate pressure" },
      { label: "High-yield OAS", keys: ["hy_oas"], format: v => v === null ? "n/a" : `${v.toFixed(2)}%`, sub: "Credit risk stress" }
    ];
    $("#macroCards").innerHTML = definitions.map((def, index) => {
      const resolved = index === 0 ? { value: score } : latestMacroValue(def.keys);
      return `<article class="macro-card">
        <div class="macro-card-label">${escapeHtml(def.label)}</div>
        <div class="macro-card-value ${index === 0 ? (toneClass(score) === "positive" ? "value-positive" : toneClass(score) === "negative" ? "value-negative" : "") : ""}">${escapeHtml(def.format(resolved.value))}</div>
        <div class="macro-card-sub">${escapeHtml(def.sub)}</div>
      </article>`;
    }).join("");
  }

  function renderMacroChart() {
    if (!window.Plotly) return;
    const series = macroScoreSeries();
    const t = plotTokens();
    if (!series.length) {
      $("#macroChart").innerHTML = `<div class="error-state"><strong>Macro score history unavailable</strong>The current macro cards remain available from the latest monitor payload.</div>`;
      return;
    }
    Plotly.react("macroChart", [{
      type: "scatter",
      mode: "lines",
      fill: "tozeroy",
      name: "Liquidity score",
      x: series.map(row => row.date),
      y: series.map(row => row.value),
      line: { color: "#f4b64e", width: 2.4 },
      fillcolor: state.theme === "light" ? "rgba(184,121,10,.08)" : "rgba(244,182,78,.08)",
      hovertemplate: "%{x}<br>Score %{y:.1f}<extra></extra>"
    }], {
      paper_bgcolor: t.paper,
      plot_bgcolor: t.plot,
      margin: { l: 48, r: 24, t: 18, b: 42 },
      font: { family: "Inter, ui-sans-serif, sans-serif", color: t.text, size: 10 },
      showlegend: false,
      hovermode: "x",
      xaxis: { type: "date", gridcolor: t.grid, tickfont: { color: t.muted, size: 9 }, linecolor: t.zero },
      yaxis: { range: [0, 100], dtick: 20, gridcolor: t.grid, zeroline: false, tickfont: { color: t.muted, size: 9 } },
      shapes: [
        { type: "line", xref: "paper", x0: 0, x1: 1, y0: 50, y1: 50, line: { color: t.zero, width: 1, dash: "dot" } }
      ]
    }, { responsive: true, displayModeBar: false });
  }

  function renderMacroDrivers() {
    const driverDefs = [
      ["Fed net-liquidity impulse", ["net_liquidity_4w_change"], "4-week change; positive is generally supportive", "bn"],
      ["Bank reserves", ["bank_reserves_4w_change"], "4-week reserve impulse", "bn"],
      ["Repo stress", ["sofr_iorb_spread", "sofr_iorb_spread_4w_change"], "SOFR relative to IORB", "pp"],
      ["Real-yield pressure", ["real_yield_4w_change", "real_yield_10y"], "Higher real yields tighten financial conditions", "pp"],
      ["Credit spreads", ["hy_oas_4w_change", "hy_oas"], "Wider spreads are restrictive", "pp"],
      ["Broad dollar", ["dollar_4w_change", "dollar_index"], "A stronger dollar can tighten global liquidity", ""]
    ];
    $("#macroDrivers").innerHTML = driverDefs.map(([label, keys, sub, unit]) => {
      const resolved = latestMacroValue(keys);
      const value = resolved.value;
      return `<div class="driver-row">
        <div class="driver-label">${escapeHtml(label)}<small>${escapeHtml(sub)}</small></div>
        <div class="driver-value ${signedClass(value)}">${value === null ? "n/a" : signed(value, unit === "pp" ? 3 : 1, unit ? ` ${unit}` : "")}</div>
      </div>`;
    }).join("");
  }

  function renderRangeButtons() {
    $$("#rangeButtons button").forEach(button => button.classList.toggle("active", button.dataset.range === state.range));
  }

  function renderAll() {
    state.dataset = chooseDatasetForMarket(state.market, state.dataset);
    if (!state.activeCategories.size || [...state.activeCategories].every(key => !categoryKeys().includes(key))) {
      state.activeCategories = new Set(categoryKeys());
    }
    renderInstrumentTabs();
    renderControls();
    renderFreshness();
    renderHeadlineCards();
    renderRangeButtons();
    renderMainChart();
    renderWeeklyChanges();
    renderPositioning();
    renderCotScore();
    renderMacroCards();
    renderMacroChart();
    renderMacroDrivers();
  }

  function bindEvents() {
    document.addEventListener("click", event => {
      const marketButton = event.target.closest("[data-market]");
      if (marketButton) return setMarket(marketButton.dataset.market);

      const categoryButton = event.target.closest("[data-category]");
      if (categoryButton) {
        const key = categoryButton.dataset.category;
        if (state.activeCategories.has(key)) state.activeCategories.delete(key);
        else state.activeCategories.add(key);
        renderControls();
        renderMainChart();
        return;
      }

      const priceButton = event.target.closest("[data-price-overlay]");
      if (priceButton) {
        const key = priceButton.dataset.priceOverlay;
        if (state.priceOverlays.has(key)) state.priceOverlays.delete(key);
        else state.priceOverlays.add(key);
        renderControls();
        renderMainChart();
        return;
      }

      const factorButton = event.target.closest("[data-factor-overlay]");
      if (factorButton) {
        const key = factorButton.dataset.factorOverlay;
        if (state.factorOverlays.has(key)) state.factorOverlays.delete(key);
        else state.factorOverlays.add(key);
        renderControls();
        renderMainChart();
        return;
      }

      const rangeButton = event.target.closest("[data-range]");
      if (rangeButton) {
        state.range = rangeButton.dataset.range;
        renderRangeButtons();
        renderMainChart();
        return;
      }
    });

    document.addEventListener("change", event => {
      const control = event.target.closest("[data-control]");
      if (!control) return;
      if (control.dataset.control === "dataset") setDataset(control.value);
      if (control.dataset.control === "metric") {
        state.metric = control.value;
        renderControls();
        renderMainChart();
      }
    });

    $("#themeToggle").addEventListener("click", () => {
      state.theme = state.theme === "dark" ? "light" : "dark";
      applyTheme();
      renderMainChart();
      renderMacroChart();
    });

    window.addEventListener("resize", () => {
      if (window.Plotly?.Plots) {
        for (const id of ["mainChart", "macroChart"]) {
          const el = document.getElementById(id);
          if (el?.data) Plotly.Plots.resize(el);
        }
      }
    });
  }

  async function init() {
    applyTheme();
    bindEvents();
    try {
      await loadData();
      state.dataset = chooseDatasetForMarket(state.market, "tff");
      state.activeCategories = new Set(categoryKeys());
      renderAll();
      $("#loadingOverlay").classList.add("done");
    } catch (error) {
      console.error(error);
      $("#loadingOverlay").innerHTML = `<div class="loading-card"><strong style="color:#ff6675">Dashboard data failed to load</strong><span>${escapeHtml(error.message || error)}</span></div>`;
    }
  }

  init();
})();
