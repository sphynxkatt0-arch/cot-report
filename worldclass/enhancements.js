(() => {
  "use strict";

  const MARKET_LABELS = {
    sp500: "S&P 500", nq: "Nasdaq-100", vix: "VIX Futures",
    rty: "Russell 2000", dow: "Dow Jones", gold: "Gold", silver: "Silver"
  };
  const DATASET_LABELS = { tff: "TFF Detailed", legacy: "Legacy", disaggregated: "Disaggregated" };
  const HORIZON_ORDER = ["1w", "2w", "4w", "13w", "26w"];
  const METAL_ROLES = [
    ["Producer / Merchant / Processor / User", "Commercial physical hedgers; producers, processors and users of the commodity."],
    ["Swap Dealers", "Swap/intermediation books serving clients and carrying OTC-linked risk; not the same cohort as TFF Dealer/Intermediary."],
    ["Managed Money", "CTAs, CPOs and other managed speculative money; the closest metal analogue to a fund/speculative cohort, but not identical to TFF Leveraged Funds."],
    ["Other Reportables", "Large reportable traders outside the named groups; modeled inversely in the dashboard score."],
    ["Non-reportable", "Smaller traders below CFTC reporting thresholds; modeled inversely/contrarian in the dashboard score."]
  ];

  let analytics = null;
  let autoFitY = true;
  let fittingAxes = false;

  const $ = selector => document.querySelector(selector);
  const $$ = selector => [...document.querySelectorAll(selector)];

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function finite(value) {
    const n = Number(value);
    return Number.isFinite(n) ? n : null;
  }

  function activeMarket() {
    return $("#instrumentTabs [data-market].active")?.dataset.market || "sp500";
  }

  function activeDataset() {
    return $("#desktopControls [data-control='dataset']")?.value
      || $("#mobileControlBody [data-control='dataset']")?.value
      || (activeMarket() === "gold" || activeMarket() === "silver" ? "disaggregated" : "tff");
  }

  function signedPct(value, digits = 2) {
    const n = finite(value);
    if (n === null) return "n/a";
    return `${n > 0 ? "+" : n < 0 ? "−" : ""}${Math.abs(n).toFixed(digits)}%`;
  }

  function tone(value) {
    const n = finite(value);
    if (n === null || Math.abs(n) < 1e-9) return "wc-neutral";
    return n > 0 ? "wc-positive" : "wc-negative";
  }

  function ensureTaxonomyBanner() {
    const controls = $(".controls-surface");
    if (!controls) return;
    let banner = $("#wcTaxonomyBanner");
    if (!banner) {
      banner = document.createElement("section");
      banner.id = "wcTaxonomyBanner";
      banner.className = "wc-taxonomy-banner";
      controls.insertAdjacentElement("afterend", banner);
    }

    const market = activeMarket();
    if (market !== "gold" && market !== "silver") {
      banner.hidden = true;
      return;
    }
    banner.hidden = false;
    banner.innerHTML = `
      <div class="wc-taxonomy-title">
        <span class="wc-taxonomy-badge">Different CFTC report family by design</span>
        ${escapeHtml(MARKET_LABELS[market])} uses Disaggregated Futures Only — these actors are not the NQ/ES TFF actors.
      </div>
      <div class="wc-taxonomy-copy">
        Asset Manager / Institutional and Leveraged Funds are TFF financial-futures classifications. Gold and Silver are physical commodity contracts, so the CFTC publishes Producer/Merchant, Swap Dealer and Managed Money instead. The dashboard keeps the official taxonomy rather than relabeling different populations as if they were identical.
      </div>
      <div class="wc-role-grid">
        ${METAL_ROLES.map(([name, description]) => `<div class="wc-role"><strong>${escapeHtml(name)}</strong>${escapeHtml(description)}</div>`).join("")}
      </div>`;
  }

  function ensureForecastShell() {
    if ($("#wcForecastPanel")) return;
    const macroHeading = $$(".section-heading").find(section => section.querySelector("h2")?.textContent.trim() === "Macro liquidity");
    if (!macroHeading) return;
    const heading = document.createElement("section");
    heading.className = "section-heading wc-forecast-heading";
    heading.innerHTML = `<div><div class="section-number">02</div><div><h2>Backtest & forward expectancy</h2><p>Lookahead-safe historical analogs for the currently selected COT score.</p></div></div>`;
    const panel = document.createElement("section");
    panel.id = "wcForecastPanel";
    panel.className = "panel wc-forecast-panel";
    panel.innerHTML = `<div class="wc-forecast-note">Loading walk-forward backtest…</div>`;
    macroHeading.parentNode.insertBefore(heading, macroHeading);
    macroHeading.parentNode.insertBefore(panel, macroHeading);
    // The original numbering called Macro "02". Shift subsequent section labels visually.
    macroHeading.querySelector(".section-number").textContent = "03";
    const later = $$(".section-heading").find(section => section.querySelector("h2")?.textContent.trim() === "Data integrity & methodology");
    if (later) later.querySelector(".section-number").textContent = "04";
  }

  function activeBacktest() {
    const market = activeMarket();
    const dataset = activeDataset();
    const marketPayload = analytics?.markets?.[market];
    if (!marketPayload?.datasets) return null;
    return marketPayload.datasets[dataset] || marketPayload.datasets[Object.keys(marketPayload.datasets)[0]] || null;
  }

  function renderForecast() {
    const panel = $("#wcForecastPanel");
    if (!panel) return;
    if (!analytics) {
      panel.innerHTML = `<div class="wc-forecast-note">Loading walk-forward backtest…</div>`;
      return;
    }
    const payload = activeBacktest();
    if (!payload) {
      panel.innerHTML = `<div class="wc-forecast-note"><strong>No backtest is available for this report selection yet.</strong><br>The dashboard will keep the weekly position changes visible, but it will not manufacture a forward forecast without a validated price/COT history.</div>`;
      return;
    }

    const horizons = payload.horizons || {};
    const primary = horizons["4w"] || horizons["13w"] || horizons[Object.keys(horizons)[0]] || {};
    const current = payload.current || {};
    const primaryLabel = horizons["4w"] ? "4W" : horizons["13w"] ? "13W" : "Forward";
    const expected = finite(primary.expected_return_pct);
    const hitRate = finite(primary.hit_rate_pct);
    const stats = [
      ["Current COT score", finite(current.score)?.toFixed(0) ?? "n/a", `4W score momentum ${signedPct(current.score_delta_4w, 1)}`],
      [`${primaryLabel} analog expectancy`, signedPct(expected), `vs unconditional ${signedPct(primary.unconditional_return_pct)}`],
      ["Positive outcome rate", hitRate === null ? "n/a" : `${hitRate.toFixed(0)}%`, `${primary.observations || 0} nearest historical analogs`],
      ["Release anchor", current.release_target_date || "n/a", "First close on/after Friday release target"]
    ];

    const rows = HORIZON_ORDER.filter(key => horizons[key]).map(key => {
      const row = horizons[key];
      return `<tr>
        <td><strong>${key.toUpperCase()}</strong></td>
        <td class="${tone(row.expected_return_pct)}"><strong>${signedPct(row.expected_return_pct)}</strong></td>
        <td class="${tone(row.median_return_pct)}">${signedPct(row.median_return_pct)}</td>
        <td>${finite(row.hit_rate_pct) === null ? "n/a" : `${finite(row.hit_rate_pct).toFixed(0)}%`}</td>
        <td>${signedPct(row.q25_return_pct)} → ${signedPct(row.q75_return_pct)}</td>
        <td class="wc-negative">${signedPct(row.worst_drawdown_pct)}</td>
        <td class="${tone(row.edge_vs_unconditional_pct)}">${signedPct(row.edge_vs_unconditional_pct)}</td>
        <td>${row.observations ?? 0}</td>
        <td><span class="wc-confidence">${escapeHtml(row.confidence || "n/a")}</span></td>
      </tr>`;
    }).join("");

    const analogs = (payload.closest_analogs || []).slice(0, 6).map(row => `<div class="wc-analog-row">
      <span>${escapeHtml(row.report_date)}</span>
      <span>Score ${finite(row.score)?.toFixed(0) ?? "n/a"}</span>
      <span class="${tone(row.returns?.["4w"])}">4W ${signedPct(row.returns?.["4w"])}</span>
      <span class="${tone(row.returns?.["13w"])}">13W ${signedPct(row.returns?.["13w"])}</span>
    </div>`).join("");

    panel.innerHTML = `
      <div class="wc-forecast-top">
        ${stats.map(([label, value, sub]) => `<div class="wc-forecast-stat"><div class="wc-forecast-label">${escapeHtml(label)}</div><div class="wc-forecast-value">${escapeHtml(value)}</div><div class="wc-forecast-sub">${escapeHtml(sub)}</div></div>`).join("")}
      </div>
      <div class="wc-forecast-grid">
        <div class="wc-forecast-table-wrap">
          <table class="wc-forecast-table">
            <thead><tr><th>Horizon</th><th>Expected</th><th>Median</th><th>Hit rate</th><th>25–75% range</th><th>Worst DD</th><th>Edge vs base</th><th>N</th><th>Confidence</th></tr></thead>
            <tbody>${rows}</tbody>
          </table>
        </div>
        <aside class="wc-analogs">
          <h4>Closest historical analogs</h4>
          <p>Matched on the current 0–100 COT score plus 4-week score momentum. Historical scores use only information available at that date.</p>
          ${analogs || `<div class="wc-forecast-note">No completed analogs yet.</div>`}
        </aside>
      </div>
      <div class="wc-forecast-note">
        <strong>${escapeHtml(MARKET_LABELS[activeMarket()] || activeMarket())} · ${escapeHtml(DATASET_LABELS[activeDataset()] || activeDataset())}</strong> — statistical expectancy, not a deterministic target. COT signals are anchored after the Friday release to avoid using Tuesday positions before they were public. Macro liquidity remains a separate confirmation layer rather than being silently mixed into this backtest.
      </div>`;
  }

  function ensureChartToolbar() {
    const actions = $(".workbench-panel .panel-actions");
    if (!actions || $("#wcChartToolbar")) return;
    const toolbar = document.createElement("div");
    toolbar.id = "wcChartToolbar";
    toolbar.className = "wc-chart-toolbar";
    toolbar.innerHTML = `
      <button class="wc-chart-tool active" data-wc-chart="pan" type="button">Pan</button>
      <button class="wc-chart-tool" data-wc-chart="zoom" type="button">Zoom</button>
      <button class="wc-chart-tool active" data-wc-chart="autoy" type="button">Auto-fit Y</button>
      <button class="wc-chart-tool" data-wc-chart="fit" type="button">Fit visible</button>
      <button class="wc-chart-tool" data-wc-chart="timeline" type="button">Timeline</button>
      <button class="wc-chart-tool" data-wc-chart="reset" type="button">Reset</button>
      <span class="wc-chart-help">Wheel zooms · drag mode is explicit · Y axes can follow the visible date window</span>`;
    actions.appendChild(toolbar);
  }

  function chartElement() {
    const chart = document.getElementById("mainChart");
    return chart?.data?.length ? chart : null;
  }

  function fitVisibleAxes() {
    const chart = chartElement();
    if (!chart || fittingAxes || !window.Plotly) return;
    const xRange = chart.layout?.xaxis?.range;
    const start = xRange?.[0] ? new Date(xRange[0]).getTime() : -Infinity;
    const end = xRange?.[1] ? new Date(xRange[1]).getTime() : Infinity;
    const grouped = { y: [], y2: [] };

    for (const trace of chart.data || []) {
      if (trace.visible === false || !Array.isArray(trace.x) || !Array.isArray(trace.y)) continue;
      const axis = trace.yaxis || "y";
      if (!(axis in grouped)) continue;
      for (let i = 0; i < trace.y.length; i += 1) {
        const x = new Date(trace.x[i]).getTime();
        const y = finite(trace.y[i]);
        if (Number.isFinite(x) && x >= start && x <= end && y !== null) grouped[axis].push(y);
      }
    }

    const update = {};
    for (const [axis, values] of Object.entries(grouped)) {
      if (!values.length) continue;
      let min = Math.min(...values);
      let max = Math.max(...values);
      const span = max - min || Math.max(Math.abs(max), 1) * 0.08;
      const pad = span * 0.10;
      min -= pad;
      max += pad;
      update[`${axis === "y" ? "yaxis" : "yaxis2"}.range`] = [min, max];
      update[`${axis === "y" ? "yaxis" : "yaxis2"}.autorange`] = false;
    }
    if (!Object.keys(update).length) return;
    fittingAxes = true;
    Promise.resolve(Plotly.relayout(chart, update)).finally(() => { fittingAxes = false; });
  }

  function attachChartBehavior() {
    const chart = chartElement();
    if (!chart || chart.dataset.wcChartEnhanced === "1" || typeof chart.on !== "function") return;
    chart.dataset.wcChartEnhanced = "1";
    chart.on("plotly_relayout", changes => {
      if (!autoFitY || fittingAxes) return;
      const changedX = Object.keys(changes || {}).some(key => key.startsWith("xaxis.range") || key === "xaxis.autorange");
      if (changedX) window.setTimeout(fitVisibleAxes, 25);
    });
  }

  function setToolbarMode(mode) {
    $$("#wcChartToolbar [data-wc-chart='pan'], #wcChartToolbar [data-wc-chart='zoom']")
      .forEach(button => button.classList.toggle("active", button.dataset.wcChart === mode));
  }

  function handleChartAction(action, button) {
    const chart = chartElement();
    if (!chart || !window.Plotly) return;
    if (action === "pan" || action === "zoom") {
      Plotly.relayout(chart, { dragmode: action });
      setToolbarMode(action);
      return;
    }
    if (action === "autoy") {
      autoFitY = !autoFitY;
      button.classList.toggle("active", autoFitY);
      if (autoFitY) fitVisibleAxes();
      return;
    }
    if (action === "fit") {
      fitVisibleAxes();
      return;
    }
    if (action === "timeline") {
      const visible = Boolean(chart.layout?.xaxis?.rangeslider?.visible);
      Plotly.relayout(chart, { "xaxis.rangeslider.visible": !visible });
      button.classList.toggle("active", !visible);
      return;
    }
    if (action === "reset") {
      Plotly.relayout(chart, {
        "xaxis.autorange": true,
        "yaxis.autorange": true,
        "yaxis2.autorange": true,
        dragmode: "pan"
      });
      setToolbarMode("pan");
    }
  }

  function sync() {
    ensureTaxonomyBanner();
    ensureForecastShell();
    ensureChartToolbar();
    renderForecast();
    attachChartBehavior();
  }

  async function loadAnalytics() {
    try {
      const response = await fetch(`worldclass/backtest.json?v=${Date.now()}`, { cache: "no-store" });
      if (!response.ok) throw new Error(`backtest.json HTTP ${response.status}`);
      analytics = await response.json();
    } catch (error) {
      console.warn("Forward expectancy payload unavailable", error);
      analytics = { markets: {} };
    }
    sync();
  }

  document.addEventListener("click", event => {
    const tool = event.target.closest("[data-wc-chart]");
    if (tool) {
      handleChartAction(tool.dataset.wcChart, tool);
      return;
    }
    if (event.target.closest("[data-market], [data-category], [data-price-overlay], [data-factor-overlay], [data-range]")) {
      window.setTimeout(sync, 80);
    }
  });
  document.addEventListener("change", event => {
    if (event.target.closest("[data-control]")) window.setTimeout(sync, 80);
  });

  let attempts = 0;
  const initialTimer = window.setInterval(() => {
    sync();
    attempts += 1;
    if (attempts >= 20 || ($("#headlineCards")?.children.length && chartElement())) window.clearInterval(initialTimer);
  }, 300);

  loadAnalytics();
})();
