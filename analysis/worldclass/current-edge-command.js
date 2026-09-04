(() => {
  "use strict";

  const M = () => window.__COT_CURRENT_EDGE_MODEL__;
  const HORIZONS = ["1w", "2w", "4w", "13w", "26w"];
  const MATRIX_HORIZONS = ["monday", "tuesday", "wednesday", "thursday", "friday", "1w", "2w", "3w", "4w", "6w", "8w", "13w", "26w", "39w", "52w"];
  const VIEWS = ["overview", "edges", "week", "research", "live"];
  const MODEL_FAMILIES = ["combined", "cot", "macro"];
  const RESEARCH_SECTIONS = ["matrix", "chart", "positioning", "macro", "sentiment", "methodology"];
  const DIRECTIONAL_ROLES = new Set(["PRIMARY_DIRECTIONAL", "SECONDARY_DIRECTIONAL"]);
  const ROLE_ORDER = { PRIMARY_DIRECTIONAL: 0, SECONDARY_DIRECTIONAL: 1, INTERMEDIARY_CONTEXT: 2, HEDGER_CONTEXT: 2, OPPOSITE_SIDE_CONTEXT: 2, AGGREGATE_CONTEXT: 2 };
  const WEEKDAYS = [["monday", "MON"], ["tuesday", "MON–TUE"], ["wednesday", "MON–WED"], ["thursday", "MON–THU"], ["friday", "MON–FRI"]];

  const esc = value => String(value ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;");
  const finite = value => {
    const n = Number(value);
    return value === null || value === undefined || value === "" || !Number.isFinite(n) ? null : n;
  };
  const signed = (value, digits = 2, suffix = "") => {
    const n = finite(value);
    if (n === null) return "n/a";
    const body = Math.abs(n).toLocaleString("en-US", { minimumFractionDigits: digits, maximumFractionDigits: digits });
    return `${n > 0 ? "+" : n < 0 ? "−" : ""}${body}${suffix}`;
  };
  const integer = value => finite(value) === null ? "n/a" : Math.round(finite(value)).toLocaleString("en-US");
  const percentile = value => finite(value) === null ? "n/a" : `P${Math.round(finite(value))}`;
  const pctProbability = value => {
    const n = finite(value);
    if (n === null) return "n/a";
    return `${Math.round(Math.abs(n) <= 1 ? n * 100 : n)}%`;
  };
  const horizonLabel = value => {
    const map = { monday: "MON", tuesday: "TUE", wednesday: "WED", thursday: "THU", friday: "FRI" };
    return map[value] || String(value || "").toUpperCase();
  };
  const statusLabel = s => ({
    GLOBAL_FDR: "GLOBAL FDR",
    FAMILY_FDR: "FAMILY FDR",
    OOS_PLUS_OVERLAP: "OOS + OVERLAP",
    OOS_ONLY: "OOS ONLY",
    NO_OOS_GAIN: "NO OOS GAIN",
    INSUFFICIENT_N: "INSUFFICIENT N"
  })[s] || String(s || "UNKNOWN").replaceAll("_", " ");

  const statusTone = s => s === "GLOBAL_FDR" || s === "FAMILY_FDR" ? "strong" : s === "OOS_PLUS_OVERLAP" ? "supported" : s === "OOS_ONLY" ? "mixed" : s === "INSUFFICIENT_N" ? "weak" : "none";

  const DATASET_META = {
    tff: {
      short: "TFF",
      label: "TFF Detailed",
      actors: "Asset Manager + Leveraged Funds",
      description: "Financial-futures taxonomy"
    },
    legacy: {
      short: "LEGACY",
      label: "Legacy",
      actors: "Non-Commercial + Commercial",
      description: "Legacy CFTC taxonomy"
    },
    disaggregated: {
      short: "DISAGG",
      label: "Disaggregated",
      actors: "Managed Money + Producer/Merchant",
      description: "Physical-commodity taxonomy"
    }
  };

  function datasetMeta(key) {
    return DATASET_META[key] || { short: String(key || "N/A").toUpperCase(), label: String(key || "Unavailable"), actors: "Actor taxonomy unavailable", description: "COT taxonomy" };
  }

  function datasetSelection(market = M().state.market) {
    const datasets = state.regime?.markets?.[market]?.datasets || {};
    const priority = market === "gold" || market === "silver"
      ? ["disaggregated", "legacy", "tff"]
      : ["tff", "legacy", "disaggregated"];
    const requested = market === M()?.state?.market && state.dataset && datasets[state.dataset]
      ? state.dataset
      : null;
    const key = requested || priority.find(candidate => datasets[candidate]) || Object.keys(datasets)[0] || null;
    return { key, data: key ? datasets[key] : null, meta: datasetMeta(key) };
  }

  function availableDatasetKeys(market = M().state.market) {
    const datasets = state.regime?.markets?.[market]?.datasets || {};
    return ["tff", "legacy", "disaggregated"].filter(key => datasets[key]);
  }

  const state = {
    view: "overview",
    family: "combined",
    dataset: null,
    researchSection: "matrix",
    regime: null,
    researchDetails: new Map(),
    crossDetails: null,
    macroResearch: null,
    researchMetric: "rho",
    rendering: false
  };

  function urlState() {
    const url = new URL(window.location.href);
    const market = M()?.MARKETS?.[url.searchParams.get("market")] ? url.searchParams.get("market") : null;
    const horizon = HORIZONS.includes(url.searchParams.get("horizon")) ? url.searchParams.get("horizon") : null;
    const view = VIEWS.includes(url.searchParams.get("view")) ? url.searchParams.get("view") : null;
    const family = MODEL_FAMILIES.includes(url.searchParams.get("model")) ? url.searchParams.get("model") : null;
    const dataset = DATASET_META[url.searchParams.get("dataset")] ? url.searchParams.get("dataset") : null;
    const researchSection = RESEARCH_SECTIONS.includes(url.searchParams.get("research")) ? url.searchParams.get("research") : null;
    return { market, horizon, view, family, dataset, researchSection };
  }

  function writeUrl({ push = false } = {}) {
    const url = new URL(window.location.href);
    if (M()?.state?.market) url.searchParams.set("market", M().state.market);
    if (M()?.state?.horizon) url.searchParams.set("horizon", M().state.horizon);
    const selectedDataset = datasetSelection().key;
    if (selectedDataset) url.searchParams.set("dataset", selectedDataset);
    url.searchParams.set("view", state.view);
    url.searchParams.set("model", state.family);
    if (state.view === "research") url.searchParams.set("research", state.researchSection);
    else url.searchParams.delete("research");
    history[push ? "pushState" : "replaceState"]({}, "", url);
  }

  function mount() {
    let root = document.getElementById("currentEdgeCommand");
    if (!root) {
      root = document.createElement("section");
      root.id = "currentEdgeCommand";
      root.className = "current-edge-command";
      root.setAttribute("aria-label", "Decision-first COT market intelligence");
    }
    const anchor = document.querySelector(".instrument-bar");
    if (anchor && anchor.nextElementSibling !== root) anchor.insertAdjacentElement("afterend", root);
    else if (!root.parentNode) document.querySelector("main")?.prepend(root);
    return root;
  }

  async function fetchRegime() {
    const version = window.__COT_RUNTIME_VERSION__ || Date.now();
    try {
      const response = await fetch(`worldclass/regime_backtest.json?v=${encodeURIComponent(version)}-${Date.now()}`, { cache: "no-store" });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      state.regime = await response.json();
    } catch (error) {
      console.warn("Decision-first model estimate source unavailable", error);
      state.regime = null;
    }
  }

  async function fetchResearchDetail(market = M()?.state?.market || "sp500") {
    if (state.researchDetails.has(market)) return state.researchDetails.get(market);
    const version = window.__COT_RUNTIME_VERSION__ || Date.now();
    try {
      const response = await fetch(`worldclass/cot-edge-details/${market}.json?v=${encodeURIComponent(version)}`, { cache: "no-store" });
      if (!response.ok) return null;
      const data = await response.json();
      state.researchDetails.set(market, data);
      return data;
    } catch {
      return null;
    }
  }

  async function fetchCrossMarket() {
    if (state.crossDetails) return state.crossDetails;
    const version = window.__COT_RUNTIME_VERSION__ || Date.now();
    try {
      const response = await fetch(`worldclass/cot-cross-market.json?v=${encodeURIComponent(version)}`, { cache: "no-store" });
      if (!response.ok) return null;
      state.crossDetails = await response.json();
      return state.crossDetails;
    } catch {
      return null;
    }
  }

  async function fetchMacroResearch() {
    if (state.macroResearch) return state.macroResearch;
    const version = window.__COT_RUNTIME_VERSION__ || Date.now();
    const load = async path => {
      const response = await fetch(`${path}?v=${encodeURIComponent(version)}-${Date.now()}`, { cache: "no-store" });
      if (!response.ok) throw new Error(`${path} HTTP ${response.status}`);
      return response.json();
    };
    try {
      const [effectiveness, expansion] = await Promise.all([
        load("worldclass/macro-effectiveness.json"),
        load("model_output/macro_liquidity_expansion.json")
      ]);
      state.macroResearch = { effectiveness, expansion };
      return state.macroResearch;
    } catch (error) {
      console.warn("Macro effectiveness research unavailable", error);
      return null;
    }
  }

  function datasetFor(market = M().state.market) {
    return datasetSelection(market).data;
  }

  function familyFor(market = M().state.market, family = state.family) {
    return datasetFor(market)?.families?.[family] || null;
  }

  function currentRegime(market = M().state.market) {
    return datasetFor(market)?.current || null;
  }

  function cotScoreRead(market = M().state.market) {
    const current = currentRegime(market);
    const score = finite(current?.cot_score);
    const raw = String(current?.cot_state || "").toLowerCase();
    const tone = raw === "bullish" || (score !== null && score >= 60) ? "positive" : raw === "bearish" || (score !== null && score <= 40) ? "negative" : "neutral";
    const label = tone === "positive" ? "BULLISH" : tone === "negative" ? "BEARISH" : score === null ? "UNAVAILABLE" : "NEUTRAL";
    return { score, label, tone, delta4w: finite(current?.cot_score_delta_4w), current };
  }

  function modelEstimate(market = M().state.market, horizon = M().state.horizon, family = state.family) {
    const model = familyFor(market, family);
    const metric = model?.horizons?.[horizon] || null;
    if (!metric) return null;
    return {
      expected: finite(metric.expected_return_pct ?? metric.mean_return_pct),
      baseline: finite(metric.unconditional_return_pct ?? metric.baseline_return_pct),
      excess: finite(metric.edge_vs_unconditional_pct ?? metric.excess_return_pct),
      probability: finite(metric.probability_positive ?? (metric.hit_rate_pct !== undefined ? metric.hit_rate_pct / 100 : undefined)),
      confidence: metric.confidence || "Medium",
      observations: metric.observations || metric.effective_n,
      matchRule: model.current_regime_match?.rule || model.match_rule || "Regime conditioned"
    };
  }

  function liveForecast(market = M().state.market, horizon = M().state.horizon) {
    return M().liveForecast(market, horizon);
  }

  function directionalRanked(summary) {
    const dataset = datasetSelection().key;
    return (summary?.ranked || []).filter(item => DIRECTIONAL_ROLES.has(item?.row?.actor_role) && (!dataset || item?.row?.dataset === dataset));
  }

  function contextRanked(summary) {
    const dataset = datasetSelection().key;
    return (summary?.ranked || []).filter(item => !DIRECTIONAL_ROLES.has(item?.row?.actor_role) && (!dataset || item?.row?.dataset === dataset));
  }

  function strongestDirectional(summary) {
    return directionalRanked(summary)[0] || null;
  }

  function gradeFor(item) {
    return item?.metric ? M().edgeGrade(item.metric) : null;
  }

  function gradeText(grade) {
    if (!grade) return "D — NO ACTIVE EDGE";
    return `${grade.grade} — ${grade.label.toUpperCase()}`;
  }

  function nearestWatch() {
    const dataset = datasetSelection().key;
    const watches = M().thresholdWatchlist(24).filter(item => item.market === M().state.market && DIRECTIONAL_ROLES.has(item?.row?.actor_role) && (!dataset || item?.row?.dataset === dataset));
    return watches[0] || null;
  }

  function evidenceDrawer(item) {
    if (!item?.row || !item?.metric) return "";
    const { row, metric } = item;
    const grade = gradeFor(item);
    const lookahead = metric.lookahead_safe !== false;
    return `<details class="decision-why"><summary>Evidence details <span>▾</span></summary><div class="decision-why-grid">
      <div><span>Metric</span><strong>${signed(metric.conditional_return_pct, 2, "%")}</strong></div>
      <div><span>Normal return</span><strong>${signed(metric.baseline_return_pct, 2, "%")}</strong></div>
      <div><span>Uplift vs normal</span><strong>${signed(metric.excess_vs_baseline_pp, 2, " pp")}</strong></div>
      <div><span>Independent N</span><strong>${integer(metric.independent_n ?? metric.n)}</strong></div>
      <div><span>FDR Tier</span><strong>${esc(metric.fdr_tier || "n/a")}</strong></div>
      <div><span>OOS P90-P10</span><strong>${signed(metric.holdout_p90_minus_p10_spread_pp, 2, " pp")}</strong></div>
      <div><span>Evidence grade</span><strong>${gradeText(grade)}</strong></div>
      <div><span>Lookahead safe</span><strong>${lookahead ? "YES" : "NO"}</strong></div>
    </div></details>`;
  }

  function horizonControls() {
    return `<div class="decision-horizons" role="group" aria-label="Selected forward horizon">${HORIZONS.map(h => `<button type="button" data-decision-horizon="${h}" class="${M().state.horizon === h ? "active" : ""}" aria-pressed="${M().state.horizon === h}">${horizonLabel(h)}</button>`).join("")}</div>`;
  }

  function taxonomyControls() {
    const selected = datasetSelection().key;
    const available = availableDatasetKeys();
    return `<div class="decision-taxonomies" role="group" aria-label="COT report taxonomy">${available.map(key => {
      const meta = datasetMeta(key);
      return `<button type="button" data-decision-dataset="${key}" class="dataset-${key} ${selected === key ? "active" : ""}" aria-pressed="${selected === key}" title="${esc(meta.label)} · ${esc(meta.actors)}">${esc(meta.short)}</button>`;
    }).join("")}</div>`;
  }

  function modelControls() {
    const labels = { combined: "Combined", cot: "COT only", macro: "Macro regime" };
    return `<div class="decision-horizons decision-model-family" role="group" aria-label="Current model family">${MODEL_FAMILIES.map(family => `<button type="button" data-model-family="${family}" class="${state.family === family ? "active" : ""}" aria-pressed="${state.family === family}">${labels[family]}</button>`).join("")}</div>`;
  }

  function researchControls() {
    const labels = {
      matrix: "Evidence Matrix",
      chart: "Chart & Models",
      positioning: "Positioning",
      macro: "Macro",
      sentiment: "Sentiment",
      methodology: "Methodology"
    };
    return `<div class="decision-research-tabs" role="tablist" aria-label="Research workspace">${RESEARCH_SECTIONS.map(key => `<button type="button" role="tab" data-research-section="${key}" class="${state.researchSection === key ? "active" : ""}" aria-selected="${state.researchSection === key}">${labels[key]}</button>`).join("")}</div>`;
  }

  function navigation() {
    const labels = {
      overview: ["01", "Overview"],
      edges: ["02", "Active Edges"],
      week: ["03", "Weekday Path"],
      research: ["04", "Research"],
      live: ["05", "Live Record"]
    };
    return `<div class="decision-nav">
      <div class="decision-nav-cluster"><span class="decision-nav-caption">Section</span><nav aria-label="Dashboard sections">${VIEWS.map(v => `<button type="button" data-decision-view="${v}" class="${state.view === v ? "active" : ""}" aria-current="${state.view === v ? "page" : "false"}"><small>${labels[v][0]}</small>${labels[v][1]}</button>`).join("")}</nav></div>
      <div class="decision-nav-cluster taxonomy"><span class="decision-nav-caption">COT taxonomy</span>${taxonomyControls()}</div>
      <div class="decision-nav-cluster horizon"><span class="decision-nav-caption">Forward horizon</span>${horizonControls()}</div>
    </div>`;
  }

  function headerMeta() {
    const dates = M().reportDates();
    const live = M().state.live || {};
    const integrity = String(live?.ledger?.integrity || "UNKNOWN").toUpperCase();
    let meta = document.getElementById("decisionHeaderMeta");
    if (!meta) {
      meta = document.createElement("div");
      meta.id = "decisionHeaderMeta";
      meta.className = "decision-header-meta";
      document.querySelector(".topbar-actions")?.prepend(meta);
    }
    meta.innerHTML = `<span>Report <b>${esc(dates.report || "n/a")}</b></span><span>Released <b>${esc(dates.release || "n/a")}</b></span><span class="ledger ${integrity === "PASS" ? "pass" : ""}">Ledger ${esc(integrity)}</span>`;
    document.documentElement.classList.add("decision-first-ready");
  }

  function currentModelCard() {
    const estimate = modelEstimate();
    if (!estimate) return `<div class="decision-semantic prospective unavailable"><span>CURRENT MODEL ESTIMATE</span><strong>n/a</strong><small>No ${esc(state.family)} regime estimate is available for ${horizonLabel(M().state.horizon)}.</small>${modelControls()}</div>`;
    const macroGovernance = state.family === "cot" ? "" : `<small>Macro is used for regime/analog conditioning here; aggregate macro directional weight remains 0% until vintage-safe predictive validation.</small>`;
    return `<div class="decision-semantic prospective"><span>CURRENT MODEL ESTIMATE · ${esc(state.family.toUpperCase())}</span><strong>${signed(estimate.expected, 2, "%")}</strong><small>P(positive) ${pctProbability(estimate.probability)} · baseline ${signed(estimate.baseline, 2, "%")} · excess ${signed(estimate.excess, 2, " pp")} · N ${integer(estimate.observations)} · Confidence ${esc(estimate.confidence)}</small><small>${esc(estimate.matchRule)}</small>${macroGovernance}${modelControls()}</div>`;
  }

  function liveProspectiveCard() {
    const forecast = liveForecast();
    return forecast
      ? `<div class="decision-semantic prospective"><span>LIVE PROSPECTIVE FORECAST · FROZEN</span><strong>${signed(forecast.expected, 2, "%")}</strong><small>Expected ${horizonLabel(M().state.horizon)} return · P(positive) ${pctProbability(forecast.probability)} · Confidence ${esc(forecast.confidence)}</small></div>`
      : `<div class="decision-semantic prospective unavailable"><span>LIVE PROSPECTIVE RECORD</span><strong>NOT YET FROZEN</strong><small>No immutable live forecast exists for this market/release. Historical model estimates above are not relabeled as prospective.</small></div>`;
  }

  function historicalEdgeCard(strongest) {
    if (!strongest) return `<div class="decision-semantic historical unavailable"><span>ACTIVE HISTORICAL EDGE</span><strong>NO ACTIVE DIRECTIONAL COT EDGE</strong><small>Context-only actors cannot control the headline.</small></div>`;
    const dir = M().edgeDirection(strongest.metric);
    return `<div class="decision-semantic historical"><span>ACTIVE HISTORICAL EDGE</span><strong class="${dir.tone}">${dir.label} · ${signed(strongest.metric.excess_vs_baseline_pp, 2, " pp")}</strong><small>${esc(strongest.row.actor_label)} · conditional ${signed(strongest.metric.conditional_return_pct, 2, "%")} · normal ${signed(strongest.metric.baseline_return_pct, 2, "%")} · N ${integer(strongest.metric.independent_n ?? strongest.metric.n)}</small></div>`;
  }

  function expiryStrip() {
    const today = new Date();
    const ymd = date => date.toISOString().slice(0, 10);
    const monthly = [
      ["2026-08-21", "AUG OPEX"], ["2026-09-18", "SEP QUARTERLY"], ["2026-10-16", "OCT OPEX"],
      ["2026-11-20", "NOV OPEX"], ["2026-12-18", "DEC QUARTERLY"], ["2027-01-15", "JAN OPEX"]
    ];
    const vix = [
      ["2026-08-19", "VIX AUG"], ["2026-09-16", "VIX SEP"], ["2026-10-21", "VIX OCT"],
      ["2026-11-18", "VIX NOV"], ["2026-12-16", "VIX DEC"], ["2027-01-20", "VIX JAN"]
    ];
    const now = ymd(today);
    const nextMonthly = monthly.find(([date]) => date >= now) || monthly.at(-1);
    const nextVix = vix.find(([date]) => date >= now) || vix.at(-1);
    const fmt = date => new Date(`${date}T12:00:00Z`).toLocaleDateString(undefined, { month: "short", day: "numeric" });
    return `<div class="decision-invalidation" style="grid-column:auto; margin-top:10px"><strong>Important expiries</strong><span>Next index OPEX: <b>${esc(nextMonthly[1])} · ${fmt(nextMonthly[0])}</b> · Next VIX expiry: <b>${esc(nextVix[1])} · ${fmt(nextVix[0])}</b>. Quarterly expiries are highlighted because index/futures/options positioning can rebalance more heavily around them.</span></div>`;
  }

  function currentActorPositioningTable() {
    const market = M().state.market;
    const taxonomy = datasetSelection(market);
    const actorStates = Object.values(window.__COT_CURRENT_ACTOR_STATE__?.actor_states || {})
      .filter(r => r.market === market && (!taxonomy.key || r.dataset === taxonomy.key))
      .sort((a, b) => (ROLE_ORDER[a.actor_role] ?? 9) - (ROLE_ORDER[b.actor_role] ?? 9) || String(a.actor_label).localeCompare(String(b.actor_label)));

    if (!actorStates.length) return "";

    return `<div class="decision-actor-section">
      <div class="decision-block-head">
        <div>
          <span class="decision-kicker">POSITIONING BREAKDOWN · ${esc(M().MARKETS[market])} · ${esc(taxonomy.meta.short)}</span>
          <h3>Who is holding what, and who moved this week</h3>
          <p class="decision-taxonomy-explainer">Primary taxonomy: <b>${esc(taxonomy.meta.label)}</b> · ${esc(taxonomy.meta.actors)}. Other CFTC taxonomies stay separate and are labeled wherever they appear as supplemental evidence.</p>
        </div>
        <span class="decision-condition-label">Tuesday snapshot · Released Friday</span>
      </div>
      <div class="decision-table-wrap" tabindex="0" role="region" aria-label="Current actor positioning table; scroll horizontally for all columns">
        <table class="decision-actor-table">
          <thead>
            <tr>
              <th>Trader Group</th>
              <th>Net Contracts</th>
              <th>Net/OI</th>
              <th>Position Level</th>
              <th>1W Δ Net</th>
              <th>1W Δ Net/OI</th>
              <th>Weekly Flow</th>
            </tr>
          </thead>
          <tbody>
            ${actorStates.map(r => `
              <tr>
                <td><strong>${esc(r.actor_label)}</strong><small>${esc(r.dataset.toUpperCase())} · ${esc(r.actor_role ? r.actor_role.replaceAll("_", " ") : "Context")}</small></td>
                <td>${integer(r.net_contracts)}</td>
                <td>${signed(r.net_oi_pct, 2, "%")}</td>
                <td><span class="decision-percentile-pill">${percentile(r.position_percentile)}</span></td>
                <td>${signed(r.delta_net_contracts, 0)}</td>
                <td>${signed(r.delta_net_oi_pp, 2, " pp")}</td>
                <td><b class="${r.direction === "ADD" ? "positive" : r.direction === "CUT" ? "negative" : "neutral"}">${percentile(r.change_magnitude_percentile)} ${esc(r.direction)}</b></td>
              </tr>
            `).join("")}
          </tbody>
        </table>
      </div>
    </div>`;
  }

  function overview(summary) {
    const strongest = strongestDirectional(summary);
    const grade = gradeFor(strongest);
    const cot = cotScoreRead();
    const taxonomy = datasetSelection();
    const strongestDataset = strongest?.row?.dataset || null;
    const supplementalStrongest = Boolean(strongestDataset && taxonomy.key && strongestDataset !== taxonomy.key);
    const alignment = M().layerAlignment();
    const watch = nearestWatch();
    const condition = strongest ? `${strongest.row.actor_label} · ${percentile(strongest.row.current_change_percentile)} ${esc(strongest.row.direction)} · trigger P${esc(strongest.row.selected_threshold)}` : watch ? `Nearest directional trigger: ${watch.row.actor_label} ${percentile(watch.row.change_magnitude_percentile)} → P${Math.round(watch.edge.threshold)} · ${watch.distance.toFixed(1)}P away` : "No active directional actor threshold.";
    const scoreText = cot.score === null ? "n/a" : cot.score.toFixed(1);
    return `<section class="decision-overview" data-decision-surface="overview">
      <div class="decision-current">
        <div class="decision-title-row"><div><span class="decision-kicker">${esc(M().MARKETS[M().state.market])} <b class="decision-dataset-badge dataset-${esc(taxonomy.key)}">${esc(taxonomy.meta.short)}</b><span class="decision-dataset-name">${esc(taxonomy.meta.label)} · ${esc(taxonomy.meta.description)}</span></span><h2 class="${cot.tone}">${cot.label} COT POSITIONING</h2><p>Governed COT score <b>${scoreText}</b> / 100 · 4W score change ${signed(cot.delta4w, 1)}. ${condition}</p>${supplementalStrongest ? `<p class="decision-taxonomy-note"><b>${esc(datasetMeta(strongestDataset).short)} supplemental edge:</b> the strongest historical actor edge below comes from ${esc(datasetMeta(strongestDataset).label)}, while the headline COT score remains ${esc(taxonomy.meta.label)}.</p>` : ""}</div>
        <div class="decision-grade ${grade?.tone || "weak"}"><span>Directional edge evidence</span><strong>${grade ? gradeText(grade) : "D — NO ACTIVE DIRECTIONAL EDGE"}</strong><small>${strongest ? `N ${integer(strongest.metric.independent_n ?? strongest.metric.n)}` : "Context actors excluded from headline"}</small></div></div>
        <div class="decision-semantics" style="grid-template-columns:repeat(3,minmax(0,1fr))">${currentModelCard()}${liveProspectiveCard()}${historicalEdgeCard(strongest)}</div>${expiryStrip()}
        <div class="decision-driver-strip">
          <div class="${cot.tone}"><span>COT SCORE</span><strong>${cot.label}</strong><small>${scoreText} / 100</small></div>
          <div class="${alignment.macro.tone}"><span>MACRO</span><strong>${esc(alignment.macro.label)}</strong><small>${alignment.macro.score === null ? "score unavailable" : `${Math.round(alignment.macro.score)} / 100 · context only · 0% directional weight`}</small></div>
          <div class="${alignment.sentiment.tone}"><span>SENTIMENT</span><strong>${esc(alignment.sentiment.label)}</strong><small>${alignment.sentiment.index === null ? "not available" : `${Math.round(alignment.sentiment.index)} / 100`}</small></div>
          <div class="neutral"><span>PRICE CONFIRM</span><strong>NOT GOVERNED</strong><small>no dedicated confirmation field</small></div>
        </div>
      </div>
      ${strongestPanel(strongest)}
      <aside class="decision-scanner">${opportunityScanner()}</aside>
      <div class="decision-invalidation">${invalidation(strongest, summary)}</div>
      ${currentActorPositioningTable()}
    </section>`;
  }

  function strongestPanel(strongest) {
    if (!strongest) {
      const watch = nearestWatch();
      return `<section class="decision-strongest no-edge"><div><span class="decision-kicker">STRONGEST CURRENT DIRECTIONAL EDGE</span><h3>NO ACTIVE DIRECTIONAL COT EDGE</h3><p>Context-only actors remain available under Active Edges but cannot determine the market read.</p></div>${watch ? watchCard(watch, true) : "<small>No governed directional threshold is currently close enough to highlight.</small>"}</section>`;
    }
    const { row, metric } = strongest;
    const grade = gradeFor(strongest);
    const dir = M().edgeDirection(metric);
    return `<section class="decision-strongest"><div class="decision-block-head"><div><span class="decision-kicker">STRONGEST CURRENT DIRECTIONAL EDGE <b class="decision-dataset-badge compact dataset-${esc(row.dataset)}">${esc(datasetMeta(row.dataset).short)}</b></span><h3>${esc(row.actor_label)} · ${percentile(row.current_change_percentile)} ${esc(row.direction)}</h3></div><span class="decision-direction ${dir.tone}">${dir.label}</span></div>
      <div class="decision-edge-metrics"><div><span>Trigger</span><strong>P${esc(row.selected_threshold)}</strong></div><div><span>Historical conditional</span><strong>${signed(metric.conditional_return_pct, 2, "%")}</strong></div><div><span>Normal return</span><strong>${signed(metric.baseline_return_pct, 2, "%")}</strong></div><div><span>Uplift vs normal</span><strong class="${dir.tone}">${signed(metric.excess_vs_baseline_pp, 2, " pp")}</strong></div><div><span>Independent N</span><strong>${integer(metric.independent_n ?? metric.n)}</strong></div><div><span>Evidence</span><strong>${gradeText(grade)}</strong></div></div>${evidenceDrawer(strongest)}</section>`;
  }

  function opportunityScanner() {
    const rows = M().MARKET_ORDER.map(market => {
      const preferred = market === M().state.market ? datasetSelection(market).key : datasetSelection(market).key;
      const ranked = M().rankedEdges(M().state.horizon, market).filter(item => DIRECTIONAL_ROLES.has(item?.row?.actor_role) && (!preferred || item?.row?.dataset === preferred));
      const top = ranked[0] || null;
      const dir = top ? M().edgeDirection(top.metric) : { tone: "neutral", label: "—" };
      return { market, top, dir, grade: gradeFor(top) };
    }).sort((a, b) => Boolean(b.top) - Boolean(a.top) || Math.abs(finite(b.top?.metric?.excess_vs_baseline_pp) || 0) - Math.abs(finite(a.top?.metric?.excess_vs_baseline_pp) || 0));
    return `<div class="decision-block-head"><div><span class="decision-kicker">OPPORTUNITY SCANNER</span><h3>Directional markets with active edge</h3></div></div><div class="decision-scanner-list">${rows.map(item => `<button type="button" data-decision-market="${item.market}" class="${item.market === M().state.market ? "active" : ""}"><span>${esc(M().MARKETS[item.market])}</span><strong class="${item.dir.tone}">${item.top ? signed(item.top.metric.excess_vs_baseline_pp, 2, " pp") : "No edge"}</strong><small>${item.top ? esc(datasetMeta(item.top.row.dataset).short) : "—"} · ${item.grade ? item.grade.grade : "—"}</small></button>`).join("")}</div>`;
  }

  function edgeRow(item) {
    const { row, metric } = item;
    const dir = M().edgeDirection(metric);
    const grade = gradeFor(item);
    return `<article class="decision-edge-row"><div><strong>${esc(row.actor_label)} <b class="decision-dataset-badge compact dataset-${esc(row.dataset)}">${esc(datasetMeta(row.dataset).short)}</b></strong><small>${percentile(row.current_change_percentile)} ${esc(row.direction)} · trigger P${esc(row.selected_threshold)}</small></div><span class="decision-direction ${dir.tone}">${dir.label}</span><div><span>Historical result</span><strong>${signed(metric.conditional_return_pct, 2, "%")}</strong></div><div><span>Normal</span><strong>${signed(metric.baseline_return_pct, 2, "%")}</strong></div><div><span>Uplift</span><strong class="${dir.tone}">${signed(metric.excess_vs_baseline_pp, 2, " pp")}</strong></div><div><span>Evidence</span><strong>${grade?.grade || "D"}</strong><small>N ${integer(metric.independent_n ?? metric.n)}</small></div>${evidenceDrawer(item)}</article>`;
  }

  function activeEdges(summary) {
    const directional = directionalRanked(summary);
    const context = contextRanked(summary);
    const selectedDataset = datasetSelection().key;
    const watches = M().thresholdWatchlist(24).filter(item => item.market === M().state.market && DIRECTIONAL_ROLES.has(item?.row?.actor_role) && (!selectedDataset || item?.row?.dataset === selectedDataset)).slice(0, 4);
    return `<section class="decision-view-panel" data-decision-surface="edges"><div class="decision-block-head"><div><span class="decision-kicker">ACTIVE EDGES · ${esc(M().MARKETS[M().state.market])}</span><h2>Ranked current actor conditions</h2><p>Primary/secondary actors drive the decision layer. Context actors are shown separately and never promoted into the headline.</p></div></div><div class="decision-edge-list">${directional.length ? directional.map(edgeRow).join("") : `<div class="decision-empty"><strong>NO ACTIVE DIRECTIONAL COT EDGE</strong><span>Current directional flows are inside normal historical ranges.</span></div>`}</div>${context.length ? `<details class="decision-context"><summary>+ ${context.length} contextual signal${context.length === 1 ? "" : "s"}</summary><div class="decision-edge-list">${context.map(edgeRow).join("")}</div></details>` : ""}<div class="decision-watch-section"><div class="decision-block-head"><div><span class="decision-kicker">COMING EDGE</span><h3>Distance to governed directional trigger</h3></div><span class="decision-condition-label">Conditional watch — not a prediction</span></div>${watches.length ? `<div class="decision-watch-list">${watches.map(item => watchCard(item)).join("")}</div>` : `<div class="decision-empty"><span>No validated directional threshold is close enough to form a governed watch.</span></div>`}</div></section>`;
  }

  function watchCard(item, compact = false) {
    const current = finite(item.row.change_magnitude_percentile) ?? 0;
    const trigger = finite(item.edge.threshold) ?? 100;
    const width = Math.max(0, Math.min(100, trigger ? current / trigger * 100 : 0));
    return `<article class="decision-watch ${compact ? "compact" : ""}"><div><strong>${esc(item.row.actor_label)} ${esc(item.row.direction)} <b class="decision-dataset-badge compact dataset-${esc(item.row.dataset)}">${esc(datasetMeta(item.row.dataset).short)}</b></strong><small>Current ${percentile(current)} · trigger P${Math.round(trigger)} · ${item.distance.toFixed(1)} percentile points away</small></div><div class="decision-progress" aria-label="Current percentile ${Math.round(current)} toward trigger ${Math.round(trigger)}"><i style="width:${width.toFixed(1)}%"></i><b style="left:${Math.max(0, Math.min(100, trigger))}%"></b></div><div class="${item.direction.tone}"><span>If triggered</span><strong>${signed(item.edge.best_holdout_edge_pp, 2, " pp")}</strong><small>${horizonLabel(item.edge.best_horizon)} historical uplift · Evidence ${item.grade.grade}</small></div></article>`;
  }

  function weekPath(summary) {
    const strongest = strongestDirectional(summary);
    if (!strongest) return `<section class="decision-view-panel"><span class="decision-kicker">THIS WEEK — CUMULATIVE HISTORICAL PATH</span><h2>No governed directional weekday path</h2><div class="decision-empty"><span>A weekday path appears only when a directional threshold is active.</span></div></section>`;
    const points = WEEKDAYS.map(([key, label]) => ({ label, metric: M().metricFor(strongest.row, key) })).filter(point => point.metric);
    const grade = gradeFor(strongest);
    return `<section class="decision-view-panel" data-decision-surface="week"><div class="decision-block-head"><div><span class="decision-kicker">THIS WEEK — CUMULATIVE HISTORICAL PATH <b class="decision-dataset-badge compact dataset-${esc(strongest.row.dataset)}">${esc(datasetMeta(strongest.row.dataset).short)}</b></span><h2>${esc(strongest.row.actor_label)} · release-corrected weekday path</h2><p>Based on previous Tuesday COT positioning; publicly available Friday. Returns are cumulative to each weekday.</p></div><span class="decision-evidence-badge">${gradeText(grade)}</span></div><div class="decision-week-path">${points.map((point, index) => `<article><span>${esc(point.label)}</span><strong>${signed(point.metric.conditional_return_pct, 2, "%")}</strong><small>${finite(point.metric.positive_rate_pct) === null ? "" : `${Math.round(point.metric.positive_rate_pct)}% + · `}edge ${signed(point.metric.excess_vs_baseline_pp, 2, " pp")}</small>${index < points.length - 1 ? "<i>→</i>" : ""}</article>`).join("")}</div>${forwardHistory(strongest)}</section>`;
  }

  function forwardHistory(strongest) {
    return `<div class="decision-forward"><div class="decision-block-head"><div><span class="decision-kicker">FORWARD HORIZONS</span><h3>Historical conditional path</h3></div></div><div class="decision-forward-grid">${HORIZONS.map(h => {
      const metric = M().metricFor(strongest.row, h);
      if (!metric) return `<div><span>${horizonLabel(h)}</span><strong>n/a</strong><small>No governed metric</small></div>`;
      const dir = M().edgeDirection(metric);
      return `<div><span>${horizonLabel(h)}</span><strong class="${dir.tone}">${signed(metric.conditional_return_pct, 2, "%")}</strong><small>normal ${signed(metric.baseline_return_pct, 2, "%")} · uplift ${signed(metric.excess_vs_baseline_pp, 2, " pp")} · N ${integer(metric.independent_n ?? metric.n)}</small></div>`;
    }).join("")}</div></div>`;
  }

  function invalidation(strongest, summary) {
    if (!strongest) return `<strong>What changes the read?</strong><span>A new COT release can change the governed score/state or activate a directional actor threshold. Macro changes affect the Combined model estimate, not the raw COT score.</span>`;
    const sign = M().edgeDirection(strongest.metric).sign;
    const opposing = directionalRanked(summary).find(item => M().edgeDirection(item.metric).sign === -sign);
    return `<strong>What could invalidate the edge?</strong><span>${opposing ? `${esc(opposing.row.actor_label)} already carries an opposing ${signed(opposing.metric.excess_vs_baseline_pp, 2, " pp")} historical edge. ` : ""}The historical edge weakens if its threshold deactivates on the next release. Macro can change the Combined model estimate separately.</span>`;
  }

  function matrixVal(m) {
    if (!m) return "n/a";
    if (state.researchMetric === "rho") return signed(m.independent_spearman_rho, 2);
    if (state.researchMetric === "r2") return m.oos_r2 == null ? "n/a" : signed(Number(m.oos_r2) * 100, 1, "%");
    if (state.researchMetric === "spread") return signed(m.holdout_p90_minus_p10_spread_pp, 1, " pp");
    return integer(m.independent_n);
  }

  function macroP(value) {
    const n = finite(value);
    if (n === null) return "n/a";
    if (n < 0.001) return "<0.001";
    return n.toFixed(n < 0.1 ? 3 : 2);
  }

  function macroFactorLabel(key) {
    return ({
      score_net_liquidity: "Net liquidity",
      score_bank_reserves: "Bank reserves",
      score_treasury_supply: "Treasury supply",
      score_repo_spread: "Repo / admin spread",
      score_slr_load: "SLR balance-sheet load",
      score_real_yield: "Real yields",
      score_credit: "Credit spreads",
      score_dollar: "Dollar",
      score_vix: "VIX"
    })[key] || String(key || "").replace(/^score_/, "").replaceAll("_", " ");
  }

  function macroCandidateLabel(key) {
    return ({
      vix: "VIX",
      hy_oas: "HY OAS",
      net_liquidity_13w_change: "Net liquidity · 13W change",
      real_yield_10y: "10Y real yield",
      tga_4w_change: "TGA · 4W change"
    })[key] || String(key || "").replaceAll("_", " ");
  }

  async function macroResearchPanel() {
    const payload = await fetchMacroResearch();
    if (!payload) {
      return `<section class="decision-view-panel decision-research-shell" data-decision-surface="research"><div class="decision-block-head"><div><span class="decision-kicker">MACRO RESEARCH</span><h2>Liquidity score & predictive effectiveness</h2><p>The governed macro research payload is unavailable. No effectiveness is inferred from the current score alone.</p></div></div>${researchControls()}<div class="decision-empty">Macro effectiveness evidence unavailable.</div></section>`;
    }

    const { effectiveness, expansion } = payload;
    const latest = expansion?.existing_macro_latest || {};
    const governance = effectiveness?.governance || {};
    const score = finite(latest.liquidity_score);
    const coverage = finite(expansion?.source_coverage_ratio);
    const confidence = finite(latest.confidence_score);
    const aggregate = effectiveness?.aggregate || [];
    const factorCandidates = (effectiveness?.factor_candidates || [])
      .filter(row => finite(row.hac_q_global) !== null && finite(row.hac_q_global) <= 0.10)
      .sort((a, b) => Math.abs(finite(b.spearman) || 0) - Math.abs(finite(a.spearman) || 0))
      .slice(0, 7);
    const controls = effectiveness?.incremental_controls || [];
    const weights = effectiveness?.score_weights || {};

    const aggregateRow = (market, horizon) => aggregate.find(row => row.target === `${market}_${horizon.toUpperCase()}`) || null;
    const bestAbsRho = aggregate.reduce((best, row) => Math.max(best, Math.abs(finite(row.spearman) || 0)), 0);
    const bestOos = aggregate.reduce((best, row) => Math.max(best, finite(row.oos_r2) ?? -Infinity), -Infinity);
    const lowestHac = aggregate.reduce((best, row) => Math.min(best, finite(row.hac_p) ?? Infinity), Infinity);

    const componentRows = Object.entries(weights).map(([key, weight]) => {
      const factorScore = finite(latest[key]);
      const w = finite(weight) || 0;
      const contribution = factorScore === null ? null : factorScore * w;
      return `<div class="macro-component-row"><div><strong>${esc(macroFactorLabel(key))}</strong><small>${Math.round(w * 100)}% weight</small></div><div class="macro-component-track"><i style="width:${factorScore === null ? 0 : Math.max(0, Math.min(100, factorScore))}%"></i></div><b>${factorScore === null ? "n/a" : factorScore.toFixed(1)}</b><span>${contribution === null ? "—" : `${contribution.toFixed(1)} pts`}</span></div>`;
    }).join("");

    const horizons = ["1W", "2W", "4W", "13W", "26W"];
    const aggregateRows = horizons.map(h => {
      const spx = aggregateRow("SPX", h);
      const nq = aggregateRow("NQ", h);
      const cell = row => row ? `<td>${signed(row.spearman, 3)}</td><td>${macroP(row.hac_p)}</td><td>${row.oos_r2 == null ? "n/a" : signed(Number(row.oos_r2) * 100, 1, "%")}</td>` : `<td>n/a</td><td>n/a</td><td>n/a</td>`;
      return `<tr><th>${h}</th>${cell(spx)}${cell(nq)}</tr>`;
    }).join("");

    const candidateCards = factorCandidates.map(row => {
      const q = finite(row.hac_q_global);
      const oos = finite(row.oos_r2);
      const status = q !== null && q <= .10 && oos !== null && oos > 0 ? "RESEARCH CANDIDATE" : q !== null && q <= .10 ? "OOS FAIL / CAUTION" : "EXPLORATORY";
      const tone = status === "RESEARCH CANDIDATE" ? "supported" : "mixed";
      return `<article class="macro-factor-card ${tone}"><div class="macro-factor-head"><strong>${esc(macroCandidateLabel(row.feature))}</strong><span>${esc(status)}</span></div><h4>${esc(row.target)}</h4><div class="macro-factor-stats"><div><span>Spearman ρ</span><b>${signed(row.spearman, 3)}</b></div><div><span>HAC p</span><b>${macroP(row.hac_p)}</b></div><div><span>Global q</span><b>${macroP(row.hac_q_global)}</b></div><div><span>OOS R²</span><b>${row.oos_r2 == null ? "n/a" : signed(Number(row.oos_r2) * 100, 1, "%")}</b></div></div><small>N ${integer(row.n)} · factor-level evidence only; not a production directional vote.</small></article>`;
    }).join("");

    const incrementalRows = controls.map(row => `<tr><td>${esc(row.target)}</td><td>${macroP(row.p_hac_incremental)}</td><td>${signed(Number(row.delta_r2_in) * 100, 1, " pp")}</td><td class="${finite(row.delta_oos_r2) > 0 ? "positive" : "negative"}">${signed(Number(row.delta_oos_r2) * 100, 1, " pp")}</td><td>${signed(row.full_pred_spear, 3)}</td></tr>`).join("");

    const pillars = expansion?.pillars || {};
    const pillarKeys = ["net_liquidity", "bank_reserves", "treasury_supply", "funding_microstructure", "dealer_absorption", "fiscal_cash_flow", "auction_absorption"];
    const pillarCards = pillarKeys.map(key => {
      const p = pillars[key];
      if (!p) return "";
      const raw = finite(p.value) ?? finite(p.score);
      const unit = p.value != null ? p.unit || "" : p.score != null ? "/100" : "";
      return `<article class="macro-pillar-card"><span>${esc(p.label || key)}</span><strong>${raw === null ? "n/a" : `${signed(raw, raw >= 100 ? 0 : 1)}${unit === "/100" ? " / 100" : unit ? ` ${esc(unit)}` : ""}`}</strong><b>${esc(p.state || "Context")}</b><small>${esc((p.reasons || [])[0] || "Current observed state")}</small></article>`;
    }).join("");

    return `<section class="decision-view-panel decision-research-shell macro-research" data-decision-surface="research">
      <div class="decision-block-head"><div><span class="decision-kicker">MACRO RESEARCH · GOVERNED EFFECTIVENESS</span><h2>Liquidity score, current plumbing & predictive evidence</h2><p>Separate three questions: what the score says now, whether its inputs are fresh, and whether the score has actually predicted future returns.</p></div></div>
      ${researchControls()}

      <div class="macro-verdict-grid">
        <div><span>CURRENT LIQUIDITY SCORE</span><strong>${score === null ? "n/a" : score.toFixed(1)}</strong><small>${esc(latest.regime_label || "State unavailable")} · ${esc(latest.date || "date n/a")}</small></div>
        <div><span>SOURCE COVERAGE</span><strong>${coverage === null ? "n/a" : `${Math.round(coverage * 100)}%`}</strong><small>${esc(expansion?.source_coverage_label || "Coverage unknown")} data coverage</small></div>
        <div class="warning"><span>PREDICTIVE VALIDITY</span><strong>${esc(governance.aggregate_score_verdict || "UNKNOWN")}</strong><small>${esc(governance.aggregate_score_verdict_label || "Effectiveness not established")}</small></div>
        <div><span>PRODUCTION DIRECTIONAL WEIGHT</span><strong>${Math.round((finite(governance.aggregate_score_directional_weight) || 0) * 100)}%</strong><small>${esc(governance.production_role || "Context only")}</small></div>
        <div><span>SCORE CONFIDENCE</span><strong>${confidence === null ? "n/a" : `${Math.round(confidence)} / 100`}</strong><small>${esc(latest.confidence_label || "confidence unavailable")} · data/model confidence, not predictive accuracy</small></div>
      </div>
      <div class="macro-governance-note"><strong>Current conclusion:</strong> the aggregate score is useful for describing liquidity/plumbing conditions, but it is not a validated directional predictor. Across the 10 SPX/NQ horizon tests, max |Spearman ρ| is <b>${bestAbsRho.toFixed(3)}</b>, the lowest HAC p-value is <b>${Number.isFinite(lowestHac) ? macroP(lowestHac) : "n/a"}</b>, and the best OOS R² is only <b>${Number.isFinite(bestOos) ? signed(bestOos * 100, 2, "%") : "n/a"}</b>.</div>

      <div class="macro-research-section"><div class="decision-block-head compact"><div><span class="decision-kicker">01 · CURRENT SCORE CONSTRUCTION</span><h3>What is producing ${score === null ? "the current reading" : `${score.toFixed(1)} / 100`}?</h3><p>Factor score × fixed inferred production weight. High data quality does not imply predictive validity.</p></div></div><div class="macro-component-list">${componentRows}</div></div>

      <div class="macro-research-section"><div class="decision-block-head compact"><div><span class="decision-kicker">02 · CURRENT PLUMBING</span><h3>What is happening underneath the aggregate?</h3></div></div><div class="macro-pillar-grid">${pillarCards}</div></div>

      <div class="macro-research-section"><div class="decision-block-head compact"><div><span class="decision-kicker">03 · AGGREGATE SCORE BACKTEST</span><h3>Does a higher liquidity score predict higher future returns?</h3><p>Weekly observations, 2023-06 to 2026-08. ρ = rank correlation; HAC p adjusts for serial dependence; OOS R² tests chronological out-of-sample prediction.</p></div><span class="decision-evidence-badge">0% PRODUCTION WEIGHT</span></div><div class="macro-effectiveness-wrap"><table class="macro-effectiveness-table"><thead><tr><th rowspan="2">Horizon</th><th colspan="3">S&P 500</th><th colspan="3">Nasdaq-100</th></tr><tr><th>ρ</th><th>HAC p</th><th>OOS R²</th><th>ρ</th><th>HAC p</th><th>OOS R²</th></tr></thead><tbody>${aggregateRows}</tbody></table></div><p class="decision-footnote">No aggregate row passes the robustness standard. A positive return in a high-score regime is not enough; the relationship must survive dependence controls, eras and out-of-sample testing.</p></div>

      <div class="macro-research-section"><div class="decision-block-head compact"><div><span class="decision-kicker">04 · FACTOR-LEVEL RESEARCH</span><h3>The aggregate fails, but some individual factors are worth further validation</h3><p>These rows are deliberately not promoted to the headline score because the historical macro layer is not fully vintage/release-safe.</p></div></div><div class="macro-factor-grid">${candidateCards || `<div class="decision-empty">No factor candidate passed the stored research filter.</div>`}</div></div>

      <div class="macro-research-section"><div class="decision-block-head compact"><div><span class="decision-kicker">05 · NET-LIQUIDITY INCREMENTAL TEST</span><h3>Does 13W net-liquidity change add information beyond price state + VIX?</h3></div></div><div class="macro-effectiveness-wrap"><table class="macro-effectiveness-table compact"><thead><tr><th>Target</th><th>Incremental HAC p</th><th>In-sample ΔR²</th><th>OOS ΔR²</th><th>Full-model pred. ρ</th></tr></thead><tbody>${incrementalRows}</tbody></table></div><p class="decision-footnote">13W SPX/NQ improves out-of-sample fit in this research sample; 26W degrades sharply. That horizon instability is one reason the factor remains research-only.</p></div>

      <div class="decision-promotion-box"><h4>Promotion rule</h4><p>${esc(governance.promotion_rule || "Point-in-time validation is required before any macro factor receives non-zero production directional weight.")}</p></div>
    </section>`;
  }

  async function researchPanel() {
    const market = M().state.market;
    const sectionCopy = {
      chart: ["CHART & MODEL RESEARCH", "Price, positioning overlays and forward-model diagnostics", "Use the same market and COT taxonomy selected above. Chart controls and forward expectancy remain inside this research workspace."],
      positioning: ["POSITIONING RESEARCH", "Detailed actor flow, crowding and cross-market positioning", "Weekly changes, historical extremes and actor-level diagnostics are grouped here instead of opening a second dashboard."],
      macro: ["MACRO RESEARCH", "Liquidity, funding and transmission diagnostics", "Macro remains a separate confirmation/context layer and does not silently overwrite the selected COT taxonomy."],
      sentiment: ["SENTIMENT RESEARCH", "Media, social and prediction-market context", "Sentiment remains observational context and is kept separate from the governed COT signal."],
      methodology: ["METHODOLOGY", "Model definitions, taxonomy rules and release governance", "The full methodology remains available without leaving the current terminal shell."]
    };

    if (state.researchSection === "macro") return macroResearchPanel();

    if (state.researchSection !== "matrix") {
      const [kicker, title, copy] = sectionCopy[state.researchSection] || sectionCopy.positioning;
      return `<section class="decision-view-panel decision-research-shell" data-decision-surface="research">
        <div class="decision-block-head"><div><span class="decision-kicker">${kicker} · ${esc(M().MARKETS[market])}</span><h2>${title}</h2><p>${copy}</p></div></div>
        ${researchControls()}
      </section>`;
    }

    const detail = await fetchResearchDetail(market);
    const cross = await fetchCrossMarket();

    if (!detail) {
      return `<section class="decision-view-panel"><div class="decision-block-head"><div><span class="decision-kicker">DEEP RESEARCH MATRIX</span><h2>Statistical evidence & predictive matrices</h2></div></div>${researchControls()}<div class="decision-empty">Loading market research details...</div></section>`;
    }

    const grouped = {};
    const selectedDataset = datasetSelection(market).key;
    for (const r of (detail.actors || []).filter(row => !selectedDataset || row.dataset === selectedDataset)) {
      const g = grouped[r.series] || (grouped[r.series] = { series: r.series, actor: r.actor, actor_role: r.actor_role, dataset: r.dataset, h: {} });
      g.h[r.horizon] = r.best_overall;
    }
    const actors = Object.values(grouped).sort((a, b) => (ROLE_ORDER[a.actor_role] ?? 9) - (ROLE_ORDER[b.actor_role] ?? 9) || a.actor.localeCompare(b.actor));

    return `<section class="decision-view-panel" data-decision-surface="research">
      <div class="decision-block-head">
        <div>
          <span class="decision-kicker">DEEP RESEARCH MATRIX · ${esc(M().MARKETS[market])}</span>
          <h2>Actor × Forward-Horizon Evidence Matrix</h2>
          <p>Auditable out-of-sample predictability, Spearman correlation and holdout spreads across all horizons.</p>
        </div>
        <div class="decision-metric-select">
          <label>Metric:
            <select id="researchMetricSelector">
              <option value="rho" ${state.researchMetric === "rho" ? "selected" : ""}>Independent ρ (Spearman)</option>
              <option value="r2" ${state.researchMetric === "r2" ? "selected" : ""}>OOS R² (%)</option>
              <option value="spread" ${state.researchMetric === "spread" ? "selected" : ""}>P90−P10 Spread (pp)</option>
              <option value="n" ${state.researchMetric === "n" ? "selected" : ""}>Independent N</option>
            </select>
          </label>
        </div>
      </div>
      ${researchControls()}

      <div class="decision-matrix-wrap">
        <table class="decision-matrix">
          <thead>
            <tr>
              <th>Trader Group</th>
              ${MATRIX_HORIZONS.map(h => `<th>${horizonLabel(h)}</th>`).join("")}
            </tr>
          </thead>
          <tbody>
            ${actors.map(a => `
              <tr>
                <th><strong>${esc(a.actor)} <b class="decision-dataset-badge compact dataset-${esc(a.dataset)}">${esc(datasetMeta(a.dataset).short)}</b></strong><small>${esc(a.actor_role ? a.actor_role.replaceAll("_", " ") : "Context")}</small></th>
                ${MATRIX_HORIZONS.map(h => {
                  const m = a.h[h];
                  const tone = statusTone(m?.evidence_status);
                  const isInsufficient = m?.sample_grade === "INSUFFICIENT" || (["26w", "39w", "52w"].includes(h) && (m?.independent_n ?? 0) < 15);
                  return `<td class="${tone} ${isInsufficient ? "insufficient" : ""}" title="${esc(statusLabel(m?.evidence_status))} · predictor ${esc(m?.predictor || "n/a")} · N ${esc(m?.independent_n ?? "n/a")}">
                    <span>${matrixVal(m)}</span>
                    <small>${m ? statusLabel(m.evidence_status) : "n/a"}</small>
                  </td>`;
                }).join("")}
              </tr>
            `).join("")}
          </tbody>
        </table>
      </div>
      <p class="decision-footnote">Long-horizon cells (26W/39W/52W) with independent N &lt; 15 are tagged insufficient even if point estimates are high.</p>

      ${crossMarketSection(cross, market)}
    </section>`;
  }

  function crossMarketSection(cross, market) {
    if (!cross) return "";
    const groups = Object.entries(cross.current_same_actor_across_markets || {}).filter(([, rows]) => rows.some(r => r.market === market));
    if (!groups.length) return "";

    return `<div class="decision-cross-section">
      <div class="decision-block-head">
        <div>
          <span class="decision-kicker">CROSS-MARKET ALIGNMENT</span>
          <h3>Same participant positioning across equity & commodity complexes</h3>
        </div>
      </div>
      <div class="decision-cross-grid">
        ${groups.map(([key, rows]) => `
          <article class="decision-cross-card">
            <div class="decision-cross-card-head"><strong>${esc(rows[0]?.actor_label || key)}</strong></div>
            <div class="decision-cross-markets">
              ${rows.map(r => `
                <div class="${r.market === market ? "active" : ""}">
                  <span>${esc(M().MARKETS[r.market] || r.market)}</span>
                  <b>${percentile(r.position_percentile)} · ${percentile(r.change_magnitude_percentile)} ${esc(r.direction)}</b>
                  <small>Δnet/OI ${signed(r.delta_net_oi_pp, 2, " pp")}</small>
                </div>
              `).join("")}
            </div>
          </article>
        `).join("")}
      </div>
    </div>`;
  }

  function livePanel() {
    const live = M().state.live || {};
    const integrity = String(live?.ledger?.integrity || "UNKNOWN").toUpperCase();
    const edgeEvidence = live?.edge_evidence || null;

    return `<section class="decision-view-panel" data-decision-surface="live">
      <div class="decision-block-head">
        <div>
          <span class="decision-kicker">PROSPECTIVE TRACK RECORD & AUDIT LEDGER</span>
          <h2>Verifiable live forecast verification</h2>
          <p>Historical backtests and future live forecasts remain strictly decoupled. Past reports are never retroactively backfilled as live proof.</p>
        </div>
        <span class="decision-evidence-badge ${integrity === "PASS" ? "pass" : ""}">${esc(integrity)}</span>
      </div>

      <div class="decision-live-summary">
        <div><span>Core Ledger Audit</span><strong class="${integrity === "PASS" ? "positive" : ""}">${esc(integrity)}</strong></div>
        <div><span>Frozen Forecasts</span><strong>${integer(live.forecast_count || 0)}</strong></div>
        <div><span>Matured Signals</span><strong>${integer(live.matured_signal_count || 0)}</strong></div>
        <div><span>Actor Edge Forecasts</span><strong>${integer(edgeEvidence?.forecast_count || 0)}</strong></div>
        <div><span>Actor Edge Matured</span><strong>${integer(edgeEvidence?.matured_signal_count || 0)}</strong></div>
        <div><span>Historical Backfill</span><strong class="negative">DISALLOWED</strong></div>
      </div>

      <div class="decision-promotion-box">
        <h4>Model Governance & Promotion Principle</h4>
        <p>Statistical research signals become eligible only for <b>Governance Review</b>. No automated process or frontend click can modify live production model weights without immutable version release commits.</p>
      </div>
    </section>`;
  }

  function setView(next, { push = true } = {}) {
    state.view = VIEWS.includes(next) ? next : "overview";
    document.documentElement.dataset.cotDecisionView = state.view;
    writeUrl({ push });
    render();
  }

  function selectMarket(market, { push = true } = {}) {
    if (!M().MARKETS[market]) return;
    const button = document.querySelector(`#instrumentTabs [data-market="${market}"]`);
    if (button && market !== M().selectedMarket()) button.click();
    M().state.market = market;
    const baseDataset = document.querySelector('#desktopControls [data-control="dataset"]')?.value
      || document.querySelector('#mobileControlBody [data-control="dataset"]')?.value;
    state.dataset = availableDatasetKeys(market).includes(baseDataset) ? baseDataset : null;
    writeUrl({ push });
    render();
  }

  function selectHorizon(horizon, { push = true } = {}) {
    if (!HORIZONS.includes(horizon)) return;
    M().state.horizon = horizon;
    writeUrl({ push });
    render();
  }

  function selectFamily(family, { push = true } = {}) {
    if (!MODEL_FAMILIES.includes(family)) return;
    state.family = family;
    writeUrl({ push });
    render();
  }

  function selectResearchSection(section, { push = true } = {}) {
    if (!RESEARCH_SECTIONS.includes(section)) return;
    state.researchSection = section;
    document.documentElement.dataset.cotResearchSection = section;
    writeUrl({ push });
    render();
  }

  function syncBaseDashboardDataset(dataset, attemptsLeft = 20) {
    const selects = [...document.querySelectorAll('[data-control="dataset"]')];
    const target = selects.find(select => [...select.options].some(option => option.value === dataset));
    if (!target) {
      if (attemptsLeft > 0) window.setTimeout(() => syncBaseDashboardDataset(dataset, attemptsLeft - 1), 100);
      return;
    }
    if (target.value === dataset) return;
    target.value = dataset;
    target.dispatchEvent(new Event("change", { bubbles: true }));
  }

  function selectDataset(dataset, { push = true } = {}) {
    if (!availableDatasetKeys().includes(dataset)) return;
    state.dataset = dataset;
    syncBaseDashboardDataset(dataset);
    writeUrl({ push });
    render();
  }

  async function render() {
    if (state.rendering || !M()) return;
    state.rendering = true;
    try {
      const root = mount();
      if (!M().state.current || !M().state.active || !M().state.registry) {
        root.innerHTML = `<div class="decision-loading">Loading governed COT decision layer…</div>`;
        return;
      }
      // Keep an explicit URL/programmatic market authoritative during boot.
      // The legacy instrument tabs can mount a few frames later; blindly
      // reading their temporary S&P default here used to erase deep links such
      // as ?market=nq before the tabs had a chance to synchronize.
      if (!M().MARKETS[M().state.market]) M().state.market = M().selectedMarket();
      const summary = M().summary();
      headerMeta();
      document.documentElement.dataset.cotDecisionView = state.view;
      document.documentElement.dataset.cotResearchSection = state.researchSection;
      document.documentElement.dataset.cotDataset = datasetSelection().key || "unavailable";

      let content = "";
      if (state.view === "overview") content = overview(summary);
      else if (state.view === "edges") content = activeEdges(summary);
      else if (state.view === "week") content = weekPath(summary);
      else if (state.view === "research") content = await researchPanel();
      else if (state.view === "live") content = livePanel();

      root.innerHTML = `${navigation()}${content}`;
      writeUrl({ push: false });
    } finally {
      state.rendering = false;
    }
  }

  function bind(root) {
    root.addEventListener("click", event => {
      const market = event.target.closest("[data-decision-market]")?.dataset.decisionMarket;
      if (market) return selectMarket(market);
      const horizon = event.target.closest("[data-decision-horizon]")?.dataset.decisionHorizon;
      if (horizon) return selectHorizon(horizon);
      const view = event.target.closest("[data-decision-view]")?.dataset.decisionView;
      if (view) return setView(view);
      const family = event.target.closest("[data-model-family]")?.dataset.modelFamily;
      if (family) return selectFamily(family);
      const dataset = event.target.closest("[data-decision-dataset]")?.dataset.decisionDataset;
      if (dataset) return selectDataset(dataset);
      const researchSection = event.target.closest("[data-research-section]")?.dataset.researchSection;
      if (researchSection) return selectResearchSection(researchSection);
    });

    root.addEventListener("change", event => {
      if (event.target.id === "researchMetricSelector") {
        state.researchMetric = event.target.value;
        render();
      }
    });
  }

  function observeMarket() {
    const tabs = document.getElementById("instrumentTabs");
    tabs?.addEventListener("click", () => window.setTimeout(() => {
      const market = M().selectedMarket();
      if (market !== M().state.market) {
        M().state.market = market;
        const baseDataset = document.querySelector('#desktopControls [data-control="dataset"]')?.value
          || document.querySelector('#mobileControlBody [data-control="dataset"]')?.value;
        state.dataset = availableDatasetKeys(market).includes(baseDataset) ? baseDataset : null;
        writeUrl({ push: true });
        render();
      }
    }, 0));
    document.addEventListener("change", event => {
      const control = event.target.closest?.('[data-control="dataset"]');
      if (!control || !availableDatasetKeys().includes(control.value) || control.value === state.dataset) return;
      state.dataset = control.value;
      writeUrl({ push: false });
      render();
    });
  }

  function applyInitialUrl() {
    const initial = urlState();
    state.view = initial.view || "overview";
    state.family = initial.family || "combined";
    state.dataset = initial.dataset || null;
    state.researchSection = initial.researchSection || "matrix";
    M().state.horizon = initial.horizon || "1w";
    if (initial.market) {
      const button = document.querySelector(`#instrumentTabs [data-market="${initial.market}"]`);
      if (button && !button.classList.contains("active")) button.click();
      M().state.market = initial.market;
    } else {
      M().state.market = M().selectedMarket();
    }
    if (!availableDatasetKeys(M().state.market).includes(state.dataset)) state.dataset = null;
    if (state.dataset) window.setTimeout(() => syncBaseDashboardDataset(state.dataset), 0);
    document.documentElement.dataset.cotDecisionView = state.view;
    document.documentElement.dataset.cotResearchSection = state.researchSection;
  }

  async function boot() {
    const root = mount();
    bind(root);
    if (!M()) throw new Error("Current Edge model missing");
    await Promise.all([M().load(), fetchRegime()]);
    applyInitialUrl();
    await render();
    observeMarket();
    window.addEventListener("popstate", () => {
      const initial = urlState();
      state.view = initial.view || "overview";
      state.family = initial.family || "combined";
      state.dataset = initial.dataset || null;
      state.researchSection = initial.researchSection || "matrix";
      M().state.horizon = initial.horizon || "1w";
      if (initial.market && initial.market !== M().selectedMarket()) document.querySelector(`#instrumentTabs [data-market="${initial.market}"]`)?.click();
      M().state.market = initial.market || M().selectedMarket();
      if (!availableDatasetKeys(M().state.market).includes(state.dataset)) state.dataset = null;
      if (state.dataset) syncBaseDashboardDataset(state.dataset);
      document.documentElement.dataset.cotResearchSection = state.researchSection;
      render();
    });
    window.addEventListener("cot:intelligence-ready", render);
    // Bootstrap loads the shared base payload asynchronously, after this script runs, so
    // neither __COT_APP_DATA_READY__ nor cot:intelligence-ready reliably fires once it is
    // installed. Poll briefly and re-render when __COT_WORLDCLASS_BASE__ appears, otherwise
    // the macro/sentiment chips stay frozen on "unavailable".
    const rerenderWithSharedBase = (attemptsLeft) => {
      if (window.__COT_WORLDCLASS_BASE__) render();
      else if (attemptsLeft > 0) window.setTimeout(() => rerenderWithSharedBase(attemptsLeft - 1), 250);
    };
    rerenderWithSharedBase(120);
  }

  boot().catch(error => {
    console.error("Decision-first COT command center failed to initialize.", error);
    const root = mount();
    root.innerHTML = `<div class="decision-loading"><strong>Decision layer unavailable.</strong><span>The underlying research dashboard remains intact; no forecast is fabricated.</span></div>`;
  });
})();
