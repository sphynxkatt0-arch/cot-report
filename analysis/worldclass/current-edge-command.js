(() => {
  "use strict";

  const M = () => window.__COT_CURRENT_EDGE_MODEL__;
  const HORIZONS = ["1w", "2w", "4w", "13w", "26w"];
  const VIEWS = ["today", "research", "live"];
  const VIEW_ALIASES = { overview: "today", edges: "today", week: "today", today: "today", research: "research", live: "live" };
  const MODEL_FAMILIES = ["combined", "cot", "macro"];
  const DIRECTIONAL_ROLES = new Set(["PRIMARY_DIRECTIONAL", "SECONDARY_DIRECTIONAL"]);
  const WEEKDAYS = [["monday", "MON"], ["tuesday", "MON–TUE"], ["wednesday", "MON–WED"], ["thursday", "MON–THU"], ["friday", "MON–FRI"]];

  const esc = value => String(value ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;");
  const finite = value => {
    const n = Number(value);
    return value === null || value === undefined || value === "" || !Number.isFinite(n) ? null : n;
  };
  const signed = (value, digits = 2, suffix = "") => {
    const n = finite(value);
    if (n === null) return "n/a";
    const body = Math.abs(n).toLocaleString(undefined, { minimumFractionDigits: digits, maximumFractionDigits: digits });
    return `${n > 0 ? "+" : n < 0 ? "−" : ""}${body}${suffix}`;
  };
  const integer = value => finite(value) === null ? "n/a" : Math.round(finite(value)).toLocaleString();
  const percentile = value => finite(value) === null ? "n/a" : `P${Math.round(finite(value))}`;
  const pctProbability = value => {
    const n = finite(value);
    if (n === null) return "n/a";
    return `${Math.round(Math.abs(n) <= 1 ? n * 100 : n)}%`;
  };
  const horizonLabel = value => String(value || "").toUpperCase();
  const toneForNumber = value => finite(value) === null || Math.abs(finite(value)) < 0.0001 ? "neutral" : finite(value) > 0 ? "positive" : "negative";
  const normalizeView = value => VIEW_ALIASES[String(value || "").toLowerCase()] || null;
  const state = { view: "today", family: "combined", regime: null, rendering: false };

  function urlState() {
    const url = new URL(window.location.href);
    const market = M()?.MARKETS?.[url.searchParams.get("market")] ? url.searchParams.get("market") : null;
    const horizon = HORIZONS.includes(url.searchParams.get("horizon")) ? url.searchParams.get("horizon") : null;
    const view = normalizeView(url.searchParams.get("view"));
    const family = MODEL_FAMILIES.includes(url.searchParams.get("model")) ? url.searchParams.get("model") : null;
    return { market, horizon, view, family };
  }

  function writeUrl({ push = false } = {}) {
    const url = new URL(window.location.href);
    url.searchParams.set("market", M().state.market);
    url.searchParams.set("horizon", M().state.horizon);
    url.searchParams.set("view", state.view);
    url.searchParams.set("model", state.family);
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

  function datasetFor(market = M().state.market) {
    const datasets = state.regime?.markets?.[market]?.datasets || {};
    return datasets.tff || datasets.disaggregated || Object.values(datasets)[0] || null;
  }
  function familyFor(market = M().state.market, family = state.family) { return datasetFor(market)?.families?.[family] || null; }
  function currentRegime(market = M().state.market) { return datasetFor(market)?.current || null; }

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
      family,
      expected: finite(metric.mean_return_pct),
      median: finite(metric.median_return_pct),
      probability: finite(metric.hit_rate_pct),
      baseline: finite(metric.baseline_return_pct),
      excess: finite(metric.excess_return_pct),
      observations: finite(metric.observations ?? model.sample_size),
      confidence: metric.confidence || "n/a",
      matchRule: model.match_rule || "",
      current: currentRegime(market)
    };
  }

  function liveForecast(market = M().state.market, horizon = M().state.horizon) {
    const rows = (M().state.live?.current_predictions || []).filter(row => row?.market === market);
    const combined = rows.filter(row => row?.model_family === "combined");
    const model = (combined.length ? combined : rows).at(-1) || null;
    if (!model) return null;
    const expected = finite(model[`expected_${horizon}_return_pct`] ?? model[`expected_${horizon}_return`] ?? model?.historical_horizons?.[horizon]?.expected_return_pct);
    const probability = finite(model[`probability_positive_${horizon}`] ?? model[`probability_positive_${horizon}_pct`] ?? model?.historical_horizons?.[horizon]?.probability_positive);
    if (expected === null && probability === null) return null;
    return { model, expected, probability, confidence: model.confidence || model?.historical_horizons?.[horizon]?.confidence || "n/a" };
  }

  function directionalRanked(summary = M().summary()) { return (summary.ranked || []).filter(item => DIRECTIONAL_ROLES.has(item?.row?.actor_role)); }
  function contextRanked(summary = M().summary()) { return (summary.ranked || []).filter(item => !DIRECTIONAL_ROLES.has(item?.row?.actor_role)); }
  function strongestDirectional(summary = M().summary()) { return directionalRanked(summary)[0] || null; }
  function gradeFor(item) { return item ? M().evidenceGrade(M().evidenceStatus(item.row, item.metric)) : null; }
  function gradeText(grade) {
    if (!grade) return "No evidence";
    return `${grade.grade} — ${grade.grade === "A" ? "STRONG" : grade.grade === "B" ? "SUPPORTED" : grade.grade === "C" ? "TENTATIVE" : "RESEARCH ONLY"}`;
  }
  function nearestWatch(market = M().state.market) { return M().thresholdWatchlist(50).find(item => item.market === market && DIRECTIONAL_ROLES.has(item?.row?.actor_role)) || null; }

  function evidenceDrawer(item) {
    if (!item) return "";
    const { row, metric } = item;
    const status = M().evidenceStatus(row, metric);
    const rawChange = finite(row.raw_weekly_change ?? row.weekly_change ?? row.net_change ?? row.change_value ?? row.delta_net_contracts);
    const discoveryN = finite(metric.discovery_n ?? row.discovery_n);
    const holdoutN = finite(metric.holdout_n ?? row.holdout_n);
    const positiveDiff = finite(metric.positive_rate_diff_pp ?? metric.positive_rate_excess_pp);
    const registry = M().state.registry || {};
    const active = M().state.active || {};
    const lookahead = registry.lookahead_safe ?? active.lookahead_safe ?? true;
    const era = metric.era_consistency ?? metric.era_stability ?? "n/a";
    const overlap = metric.overlap_correction ?? metric.overlap_method ?? "n/a";
    const modelVersion = registry.model_version || active.model_version || state.regime?.model_version || "n/a";
    return `<details class="decision-why"><summary>Why this edge? <span>→</span></summary><div class="decision-why-grid">
      <div><span>Current percentile</span><strong>${percentile(row.current_change_percentile ?? row.change_magnitude_percentile)}</strong></div>
      <div><span>Raw weekly change</span><strong>${rawChange === null ? "n/a" : signed(rawChange, 0)}</strong></div>
      <div><span>Frozen threshold</span><strong>P${esc(row.selected_threshold ?? "n/a")}</strong></div>
      <div><span>Discovery sample</span><strong>${integer(discoveryN)}</strong></div>
      <div><span>Holdout sample</span><strong>${integer(holdoutN)}</strong></div>
      <div><span>Independent N</span><strong>${integer(metric.independent_n ?? metric.n)}</strong></div>
      <div><span>Conditional mean</span><strong>${signed(metric.conditional_return_pct, 2, "%")}</strong></div>
      <div><span>Baseline mean</span><strong>${signed(metric.baseline_return_pct, 2, "%")}</strong></div>
      <div><span>Excess return</span><strong>${signed(metric.excess_vs_baseline_pp, 2, " pp")}</strong></div>
      <div><span>Positive-rate diff.</span><strong>${positiveDiff === null ? "n/a" : signed(positiveDiff, 1, " pp")}</strong></div>
      <div><span>Era consistency</span><strong>${esc(era)}</strong></div>
      <div><span>Overlap correction</span><strong>${esc(overlap)}</strong></div>
      <div><span>Evidence class</span><strong>${esc(status)}</strong></div>
      <div><span>Model version</span><strong>${esc(modelVersion)}</strong></div>
      <div><span>Lookahead safe</span><strong>${lookahead ? "YES" : "NO"}</strong></div>
    </div></details>`;
  }

  function horizonControls() {
    return `<div class="decision-horizons" role="group" aria-label="Selected forward horizon">${HORIZONS.map(h => `<button type="button" data-decision-horizon="${h}" class="${M().state.horizon === h ? "active" : ""}" aria-pressed="${M().state.horizon === h}">${horizonLabel(h)}</button>`).join("")}</div>`;
  }
  function modelControls() {
    const labels = { combined: "Combined", cot: "COT only", macro: "Macro only" };
    return `<div class="decision-horizons decision-model-family" role="group" aria-label="Current model family">${MODEL_FAMILIES.map(family => `<button type="button" data-model-family="${family}" class="${state.family === family ? "active" : ""}" aria-pressed="${state.family === family}">${labels[family]}</button>`).join("")}</div>`;
  }
  function navigation() {
    const labels = { today: "Today", research: "Research", live: "Live Record" };
    return `<div class="decision-nav"><nav aria-label="Dashboard sections">${VIEWS.map(v => `<button type="button" data-decision-view="${v}" class="${state.view === v ? "active" : ""}" aria-current="${state.view === v ? "page" : "false"}">${labels[v]}</button>`).join("")}</nav>${state.view === "today" ? horizonControls() : ""}</div>`;
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
    meta.innerHTML = `<span>Report <b>${esc(dates.report || "n/a")}</b></span><span>Released <b>${esc(dates.release || "n/a")}</b></span><span class="ledger ${integrity === "PASS" ? "pass" : ""}">${esc(integrity)}</span>`;
    document.documentElement.classList.add("decision-first-ready");
  }

  function flowInterpretation(row) {
    const longDelta = finite(row?.delta_long_contracts);
    const shortDelta = finite(row?.delta_short_contracts);
    if (longDelta === null || shortDelta === null) return "Weekly side changes unavailable";
    if (longDelta > 0 && shortDelta < 0) return "Long add + short cover";
    if (longDelta > 0 && shortDelta > 0) return "Long add + shorts add";
    if (longDelta < 0 && shortDelta < 0) return "Long liquidation + short cover";
    if (longDelta < 0 && shortDelta > 0) return "Long liquidation + shorts add";
    if (longDelta > 0) return "Long add";
    if (longDelta < 0) return "Long liquidation";
    if (shortDelta > 0) return "Shorts add";
    if (shortDelta < 0) return "Short cover";
    return "Little gross positioning change";
  }

  function latestCotChanges(cot = cotScoreRead()) {
    const rows = [...M().currentRows(M().state.market)].sort((a, b) => {
      const role = (M().ROLE_ORDER?.[a.actor_role] ?? 9) - (M().ROLE_ORDER?.[b.actor_role] ?? 9);
      if (role) return role;
      return Math.abs(finite(b.delta_net_contracts) || 0) - Math.abs(finite(a.delta_net_contracts) || 0);
    });
    const dates = M().reportDates();
    if (!rows.length) {
      return `<section class="decision-latest-cot"><div class="decision-block-head"><div><span class="decision-kicker">LATEST COT POSITION CHANGES</span><h3>No current actor state available</h3></div></div></section>`;
    }
    const biggest = [...rows].sort((a, b) => Math.abs(finite(b.delta_net_contracts) || 0) - Math.abs(finite(a.delta_net_contracts) || 0))[0];
    const scoreText = cot.score === null ? "n/a" : cot.score.toFixed(1);
    return `<section class="decision-latest-cot" data-decision-surface="latest-cot-changes">
      <div class="decision-block-head"><div><span class="decision-kicker">LATEST COT POSITION CHANGES</span><h3>Newest released actor repositioning</h3><p>Positions as of <b>${esc(dates.report || "n/a")}</b> · released <b>${esc(dates.release || "n/a")}</b> · weekly deltas are versus the prior COT report.</p></div><div class="decision-biggest-move"><span>Largest net move</span><strong class="${toneForNumber(biggest?.delta_net_contracts)}">${esc(biggest?.actor_label || "n/a")} · ${signed(biggest?.delta_net_contracts, 0)}</strong><small>${percentile(biggest?.change_magnitude_percentile)} weekly magnitude</small></div></div>
      <div class="decision-cot-change-table" role="table" aria-label="Latest COT actor position changes">
        <div class="decision-cot-change-head" role="row"><span>Actor</span><span>Net position</span><span>Weekly Δ</span><span>Long Δ</span><span>Short Δ</span><span>Position %ile</span><span>Weekly %ile</span></div>
        ${rows.map(row => `<article class="decision-cot-change-row" role="row"><div><strong>${esc(row.actor_label)}</strong><small>${esc(M().ROLE_LABEL?.[row.actor_role] || row.actor_role || "Actor")} · ${esc(flowInterpretation(row))}</small></div><strong>${signed(row.net_contracts, 0)}</strong><strong class="decision-weekly-change ${toneForNumber(row.delta_net_contracts)}">${signed(row.delta_net_contracts, 0)}</strong><span class="${toneForNumber(row.delta_long_contracts)}">${signed(row.delta_long_contracts, 0)}</span><span class="${toneForNumber(-finite(row.delta_short_contracts))}">${signed(row.delta_short_contracts, 0)}</span><span>${percentile(row.position_percentile)}</span><span>${percentile(row.change_magnitude_percentile)}</span></article>`).join("")}
      </div>
      <div class="decision-cot-score-bridge"><div><span>Governed COT score</span><strong class="${cot.tone}">${scoreText} / 100</strong></div><div><span>4W score change</span><strong class="${toneForNumber(cot.delta4w)}">${signed(cot.delta4w, 1)}</strong></div><div><span>Interpretation</span><strong>${esc(cot.label)}</strong><small>Raw actor changes describe the release; historical edges remain separately governed.</small></div></div>
    </section>`;
  }

  function currentModelCard() {
    const estimate = modelEstimate();
    if (!estimate) return `<div class="decision-semantic prospective unavailable"><span>CURRENT MODEL ESTIMATE</span><strong>n/a</strong><small>No ${esc(state.family)} regime estimate is available for ${horizonLabel(M().state.horizon)}.</small>${modelControls()}</div>`;
    return `<div class="decision-semantic prospective"><span>CURRENT MODEL ESTIMATE · ${esc(state.family.toUpperCase())}</span><strong>${signed(estimate.expected, 2, "%")}</strong><small>P(positive) ${pctProbability(estimate.probability)} · baseline ${signed(estimate.baseline, 2, "%")} · excess ${signed(estimate.excess, 2, " pp")} · N ${integer(estimate.observations)} · Confidence ${esc(estimate.confidence)}</small><small>${esc(estimate.matchRule)}</small>${modelControls()}</div>`;
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
    const monthly = [["2026-08-21", "AUG OPEX"], ["2026-09-18", "SEP QUARTERLY"], ["2026-10-16", "OCT OPEX"], ["2026-11-20", "NOV OPEX"], ["2026-12-18", "DEC QUARTERLY"], ["2027-01-15", "JAN OPEX"]];
    const vix = [["2026-08-19", "VIX AUG"], ["2026-09-16", "VIX SEP"], ["2026-10-21", "VIX OCT"], ["2026-11-18", "VIX NOV"], ["2026-12-16", "VIX DEC"], ["2027-01-20", "VIX JAN"]];
    const now = ymd(today);
    const nextMonthly = monthly.find(([date]) => date >= now) || monthly.at(-1);
    const nextVix = vix.find(([date]) => date >= now) || vix.at(-1);
    const fmt = date => new Date(`${date}T12:00:00Z`).toLocaleDateString(undefined, { month: "short", day: "numeric" });
    return `<div class="decision-invalidation decision-expiries"><strong>Important expiries</strong><span>Next index OPEX: <b>${esc(nextMonthly[1])} · ${fmt(nextMonthly[0])}</b> · Next VIX expiry: <b>${esc(nextVix[1])} · ${fmt(nextVix[0])}</b>. Quarterly expiries are highlighted because index/futures/options positioning can rebalance more heavily around them.</span></div>`;
  }

  function overview(summary) {
    const strongest = strongestDirectional(summary);
    const grade = gradeFor(strongest);
    const cot = cotScoreRead();
    const alignment = M().layerAlignment();
    const watch = nearestWatch();
    const condition = strongest ? `${strongest.row.actor_label} · ${percentile(strongest.row.current_change_percentile ?? strongest.row.change_magnitude_percentile)} ${esc(strongest.row.direction)} · trigger P${esc(strongest.row.selected_threshold)}` : watch ? `Nearest directional trigger: ${watch.row.actor_label} ${percentile(watch.row.change_magnitude_percentile)} → P${Math.round(watch.edge.threshold)} · ${watch.distance.toFixed(1)}P away` : "No active directional actor threshold.";
    const scoreText = cot.score === null ? "n/a" : cot.score.toFixed(1);
    return `<section class="decision-overview" data-decision-surface="today-overview">
      <div class="decision-current"><div class="decision-title-row"><div><span class="decision-kicker">${esc(M().MARKETS[M().state.market])}</span><h2 class="${cot.tone}">${cot.label} COT POSITIONING</h2><p>Governed COT score <b>${scoreText}</b> / 100 · 4W score change ${signed(cot.delta4w, 1)}. ${condition}</p></div><div class="decision-grade ${grade?.tone || "weak"}"><span>Directional edge evidence</span><strong>${grade ? gradeText(grade) : "D — NO ACTIVE DIRECTIONAL EDGE"}</strong><small>${strongest ? `N ${integer(strongest.metric.independent_n ?? strongest.metric.n)}` : "Context actors excluded from headline"}</small></div></div>
        ${latestCotChanges(cot)}
        <div class="decision-semantics">${currentModelCard()}${liveProspectiveCard()}${historicalEdgeCard(strongest)}</div>
        <div class="decision-driver-strip"><div class="${cot.tone}"><span>COT SCORE</span><strong>${cot.label}</strong><small>${scoreText} / 100</small></div><div class="${alignment.macro.tone}"><span>MACRO</span><strong>${esc(alignment.macro.label)}</strong><small>${alignment.macro.score === null ? "score unavailable" : `${Math.round(alignment.macro.score)} / 100`}</small></div><div class="${alignment.sentiment.tone}"><span>SENTIMENT</span><strong>${esc(alignment.sentiment.label)}</strong><small>${alignment.sentiment.index === null ? "not available" : `${Math.round(alignment.sentiment.index)} / 100`}</small></div><div class="neutral"><span>PRICE CONFIRM</span><strong>NOT GOVERNED</strong><small>no dedicated confirmation field</small></div></div>${expiryStrip()}
      </div>
      ${strongestPanel(strongest)}
      <aside class="decision-scanner">${opportunityScanner()}</aside>
      <div class="decision-invalidation">${invalidation(strongest, summary)}</div>
    </section>`;
  }

  function strongestPanel(strongest) {
    if (!strongest) {
      const watch = nearestWatch();
      return `<section class="decision-strongest no-edge"><div><span class="decision-kicker">STRONGEST CURRENT DIRECTIONAL EDGE</span><h3>NO ACTIVE DIRECTIONAL COT EDGE</h3><p>Context-only actors remain research evidence and cannot determine the market read.</p></div>${watch ? watchCard(watch, true) : "<small>No governed directional threshold is currently close enough to highlight.</small>"}</section>`;
    }
    const { row, metric } = strongest;
    const grade = gradeFor(strongest);
    const dir = M().edgeDirection(metric);
    return `<section class="decision-strongest"><div class="decision-block-head"><div><span class="decision-kicker">STRONGEST CURRENT DIRECTIONAL EDGE</span><h3>${esc(row.actor_label)} · ${percentile(row.current_change_percentile ?? row.change_magnitude_percentile)} ${esc(row.direction)}</h3></div><span class="decision-direction ${dir.tone}">${dir.label}</span></div><div class="decision-edge-metrics"><div><span>Trigger</span><strong>P${esc(row.selected_threshold)}</strong></div><div><span>Historical conditional</span><strong>${signed(metric.conditional_return_pct, 2, "%")}</strong></div><div><span>Normal return</span><strong>${signed(metric.baseline_return_pct, 2, "%")}</strong></div><div><span>Uplift vs normal</span><strong class="${dir.tone}">${signed(metric.excess_vs_baseline_pp, 2, " pp")}</strong></div><div><span>Independent N</span><strong>${integer(metric.independent_n ?? metric.n)}</strong></div><div><span>Evidence</span><strong>${gradeText(grade)}</strong></div></div>${evidenceDrawer(strongest)}</section>`;
  }

  function opportunityScanner() {
    const rows = M().MARKET_ORDER.map(market => {
      const ranked = M().rankedEdges(M().state.horizon, market).filter(item => DIRECTIONAL_ROLES.has(item?.row?.actor_role));
      const top = ranked[0] || null;
      const dir = top ? M().edgeDirection(top.metric) : { tone: "neutral", label: "—" };
      return { market, top, dir, grade: gradeFor(top) };
    }).sort((a, b) => Boolean(b.top) - Boolean(a.top) || Math.abs(finite(b.top?.metric?.excess_vs_baseline_pp) || 0) - Math.abs(finite(a.top?.metric?.excess_vs_baseline_pp) || 0));
    return `<div class="decision-block-head"><div><span class="decision-kicker">OPPORTUNITY SCANNER</span><h3>Directional markets with active edge</h3></div></div><div class="decision-scanner-list">${rows.map(item => `<button type="button" data-decision-market="${item.market}" class="${item.market === M().state.market ? "active" : ""}"><span>${esc(M().MARKETS[item.market])}</span><strong class="${item.dir.tone}">${item.top ? signed(item.top.metric.excess_vs_baseline_pp, 2, " pp") : "No edge"}</strong><small>${item.grade ? item.grade.grade : "—"}</small></button>`).join("")}</div>`;
  }

  function edgeRow(item) {
    const { row, metric } = item;
    const dir = M().edgeDirection(metric);
    const grade = gradeFor(item);
    return `<article class="decision-edge-row"><div><strong>${esc(row.actor_label)}</strong><small>${percentile(row.current_change_percentile ?? row.change_magnitude_percentile)} ${esc(row.direction)} · trigger P${esc(row.selected_threshold)}</small></div><span class="decision-direction ${dir.tone}">${dir.label}</span><div><span>Historical result</span><strong>${signed(metric.conditional_return_pct, 2, "%")}</strong></div><div><span>Normal</span><strong>${signed(metric.baseline_return_pct, 2, "%")}</strong></div><div><span>Uplift</span><strong class="${dir.tone}">${signed(metric.excess_vs_baseline_pp, 2, " pp")}</strong></div><div><span>Evidence</span><strong>${grade?.grade || "D"}</strong><small>N ${integer(metric.independent_n ?? metric.n)}</small></div>${evidenceDrawer(item)}</article>`;
  }

  function watchCard(item, compact = false) {
    const current = finite(item.row.change_magnitude_percentile) ?? 0;
    const trigger = finite(item.edge.threshold) ?? 100;
    const width = Math.max(0, Math.min(100, trigger ? current / trigger * 100 : 0));
    return `<article class="decision-watch ${compact ? "compact" : ""}"><div><strong>${esc(item.row.actor_label)} ${esc(item.row.direction)}</strong><small>Current ${percentile(current)} · trigger P${Math.round(trigger)} · ${item.distance.toFixed(1)} percentile points away</small></div><div class="decision-progress" aria-label="Current percentile ${Math.round(current)} toward trigger ${Math.round(trigger)}"><i style="width:${width.toFixed(1)}%"></i><b style="left:${Math.max(0, Math.min(100, trigger))}%"></b></div><div class="${item.direction.tone}"><span>If triggered</span><strong>${signed(item.edge.best_holdout_edge_pp, 2, " pp")}</strong><small>${horizonLabel(item.edge.best_horizon)} historical uplift · Evidence ${item.grade.grade}</small></div></article>`;
  }

  function comingEdge() {
    const watches = M().thresholdWatchlist(24).filter(item => item.market === M().state.market && DIRECTIONAL_ROLES.has(item?.row?.actor_role)).slice(0, 4);
    return `<section class="decision-view-panel decision-coming-edge" data-decision-surface="coming-edge"><div class="decision-block-head"><div><span class="decision-kicker">COMING EDGE</span><h2>Distance to governed directional trigger</h2><p>These are threshold watches only. They become active historical edges only after a future COT release crosses a frozen validation threshold.</p></div><span class="decision-condition-label">Conditional watch — not a prediction</span></div>${watches.length ? `<div class="decision-watch-list">${watches.map(item => watchCard(item)).join("")}</div>` : `<div class="decision-empty"><span>No validated directional threshold is close enough to form a governed watch.</span></div>`}</section>`;
  }

  function weekPath(summary) {
    const strongest = strongestDirectional(summary);
    if (!strongest) return `<section class="decision-view-panel" data-decision-surface="week-path"><span class="decision-kicker">THIS WEEK — CUMULATIVE HISTORICAL PATH</span><h2>No governed directional weekday path</h2><div class="decision-empty"><span>A weekday path appears only when a directional threshold is active.</span></div></section>`;
    const points = WEEKDAYS.map(([key, label]) => ({ label, metric: M().metricFor(strongest.row, key) })).filter(point => point.metric);
    const grade = gradeFor(strongest);
    return `<section class="decision-view-panel" data-decision-surface="week-path"><div class="decision-block-head"><div><span class="decision-kicker">THIS WEEK — CUMULATIVE HISTORICAL PATH</span><h2>${esc(strongest.row.actor_label)} · release-corrected weekday path</h2><p>Based on previous Tuesday COT positioning; publicly available Friday. Returns are cumulative to each weekday.</p></div><span class="decision-evidence-badge">${gradeText(grade)}</span></div><div class="decision-week-path">${points.map((point, index) => `<article><span>${esc(point.label)}</span><strong>${signed(point.metric.conditional_return_pct, 2, "%")}</strong><small>${finite(point.metric.positive_rate_pct) === null ? "" : `${Math.round(point.metric.positive_rate_pct)}% + · `}edge ${signed(point.metric.excess_vs_baseline_pp, 2, " pp")}</small>${index < points.length - 1 ? "<i>→</i>" : ""}</article>`).join("")}</div>${forwardHistory(strongest)}</section>`;
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

  let macroEffectivenessData = null;
  async function loadMacroEffectiveness() {
    if (macroEffectivenessData) return macroEffectivenessData;
    try {
      const v = window.__COT_RUNTIME_VERSION__ || Date.now();
      const res = await fetch(`worldclass/macro-effectiveness.json?v=${encodeURIComponent(v)}`);
      if (res.ok) macroEffectivenessData = await res.json();
    } catch (_) {}
    return macroEffectivenessData;
  }

  function macroEffectivenessSection() {
    const data = macroEffectivenessData;
    if (!data || !data.aggregate) return "";
    const horizons = ["1W", "2W", "4W", "13W", "26W"];
    const findRow = (market, h) => (data.aggregate || []).find(r => r.target === `${market}_${h}`) || {};
    const rows = horizons.map(h => {
      const spx = findRow("SPX", h);
      const nq = findRow("NQ", h);
      const fmtRho = v => v === undefined || v === null ? "n/a" : (v >= 0 ? `+${Number(v).toFixed(3)}` : Number(v).toFixed(3));
      const fmtP = v => v === undefined || v === null ? "n/a" : Number(v).toFixed(3);
      const fmtOos = v => v === undefined || v === null ? "n/a" : `${(Number(v) * 100).toFixed(1)}%`;
      return `<tr><td>${h}</td><td class="${(spx.spearman || 0) >= 0 ? 'positive' : 'negative'}">${fmtRho(spx.spearman)}</td><td>${fmtP(spx.hac_p)}</td><td>${fmtOos(spx.oos_r2)}</td><td class="${(nq.spearman || 0) >= 0 ? 'positive' : 'negative'}">${fmtRho(nq.spearman)}</td><td>${fmtP(nq.hac_p)}</td><td>${fmtOos(nq.oos_r2)}</td></tr>`;
    }).join("");
    return `<div class="macro-research-section"><div class="decision-block-head compact"><div><span class="decision-kicker">03 · AGGREGATE SCORE BACKTEST</span><h3>Does a higher liquidity score predict higher future returns?</h3><p>Weekly observations, 2023-06 to 2026-08. ρ = rank correlation; HAC p adjusts for serial dependence; OOS R² tests chronological out-of-sample prediction.</p></div><span class="decision-evidence-badge">0% PRODUCTION WEIGHT</span></div><div class="macro-effectiveness-wrap"><table class="macro-effectiveness-table"><thead><tr><th rowspan="2">Horizon</th><th colspan="3">S&P 500</th><th colspan="3">Nasdaq-100</th></tr><tr><th>ρ</th><th>HAC p</th><th>OOS R²</th><th>ρ</th><th>HAC p</th><th>OOS R²</th></tr></thead><tbody>${rows}</tbody></table></div><p class="decision-footnote">No aggregate row passes the robustness standard. A positive return in a high-score regime is not enough; the relationship must survive dependence controls, eras and out-of-sample testing.</p></div>`;
  }

  function researchView(summary) {
    const directional = directionalRanked(summary);
    const context = contextRanked(summary);
    const strongest = strongestDirectional(summary);
    const alignment = M().layerAlignment();
    const dataset = datasetFor();
    const registry = M().state.registry || {};
    const active = M().state.active || {};
    return `<section class="decision-view-panel decision-research" data-decision-surface="research"><div class="decision-block-head"><div><span class="decision-kicker">RESEARCH</span><h2>Evidence behind the current read</h2><p>Deep evidence stays in one self-contained view. The legacy dashboard is not reopened or scrolled into view.</p></div></div>
      <details class="decision-research-group" open><summary>Positioning & actors <span>${directional.length + context.length} active conditions</span></summary><div class="decision-research-body"><div class="decision-edge-list">${directional.length ? directional.map(edgeRow).join("") : `<div class="decision-empty"><span>No active directional threshold.</span></div>`}</div>${context.length ? `<details class="decision-context"><summary>+ ${context.length} contextual signal${context.length === 1 ? "" : "s"}</summary><div class="decision-edge-list">${context.map(edgeRow).join("")}</div></details>` : ""}</div></details>
      <details class="decision-research-group"><summary>Backtests & regimes <span>${horizonLabel(M().state.horizon)} selected</span></summary><div class="decision-research-body">${strongest ? forwardHistory(strongest) : `<div class="decision-empty"><span>No active directional edge is available for forward conditional evidence.</span></div>`}<div class="decision-research-meta"><div><span>Current COT regime</span><strong>${esc(currentRegime()?.cot_state || "n/a")}</strong></div><div><span>Current macro regime</span><strong>${esc(currentRegime()?.macro_state || "n/a")}</strong></div><div><span>Combined regime</span><strong>${esc(currentRegime()?.combined_state || "n/a")}</strong></div><div><span>Historical signal count</span><strong>${integer(dataset?.historical_signal_count)}</strong></div></div></div></details>
      <details class="decision-research-group"><summary>Macro evidence <span>context / risk budget</span></summary><div class="decision-research-body"><div class="decision-research-meta"><div><span>Macro state</span><strong class="${alignment.macro.tone}">${esc(alignment.macro.label)}</strong></div><div><span>Macro score</span><strong>${alignment.macro.score === null ? "n/a" : `${Math.round(alignment.macro.score)} / 100`}</strong></div><div><span>Sentiment</span><strong class="${alignment.sentiment.tone}">${esc(alignment.sentiment.label)}</strong></div><div><span>Layer alignment</span><strong class="${alignment.tone}">${esc(alignment.label)}</strong></div></div><p>${esc(alignment.note)}</p>${macroEffectivenessSection()}</div></details>
      <details class="decision-research-group"><summary>Methodology & provenance <span>audit trail</span></summary><div class="decision-research-body"><div class="decision-research-meta"><div><span>Model version</span><strong>${esc(registry.model_version || active.model_version || state.regime?.model_version || "n/a")}</strong></div><div><span>Research generation</span><strong>${esc(M().state.current?.research_generation || state.regime?.research_generation || "n/a")}</strong></div><div><span>COT lookahead-safe</span><strong>${dataset?.methodology?.lookahead_safe_cot === false ? "NO" : "YES"}</strong></div><div><span>Macro vintage-safe</span><strong>${dataset?.methodology?.macro_vintage_safe === true ? "YES" : "NO"}</strong></div></div><p>${esc(dataset?.methodology?.cot_release_anchor || "COT availability is governed by the canonical CFTC release calendar.")}</p></div></details>
    </section>`;
  }

  function liveIntro() {
    const live = M().state.live || {};
    const integrity = String(live?.ledger?.integrity || "UNKNOWN").toUpperCase();
    return `<section class="decision-view-panel" data-decision-surface="live"><span class="decision-kicker">LIVE RECORD</span><h2>Frozen prospective forecasts and realized outcomes</h2><div class="decision-live-summary"><div><span>Ledger</span><strong>${esc(integrity)}</strong></div><div><span>Forecasts</span><strong>${integer(live.forecast_count || 0)}</strong></div><div><span>Matured signals</span><strong>${integer(live.matured_signal_count || 0)}</strong></div><div><span>Historical backfill</span><strong>DISALLOWED</strong></div></div><p>Only forecasts recorded before outcomes count as live evidence. Current model estimates on Today are not retroactively entered into the live ledger.</p></section>`;
  }

  function today(summary) { return `${overview(summary)}${weekPath(summary)}${comingEdge()}`; }

  function setView(next, { push = true } = {}) {
    state.view = normalizeView(next) || "today";
    document.documentElement.dataset.cotDecisionView = state.view;
    writeUrl({ push });
    render();
  }

  function selectMarket(market, { push = true } = {}) {
    if (!M().MARKETS[market]) return;
    const button = document.querySelector(`#instrumentTabs [data-market="${market}"]`);
    if (button && market !== M().selectedMarket()) button.click();
    M().state.market = market;
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

  function render() {
    if (state.rendering || !M()) return;
    state.rendering = true;
    try {
      const root = mount();
      if (!M().state.current || !M().state.active || !M().state.registry) {
        root.innerHTML = `<div class="decision-loading">Loading governed COT decision layer…</div>`;
        return;
      }
      M().state.market = M().selectedMarket();
      const summary = M().summary();
      headerMeta();
      document.documentElement.dataset.cotDecisionView = state.view;
      const content = state.view === "research" ? researchView(summary) : state.view === "live" ? liveIntro() : today(summary);
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
    });
  }

  function observeMarket() {
    const tabs = document.getElementById("instrumentTabs");
    tabs?.addEventListener("click", () => window.setTimeout(() => {
      const market = M().selectedMarket();
      if (market !== M().state.market) {
        M().state.market = market;
        writeUrl({ push: true });
        render();
      }
    }, 0));
  }

  function applyInitialUrl() {
    const initial = urlState();
    state.view = initial.view || "today";
    state.family = initial.family || "combined";
    M().state.horizon = initial.horizon || "1w";
    if (initial.market) {
      const button = document.querySelector(`#instrumentTabs [data-market="${initial.market}"]`);
      if (button && !button.classList.contains("active")) button.click();
      M().state.market = initial.market;
    } else {
      M().state.market = M().selectedMarket();
    }
    document.documentElement.dataset.cotDecisionView = state.view;
  }

  async function boot() {
    const root = mount();
    bind(root);
    if (!M()) throw new Error("Current Edge model missing");
    await Promise.all([M().load(), fetchRegime(), loadMacroEffectiveness()]);
    applyInitialUrl();
    render();
    observeMarket();
    window.addEventListener("popstate", () => {
      const initial = urlState();
      state.view = initial.view || "today";
      state.family = initial.family || "combined";
      M().state.horizon = initial.horizon || "1w";
      if (initial.market && initial.market !== M().selectedMarket()) document.querySelector(`#instrumentTabs [data-market="${initial.market}"]`)?.click();
      M().state.market = initial.market || M().selectedMarket();
      render();
    });
    window.addEventListener("cot:intelligence-ready", render);
    window.__COT_APP_DATA_READY__?.then(render).catch(() => {});
  }

  boot().catch(error => {
    console.error("Decision-first COT command center failed to initialize.", error);
    const root = mount();
    root.innerHTML = `<div class="decision-loading"><strong>Decision layer unavailable.</strong><span>No forecast is fabricated; underlying research data remains untouched.</span></div>`;
  });
})();
