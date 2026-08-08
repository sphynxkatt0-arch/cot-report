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
    addScript("worldclass/decision-system.js?v=20260808-2340", () => {
      addScript("worldclass/macro-control-fallback.js?v=20260808-2340", () => {
        addScript("worldclass/macro-state-renderer.js?v=20260808-2340", () => {
          addScript("worldclass/macro-live-sources.js?v=20260808-2340");
        });
      });
    });
  }

  function loadApp() {
    addScript("worldclass/app.js", () => {
      window.__COT_RESOLVE_APP_DATA_READY__?.({ bootstrap: true, source: window.__COT_BOOTSTRAP_SOURCE__ || "unknown" });
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

  function hasKeys(value) {
    return value && typeof value === "object" && Object.keys(value).length > 0;
  }

  function validateBase(base) {
    if (!base || typeof base !== "object") throw new Error("runtime bundle is not an object");
    if (!hasKeys(base.COT_DATA)) throw new Error("runtime bundle has no COT_DATA");
    if (!hasKeys(base.PRICE_DATA)) throw new Error("runtime bundle has no PRICE_DATA");
    return base;
  }

  function extractEmbeddedConstant(text, name) {
    const marker = `const ${name} = `;
    const markerIndex = text.indexOf(marker);
    if (markerIndex < 0) return {};
    let cursor = markerIndex + marker.length;
    while (cursor < text.length && /\s/.test(text[cursor])) cursor += 1;
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
        continue;
      }
      if (char === "}" || char === "]") {
        depth -= 1;
        if (started && depth === 0) return JSON.parse(text.slice(start, cursor + 1));
      }
    }
    throw new Error(`embedded constant ${name} is truncated`);
  }

  async function loadCompactBase() {
    const response = await originalFetch(`worldclass/base.json?v=${Date.now()}`, { cache: "no-store" });
    if (!response.ok) throw new Error(`base.json HTTP ${response.status}`);
    const text = await response.text();
    if (!text.trim()) throw new Error("base.json is empty");
    return validateBase(JSON.parse(text));
  }

  async function loadLegacyBase() {
    const response = await originalFetch(`interactive_cot_dashboard.html?v=${Date.now()}`, { cache: "no-store" });
    if (!response.ok) throw new Error(`interactive dashboard HTTP ${response.status}`);
    const text = await response.text();
    const base = Object.fromEntries(CONSTANTS.map(name => [name, extractEmbeddedConstant(text, name)]));
    base.bundle_meta = {
      source: "legacy-html-runtime-recovery",
      source_html_bytes: text.length,
      recovered_at_utc: new Date().toISOString()
    };
    return validateBase(base);
  }

  function installSharedBase(base, source) {
    window.__COT_WORLDCLASS_BASE__ = base;
    window.__COT_BOOTSTRAP_SOURCE__ = source;
    const syntheticHtml = CONSTANTS.map(name => `const ${name} = ${JSON.stringify(base[name] || {})};`).join("\n");
    window.fetch = (input, init) => {
      const url = typeof input === "string" ? input : input?.url;
      if (url && /(^|\/)interactive_cot_dashboard\.html(?:[?#].*)?$/.test(url)) {
        return Promise.resolve(new Response(syntheticHtml, {
          status: 200,
          headers: { "Content-Type": "text/html; charset=utf-8", "X-COT-Data-Source": source }
        }));
      }
      return originalFetch(input, init);
    };
  }

  function exposeRecoveryState(error) {
    window.__COT_BOOTSTRAP_SOURCE__ = "legacy-app-direct";
    window.__COT_BOOTSTRAP_ERROR__ = String(error?.message || error || "runtime data unavailable");
    console.error("Both compact and legacy shared-data bootstrap failed; app.js will attempt its own legacy loader.", error);
  }

  async function boot() {
    let base = null;
    try {
      base = await loadCompactBase();
      installSharedBase(base, "compact-base");
    } catch (compactError) {
      console.warn("Compact data bundle unavailable; recovering from tracked legacy dashboard.", compactError);
      try {
        base = await loadLegacyBase();
        installSharedBase(base, "legacy-html-runtime-recovery");
        console.info("Recovered shared dashboard data from interactive_cot_dashboard.html.");
      } catch (legacyError) {
        exposeRecoveryState(legacyError);
      }
    }

    loadApp();
    schedulePlotly();
  }

  boot();
})();
