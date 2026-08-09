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
  const state = { metals: null, release: null, track: null, selected: "sp500", compact: false };
  const $ = selector => document.querySelector(selector);
  const finite = value => {
    if (value === null || value === undefined || value === "") return null;
    const number = Number(value);
    return Number.isFinite(number) ? number : null;
  };
  const esc = value => String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");

  function signed(value, digits = 1, suffix = "") {
    const n = finite(value);
    if (n === null) return "n/a";
    const body = Math.abs(n).toLocaleString(undefined, { minimumFractionDigits: digits, maximumFractionDigits: digits });
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
    return end !== null && start !== null && start !== 0 ? ((end / start) - 1) * 100 : null;
  }

  function ageDays(date) {
    if (!date) return null;
    const ms = Date.parse(`${String(date).slice(0, 10)}T12:00:00Z`);
    return Number.isFinite(ms) ? Math.max(0, Math.floor((Date.now() - ms) / 86400000)) : null;
  }

  function directionalSign(value, upper, lower) {
    const n = finite(value);
    if (n === null) return 0;
    if (n >= upper) return 1;
    if (n <= lower) return -1;
    return 0;
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
    const releaseMarket = state.release?.market_states?.[market] || state.release?.markets?.[market] || null;
    const releaseState = String(releaseMarket?.state || releaseMarket?.status || "UNKNOWN").toUpperCase();
    const dataPoints = [scored.score, macroScore, price3m, latestDate].filter(value => value !== null && value !== undefined).length;
    const fresh = cotAge !== null && cotAge <= 10 && releaseState === "LIVE";
    const coverage = dataPoints >= 4 && fresh ? "High" : dataPoints >= 3 ? "Medium" : "Low";
    const scoreDelta = scored.score !== null && priorScored.score !== null ? scored.score - priorScored.score : null;
    const dislocation = scored.score === null ? -1 : Math.abs(scored.score - 50) + Math.min(20, Math.abs(scoreDelta || 0) * 2);
    return {
      market, dataset, score: scored.score, scoreDelta, macroScore, leadActor,
      latestDate, cotAge, price1m, price3m, coverage, dislocation, releaseState
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

  function macroLabel(score) {
    const n = finite(score);
    if (n === null) return "unavailable";
    if (n >= 70) return "strongly supportive";
    if (n >= 60) return "supportive";
    if (n <= 30) return "strongly restrictive";
    if (n <= 40) return "restrictive";
    return "neutral";
  }

  function regime(snapshot) {
    const values = [snapshot.score, snapshot.macroScore, snapshot.price3m];
    const signs = [
      directionalSign(snapshot.score, 60, 40),
      directionalSign(snapshot.macroScore, 60, 40),
      directionalSign(snapshot.price3m, 3, -3)
    ];
    const observed = values.filter(value => finite(value) !== null).length;
    const bullish = signs.filter(x => x > 0).length;
    const bearish = signs.filter(x => x < 0).length;
    if (bullish >= 2 && bullish > bearish) return { label: "Risk-on alignment", tone: "positive", detail: `${bullish}/${observed || 3} observed layers are supportive.`, alignment: bullish };
    if (bearish >= 2 && bearish > bullish) return { label: "Risk-off alignment", tone: "negative", detail: `${bearish}/${observed || 3} observed layers are defensive.`, alignment: bearish };
    return { label: "Mixed regime", tone: "neutral", detail: "Positioning, macro and price are not cleanly aligned.", alignment: Math.max(bullish, bearish) };
  }

  function crowdingText(actor) {
    if (!actor || actor.rank === null) return "No directional actor";
    if (actor.rank >= 95) return `${actor.label}: extreme long`;
    if (actor.rank >= 80) return `${actor.label}: crowded long`;
    if (actor.rank <= 5) return `${actor.label}: extreme short`;
    if (actor.rank <= 20) return `${actor.label}: crowded short`;
    return `${actor.label}: ${actor.rank.toFixed(0)}th pct`;
  }

  function evidenceQuality(snapshot) {
    let score = snapshot.coverage === "High" ? 3 : snapshot.coverage === "Medium" ? 2 : 1;
    const r = regime(snapshot);
    if (r.alignment >= 2) score += 1;
    if (snapshot.cotAge !== null && snapshot.cotAge > 10) score -= 2;
    if (snapshot.releaseState !== "LIVE") score -= 2;
    if (score >= 4) return { label: "High", tone: "positive" };
    if (score >= 2) return { label: "Medium", tone: "neutral" };
    return { label: "Low", tone: "negative" };
  }

  function tensionText(snapshot) {
    const cot = directionalSign(snapshot.score, 60, 40);
    const macro = directionalSign(snapshot.macroScore, 60, 40);
    const price = directionalSign(snapshot.price3m, 3, -3);
    const tensions = [];
    if (cot && macro && cot !== macro) tensions.push("positioning and macro disagree");
    if (cot && price && cot !== price) tensions.push("positioning and 3M price disagree");
    if (!tensions.length) return null;
    return `Tension: ${tensions.join("; ")}. Treat the read as conditional until layers converge.`;
  }

  function brief(snapshot) {
    const cotTone = directionalSign(snapshot.score, 60, 40);
    const impulse = finite(snapshot.scoreDelta);
    const actor = crowdingText(snapshot.leadActor);
    const parts = [];
    if (snapshot.score !== null) parts.push(`COT is ${stateLabel(snapshot.score).toLowerCase()} at ${snapshot.score.toFixed(0)}/100`);
    if (impulse !== null) parts.push(`weekly impulse is ${signed(impulse, 1)} pts`);
    if (snapshot.leadActor?.rank !== null) parts.push(actor);
    if (snapshot.macroScore !== null) parts.push(`macro is ${macroLabel(snapshot.macroScore)} at ${snapshot.macroScore.toFixed(0)}/100`);
    if (snapshot.price3m !== null) parts.push(`3M price is ${signed(snapshot.price3m, 1, "%")}`);
    const whyNow = parts.length ? `${parts.join("; ")}.` : "Insufficient live inputs for a decision brief.";

    let confirmation;
    let invalidation;
    if (cotTone > 0) {
      confirmation = "Higher-quality continuation requires COT to stay above 60, weekly impulse to avoid a material reversal, and price/macro not to flip defensive.";
      invalidation = "Downgrade the constructive read if COT falls below 60; invalidate alignment if it enters the defensive band or the release becomes stale/delayed.";
    } else if (cotTone < 0) {
      confirmation = "Higher-quality downside continuation requires COT to stay below 40, weekly impulse to avoid a material rebound, and price/macro not to flip supportive.";
      invalidation = "Downgrade the defensive read if COT rises above 40; invalidate alignment if it enters the constructive band or the release becomes stale/delayed.";
    } else {
      confirmation = "No directional regime is active. Require COT to leave the 40–60 balance band and seek confirmation from macro or 3M price before upgrading the read.";
      invalidation = "A balanced read is invalidated only by a sustained move into a directional COT band; stale or delayed data always lowers evidence quality.";
    }
    return { whyNow, confirmation, invalidation };
  }

  function releaseTone(value) {
    const text = String(value || "UNKNOWN").toUpperCase();
    if (["PASS", "LIVE"].includes(text)) return "positive";
    if (["DELAYED", "DEGRADED", "FAIL", "FAILED", "ERROR"].includes(text)) return "negative";
    return "neutral";
  }

  function trackState() {
    if (!state.track) return { label: "UNAVAILABLE", tone: "neutral", detail: "prospective ledger unavailable" };
    const integrity = String(state.track?.ledger?.integrity || "UNKNOWN").toUpperCase();
    if (integrity !== "PASS") return { label: integrity, tone: "negative", detail: "ledger integrity" };
    const matured = Number(state.track?.matured_signal_count || 0);
    const forecasts = Number(state.track?.forecast_count || 0);
    if (!forecasts) return { label: "LEDGER READY", tone: "neutral", detail: "0 prospective forecasts" };
    if (!matured) return { label: "FORWARD TESTING", tone: "neutral", detail: `${forecasts} forecasts · 0 matured` };
    return { label: "LIVE EVIDENCE", tone: "positive", detail: `${matured} matured signals` };
  }

  function renderIntegrity() {
    const release = state.release || {};
    const releaseState = String(release.state || "UNVERIFIED").toUpperCase();
    const macro = release.macro_plumbing || {};
    const macroState = String(macro.state || "UNVERIFIED").toUpperCase();
    const coverage = finite(macro.source_coverage_ratio);
    const track = trackState();
    const model = release.model?.model_version || window.__COT_WORLDCLASS_BASE__?.MODEL_SPEC?.model_version || "n/a";
    return `<div class="wc-v3-integrity" aria-label="Production data integrity">
      <div class="wc-v3-integrity-title"><span class="wc-v3-kicker">PRODUCTION HEALTH</span><strong>Verified inputs before interpretation</strong></div>
      <div class="wc-v3-integrity-item ${releaseTone(releaseState)}"><span>CFTC release</span><strong>${esc(releaseState)}</strong><small>${esc(release.latest_cot_report_date || "date unavailable")}</small></div>
      <div class="wc-v3-integrity-item ${releaseTone(release.data_contracts)}"><span>Data contract</span><strong>${esc(release.data_contracts || "UNVERIFIED")}</strong><small>taxonomy ${esc(release.actor_taxonomy || "n/a")}</small></div>
      <div class="wc-v3-integrity-item ${releaseTone(macroState)}"><span>Macro plumbing</span><strong>${esc(macroState)}</strong><small>${coverage === null ? "coverage n/a" : `${Math.round(coverage * 100)}% source coverage`}</small></div>
      <div class="wc-v3-integrity-item ${track.tone}"><span>Prospective evidence</span><strong>${esc(track.label)}</strong><small>${esc(track.detail)}</small></div>
      <div class="wc-v3-integrity-item neutral"><span>Governed model</span><strong>v${esc(model)}</strong><small>lookahead ${esc(release.lookahead_safety || "n/a")}</small></div>
    </div>`;
  }

  function renderMatrix(snapshots) {
    return MARKET_ORDER.map(market => {
      const s = snapshots.find(item => item.market === market);
      const active = market === state.selected ? " active" : "";
      const tone = toneForScore(s?.score);
      const health = ["DELAYED", "DEGRADED"].includes(s?.releaseState) ? `<span class="wc-v3-market-health">${esc(s.releaseState)}</span>` : "";
      return `<button class="wc-v3-market${active} ${tone}" type="button" data-wc-v3-market="${market}" aria-pressed="${market === state.selected}">
        <span class="wc-v3-market-top"><span class="wc-v3-market-name">${esc(MARKET_META[market].short)}</span>${health}</span>
        <strong>${s?.score === null || s?.score === undefined ? "n/a" : s.score.toFixed(0)}</strong>
        <span class="wc-v3-market-state">${esc(stateLabel(s?.score))}</span>
        <span class="wc-v3-market-foot"><small>${s?.scoreDelta === null || s?.scoreDelta === undefined ? "Δ n/a" : `Δ ${signed(s.scoreDelta, 1)}`}</small><small>${s?.price3m === null || s?.price3m === undefined ? "3M n/a" : `3M ${signed(s.price3m, 1, "%")}`}</small></span>
      </button>`;
    }).join("");
  }

  function renderSelected(snapshot) {
    const r = regime(snapshot);
    const quality = evidenceQuality(snapshot);
    const freshness = snapshot.cotAge === null ? "Unknown freshness" : snapshot.cotAge <= 10 ? `${snapshot.cotAge}d since COT observation` : `${snapshot.cotAge}d · stale`;
    const tension = tensionText(snapshot);
    const decision = brief(snapshot);
    const cards = [
      ["Positioning", snapshot.score === null ? "n/a" : `${snapshot.score.toFixed(0)}/100`, stateLabel(snapshot.score), toneForScore(snapshot.score)],
      ["Weekly impulse", snapshot.scoreDelta === null ? "n/a" : `${signed(snapshot.scoreDelta, 1)} pts`, snapshot.scoreDelta === null ? "Unavailable" : snapshot.scoreDelta > 2 ? "Improving" : snapshot.scoreDelta < -2 ? "Deteriorating" : "Stable", snapshot.scoreDelta > 2 ? "positive" : snapshot.scoreDelta < -2 ? "negative" : "neutral"],
      ["Crowding", snapshot.leadActor?.rank === null || !snapshot.leadActor ? "n/a" : `${snapshot.leadActor.rank.toFixed(0)}th`, crowdingText(snapshot.leadActor), snapshot.leadActor?.rank >= 80 ? "positive" : snapshot.leadActor?.rank <= 20 ? "negative" : "neutral"],
      ["3M price", snapshot.price3m === null ? "n/a" : signed(snapshot.price3m, 1, "%"), snapshot.price1m === null ? "Price context" : `1M ${signed(snapshot.price1m, 1, "%")}`, snapshot.price3m > 3 ? "positive" : snapshot.price3m < -3 ? "negative" : "neutral"],
      ["Macro", snapshot.macroScore === null ? "n/a" : `${snapshot.macroScore.toFixed(0)}/100`, snapshot.macroScore === null ? "Unavailable" : snapshot.macroScore >= 60 ? "Supportive" : snapshot.macroScore <= 40 ? "Defensive" : "Neutral", toneForScore(snapshot.macroScore)]
    ];
    return `<div class="wc-v3-verdict ${r.tone}">
      <div>
        <span class="wc-v3-kicker">EVIDENCE-BASED MARKET READ</span>
        <h3>${esc(MARKET_META[snapshot.market].label)} · ${esc(r.label)}</h3>
        <p>${esc(r.detail)} This is a governed decomposition of observable inputs, not a claimed trading edge.</p>
      </div>
      <div class="wc-v3-verdict-meta">
        <span class="${quality.tone}">Evidence quality <strong>${esc(quality.label)}</strong></span>
        <span>${esc(freshness)}</span>
        <span>${esc(snapshot.dataset.toUpperCase())}</span>
      </div>
    </div>
    ${tension ? `<div class="wc-v3-tension" role="status">${esc(tension)}</div>` : ""}
    <div class="wc-v3-signal-grid">${cards.map(([label, value, detail, tone]) => `<article class="wc-v3-signal ${tone}"><span>${esc(label)}</span><strong>${esc(value)}</strong><small>${esc(detail)}</small></article>`).join("")}</div>
    <div class="wc-v3-brief" aria-label="Decision brief">
      <article><span>WHY NOW</span><strong>Current evidence</strong><p>${esc(decision.whyNow)}</p></article>
      <article><span>CONFIRMATION</span><strong>What upgrades the read</strong><p>${esc(decision.confirmation)}</p></article>
      <article><span>INVALIDATION</span><strong>What weakens it</strong><p>${esc(decision.invalidation)}</p></article>
    </div>`;
  }

  function renderDislocations(snapshots) {
    const ranked = [...snapshots]
      .filter(item => item.score !== null)
      .sort((a, b) => b.dislocation - a.dislocation)
      .slice(0, 7);
    return ranked.map((item, index) => {
      const r = regime(item);
      return `<button type="button" class="wc-v3-watch-row" data-wc-v3-market="${item.market}">
        <span class="wc-v3-watch-rank">${String(index + 1).padStart(2, "0")}</span>
        <span class="wc-v3-watch-name"><strong>${esc(MARKET_META[item.market].label)}</strong><small>${esc(r.label)} · ${esc(crowdingText(item.leadActor))}</small></span>
        <span class="wc-v3-watch-score ${toneForScore(item.score)}">${item.score.toFixed(0)}</span>
        <span class="wc-v3-watch-delta">${item.scoreDelta === null ? "n/a" : signed(item.scoreDelta, 1)}</span>
      </button>`;
    }).join("");
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
    const aligned = snapshots.filter(item => regime(item).alignment >= 2).length;
    root.innerHTML = `
      ${renderIntegrity()}
      <div class="wc-v3-head">
        <div>
          <span class="wc-v3-kicker">GLOBAL POSITIONING COMMAND CENTER</span>
          <h2>Cross-market regime & decision map</h2>
          <p>Positioning, weekly impulse, crowding, price confirmation, macro alignment, release health and prospective evidence in one auditable screen.</p>
        </div>
        <div class="wc-v3-head-actions">
          <div class="wc-v3-breadth" aria-label="Cross-market breadth">
            <span><strong>${bullish}</strong> bullish</span>
            <span><strong>${bearish}</strong> bearish</span>
            <span><strong>${aligned}</strong> aligned</span>
            <span><strong>${available}</strong> covered</span>
          </div>
          <button id="wcV3Density" class="wc-v3-density" type="button" aria-pressed="${state.compact}">${state.compact ? "Deep view" : "Focus view"}</button>
        </div>
      </div>
      <div class="wc-v3-market-grid" role="group" aria-label="Cross-market positioning scores">${renderMatrix(snapshots)}</div>
      <div class="wc-v3-body">
        <section class="wc-v3-selected" aria-live="polite">${renderSelected(selected)}</section>
        <aside class="wc-v3-watch">
          <div class="wc-v3-watch-head"><div><span class="wc-v3-kicker">DISLOCATION RADAR</span><h3>Highest-priority review</h3></div><span>score / Δ</span></div>
          <div class="wc-v3-watch-list">${renderDislocations(snapshots)}</div>
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
    root.querySelectorAll("[data-wc-v3-market]").forEach(button => {
      button.addEventListener("click", () => selectMarket(button.dataset.wcV3Market));
    });
    root.querySelector("#wcV3Density")?.addEventListener("click", () => {
      state.compact = !state.compact;
      document.documentElement.classList.toggle("wc-v3-focus", state.compact);
      render(window.__COT_WORLDCLASS_BASE__);
    });
  }

  function mount() {
    if ($("#wcCommandCenter")) return;
    const anchor = $(".instrument-bar");
    if (!anchor) return;
    const section = document.createElement("section");
    section.id = "wcCommandCenter";
    section.className = "wc-v3-command";
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

  async function fetchJson(path) {
    const version = window.__COT_RUNTIME_VERSION__ || Date.now();
    const response = await fetch(`${path}?v=${encodeURIComponent(version)}-${Date.now()}`, { cache: "no-store" });
    if (!response.ok) throw new Error(`${path} HTTP ${response.status}`);
    return response.json();
  }

  async function loadContext() {
    const [metals, release, track] = await Promise.allSettled([
      fetchJson("worldclass/metals.json"),
      fetchJson("worldclass/release-status.json"),
      fetchJson("worldclass/live-track-record.json")
    ]);
    if (metals.status === "fulfilled") state.metals = metals.value;
    else console.warn("Command center metals context unavailable; retaining canonical index view.", metals.reason);
    if (release.status === "fulfilled") state.release = release.value;
    else console.warn("Release health unavailable; command center will show UNVERIFIED.", release.reason);
    if (track.status === "fulfilled") state.track = track.value;
    else console.warn("Prospective evidence unavailable; command center will show UNKNOWN.", track.reason);
  }

  async function boot() {
    try {
      if (window.__COT_APP_DATA_READY__) await window.__COT_APP_DATA_READY__;
      await loadContext();
      mount();
    } catch (error) {
      console.error("Command center failed to initialize.", error);
    }
  }

  boot();
})();
