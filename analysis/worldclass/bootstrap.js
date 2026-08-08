(() => {
  "use strict";

  const originalFetch = window.fetch.bind(window);
  window.__COT_APP_DATA_READY__ = window.__COT_APP_DATA_READY__ || new Promise(resolve => { window.__COT_RESOLVE_APP_DATA_READY__ = resolve; });
  const CONSTANTS = [
    "COT_DATA",
    "PRICE_DATA",
    "FACTOR_DATA",
    "LIQUIDITY_DATA",
    "MACRO_MONITOR",
    "MACRO_LENS",
    "METADATA"
  ];

  function addStylesheet(href, dataKey) {
    if (document.querySelector(`link[${dataKey}]`)) return;
    const link = document.createElement("link");
    link.rel = "stylesheet";
    link.href = href;
    link.setAttribute(dataKey, "1");
    document.head.appendChild(link);
  }

  function addScript(src, onload) {
    const script = document.createElement("script");
    script.src = src;
    script.defer = true;
    if (onload) script.addEventListener("load", onload, { once: true });
    document.body.appendChild(script);
    return script;
  }

  function loadEnhancements() {
    addStylesheet("worldclass/enhancements.css", "data-worldclass-enhancements");
    addStylesheet("worldclass/kpi-accent.css", "data-worldclass-kpi-accent");
    addStylesheet("worldclass/decision-system.css", "data-worldclass-decision-system");
    addScript("worldclass/enhancements.js");
    addScript("worldclass/decision-system.js", () => addScript("worldclass/macro-control-fallback.js?v=20260808-2130"));
  }

  function loadApp() {
    addScript("worldclass/app.js", () => {
      window.__COT_RESOLVE_APP_DATA_READY__?.({ bootstrap: true });
      loadEnhancements();
    });
  }

  function announcePlotlyReady() {
    window.dispatchEvent(new CustomEvent("cot:plotly-ready"));
    window.setTimeout(() => document.querySelector("#instrumentTabs [data-market].active")?.click(), 0);
  }

  function loadPlotlyFallback() {
    if (window.Plotly) return announcePlotlyReady();
    const cdn = addScript("https://cdn.plot.ly/plotly-2.35.2.min.js", announcePlotlyReady);
    cdn.addEventListener("error", () => console.warn("Plotly could not be loaded from local or CDN sources."), { once: true });
  }

  function loadPlotly() {
    if (window.Plotly) return announcePlotlyReady();
    const local = addScript("dashboard_template/plotly-2.35.2.min.js", announcePlotlyReady);
    local.addEventListener("error", loadPlotlyFallback, { once: true });
  }

  function schedulePlotly() {
    if ("requestIdleCallback" in window) window.requestIdleCallback(loadPlotly, { timeout: 900 });
    else window.setTimeout(loadPlotly, 80);
  }

  async function boot() {
    try {
      const response = await originalFetch(`worldclass/base.json?v=${Date.now()}`, { cache: "no-store" });
      if (!response.ok) throw new Error(`base.json HTTP ${response.status}`);
      const base = await response.json();
      window.__COT_WORLDCLASS_BASE__ = base;
      const syntheticHtml = CONSTANTS.map(name => `const ${name} = ${JSON.stringify(base[name] || {})};`).join("\n");
      window.fetch = (input, init) => {
        const url = typeof input === "string" ? input : input?.url;
        if (url && /(^|\/)interactive_cot_dashboard\.html(?:[?#].*)?$/.test(url)) {
          return Promise.resolve(new Response(syntheticHtml, { status: 200, headers: { "Content-Type": "text/html; charset=utf-8" } }));
        }
        return originalFetch(input, init);
      };
    } catch (error) {
      console.warn("Compact data bundle unavailable; using legacy dashboard payload fallback.", error);
    }

    loadApp();
    schedulePlotly();
  }

  boot();
})();
