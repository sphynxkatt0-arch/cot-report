(() => {
  "use strict";

  const M = () => window.__COT_CURRENT_EDGE_MODEL__;
  const HORIZONS = ["1w", "2w", "4w", "13w", "26w"];
  const VIEWS = ["overview", "edges", "week", "research", "live"];
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

  let view = "overview";
  let rendering = false;
  let observer = null;

  function urlState() {
    const url = new URL(window.location.href);
    const market = M()?.MARKETS?.[url.searchParams.get("market")] ? url.searchParams.get("market") : null;
    const horizon = HORIZONS.includes(url.searchParams.get("horizon")) ? url.searchParams.get("horizon") : null;
    const nextView = VIEWS.includes(url.searchParams.get("view")) ? url.searchParams.get("view") : null;
    return { market, horizon, view: nextView };
  }

  function writeUrl({ push = false } = {}) {
    const url = new URL(window.location.href);
    url.searchParams.set("market", M().state.market);
    url.searchParams.set("horizon", M().state.horizon);
    url.searchParams.set("view", view);
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

  function setView(next, { push = true } = {}) {
    view = VIEWS.includes(next) ? next : "overview";
    document.documentElement.dataset.cotDecisionView = view;
    writeUrl({ push });
    render();
    if (view === "research") window.setTimeout(() => document.getElementById("cotIntelligence")?.scrollIntoView({ block: "start", behavior: "smooth" }), 0);
    if (view === "live") window.setTimeout(() => document.getElementById("liveTrackRecordPanel")?.scrollIntoView({ block: "start", behavior: "smooth" }), 0);
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

  function forecastFor(model, horizon) {
    if (!model) return null;
    const expected = finite(model[`expected_${horizon}_return_pct`]);
    const probability = finite(model[`probability_positive_${horizon}`] ?? model[`probability_positive_${horizon}_pct`]);
    if (expected === null && probability === null) return null;
    return { expected, probability, confidence: model.confidence || "n/a", status: model.status || "OPEN" };
  }

  function gradeFor(item) {
    return item ? M().evidenceGrade(M().evidenceStatus(item.row, item.metric)) : null;
  }

  function gradeText(grade) {
    if (!grade) return "No evidence";
    return `${grade.grade} — ${grade.grade === "A" ? "STRONG" : grade.grade === "B" ? "SUPPORTED" : grade.grade === "C" ? "TENTATIVE" : "RESEARCH ONLY"}`;
  }

  function cotLayer(summary) {
    if (!summary.strongest) return { label: "NO ACTIVE EDGE", tone: "neutral", sub: "flows inside governed thresholds" };
    const dir = M().edgeDirection(summary.strongest.metric);
    return {
      label: dir.label,
      tone: dir.tone,
      sub: `${summary.strongest.row.actor_label} · ${signed(summary.strongest.metric.excess_vs_baseline_pp, 2, " pp")} uplift`
    };
  }

  function environment(summary) {
    const alignment = M().layerAlignment();
    const cot = cotLayer(summary);
    return [
      { name: "COT", label: cot.label, tone: cot.tone, sub: cot.sub },
      { name: "MACRO", label: alignment.macro.label, tone: alignment.macro.tone, sub: alignment.macro.score === null ? "score unavailable" : `${Math.round(alignment.macro.score)} / 100` },
      { name: "SENTIMENT", label: alignment.sentiment.label, tone: alignment.sentiment.tone, sub: alignment.sentiment.index === null ? "not available" : `${Math.round(alignment.sentiment.index)} / 100` },
      { name: "PRICE CONFIRM", label: "NOT GOVERNED", tone: "neutral", sub: "no dedicated confirmation field" }
    ];
  }

  function nearestWatch(market = M().state.market) {
    return M().thresholdWatchlist(50).find(item => item.market === market) || null;
  }

  function evidenceDrawer(item) {
    if (!item) return "";
    const { row, metric } = item;
    const status = M().evidenceStatus(row, metric);
    const rawChange = finite(row.raw_weekly_change ?? row.weekly_change ?? row.net_change ?? row.change_value);
    const discoveryN = finite(metric.discovery_n ?? row.discovery_n);
    const holdoutN = finite(metric.holdout_n ?? row.holdout_n);
    const positiveDiff = finite(metric.positive_rate_diff_pp ?? metric.positive_rate_excess_pp);
    const registry = M().state.registry || {};
    const active = M().state.active || {};
    const lookahead = registry.lookahead_safe ?? active.lookahead_safe ?? true;
    const era = metric.era_consistency ?? metric.era_stability ?? "n/a";
    const overlap = metric.overlap_correction ?? metric.overlap_method ?? "n/a";
    const modelVersion = registry.model_version || active.model_version || registry.research_generation || active.research_generation || "n/a";
    return `<details class="decision-why">
      <summary>Why this edge? <span>→</span></summary>
      <div class="decision-why-grid">
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
        <div><span>Research version</span><strong>${esc(modelVersion)}</strong></div>
        <div><span>Lookahead safe</span><strong>${lookahead ? "YES" : "NO"}</strong></div>
      </div>
    </details>`;
  }

  function horizonControls() {
    return `<div class="decision-horizons" role="group" aria-label="Selected forward horizon">${HORIZONS.map(h => `<button type="button" data-decision-horizon="${h}" class="${M().state.horizon === h ? "active" : ""}" aria-pressed="${M().state.horizon === h}">${horizonLabel(h)}</button>`).join("")}</div>`;
  }

  function navigation() {
    const labels = { overview: "Overview", edges: "Active Edges", week: "Week Path", research: "Research", live: "Live Record" };
    return `<div class="decision-nav">
      <nav aria-label="Dashboard sections">${VIEWS.map(v => `<button type="button" data-decision-view="${v}" class="${view === v ? "active" : ""}" aria-current="${view === v ? "page" : "false"}">${labels[v]}</button>`).join("")}</nav>
      ${horizonControls()}
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
    meta.innerHTML = `<span>Report <b>${esc(dates.report || "n/a")}</b></span><span>Released <b>${esc(dates.release || "n/a")}</b></span><span class="ledger ${integrity === "PASS" ? "pass" : ""}">${esc(integrity)}</span>`;
    document.documentElement.classList.add("decision-first-ready");
  }

  function overview(summary) {
    const strongest = summary.strongest;
    const metric = strongest?.metric || null;
    const grade = gradeFor(strongest);
    const direction = strongest ? M().edgeDirection(metric) : { tone: "neutral", label: "NO EDGE" };
    const model = summary.model || M().corePrediction();
    const forecast = forecastFor(model, M().state.horizon);
    const env = environment(summary);
    const watch = nearestWatch();
    const forecastHtml = forecast
      ? `<div class="decision-semantic prospective"><span>PROSPECTIVE FORECAST</span><strong>${signed(forecast.expected, 2, "%")}</strong><small>Expected ${horizonLabel(M().state.horizon)} return · P(positive) ${pctProbability(forecast.probability)} · Confidence ${esc(forecast.confidence)}</small></div>`
      : `<div class="decision-semantic prospective unavailable"><span>PROSPECTIVE FORECAST</span><strong>n/a</strong><small>No governed prospective ${horizonLabel(M().state.horizon)} return is published for this model.</small></div>`;
    const historyHtml = strongest
      ? `<div class="decision-semantic historical"><span>HISTORICAL EDGE</span><strong class="${direction.tone}">${signed(metric.conditional_return_pct, 2, "%")}</strong><small>Historical conditional return · normal ${signed(metric.baseline_return_pct, 2, "%")} · <b>uplift ${signed(metric.excess_vs_baseline_pp, 2, " pp")}</b></small></div>`
      : `<div class="decision-semantic historical unavailable"><span>HISTORICAL EDGE</span><strong>NO ACTIVE COT EDGE</strong><small>Current flows are inside normal governed historical ranges.</small></div>`;
    const condition = strongest ? `${strongest.row.actor_label} · ${percentile(strongest.row.current_change_percentile)} ${esc(strongest.row.direction)} · trigger P${esc(strongest.row.selected_threshold)}` : watch ? `Nearest: ${watch.row.actor_label} ${percentile(watch.row.change_magnitude_percentile)} → trigger P${Math.round(watch.edge.threshold)} · ${watch.distance.toFixed(1)}P away` : "No validated threshold is currently active or near trigger.";
    return `<section class="decision-overview" data-decision-surface="overview">
      <div class="decision-current">
        <div class="decision-title-row">
          <div><span class="decision-kicker">${esc(M().MARKETS[M().state.market])}</span><h2>${esc(summary.label)}</h2><p>${condition}</p></div>
          <div class="decision-grade ${grade?.tone || "weak"}"><span>Evidence</span><strong>${grade ? gradeText(grade) : "D — RESEARCH ONLY"}</strong><small>${strongest ? `${M().sampleLabel(metric.independent_n ?? metric.n)} · N ${integer(metric.independent_n ?? metric.n)}` : "No active governed sample"}</small></div>
        </div>
        <div class="decision-semantics">${forecastHtml}${historyHtml}</div>
        <div class="decision-driver-strip">${env.map(item => `<div class="${item.tone}"><span>${item.name}</span><strong>${esc(item.label)}</strong><small>${esc(item.sub)}</small></div>`).join("")}</div>
      </div>
      ${strongestPanel(summary)}
      <aside class="decision-scanner">${opportunityScanner()}</aside>
      <div class="decision-invalidation">${invalidation(summary)}</div>
    </section>`;
  }

  function strongestPanel(summary) {
    const strongest = summary.strongest;
    if (!strongest) {
      const watch = nearestWatch();
      return `<section class="decision-strongest no-edge"><div><span class="decision-kicker">STRONGEST CURRENT EDGE</span><h3>NO ACTIVE COT EDGE</h3><p>Current flows are inside normal historical ranges.</p></div>${watch ? watchCard(watch, true) : "<small>No governed threshold is currently close enough to highlight.</small>"}</section>`;
    }
    const { row, metric } = strongest;
    const grade = gradeFor(strongest);
    const dir = M().edgeDirection(metric);
    return `<section class="decision-strongest">
      <div class="decision-block-head"><div><span class="decision-kicker">STRONGEST CURRENT EDGE</span><h3>${esc(row.actor_label)} · ${percentile(row.current_change_percentile)} ${esc(row.direction)}</h3></div><span class="decision-direction ${dir.tone}">${dir.label}</span></div>
      <div class="decision-edge-metrics">
        <div><span>Trigger</span><strong>P${esc(row.selected_threshold)}</strong></div>
        <div><span>Historical conditional</span><strong>${signed(metric.conditional_return_pct, 2, "%")}</strong></div>
        <div><span>Normal return</span><strong>${signed(metric.baseline_return_pct, 2, "%")}</strong></div>
        <div><span>Uplift vs normal</span><strong class="${dir.tone}">${signed(metric.excess_vs_baseline_pp, 2, " pp")}</strong></div>
        <div><span>Independent N</span><strong>${integer(metric.independent_n ?? metric.n)}</strong></div>
        <div><span>Evidence</span><strong>${gradeText(grade)}</strong></div>
      </div>
      ${evidenceDrawer(strongest)}
    </section>`;
  }

  function opportunityScanner() {
    const rows = M().MARKET_ORDER.map(market => {
      const top = M().rankedEdges(M().state.horizon, market)[0] || null;
      return { market, top, dir: top ? M().edgeDirection(top.metric) : { tone: "neutral", label: "—" }, grade: gradeFor(top) };
    }).sort((a, b) => Boolean(b.top) - Boolean(a.top) || Math.abs(finite(b.top?.metric?.excess_vs_baseline_pp) || 0) - Math.abs(finite(a.top?.metric?.excess_vs_baseline_pp) || 0));
    return `<div class="decision-block-head"><div><span class="decision-kicker">OPPORTUNITY SCANNER</span><h3>Markets with active edge</h3></div></div>
      <div class="decision-scanner-list">${rows.map(item => `<button type="button" data-decision-market="${item.market}" class="${item.market === M().state.market ? "active" : ""}">
        <span>${esc(M().MARKETS[item.market])}</span>
        <strong class="${item.dir.tone}">${item.top ? signed(item.top.metric.excess_vs_baseline_pp, 2, " pp") : "No edge"}</strong>
        <small>${item.grade ? item.grade.grade : "—"}</small>
      </button>`).join("")}</div>`;
  }

  function edgeRow(item) {
    const { row, metric } = item;
    const dir = M().edgeDirection(metric);
    const grade = gradeFor(item);
    return `<article class="decision-edge-row">
      <div><strong>${esc(row.actor_label)}</strong><small>${percentile(row.current_change_percentile)} ${esc(row.direction)} · trigger P${esc(row.selected_threshold)}</small></div>
      <span class="decision-direction ${dir.tone}">${dir.label}</span>
      <div><span>Historical result</span><strong>${signed(metric.conditional_return_pct, 2, "%")}</strong></div>
      <div><span>Normal</span><strong>${signed(metric.baseline_return_pct, 2, "%")}</strong></div>
      <div><span>Uplift</span><strong class="${dir.tone}">${signed(metric.excess_vs_baseline_pp, 2, " pp")}</strong></div>
      <div><span>Evidence</span><strong>${grade?.grade || "D"}</strong><small>N ${integer(metric.independent_n ?? metric.n)}</small></div>
      ${evidenceDrawer(item)}
    </article>`;
  }

  function activeEdges(summary) {
    const directional = summary.ranked.filter(item => ["PRIMARY_DIRECTIONAL", "SECONDARY_DIRECTIONAL"].includes(item.row.actor_role));
    const context = summary.ranked.filter(item => !["PRIMARY_DIRECTIONAL", "SECONDARY_DIRECTIONAL"].includes(item.row.actor_role));
    const watches = M().thresholdWatchlist(12).filter(item => item.market === M().state.market).slice(0, 4);
    return `<section class="decision-view-panel" data-decision-surface="edges">
      <div class="decision-block-head"><div><span class="decision-kicker">ACTIVE EDGES · ${esc(M().MARKETS[M().state.market])}</span><h2>Ranked current actor conditions</h2><p>Primary directional actors remain dominant. Historical edge = conditional return minus baseline; actors are ranked, never summed.</p></div></div>
      <div class="decision-edge-list">${directional.length ? directional.map(edgeRow).join("") : `<div class="decision-empty"><strong>NO ACTIVE DIRECTIONAL COT EDGE</strong><span>Current flows are inside normal historical ranges.</span></div>`}</div>
      ${context.length ? `<details class="decision-context"><summary>+ ${context.length} contextual signal${context.length === 1 ? "" : "s"}</summary><div class="decision-edge-list">${context.map(edgeRow).join("")}</div></details>` : ""}
      <div class="decision-watch-section"><div class="decision-block-head"><div><span class="decision-kicker">COMING EDGE</span><h3>Distance to governed trigger</h3></div><span class="decision-condition-label">Conditional watch — not a prediction</span></div>
        ${watches.length ? `<div class="decision-watch-list">${watches.map(item => watchCard(item)).join("")}</div>` : `<div class="decision-empty"><span>No validated threshold is close enough to form a governed watch for this market.</span></div>`}
      </div>
    </section>`;
  }

  function watchCard(item, compact = false) {
    const current = finite(item.row.change_magnitude_percentile) ?? 0;
    const trigger = finite(item.edge.threshold) ?? 100;
    const width = Math.max(0, Math.min(100, trigger ? current / trigger * 100 : 0));
    return `<article class="decision-watch ${compact ? "compact" : ""}">
      <div><strong>${esc(item.row.actor_label)} ${esc(item.row.direction)}</strong><small>Current ${percentile(current)} · trigger P${Math.round(trigger)} · ${item.distance.toFixed(1)} percentile points away</small></div>
      <div class="decision-progress" aria-label="Current percentile ${Math.round(current)} toward trigger ${Math.round(trigger)}"><i style="width:${width.toFixed(1)}%"></i><b style="left:${Math.max(0, Math.min(100, trigger))}%"></b></div>
      <div class="${item.direction.tone}"><span>If triggered</span><strong>${signed(item.edge.best_holdout_edge_pp, 2, " pp")}</strong><small>${horizonLabel(item.edge.best_horizon)} historical uplift · Evidence ${item.grade.grade}</small></div>
    </article>`;
  }

  function weekPath(summary) {
    const strongest = summary.strongest;
    if (!strongest) return `<section class="decision-view-panel"><span class="decision-kicker">THIS WEEK — CUMULATIVE HISTORICAL PATH</span><h2>No governed weekday path</h2><div class="decision-empty"><span>A weekday path appears only when a frozen current threshold is active.</span></div></section>`;
    const points = WEEKDAYS.map(([key, label]) => ({ label, metric: M().metricFor(strongest.row, key) })).filter(point => point.metric);
    const grade = gradeFor(strongest);
    return `<section class="decision-view-panel" data-decision-surface="week">
      <div class="decision-block-head"><div><span class="decision-kicker">THIS WEEK — CUMULATIVE HISTORICAL PATH</span><h2>${esc(strongest.row.actor_label)} · release-corrected weekday path</h2><p>Based on previous Tuesday COT positioning; publicly available Friday. Returns are cumulative to each weekday.</p></div><span class="decision-evidence-badge">${gradeText(grade)}</span></div>
      <div class="decision-week-path">${points.map((point, index) => `<article><span>${esc(point.label)}</span><strong>${signed(point.metric.conditional_return_pct, 2, "%")}</strong><small>${finite(point.metric.positive_rate_pct) === null ? "" : `${Math.round(point.metric.positive_rate_pct)}% + · `}edge ${signed(point.metric.excess_vs_baseline_pp, 2, " pp")}</small>${index < points.length - 1 ? "<i>→</i>" : ""}</article>`).join("")}</div>
      ${forwardHistory(strongest)}
    </section>`;
  }

  function forwardHistory(strongest) {
    return `<div class="decision-forward"><div class="decision-block-head"><div><span class="decision-kicker">FORWARD HORIZONS</span><h3>Historical conditional path</h3></div></div>
      <div class="decision-forward-grid">${HORIZONS.map(h => {
        const metric = M().metricFor(strongest.row, h);
        if (!metric) return `<div><span>${horizonLabel(h)}</span><strong>n/a</strong><small>No governed metric</small></div>`;
        const dir = M().edgeDirection(metric);
        return `<div><span>${horizonLabel(h)}</span><strong class="${dir.tone}">${signed(metric.conditional_return_pct, 2, "%")}</strong><small>normal ${signed(metric.baseline_return_pct, 2, "%")} · uplift ${signed(metric.excess_vs_baseline_pp, 2, " pp")} · N ${integer(metric.independent_n ?? metric.n)}</small></div>`;
      }).join("")}</div>
    </div>`;
  }

  function invalidation(summary) {
    if (!summary.strongest) return `<strong>What changes the read?</strong><span>A new release crossing a frozen actor threshold, a new prospective forecast, or a material macro/sentiment regime change.</span>`;
    const sign = M().edgeDirection(summary.strongest.metric).sign;
    const opposing = summary.ranked.find(item => M().edgeDirection(item.metric).sign === -sign);
    return `<strong>What could invalidate the thesis?</strong><span>${opposing ? `${esc(opposing.row.actor_label)} already carries an opposing ${signed(opposing.metric.excess_vs_baseline_pp, 2, " pp")} historical edge. ` : ""}The read weakens if the active threshold deactivates on the next release or independent macro/sentiment context turns decisively against it.</span>`;
  }

  function researchIntro() {
    return `<section class="decision-view-panel decision-research-intro"><span class="decision-kicker">DEEP RESEARCH</span><h2>Proof after conclusion</h2><p>Detailed charts, weekly actor changes, positioning regime, COT score, macro drivers, actor research, methodology and provenance are available below. Market selection remains synchronized with the primary selector.</p></section>`;
  }

  function liveIntro() {
    const live = M().state.live || {};
    const integrity = String(live?.ledger?.integrity || "UNKNOWN").toUpperCase();
    return `<section class="decision-view-panel"><span class="decision-kicker">LIVE RECORD</span><h2>Frozen prospective forecasts and realized outcomes</h2><div class="decision-live-summary">
      <div><span>Ledger</span><strong>${esc(integrity)}</strong></div>
      <div><span>Forecasts</span><strong>${integer(live.forecast_count || 0)}</strong></div>
      <div><span>Matured signals</span><strong>${integer(live.matured_signal_count || 0)}</strong></div>
      <div><span>Historical backfill</span><strong>DISALLOWED</strong></div>
    </div><p>Only forecasts recorded before the outcome count as live evidence. The full immutable live record is shown below.</p></section>`;
  }

  function render() {
    if (rendering || !M()) return;
    rendering = true;
    try {
      const root = mount();
      if (!M().state.current || !M().state.active || !M().state.registry) {
        root.innerHTML = `<div class="decision-loading">Loading governed COT decision layer…</div>`;
        return;
      }
      M().state.market = M().selectedMarket();
      const summary = M().summary();
      headerMeta();
      document.documentElement.dataset.cotDecisionView = view;
      const content = view === "overview" ? overview(summary)
        : view === "edges" ? activeEdges(summary)
        : view === "week" ? weekPath(summary)
        : view === "research" ? researchIntro()
        : liveIntro();
      root.innerHTML = `${navigation()}${content}`;
      writeUrl({ push: false });
    } finally {
      rendering = false;
    }
  }

  function bind(root) {
    root.addEventListener("click", event => {
      const market = event.target.closest("[data-decision-market]")?.dataset.decisionMarket;
      if (market) return selectMarket(market);
      const horizon = event.target.closest("[data-decision-horizon]")?.dataset.decisionHorizon;
      if (horizon) return selectHorizon(horizon);
      const nextView = event.target.closest("[data-decision-view]")?.dataset.decisionView;
      if (nextView) return setView(nextView);
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
    observer = new MutationObserver(() => {
      if (rendering) return;
      const market = M().selectedMarket();
      if (market !== M().state.market) {
        M().state.market = market;
        render();
      }
    });
    observer.observe(tabs || document.documentElement, { subtree: true, childList: true, attributes: true, attributeFilter: ["class", "aria-pressed"] });
  }

  function applyInitialUrl() {
    const state = urlState();
    view = state.view || "overview";
    M().state.horizon = state.horizon || "4w";
    if (state.market) {
      const button = document.querySelector(`#instrumentTabs [data-market="${state.market}"]`);
      if (button && !button.classList.contains("active")) button.click();
      M().state.market = state.market;
    } else {
      M().state.market = M().selectedMarket();
    }
    document.documentElement.dataset.cotDecisionView = view;
  }

  async function boot() {
    const root = mount();
    bind(root);
    if (!M()) throw new Error("Current Edge model missing");
    await M().load();
    applyInitialUrl();
    render();
    observeMarket();
    window.addEventListener("popstate", () => {
      const state = urlState();
      view = state.view || "overview";
      if (state.horizon) M().state.horizon = state.horizon;
      if (state.market && state.market !== M().selectedMarket()) document.querySelector(`#instrumentTabs [data-market="${state.market}"]`)?.click();
      M().state.market = state.market || M().selectedMarket();
      render();
    });
    window.addEventListener("cot:intelligence-ready", render);
    window.__COT_APP_DATA_READY__?.then(render).catch(() => {});
  }

  boot().catch(error => {
    console.error("Decision-first COT command center failed to initialize.", error);
    const root = mount();
    root.innerHTML = `<div class="decision-loading"><strong>Decision layer unavailable.</strong><span>The underlying research dashboard remains intact; no forecast is fabricated.</span></div>`;
  });
})();