(() => {
  "use strict";

  const originalFetch = window.fetch.bind(window);
  const CONSTANTS = [
    "COT_DATA",
    "PRICE_DATA",
    "FACTOR_DATA",
    "LIQUIDITY_DATA",
    "MACRO_MONITOR",
    "MACRO_LENS",
    "METADATA"
  ];

  function loadEnhancements() {
    if (!document.querySelector('link[data-worldclass-enhancements]')) {
      const link = document.createElement("link");
      link.rel = "stylesheet";
      link.href = "worldclass/enhancements.css";
      link.dataset.worldclassEnhancements = "1";
      document.head.appendChild(link);
    }
    const script = document.createElement("script");
    script.src = "worldclass/enhancements.js";
    script.defer = true;
    document.body.appendChild(script);
  }

  function loadApp() {
    const script = document.createElement("script");
    script.src = "worldclass/app.js";
    script.defer = true;
    script.addEventListener("load", loadEnhancements, { once: true });
    document.body.appendChild(script);
  }

  async function boot() {
    try {
      const response = await originalFetch(`worldclass/base.json?v=${Date.now()}`, { cache: "no-store" });
      if (!response.ok) throw new Error(`base.json HTTP ${response.status}`);
      const base = await response.json();
      const syntheticHtml = CONSTANTS
        .map(name => `const ${name} = ${JSON.stringify(base[name] || {})};`)
        .join("\n");

      // app.js retains a backwards-compatible loader for the original research
      // dashboard. Intercept only that request and satisfy it from the compact
      // build-time bundle. All other fetches continue to use native fetch.
      window.fetch = (input, init) => {
        const url = typeof input === "string" ? input : input?.url;
        if (url && /(^|\/)interactive_cot_dashboard\.html(?:[?#].*)?$/.test(url)) {
          return Promise.resolve(new Response(syntheticHtml, {
            status: 200,
            headers: { "Content-Type": "text/html; charset=utf-8" }
          }));
        }
        return originalFetch(input, init);
      };
    } catch (error) {
      console.warn("Compact data bundle unavailable; using legacy dashboard payload fallback.", error);
    }
    loadApp();
  }

  boot();
})();
