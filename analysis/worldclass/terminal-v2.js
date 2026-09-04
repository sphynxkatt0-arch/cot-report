(() => {
  "use strict";

  const MARKET_META = {
    sp500: { label: "S&P 500", short: "S&P", dataset: "tff" },
    nq: { label: "Nasdaq-100", short: "NQ", dataset: "tff" },
    vix: { label: "VIX Futures", short: "VIX", dataset: "tff" },
    rty: { label: "Russell 2000", short: "RTY", dataset: "tff" },
    dow: { label: "Dow Jones", short: "Dow", dataset: "tff" },
    gold: { label: "Gold", short: "Gold", dataset: "disaggregated" },
    silver: { label: "Silver", short: "Silver", dataset: "disaggregated" }
  };
  const MARKET_ORDER = Object.keys(MARKET_META);
  const state = { metals: null, selected: "sp500", compact: false };
  const $ = selector => document.querySelector(selector);
  const finite = value => Number.isFinite(Number(value)) ? Number(value) : null;
  const esc = value => String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");

  function signed(value, digits = 1, suffix = "") {
    const n = finite(value);
    if (n === null) return "n/a";
    const body = Math.abs(n).toLocaleString("en-US", { minimumFractionDigits: digits, maximumFractionDigits: digits });
    return `${n > 0 ? "+" : n < 0 ? "−" : ""}${body}${suffix}`;
  }

  function percentile(values, value) {
    const current = finite(value);
    const clean = values.map(finite).filter(v => v !== null).sort((a, b) => a - b);
    if (current === null || !clean.length) return null;
    let below = 0;
    let equal = 0;
    clean.forEach(item => {
      if (item < current) below += 1;
      else if (item === current) equal += 1;
    });
    return ((below + Math.max(equal, 1) / 2) / clean.length) * 100;
  }

  function findSeries(root, keys, depth = 0, seen = new Set()) {
    if (!root || depth > 8 || typeof root !== "object" || seen.has(root)) return [];
    seen.add(root);
    let best = [];
    if (Array.isArray(root)) {
      for (const key of keys) {
        const rows = root
          .filter(row => row?.date && finite(row?.[key]) !== null)
          .map(row => ({ date: String(row.date).slice(0, 10), value: finite(row[key]), raw: row }));
        if (rows.length > best.length) best = rows;
      }
      return best;
    }
    for (const child of Object.values(root)) {
      const rows = findSeries(child, keys, depth + 1, seen);
      if (rows.length > best.length) best = rows;
    }
    return best;
  }

  function priceRows(base, market) {
    const raw = state.metals?.prices?.[market] || base?.PRICE_DATA?.[market];
    const rows = Array.isArray(raw) ? raw : raw?.records;
    return (rows || []).filter(row => row?.date && finite(row.price) !== null);
  }

  function payloadFor(base, market) {
    const preferred = MARKET_META[market]?.dataset || "tff";
    if (preferred === "disaggregated" && state.metals?.markets?.[market]) {
      return { dataset: preferred, payload: state.metals.markets[market] };
    }
    const priorities = preferred === "disaggregated"
      ? ["disaggregated", "legacy", "tff"]
      : ["tff", "legacy", "disaggregated"];
    for (const dataset of priorities) {
      const payload = base?.COT_DATA?.[dataset]?.[market];
      if (Array.isArray(payload?.records) && payload.records.length > 1) return { dataset, payload };
    }
    return { dataset: preferred, payload: null };
  }

  function scoreRow(row, records, categories, weights) {
    let numerator = 0;
    let denominator = 0;
    const actors = [];
    for (const [key, label] of Object.entries(categories || {})) {
      const weight = finite(weights?.[key]) ?? 0;
      const field = `${key}_net_oi_pct`;
      const value = finite(row?.[field]);
      const rank = percentile(records.map(item => item?.[field]), value);
      if (rank !== null && weight !== 0) {
        numerator += weight * ((rank - 50) / 50);
        denominator += Math.abs(weight);
      }
      actors.push({ key, label, weight, value, rank });
    }
    if (!denominator) return { score: null, actors };
    return { score: Math.max(0, Math.min(100, 50 + 50 * numerator / denominator)), actors };
  }

  function latestPriceReturn(rows, lookback) {
    if (rows.length < 2) return null;
    const end = finite(rows.at(-1)?.price);
    const start = finite(rows[Math.max(0, rows.length - 1 - lookback)]?.price);
    return end !== null && start ? ((end / start) - 1) * 100 : null;
  }

  function ageDays(date) {
    if (!date) return null;
    const ms = Date.parse(`${String(date).slice(0, 10)}T12:00:00Z`);
    return Number.isFinite(ms) ? Math.max(0, Math.floor((Date.now() - ms) / 86400000)) : null;
  }

  function marketSnapshot(base, market, macroScore) {
    const { dataset, payload } = payloadFor(base, market);
    const records = (payload?.records || []).filter(row => row?.date);
    const categories = payload?.categories || {};
    const weights = base?.MODEL_SPEC?.score_models?.[dataset]?.category_weights || {};
    const latest = records.at(-1) || {};
    const prior = records.at(-2) || {};
    const scored = scoreRow(latest, records, categories, weights);
    const priorScored = scoreRow(prior, records, categories, weights);
    const prices = priceRows(base, market);
    const price1m = latestPriceReturn(prices, 21);
    const price3m = latestPriceReturn(prices, 63);
    const scoredActors = scored.actors
      .filter(actor => actor.weight !== 0 && actor.rank !== null)
      .sort((a, b) => Math.abs((b.rank ?? 50) - 50) - Math.abs((a.rank ?? 50) - 50));
    const leadActor = scoredActors[0] || null;
    const latestDate = latest?.date || null;
    const cotAge = ageDays(latestDate);
    const dataPoints = [scored.score, macroScore, price3m, latestDate].filter(value => value !== null && value !== undefined).length;
    const coverage = dataPoints >= 4 && (cotAge === null || cotAge <= 10) ? "High" : dataPoints >= 3 ? "Medium" : "Low";
    const scoreDelta = scored.score !== null && priorScored.score !== null ? scored.score - priorScored.score : null;
    const dislocation = scored.score === null ? -1 : Math.abs(scored.score - 50) + Math.min(20, Math.abs(scoreDelta || 0) * 2);
    return {
      market,
      dataset,
      score: scored.score,
      scoreDelta,
      macroScore,
      leadActor,
      latestDate,
      cotAge,
      price1m,
      price3m,
      coverage,
      dislocation
    };
  }

  function toneForScore(score) {
    const n = finite(score);
    if (n === null) return "neutral";
    if (n >= 60) return "positive";
    if (n <= 40) return "negative";
    return "neutral";
  }

  function stateLabel(score) {
    const n = finite(score);
    if (n === null) return "Unavailable";
    if (n >= 70) return "Strong long bias";
    if (n >= 60) return "Constructive";
    if (n <= 30) return "Strong short bias";
    if (n <= 40) return "Defensive";
    return "Balanced";
  }

  function regime(snapshot) {
    const signs = [];
    if (snapshot.score !== null) signs.push(snapshot.score >= 60 ? 1 : snapshot.score <= 40 ? -1 : 0);
    if (snapshot.macroScore !== null) signs.push(snapshot.macroScore >= 60 ? 1 : snapshot.macroScore <= 40 ? -1 : 0);
    if (snapshot.price3m !== null) signs.push(snapshot.price3m >= 3 ? 1 : snapshot.price3m <= -3 ? -1 : 0);
    const bullish = signs.filter(x => x > 0).length;
    const bearish = signs.filter(x => x < 0).length;
    if (bullish >= 2 && bullish > bearish) return { label: "Risk-on alignment", tone: "positive", detail: `${bullish}/${signs.length} observed layers are supportive.` };
    if (bearish >= 2 && bearish > bullish) return { label: "Risk-off alignment", tone: "negative", detail: `${bearish}/${signs.length} observed layers are defensive.` };
    return { label: "Mixed regime", tone: "neutral", detail: "Positioning, macro and price are not cleanly aligned." };
  }

  function crowdingText(actor) {
    if (!actor || actor.rank === null) return "No directional actor";
    if (actor.rank >= 95) return `${actor.label}: extreme long`;
    if (actor.rank >= 80) return `${actor.label}: crowded long`;
    if (actor.rank <= 5) return `${actor.label}: extreme short`;
    if (actor.rank <= 20) return `${actor.label}: crowded short`;
    return `${actor.label}: ${actor.rank.toFixed(0)}th pct`;
  }

  function renderMatrix(snapshots) {
    return MARKET_ORDER.map(market => {
      const s = snapshots.find(item => item.market === market);
      const active = market === state.selected ? " active" : "";
      const tone = toneForScore(s?.score);
      return `<button class="wc-v2-market${active} ${tone}" type="button" data-wc-v2-market="${market}" aria-pressed="${market === state.selected}">
        <span class="wc-v2-market-name">${esc(MARKET_META[market].short)}</span>
        <strong>${s?.score === null || s?.score === undefined ? "n/a" : s.score.toFixed(0)}</strong>
        <span class="wc-v2-market-state">${esc(stateLabel(s?.score))}</span>
        <small>${s?.scoreDelta === null || s?.scoreDelta === undefined ? "No weekly delta" : `${signed(s.scoreDelta, 1)} pts / wk`}</small>
      </button>`;
    }).join("");
  }

  function renderSelected(snapshot) {
    const r = regime(snapshot);
    const freshness = snapshot.cotAge === null ? "Unknown freshness" : snapshot.cotAge <= 10 ? `${snapshot.cotAge}d since COT observation` : `${snapshot.cotAge}d · stale`;
    const cards = [
      ["Positioning", snapshot.score === null ? "n/a" : `${snapshot.score.toFixed(0)}/100`, stateLabel(snapshot.score), toneForScore(snapshot.score)],
      ["Weekly impulse", snapshot.scoreDelta === null ? "n/a" : `${signed(snapshot.scoreDelta, 1)} pts`, snapshot.scoreDelta === null ? "Unavailable" : snapshot.scoreDelta > 2 ? "Improving" : snapshot.scoreDelta < -2 ? "Deteriorating" : "Stable", snapshot.scoreDelta > 2 ? "positive" : snapshot.scoreDelta < -2 ? "negative" : "neutral"],
      ["Crowding", snapshot.leadActor?.rank === null || !snapshot.leadActor ? "n/a" : `${snapshot.leadActor.rank.toFixed(0)}th`, crowdingText(snapshot.leadActor), snapshot.leadActor?.rank >= 80 ? "positive" : snapshot.leadActor?.rank <= 20 ? "negative" : "neutral"],
      ["3M price", snapshot.price3m === null ? "n/a" : signed(snapshot.price3m, 1, "%"), snapshot.price1m === null ? "Price context" : `1M ${signed(snapshot.price1m, 1, "%")}`, snapshot.price3m > 3 ? "positive" : snapshot.price3m < -3 ? "negative" : "neutral"],
      ["Macro", snapshot.macroScore === null ? "n/a" : `${snapshot.macroScore.toFixed(0)}/100`, snapshot.macroScore === null ? "Unavailable" : snapshot.macroScore >= 60 ? "Supportive" : snapshot.macroScore <= 40 ? "Defensive" : "Neutral", toneForScore(snapshot.macroScore)]
    ];
    return `<div class="wc-v2-verdict ${r.tone}">
      <div>
        <span class="wc-v2-kicker">RESEARCH ALIGNMENT</span>
        <h3>${esc(MARKET_META[snapshot.market].label)} · ${esc(r.label)}</h3>
        <p>${esc(r.detail)} This is a decomposition of current evidence, not a standalone forecast.</p>
      </div>
      <div class="wc-v2-verdict-meta">
        <span>Coverage <strong>${esc(snapshot.coverage)}</strong></span>
        <span>${esc(freshness)}</span>
        <span>${esc(snapshot.dataset.toUpperCase())}</span>
      </div>
    </div>
    <div class="wc-v2-signal-grid">${cards.map(([label, value, detail, tone]) => `<article class="wc-v2-signal ${tone}"><span>${esc(label)}</span><strong>${esc(value)}</strong><small>${esc(detail)}</small></article>`).join("")}</div>`;
  }

  function renderDislocations(snapshots) {
    const ranked = [...snapshots]
      .filter(item => item.score !== null)
      .sort((a, b) => b.dislocation - a.dislocation)
      .slice(0, 5);
    return ranked.map((item, index) => `<button type="button" class="wc-v2-watch-row" data-wc-v2-market="${item.market}">
      <span class="wc-v2-watch-rank">${String(index + 1).padStart(2, "0")}</span>
      <span class="wc-v2-watch-name"><strong>${esc(MARKET_META[item.market].label)}</strong><small>${esc(crowdingText(item.leadActor))}</small></span>
      <span class="wc-v2-watch-score ${toneForScore(item.score)}">${item.score.toFixed(0)}</span>
      <span class="wc-v2-watch-delta">${item.scoreDelta === null ? "n/a" : signed(item.scoreDelta, 1)}</span>
    </button>`).join("");
  }

  function render(base) {
    const root = $("#wcCommandCenter");
    if (!root || !base) return;
    const macroSeries = findSeries(base.MACRO_MONITOR, ["liquidity_score", "macro_score", "unified_score", "score"]);
    const macroScore = macroSeries.at(-1)?.value ?? null;
    const snapshots = MARKET_ORDER.map(market => marketSnapshot(base, market, macroScore));
    if (!snapshots.some(item => item.market === state.selected && item.score !== null)) {
      state.selected = snapshots.find(item => item.score !== null)?.market || "sp500";
    }
    const selected = snapshots.find(item => item.market === state.selected) || snapshots[0];
    const available = snapshots.filter(item => item.score !== null).length;
    const bullish = snapshots.filter(item => item.score !== null && item.score >= 60).length;
    const bearish = snapshots.filter(item => item.score !== null && item.score <= 40).length;
    root.innerHTML = `
      <div class="wc-v2-head">
        <div>
          <span class="wc-v2-kicker">GLOBAL POSITIONING COMMAND CENTER</span>
          <h2>Cross-market regime map</h2>
          <p>One screen for positioning, weekly impulse, crowding, price confirmation, macro alignment and freshness.</p>
        </div>
        <div class="wc-v2-head-actions">
          <div class="wc-v2-breadth" aria-label="Cross-market breadth">
            <span><strong>${bullish}</strong> bullish</span>
            <span><strong>${bearish}</strong> bearish</span>
            <span><strong>${available}</strong> covered</span>
          </div>
          <button id="wcV2Density" class="wc-v2-density" type="button" aria-pressed="${state.compact}">${state.compact ? "Deep view" : "Focus view"}</button>
        </div>
      </div>
      <div class="wc-v2-market-grid" role="group" aria-label="Cross-market positioning scores">${renderMatrix(snapshots)}</div>
      <div class="wc-v2-body">
        <section class="wc-v2-selected" aria-live="polite">${renderSelected(selected)}</section>
        <aside class="wc-v2-watch">
          <div class="wc-v2-watch-head"><div><span class="wc-v2-kicker">DISLOCATION RADAR</span><h3>Highest-priority review</h3></div><span>score / Δ</span></div>
          <div class="wc-v2-watch-list">${renderDislocations(snapshots)}</div>
        </aside>
      </div>`;
    bind(root);
  }

  function selectMarket(market) {
    if (!MARKET_META[market]) return;
    state.selected = market;
    const tab = document.querySelector(`#instrumentTabs [data-market="${market}"]`);
    if (tab && !tab.classList.contains("active")) tab.click();
    render(window.__COT_WORLDCLASS_BASE__);
  }

  function bind(root) {
    root.querySelectorAll("[data-wc-v2-market]").forEach(button => {
      button.addEventListener("click", () => selectMarket(button.dataset.wcV2Market));
    });
    root.querySelector("#wcV2Density")?.addEventListener("click", () => {
      state.compact = !state.compact;
      document.documentElement.classList.toggle("wc-v2-focus", state.compact);
      render(window.__COT_WORLDCLASS_BASE__);
    });
  }

  function mount() {
    if ($("#wcCommandCenter")) return;
    const anchor = $(".instrument-bar");
    if (!anchor) return;
    const section = document.createElement("section");
    section.id = "wcCommandCenter";
    section.className = "wc-v2-command";
    section.setAttribute("aria-label", "Global positioning command center");
    anchor.insertAdjacentElement("afterend", section);
    state.selected = $("#instrumentTabs [data-market].active")?.dataset.market || "sp500";
    render(window.__COT_WORLDCLASS_BASE__);

    $("#instrumentTabs")?.addEventListener("click", event => {
      const button = event.target.closest("[data-market]");
      if (!button) return;
      state.selected = button.dataset.market;
      window.setTimeout(() => render(window.__COT_WORLDCLASS_BASE__), 0);
    });

    document.addEventListener("keydown", event => {
      if (event.altKey || event.ctrlKey || event.metaKey || /INPUT|SELECT|TEXTAREA/.test(document.activeElement?.tagName || "")) return;
      const number = Number(event.key);
      if (number >= 1 && number <= MARKET_ORDER.length) selectMarket(MARKET_ORDER[number - 1]);
    });
  }

  async function loadMetals() {
    try {
      const version = window.__COT_RUNTIME_VERSION__ || Date.now();
      const response = await fetch(`worldclass/metals.json?v=${encodeURIComponent(version)}`, { cache: "no-store" });
      if (response.ok) state.metals = await response.json();
    } catch (error) {
      console.warn("Command center metals context unavailable; retaining canonical index view.", error);
    }
  }

  async function boot() {
    try {
      if (window.__COT_APP_DATA_READY__) await window.__COT_APP_DATA_READY__;
      await loadMetals();
      mount();
    } catch (error) {
      console.error("Command center failed to initialize.", error);
    }
  }

  boot();
})();
