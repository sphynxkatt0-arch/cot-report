(() => {
  "use strict";

  const MARKET_LABELS = {
    sp500: "S&P 500", nq: "Nasdaq-100", vix: "VIX Futures",
    rty: "Russell 2000", dow: "Dow Jones", gold: "Gold", silver: "Silver"
  };
  const METAL_ROLES = [
    ["Producer / Merchant / Processor / User", "Commercial physical hedgers; producers, processors and users of the commodity."],
    ["Swap Dealers", "Swap/intermediation books serving clients and carrying OTC-linked risk; not the same cohort as TFF Dealer/Intermediary."],
    ["Managed Money", "CTAs, CPOs and other managed speculative money; the closest metal analogue to a fund/speculative cohort, but not identical to TFF Leveraged Funds."],
    ["Other Reportables", "Large reportable traders outside the named groups; modeled inversely in the dashboard score."],
    ["Non-reportable", "Smaller traders below CFTC reporting thresholds; modeled inversely/contrarian in the dashboard score."]
  ];

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

  function removeLegacyForecastShell() {
    // Charts & data used to load worldclass/backtest.json and render a second,
    // score-nearest-neighbour backtest beside the governed threshold/regime
    // evidence used by Today + Research. The two methodologies can legitimately
    // produce different numbers, but presenting both as "the backtest" made the
    // dashboard look internally inconsistent. Charts & data is now strictly the
    // raw analytical workbench; governed historical evidence lives in the shared
    // decision shell / Research view.
    $("#wcForecastPanel")?.remove();
    $$(".wc-forecast-heading").forEach(node => node.remove());
    const macroHeading = $$(".section-heading").find(section => section.querySelector("h2")?.textContent.trim() === "Macro liquidity");
    if (macroHeading) macroHeading.querySelector(".section-number").textContent = "02";
    const methodologyHeading = $$(".section-heading").find(section => section.querySelector("h2")?.textContent.trim() === "Data integrity & methodology");
    if (methodologyHeading) methodologyHeading.querySelector(".section-number").textContent = "03";
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
    removeLegacyForecastShell();
    ensureChartToolbar();
    attachChartBehavior();
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

  sync();
})();
