(() => {
  "use strict";

  const originalFetch = window.fetch.bind(window);
  const bootstrapScript = document.currentScript;
  const scriptVersion = (() => {
    try {
      return new URL(bootstrapScript?.src || window.location.href, window.location.href).searchParams.get("v");
    } catch (_) {
      return null;
    }
  })();
  const RUNTIME_VERSION = String(window.__COT_RUNTIME_VERSION__ || scriptVersion || Date.now());
  window.__COT_RUNTIME_VERSION__ = RUNTIME_VERSION;
  window.__COT_APP_DATA_READY__ = window.__COT_APP_DATA_READY__ || new Promise(resolve => { window.__COT_RESOLVE_APP_DATA_READY__ = resolve; });
  const CONSTANTS = ["COT_DATA","PRICE_DATA","FACTOR_DATA","LIQUIDITY_DATA","MACRO_MONITOR","MACRO_LENS","METADATA","MODEL_SPEC"];
  const MACRO_CORE_GROUPS = [
    ["net_liquidity_4w_change"],
    ["bank_reserves_4w_change", "bank_reserves"],
    ["sofr_iorb_spread", "effr_iorb_spread"]
  ];

  function versionedAsset(src) {
    if (/^(?:https?:)?\/\//i.test(src)) return src;
    const clean = String(src).split("?")[0].split("#")[0];
    return `${clean}?v=${encodeURIComponent(RUNTIME_VERSION)}`;
  }

  function addStylesheet(href, dataKey) {
    if (document.querySelector(`link[${dataKey}]`)) return;
    const link = document.createElement("link");
    link.rel = "stylesheet";
    link.href = versionedAsset(href);
    link.setAttribute(dataKey, "1");
    document.head.appendChild(link);
  }

  function addScript(src, onload) {
    const script = document.createElement("script");
    script.src = versionedAsset(src);
    script.defer = true;
    if (onload) script.addEventListener("load", onload, { once: true });
    document.body.appendChild(script);
    return script;
  }

  function loadEnhancements() {
    addStylesheet("worldclass/enhancements.css", "data-worldclass-enhancements");
    addStylesheet("worldclass/kpi-accent.css", "data-worldclass-kpi-accent");
    addStylesheet("worldclass/decision-system.css", "data-worldclass-decision-system");
    addStylesheet("worldclass/terminal-v2.css", "data-worldclass-terminal-v2");
    addStylesheet("worldclass/sentiment-panel.css", "data-worldclass-sentiment");
    addScript("worldclass/enhancements.js");
    addScript("worldclass/sentiment-panel.js");
    addScript("worldclass/terminal-v2.js");
    addScript("worldclass/decision-system.js", () => {
      addScript("worldclass/macro-control-fallback.js", () => {
        addScript("worldclass/macro-state-renderer.js", () => {
          addScript("worldclass/macro-live-sources.js");
        });
      });
    });
  }

  function loadApp() {
    addScript("worldclass/app.js", () => {
      window.__COT_RESOLVE_APP_DATA_READY__?.({ bootstrap: true, source: window.__COT_BOOTSTRAP_SOURCE__ || "unknown", runtimeVersion: RUNTIME_VERSION });
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

  const hasKeys = value => value && typeof value === "object" && Object.keys(value).length > 0;
  const finiteNumber = value => Number.isFinite(Number(value)) ? Number(value) : null;

  function findMetric(node, keys, depth = 0) {
    if (!node || depth > 10 || typeof node !== "object") return null;
    if (Array.isArray(node)) {
      for (let i = node.length - 1; i >= 0; i -= 1) {
        const found = findMetric(node[i], keys, depth + 1);
        if (found !== null) return found;
      }
      return null;
    }
    for (const key of keys) {
      if (key in node) {
        const value = finiteNumber(node[key]);
        if (value !== null) return value;
      }
    }
    for (const key of ["latest", "current", "state"]) {
      const found = findMetric(node[key], keys, depth + 1);
      if (found !== null) return found;
    }
    for (const [key, value] of Object.entries(node)) {
      if (["latest", "current", "state"].includes(key)) continue;
      const found = findMetric(value, keys, depth + 1);
      if (found !== null) return found;
    }
    return null;
  }

  function validateMacroMonitor(macro) {
    if (!hasKeys(macro)) throw new Error("runtime bundle has no MACRO_MONITOR");
    const missing = MACRO_CORE_GROUPS.filter(group => findMetric(macro, group) === null).map(group => group.join("/"));
    if (missing.length) throw new Error(`runtime MACRO_MONITOR missing core metrics: ${missing.join(", ")}`);
  }

  function validateModelSpec(spec) {
    if (!spec || typeof spec !== "object") throw new Error("runtime MODEL_SPEC is not an object");
    if (!spec.model_version) throw new Error("runtime MODEL_SPEC has no model_version");
    if (!/^[a-f0-9]{64}$/i.test(String(spec.model_spec_hash || ""))) throw new Error("runtime MODEL_SPEC has no valid SHA-256 hash");
    if (!hasKeys(spec.score_models)) throw new Error("runtime MODEL_SPEC has no score_models");
    for (const dataset of ["tff", "legacy", "disaggregated"]) {
      if (!hasKeys(spec.score_models?.[dataset]?.category_weights)) throw new Error(`runtime MODEL_SPEC has no ${dataset} category weights`);
    }
    return spec;
  }

  function validateBase(base) {
    if (!base || typeof base !== "object") throw new Error("runtime bundle is not an object");
    if (!hasKeys(base.COT_DATA)) throw new Error("runtime bundle has no COT_DATA");
    if (!hasKeys(base.PRICE_DATA)) throw new Error("runtime bundle has no PRICE_DATA");
    validateMacroMonitor(base.MACRO_MONITOR);
    validateModelSpec(base.MODEL_SPEC);
    return base;
  }

  function extractEmbeddedConstant(text, name) {
    const marker = `const ${name} = `;
    const markerIndex = text.indexOf(marker);
    if (markerIndex < 0) return {};
    let cursor = markerIndex + marker.length;
    while (cursor < text.length && /\s/.test(text[cursor])) cursor += 1;
    const start = cursor;
    let depth = 0, started = false, inString = false, escaped = false;
    for (; cursor < text.length; cursor += 1) {
      const char = text[cursor];
      if (inString) {
        if (escaped) escaped = false;
        else if (char === "\\") escaped = true;
        else if (char === '"') inString = false;
        continue;
      }
      if (char === '"') { inString = true; continue; }
      if (char === "{" || char === "[") { depth += 1; started = true; continue; }
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

  async function loadRuntimeModelSpec() {
    const response = await originalFetch(`worldclass/model-spec.json?v=${Date.now()}`, { cache: "no-store" });
    if (!response.ok) throw new Error(`model-spec.json HTTP ${response.status}`);
    const text = await response.text();
    if (!text.trim()) throw new Error("model-spec.json is empty");
    return validateModelSpec(JSON.parse(text));
  }

  async function loadLegacyBase() {
    const [legacyResponse, modelSpec] = await Promise.all([
      originalFetch(`interactive_cot_dashboard.html?v=${Date.now()}`, { cache: "no-store" }),
      loadRuntimeModelSpec()
    ]);
    if (!legacyResponse.ok) throw new Error(`interactive dashboard HTTP ${legacyResponse.status}`);
    const text = await legacyResponse.text();
    const base = Object.fromEntries(CONSTANTS.filter(name => name !== "MODEL_SPEC").map(name => [name, extractEmbeddedConstant(text, name)]));
    base.MODEL_SPEC = modelSpec;
    base.bundle_meta = {
      source: "legacy-html-runtime-recovery",
      source_html_bytes: text.length,
      recovered_at_utc: new Date().toISOString(),
      macro_core_contract: "PASS",
      model_version: modelSpec.model_version,
      model_spec_hash: modelSpec.model_spec_hash
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
        return Promise.resolve(new Response(syntheticHtml, { status: 200, headers: { "Content-Type": "text/html; charset=utf-8", "X-COT-Data-Source": source } }));
      }
      return originalFetch(input, init);
    };
  }

  function exposeRecoveryState(error) {
    window.__COT_BOOTSTRAP_SOURCE__ = "legacy-app-direct";
    window.__COT_BOOTSTRAP_ERROR__ = String(error?.message || error || "runtime data unavailable");
    console.error("Both compact and legacy shared-data bootstrap failed; app.js will surface a hard data/model contract error rather than inventing a neutral score.", error);
  }

  async function boot() {
    try {
      const base = await loadCompactBase();
      installSharedBase(base, "compact-base");
    } catch (compactError) {
      console.warn("Compact data bundle incomplete; recovering from tracked legacy dashboard.", compactError);
      try {
        const base = await loadLegacyBase();
        installSharedBase(base, "legacy-html-runtime-recovery");
        console.info("Recovered COT, price and macro data with canonical model metadata.");
      } catch (legacyError) {
        exposeRecoveryState(legacyError);
      }
    }
    loadApp();
    schedulePlotly();
  }

  boot();
})();