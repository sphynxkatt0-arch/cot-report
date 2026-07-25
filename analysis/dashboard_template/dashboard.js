    const COT_DATA = {DATA_JSON};
    const PRICE_DATA = {PRICES_JSON};
    const COLORS = {COLORS_JSON};
    const MARKET_LABELS = {MARKET_LABELS_JSON};
    const DATASET_LABELS = {DATASET_LABELS_JSON};
    const FACTOR_DATA = {FACTORS_JSON};
    const LIQUIDITY_DATA = {LIQUIDITY_JSON};
    const MACRO_MONITOR = {MACRO_MONITOR_JSON};
    const RESEARCH = {RESEARCH_JSON};
    const REGIME_RULES = {REGIME_RULES_JSON};
    const METADATA = {METADATA_JSON};
    const REGIME_BACKTEST = {REGIME_BACKTEST_JSON};
    const CROSS_MARKET = {CROSS_MARKET_JSON};
    const WEEKLY_DESK = {WEEKLY_DESK_JSON};
    const MACRO_LENS = {MACRO_LENS_JSON};
    const THEME_STORAGE_KEY = "cot-dashboard-theme";
    const MACRO_SCORE_OVERLAY_KEY = "macro_score";

    function initialTheme() {
      try {
        const stored = window.localStorage.getItem(THEME_STORAGE_KEY);
        return stored === "light" ? "light" : "dark";
      } catch (e) {
        return "dark";
      }
    }

    function isMobileControls() {
      return window.matchMedia("(max-width: 900px)").matches;
    }

    function isCompactPlot() {
      return window.matchMedia("(max-width: 900px)").matches;
    }

    function initialSidebarCollapsed() {
      return true;
    }

    const state = {
      theme: initialTheme(),
      dataset: "tff",
      market: "sp500",
      metric: "net_oi_pct",
      showSp500: true,
      showNq: true,
      showFactors: {
        cnn_fear_greed: false,
        cnn_vix: true,
        fred_vix: true,
        real_yield_10y: false,
        hy_oas: false,
        dollar_index: false
      },
      priceScale: "raw",
      dragMode: "pan",
      showRangeSlider: true,
      thresholdFactor: "cnn_fear_greed",
      thresholdDirection: "<=",
      thresholdValue: 5,
      thresholdHorizon: 20,
      showThresholdMarks: true,
      priceAxisZoom: 1,
      factorAxisZoom: 1,
      rebaseTimer: null,
      selectedLine: null,
      lineSettings: {},
      tspRows: null,
      tspError: null,
      activeCategories: null,
      xRange: null,
      syncing: false,
      sidebarCollapsed: initialSidebarCollapsed(),
      showMacroScore: true
    };

    const metricLabels = {
      net_oi_pct: "Net / open interest (%)",
      net: "Net contracts",
      long: "Long contracts",
      short: "Short contracts",
      short_oi_pct: "Short / open interest (%)"
    };

    const els = {
      appShell: document.getElementById("appShell"),
      floatingControls: document.getElementById("floatingControls"),
      toggleSidebar: document.getElementById("toggleSidebar"),
      controlPanel: document.getElementById("controlPanel"),
      controlPanelHandle: document.getElementById("controlPanelHandle"),
      dataset: document.getElementById("dataset"),
      market: document.getElementById("market"),
      metric: document.getElementById("metric"),
      showSp500: document.getElementById("showSp500"),
      showNq: document.getElementById("showNq"),
      priceScale: document.getElementById("priceScale"),
      priceAxisZoom: document.getElementById("priceAxisZoom"),
      priceAxisZoomValue: document.getElementById("priceAxisZoomValue"),
      factorAxisZoom: document.getElementById("factorAxisZoom"),
      factorAxisZoomValue: document.getElementById("factorAxisZoomValue"),
      resetAxisZoom: document.getElementById("resetAxisZoom"),
      dragMode: document.getElementById("dragMode"),
      showRangeSlider: document.getElementById("showRangeSlider"),
      lineSelect: document.getElementById("lineSelect"),
      lineColor: document.getElementById("lineColor"),
      lineDash: document.getElementById("lineDash"),
      lineWidth: document.getElementById("lineWidth"),
      lineWidthValue: document.getElementById("lineWidthValue"),
      lineOpacity: document.getElementById("lineOpacity"),
      lineOpacityValue: document.getElementById("lineOpacityValue"),
      resetLine: document.getElementById("resetLine"),
      reset: document.getElementById("reset"),
      selectAll: document.getElementById("selectAll"),
      clearCategories: document.getElementById("clearCategories"),
      categoryList: document.getElementById("categoryList"),
      factorOverlayList: document.getElementById("factorOverlayList"),
      freshnessLine: document.getElementById("freshnessLine"),
      refreshStatusBanner: document.getElementById("refreshStatusBanner"),
      summaryStrip: document.getElementById("summaryStrip"),
      themeToggle: document.getElementById("themeToggle"),
      stats: document.getElementById("stats"),
      factorSidebar: document.getElementById("factorSidebar"),
      thresholdFactor: document.getElementById("thresholdFactor"),
      thresholdDirection: document.getElementById("thresholdDirection"),
      thresholdValue: document.getElementById("thresholdValue"),
      thresholdHorizon: document.getElementById("thresholdHorizon"),
      showThresholdMarks: document.getElementById("showThresholdMarks"),
      thresholdStats: document.getElementById("thresholdStats"),
      mainTitle: document.getElementById("mainTitle"),
      mainChart: document.getElementById("mainChart"),
      weeklyDeskPanel: document.getElementById("weeklyDeskPanel"),
      macroScorecardPanel: document.getElementById("macroScorecardPanel"),
      analyticSnapshot: document.getElementById("analyticSnapshot"),
      macroMonitorPanel: document.getElementById("macroMonitorPanel"),
      updateDeltaPanel: document.getElementById("updateDeltaPanel"),
      crossMarketPanel: document.getElementById("crossMarketPanel"),
      liquidityPanel: document.getElementById("liquidityPanel"),
      macroLensPanel: document.getElementById("macroLensPanel"),
      netTable: document.getElementById("netTable"),
      regimePanel: document.getElementById("regimePanel"),
      regimeBacktestPanel: document.getElementById("regimeBacktestPanel"),
      factorPanel: document.getElementById("factorPanel"),
      researchPanel: document.getElementById("researchPanel")
    };

    function resizeCharts() {
      for (const el of [els.mainChart, document.getElementById("crossMarketUnifiedChart"), document.getElementById("regimeHistoryChart"), document.getElementById("macroScoreChart"), document.getElementById("fundingStressChart")]) {
        if (!el || !el.data) continue;
        if (!window.Plotly?.Plots) continue;
        Plotly.Plots.resize(el);
      }
    }

    function renderSidebarState() {
      const mobileControls = isMobileControls();
      els.appShell.classList.toggle("sidebar-collapsed", state.sidebarCollapsed);
      els.appShell.classList.toggle("controls-drawer-open", mobileControls && !state.sidebarCollapsed);
      document.body.classList.toggle("mobile-controls-mode", mobileControls);
      document.body.classList.toggle("controls-drawer-open", mobileControls && !state.sidebarCollapsed);
      els.floatingControls?.classList.toggle("open", !state.sidebarCollapsed);
      els.toggleSidebar.setAttribute("aria-expanded", String(!state.sidebarCollapsed));
      els.toggleSidebar.setAttribute("aria-label", state.sidebarCollapsed ? "Open chart controls" : "Close chart controls");
    }

    function themeTokens() {
      if (state.theme === "light") {
        return {
          paper: "#ffffff",
          plot: "#ffffff",
          grid: "#edf0f4",
          zero: "#98a2b3",
          text: "#111827",
          muted: "#667085",
          hoverBg: "#ffffff",
          hoverBorder: "#98a2b3",
          legendBg: "rgba(255,255,255,0.86)",
          sliderBorder: "#d6dce5",
          selectorBg: "rgba(255,255,255,0.92)",
          sp500: "#991b1b",
          nq: "#111827",
          dealer: "#4b5563",
          factor: "#7c3aed",
          threshold: "#ef4444",
          haloSp500: "rgba(153, 27, 27, 0.20)",
          haloNq: "rgba(17, 24, 39, 0.22)"
        };
      }
      return {
        paper: "#0e1223",
        plot: "#0a0f1d",
        grid: "#1f2a3d",
        zero: "#64748b",
        text: "#f8fafc",
        muted: "#94a3b8",
        hoverBg: "#111827",
        hoverBorder: "#38bdf8",
        legendBg: "rgba(14,18,35,0.86)",
        sliderBorder: "#334155",
        selectorBg: "rgba(17,24,39,0.92)",
        sp500: "#f87171",
        nq: "#e5e7eb",
        dealer: "#94a3b8",
        factor: "#c084fc",
        threshold: "#f87171",
        haloSp500: "rgba(248, 113, 113, 0.20)",
        haloNq: "rgba(229, 231, 235, 0.18)"
      };
    }

    function themedLineColor(key) {
      const t = themeTokens();
      if (key === "sp500_price") return t.sp500;
      if (key === "nq_price") return t.nq;
      if (key === "dealer") return t.dealer;
      if (key === MACRO_SCORE_OVERLAY_KEY) return COLORS.macro_score || "#f59e0b";
      return COLORS[key] || "#667085";
    }

    function applyTheme() {
      document.documentElement.setAttribute("data-theme", state.theme);
      try {
        window.localStorage.setItem(THEME_STORAGE_KEY, state.theme);
      } catch (e) {
        // Storage can be blocked for local files; the theme still applies for this session.
      }
    }

    function renderThemeToggle() {
      if (!els.themeToggle) return;
      const isDark = state.theme === "dark";
      els.themeToggle.textContent = isDark ? "☾" : "☀";
      els.themeToggle.setAttribute("aria-pressed", String(isDark));
      els.themeToggle.setAttribute("aria-label", isDark ? "Switch to light theme" : "Switch to dark theme");
      els.themeToggle.setAttribute("title", isDark ? "Switch to light theme" : "Switch to dark theme");
    }

    function strongestCurrentExtreme() {
      const data = currentDataset();
      const latest = data.records[data.records.length - 1];
      const rows = currentCategoryKeys().map(key => {
        const net = Number(latest[fieldFor(key, "net_oi_pct")]);
        const history = data.records.map(row => Number(row[fieldFor(key, "net_oi_pct")])).filter(Number.isFinite);
        if (!history.length || !Number.isFinite(net)) return null;
        const low = Math.min(...history);
        const high = Math.max(...history);
        const percentile = (net - low) / (high - low || 1) * 100;
        return { key, label: data.categories[key], net, percentile, distance: Math.abs(percentile - 50) };
      }).filter(Boolean);
      return rows.sort((a, b) => b.distance - a.distance)[0] || null;
    }

    function renderSummaryStrip() {
      if (!els.summaryStrip) return;
      const data = currentDataset();
      const latest = data.records[data.records.length - 1] || {};
      const macro = MACRO_MONITOR.latest || {};
      const regime = evaluateRegime(state.market);
      const extreme = strongestCurrentExtreme();
      const extremeZone = extreme ? percentileZone(extreme.percentile) : null;
      const cards = [
        ["COT date", latest.date || "n/a", "Latest selected report", ""],
        ["Market", MARKET_LABELS[state.market], DATASET_LABELS[state.dataset], ""],
        ["Regime", regime.status.text, `Score ${formatSigned(regime.score)} | ${regime.highConviction} trigger${regime.highConviction === 1 ? "" : "s"}`, regime.status.cls],
        ["Extreme", extreme ? `${extreme.label} ${formatPct(extreme.net)}` : "n/a", extreme ? `${Math.round(extreme.percentile)}% - ${extremeZone.label}` : "No current rank", extremeZone?.cls || ""],
        ["Unified liquidity", Number.isFinite(Number(macro.liquidity_score)) ? `${Number(macro.liquidity_score).toFixed(0)} / 100` : "n/a", macro.regime_label || "Macro monitor", macroStatusClass(macro.regime_label)],
        ["Price", Number(latest.price).toLocaleString(undefined, { maximumFractionDigits: 2 }), "COT-aligned close", ""],
        ["Open interest", Number(latest.open_interest).toLocaleString(), "Consolidated contract", ""]
      ];
      els.summaryStrip.innerHTML = cards.map(([label, value, sub, cls]) => `
        <div class="summary-card ${cls || ""}">
          <div class="summary-label">${label}</div>
          <div class="summary-value">${value}</div>
          <div class="summary-sub">${sub}</div>
        </div>
      `).join("");
    }

    function currentDataset() {
      return COT_DATA[state.dataset][state.market];
    }

    function currentCategoryKeys() {
      return Object.keys(currentDataset().categories);
    }

    function ensureActiveCategories(reset = false) {
      const keys = currentCategoryKeys();
      const valid = new Set(keys);
      if (reset || !Array.isArray(state.activeCategories)) {
        state.activeCategories = [...keys];
      } else {
        state.activeCategories = state.activeCategories.filter(k => valid.has(k));
      }
    }

    function fieldFor(category, metric) {
      return `${category}_${metric}`;
    }

    function formatValue(value, metric) {
      if (value === null || value === undefined || Number.isNaN(value)) return "n/a";
      if (metric.endsWith("pct")) return `${Number(value).toFixed(2)}%`;
      return Number(value).toLocaleString(undefined, { maximumFractionDigits: 0 });
    }

    function formatPct(value) {
      if (value === null || value === undefined || Number.isNaN(value)) return "n/a";
      return `${Number(value).toFixed(2)}%`;
    }

    function formatTimestamp(value) {
      if (!value) return "n/a";
      return value.replace("T", " ").replace("Z", " UTC");
    }

    function renderFreshnessLine() {
      const tff = METADATA.cot_latest?.tff || {};
      const tffSource = METADATA.cot_source_latest?.tff || {};
      const fred = METADATA.fred_latest || {};
      const factors = METADATA.factor_latest || {};
      const cotStatus = (market) => {
        const output = tff[market] || "n/a";
        const source = tffSource[market] || "n/a";
        return output === source ? `${output} ✓` : `${output} ⚠ source ${source}`;
      };
      const items = [
        ["Built", formatTimestamp(METADATA.generated_at_utc)],
        ["CFTC S&P", cotStatus("sp500")],
        ["CFTC NQ", cotStatus("nq")],
        ["CFTC VIX", cotStatus("vix")],
        ["FRED S&P", fred.sp500 || "n/a"],
        ["FRED NQ", fred.nq || "n/a"],
        ["FRED VIX", factors.fred_vix || "n/a"],
        ["Net liq.", METADATA.liquidity_latest?.net_liquidity || "n/a"],
        ["Macro", METADATA.macro_latest || "n/a"],
        ["CNN VIX", factors.cnn_vix || "n/a"],
        ["CNN F&G", factors.cnn_fear_greed || "n/a"]
      ];
      els.freshnessLine.innerHTML = items.map(([label, value]) => `
        <span class="freshness-pill"><strong>${label}</strong>&nbsp;${value}</span>
      `).join("");
    }

    function renderRefreshStatusBanner(status) {
      if (!els.refreshStatusBanner) return;
      if (!status || status.status === "ok") {
        els.refreshStatusBanner.hidden = true;
        els.refreshStatusBanner.textContent = "";
        return;
      }
      const when = status.updated_at ? ` at ${formatTimestamp(status.updated_at)}` : "";
      const build = status.dashboard_mtime ? ` Cached dashboard build: ${formatTimestamp(status.dashboard_mtime)}.` : "";
      const detail = status.message ? ` ${status.message}` : "";
      els.refreshStatusBanner.hidden = false;
      els.refreshStatusBanner.textContent = `Refresh ${status.status}${when}. Showing cached dashboard data until the next successful refresh.${build}${detail}`;
    }

    async function loadRefreshStatus() {
      if (window.location.protocol === "file:") return;
      try {
        const response = await fetch(`dashboard_refresh_status.json?ts=${Date.now()}`, { cache: "no-store" });
        if (!response.ok) return;
        renderRefreshStatusBanner(await response.json());
      } catch (e) {
        // The dashboard still works when opened as a standalone HTML artifact.
      }
    }

    function renderAxisZoomControls() {
      els.priceAxisZoom.value = state.priceAxisZoom;
      els.factorAxisZoom.value = state.factorAxisZoom;
      els.priceAxisZoomValue.textContent = `${Number(state.priceAxisZoom).toFixed(1)}x`;
      els.factorAxisZoomValue.textContent = `${Number(state.factorAxisZoom).toFixed(1)}x`;
    }

    function renderThresholdControls() {
      const options = Object.entries(FACTOR_DATA.definitions || {}).map(([key, factor]) => (
        `<option value="${key}" ${key === state.thresholdFactor ? "selected" : ""}>${factor.label}</option>`
      )).join("");
      els.thresholdFactor.innerHTML = options;
      els.thresholdDirection.value = state.thresholdDirection;
      els.thresholdValue.value = state.thresholdValue;
      els.thresholdHorizon.value = String(state.thresholdHorizon);
      els.showThresholdMarks.checked = state.showThresholdMarks;
    }

    function renderPrimaryControls() {
      els.dataset.value = state.dataset;
      els.market.value = state.market;
      els.metric.value = state.metric;
      els.showSp500.checked = state.showSp500;
      els.showNq.checked = state.showNq;
      els.priceScale.value = state.priceScale;
      els.dragMode.value = state.dragMode;
      els.showRangeSlider.checked = state.showRangeSlider;
    }

    function defaultLineSetting(key) {
      const isPrice = key.endsWith("_price");
      const isFactor = Boolean(FACTOR_DATA.definitions?.[key]);
      const isMacroScore = key === MACRO_SCORE_OVERLAY_KEY;
      return {
        color: (isFactor || isMacroScore) ? (COLORS[key] || themeTokens().factor) : themedLineColor(key),
        width: isPrice ? 3.4 : ((isFactor || isMacroScore) ? 2.6 : 2.2),
        dash: isMacroScore ? "dot" : (isFactor ? "dash" : "solid"),
        opacity: 1
      };
    }

    function lineSetting(key) {
      if (!state.lineSettings[key]) {
        state.lineSettings[key] = defaultLineSetting(key);
      }
      return state.lineSettings[key];
    }

    function availableLineKeys() {
      const items = Object.entries(currentDataset().categories).map(([key, label]) => [key, label]);
      items.push(["sp500_price", "S&P 500 price"]);
      items.push(["nq_price", "NQ price"]);
      for (const [key, factor] of Object.entries(FACTOR_DATA.definitions || {})) {
        items.push([key, factor.label]);
      }
      if (MACRO_MONITOR.available) {
        items.push([MACRO_SCORE_OVERLAY_KEY, "Macro liquidity score"]);
      }
      return items;
    }

    function renderLineControls() {
      const lines = availableLineKeys();
      if (!state.selectedLine || !lines.some(([key]) => key === state.selectedLine)) {
        state.selectedLine = lines[0]?.[0] || null;
      }
      els.lineSelect.innerHTML = lines.map(([key, label]) => `
        <option value="${key}" ${key === state.selectedLine ? "selected" : ""}>${label}</option>
      `).join("");
      if (!state.selectedLine) return;
      const s = lineSetting(state.selectedLine);
      els.lineColor.value = s.color;
      els.lineDash.value = s.dash;
      els.lineWidth.value = s.width;
      els.lineWidthValue.textContent = Number(s.width).toFixed(2);
      els.lineOpacity.value = s.opacity;
      els.lineOpacityValue.textContent = `${Math.round(Number(s.opacity) * 100)}%`;
    }

    function renderCategoryControls() {
      const categories = currentDataset().categories;
      els.categoryList.innerHTML = Object.entries(categories).map(([key, label]) => `
        <label class="category-toggle">
          <input type="checkbox" data-category="${key}" ${state.activeCategories.includes(key) ? "checked" : ""}>
          <span class="swatch" style="background:${COLORS[key] || "#667085"}"></span>
          <span>${label}</span>
        </label>
      `).join("");
    }

    function renderFactorOverlayControls() {
      const preferred = ["cnn_vix", "fred_vix", "real_yield_10y", "hy_oas", "dollar_index", "cnn_fear_greed"];
      const entries = preferred
        .filter(key => FACTOR_DATA.definitions?.[key])
        .map(key => [key, FACTOR_DATA.definitions[key]]);
      const macroToggle = MACRO_MONITOR.available ? `
        <label class="category-toggle macro-score-toggle">
          <input type="checkbox" data-macro-score ${state.showMacroScore ? "checked" : ""}>
          <span class="swatch" style="background:${COLORS.macro_score || "#f59e0b"}"></span>
          <span>Macro liquidity score</span>
        </label>
      ` : "";
      els.factorOverlayList.innerHTML = `${macroToggle}${entries.map(([key, factor]) => `
        <label class="category-toggle">
          <input type="checkbox" data-factor="${key}" ${state.showFactors[key] ? "checked" : ""}>
          <span class="swatch" style="background:${COLORS[key] || "#667085"}"></span>
          <span>${factor.label}</span>
        </label>
      `).join("")}`;
    }

    function factorStateMatches(expected) {
      const keys = Object.keys(FACTOR_DATA.definitions || {});
      return keys.every(key => Boolean(state.showFactors[key]) === Boolean(expected[key]));
    }

    function currentPresetKey() {
      if (state.showSp500 && state.showNq && !state.showMacroScore && !state.showThresholdMarks && factorStateMatches({})) {
        return "cot_price";
      }
      if (state.showSp500 && !state.showNq && state.showMacroScore && !state.showThresholdMarks && state.priceScale === "indexed" && factorStateMatches({})) {
        return "macro";
      }
      if (state.showSp500 && !state.showNq && !state.showMacroScore && !state.showThresholdMarks && factorStateMatches({ cnn_vix: true, fred_vix: true, real_yield_10y: true, hy_oas: true })) {
        return "stress";
      }
      if (state.showSp500 && state.showNq && !state.showMacroScore && state.showThresholdMarks && factorStateMatches({ cnn_fear_greed: true, cnn_vix: true })) {
        return "sentiment";
      }
      return "";
    }

    function renderViewPresetButtons() {
      const active = currentPresetKey();
      for (const button of document.querySelectorAll("[data-view-preset]")) {
        const selected = button.getAttribute("data-view-preset") === active;
        button.classList.toggle("active", selected);
        button.setAttribute("aria-pressed", String(selected));
      }
    }

    function renderStats() {
      const data = currentDataset();
      const latest = data.records[data.records.length - 1];
      const lines = [
        ["Date", latest.date],
        ["Open interest", Number(latest.open_interest).toLocaleString()],
        ["COT price", Number(latest.price).toLocaleString(undefined, { maximumFractionDigits: 2 })]
      ];
      for (const key of state.activeCategories) {
        const label = data.categories[key];
        lines.push([label, formatValue(latest[fieldFor(key, "net_oi_pct")], "net_oi_pct")]);
      }
      els.stats.innerHTML = lines.map(([label, value]) => `
        <div class="stat-line">
          <span class="stat-label">${label}</span>
          <span class="stat-value">${value}</span>
        </div>
      `).join("");
    }

    function renderFactorSidebar() {
      const stats = FACTOR_DATA.stats?.[state.market] || {};
      const rows = Object.values(stats);
      if (!rows.length) {
        els.factorSidebar.innerHTML = `<div class="stat-line"><span class="stat-label">Factors</span><span class="stat-value">n/a</span></div>`;
        return;
      }
      els.factorSidebar.innerHTML = rows.map(row => {
        const expected = row.expected_return || {};
        const rank = Number.isFinite(Number(row.percentile)) ? `${Math.round(Number(row.percentile))}%` : "n/a";
        const contribution = regimeContributionForRow(state.market, {
          key: row.key,
          source: "factor",
          percentile: Number(row.percentile)
        });
        return `
          <div class="stat-line">
            <span class="stat-label">${row.label}<br><span class="factor-mini">${rank} rank | score ${formatSigned(contribution)} | 26w exp ${formatSignedPct(expected["26w"])}</span></span>
            <span class="stat-value">${formatFactorValue(row)}</span>
          </div>
        `;
      }).join("");
    }

    function signedNumber(value, decimals = 0) {
      const n = Number(value);
      if (!Number.isFinite(n)) return "n/a";
      return `${n > 0 ? "+" : ""}${n.toLocaleString(undefined, {
        minimumFractionDigits: decimals,
        maximumFractionDigits: decimals
      })}`;
    }

    function signedPoints(value, decimals = 2) {
      const n = Number(value);
      if (!Number.isFinite(n)) return "n/a";
      return `${n > 0 ? "+" : ""}${n.toFixed(decimals)} pts`;
    }

    function signedPercentChange(latest, previous) {
      const a = Number(latest);
      const b = Number(previous);
      if (!Number.isFinite(a) || !Number.isFinite(b) || b === 0) return "n/a";
      return `${a / b - 1 > 0 ? "+" : ""}${((a / b - 1) * 100).toFixed(2)}%`;
    }

    function directionClass(value, invert = false) {
      const n = Number(value);
      if (!Number.isFinite(n) || n === 0) return "";
      const positive = invert ? n < 0 : n > 0;
      return positive ? "score-pos" : "score-neg";
    }

    function latestTwoFactorRecords(key) {
      const byDate = new Map();
      for (const row of FACTOR_DATA.definitions?.[key]?.records || []) {
        if (!Number.isFinite(Number(row.value)) || !row.date) continue;
        byDate.set(row.date, row);
      }
      const rows = Array.from(byDate.values()).sort((a, b) => String(a.date).localeCompare(String(b.date)));
      return rows.length >= 2 ? rows.slice(-2) : null;
    }

    function factorDeltaCard(key, title, invert = true) {
      const rows = latestTwoFactorRecords(key);
      if (!rows) {
        return `
          <div class="delta-card">
            <div class="delta-label">${title}</div>
            <div class="delta-main">n/a</div>
            <div class="delta-sub">No prior reading available</div>
          </div>
        `;
      }
      const [previous, latest] = rows;
      const latestValue = Number(latest.value);
      const previousValue = Number(previous.value);
      const delta = latestValue - previousValue;
      return `
        <div class="delta-card">
          <div class="delta-label">${title}</div>
          <div class="delta-main">${latestValue.toFixed(2)}</div>
          <div class="delta-change ${directionClass(delta, invert)}">${signedPoints(delta)} | ${signedPercentChange(latestValue, previousValue)}</div>
          <div class="delta-sub">${previous.date} to ${latest.date}</div>
        </div>
      `;
    }

    function holdingDeltaRows() {
      const data = currentDataset();
      const records = data.records || [];
      if (records.length < 2) return [];
      const previous = records[records.length - 2];
      const latest = records[records.length - 1];
      return currentCategoryKeys().map(key => {
        const latestNetPct = Number(latest[fieldFor(key, "net_oi_pct")]);
        const previousNetPct = Number(previous[fieldFor(key, "net_oi_pct")]);
        const latestNet = Number(latest[fieldFor(key, "net")]);
        const previousNet = Number(previous[fieldFor(key, "net")]);
        const latestLong = Number(latest[fieldFor(key, "long")]);
        const previousLong = Number(previous[fieldFor(key, "long")]);
        const latestShort = Number(latest[fieldFor(key, "short")]);
        const previousShort = Number(previous[fieldFor(key, "short")]);
        return {
          key,
          label: data.categories[key],
          latestNetPct,
          previousNetPct,
          netPctDelta: latestNetPct - previousNetPct,
          latestNet,
          netDelta: latestNet - previousNet,
          longDelta: latestLong - previousLong,
          shortDelta: latestShort - previousShort
        };
      }).filter(row => Number.isFinite(row.latestNetPct));
    }

    function renderUpdateDeltaPanel() {
      if (!els.updateDeltaPanel) return;
      const data = currentDataset();
      const records = data.records || [];
      if (records.length < 2) {
        els.updateDeltaPanel.innerHTML = `<p class="research-copy">No prior ${DATASET_LABELS[state.dataset]} report is available for comparison.</p>`;
        return;
      }
      const previous = records[records.length - 2];
      const latest = records[records.length - 1];
      const rows = holdingDeltaRows();
      const biggest = rows
        .slice()
        .sort((a, b) => Math.abs(b.netPctDelta) - Math.abs(a.netPctDelta))[0];
      const oiDelta = Number(latest.open_interest) - Number(previous.open_interest);
      const priceDelta = Number(latest.price) - Number(previous.price);
      const rowHtml = rows.map(row => `
        <tr>
          <td>
            <div class="factor-name">
              <span class="swatch" style="background:${COLORS[row.key] || "#667085"}"></span>
              <span>${row.label}</span>
            </div>
          </td>
          <td>${formatPct(row.latestNetPct)}</td>
          <td class="${directionClass(row.netPctDelta)}">${signedPoints(row.netPctDelta)}</td>
          <td class="${directionClass(row.netDelta)}">${signedNumber(row.netDelta)}</td>
          <td class="${directionClass(row.longDelta)}">${signedNumber(row.longDelta)}</td>
          <td class="${directionClass(-row.shortDelta)}">${signedNumber(row.shortDelta)}</td>
        </tr>
      `).join("");

      els.updateDeltaPanel.innerHTML = `
        <div class="delta-hero">
          <div>
            <div class="snapshot-kicker">${MARKET_LABELS[state.market]} ${DATASET_LABELS[state.dataset]} update</div>
            <div class="snapshot-status">${latest.date} vs ${previous.date}</div>
            <div class="snapshot-body">
              ${biggest ? `Largest net/OI move: ${biggest.label} ${signedPoints(biggest.netPctDelta)}.` : "No category movement available."}
              Open interest changed ${signedNumber(oiDelta)} contracts; COT-aligned price changed ${signedNumber(priceDelta, 2)}.
            </div>
          </div>
          <div class="delta-card-grid">
            <div class="delta-card">
              <div class="delta-label">Open interest</div>
              <div class="delta-main">${Number(latest.open_interest).toLocaleString()}</div>
              <div class="delta-change ${directionClass(oiDelta)}">${signedNumber(oiDelta)}</div>
              <div class="delta-sub">contracts since prior report</div>
            </div>
            <div class="delta-card">
              <div class="delta-label">COT price</div>
              <div class="delta-main">${Number(latest.price).toLocaleString(undefined, { maximumFractionDigits: 2 })}</div>
              <div class="delta-change ${directionClass(priceDelta)}">${signedNumber(priceDelta, 2)}</div>
              <div class="delta-sub">close aligned to COT row</div>
            </div>
          </div>
        </div>
        <div class="delta-grid">
          <div class="delta-section">
            <div class="insight-head">
              <span>Holdings changes</span>
              <small>Latest report minus prior report</small>
            </div>
            <table class="factor-table update-delta-table">
              <thead>
                <tr>
                  <th>Category</th>
                  <th>Latest net/OI</th>
                  <th>Net/OI change</th>
                  <th>Net contracts</th>
                  <th>Longs</th>
                  <th>Shorts</th>
                </tr>
              </thead>
              <tbody>${rowHtml}</tbody>
            </table>
          </div>
          <div class="delta-section">
            <div class="insight-head">
              <span>VIX changes</span>
              <small>Latest reading minus prior reading</small>
            </div>
            <div class="vix-delta-grid">
              ${factorDeltaCard("fred_vix", "FRED VIX")}
              ${factorDeltaCard("cnn_vix", "CNN VIX component")}
              ${factorDeltaCard("cnn_fear_greed", "CNN Fear & Greed", false)}
            </div>
          </div>
        </div>
      `;
    }

    function biasClass(label) {
      if (label === "Bullish" || label === "Supported") return "score-pos";
      if (label === "Bearish" || label === "Contradictory") return "score-neg";
      return "";
    }

    function directionBadge(label) {
      const icon = label === "Bullish" ? "▲" : label === "Bearish" ? "▼" : label === "Neutral" ? "—" : "↔";
      return `<span class="direction-badge ${biasClass(label)}"><span aria-hidden="true">${icon}</span> ${label}</span>`;
    }

    function formatContracts(value) {
      const n = Number(value);
      if (!Number.isFinite(n)) return "n/a";
      return `${n > 0 ? "+" : ""}${Math.round(n).toLocaleString()} ctr`;
    }

    function marketFlowCell(snapshot, direction) {
      return `
        <div class="market-flow-cell">
          <div class="market-flow-line"><span>Net</span><strong class="${scoreClass(snapshot.net_notional_usd)}">${formatNotional(snapshot.net_notional_usd)}</strong></div>
          <div class="market-flow-line"><span>1w Δ</span><strong class="${scoreClass(snapshot.flow_1w_notional_usd)}">${formatNotional(snapshot.flow_1w_notional_usd)}</strong></div>
          <div class="market-flow-contracts">${formatContracts(snapshot.flow_1w_contracts)}</div>
          ${directionBadge(direction)}
        </div>
      `;
    }

    function latestTotalRiskDeltaCell(player) {
      const weekLabel = player.latest_change_from_date && player.latest_change_to_date
        ? `${player.latest_change_from_date} → ${player.latest_change_to_date}`
        : "latest report week";
      return `
        <div class="risk-split-cell latest-risk-cell">
          <div class="risk-cell-kicker">Latest risk-on exposure change</div>
          <div class="risk-cell-value ${scoreClass(player.risk_flow_1w_notional_usd)}">${formatNotional(player.risk_flow_1w_notional_usd)}</div>
          <div class="risk-cell-date">${weekLabel}</div>
          <div class="risk-cell-badge">${directionBadge(player.risk_flow_1w_direction)}</div>
          <div class="risk-cell-note">SP + NQ - VIX exposure flow</div>
        </div>
      `;
    }

    function totalRiskTrendCell(player) {
      return `
        <div class="risk-split-cell trend-risk-cell">
          <div class="risk-cell-kicker">Long-term risk-on exposure</div>
          <div class="risk-metric-row"><span>Current net</span><strong class="${scoreClass(player.risk_net_notional_usd)}">${formatNotional(player.risk_net_notional_usd)}</strong></div>
          <div class="risk-metric-row"><span>13w net change</span><strong class="${scoreClass(player.risk_net_13w_change_notional_usd)}">${formatNotional(player.risk_net_13w_change_notional_usd)}</strong></div>
          ${directionBadge(player.risk_trend_13w_direction)}
          <div class="risk-metric-row"><span>26w net change</span><strong class="${scoreClass(player.risk_net_26w_change_notional_usd)}">${formatNotional(player.risk_net_26w_change_notional_usd)}</strong></div>
          <div class="risk-cell-note">SP + NQ - VIX exposure history</div>
        </div>
      `;
    }

    function vixFlowCell(vix, player) {
      const rawFlow = Number(vix.flow_1w_notional_usd || 0);
      const riskFlow = Number(player.vix_risk_flow_1w_notional_usd || -rawFlow);
      return `
        <div class="market-flow-cell">
          <div class="market-flow-line"><span>Raw 1w</span><strong class="${scoreClass(-rawFlow)}">${formatNotional(rawFlow)}</strong></div>
          <div class="market-flow-line"><span>Risk effect</span><strong class="${scoreClass(riskFlow)}">${formatNotional(riskFlow)}</strong></div>
          <div class="market-flow-contracts">buying VIX = bearish</div>
          ${directionBadge(player.vix_flow_1w_direction)}
        </div>
      `;
    }

    function renderCrossMarketFlowChart(players) {
      const chart = document.getElementById("crossMarketFlowChart");
      if (!chart || !window.Plotly) return;
      const ordered = players.slice().sort((a, b) => Number(a.short_term_bias_score) - Number(b.short_term_bias_score));
      const labels = ordered.map(player => player.label);
      const barTraces = [
        {
          name: "S&P 500 flow",
          key: "sp500",
          color: "#2563eb",
          values: ordered.map(player => Number(player.markets?.sp500?.flow_1w_notional_usd || 0) / 1e9)
        },
        {
          name: "NASDAQ-100 flow",
          key: "nq",
          color: "#d97706",
          values: ordered.map(player => Number(player.markets?.nq?.flow_1w_notional_usd || 0) / 1e9)
        },
        {
          name: "VIX hedge effect",
          key: "vix",
          color: "#db2777",
          values: ordered.map(player => -Number(player.markets?.vix?.flow_1w_notional_usd || 0) / 1e9)
        }
      ].map(series => ({
        type: "bar",
        orientation: "h",
        name: series.name,
        x: series.values,
        y: labels,
        marker: { color: series.color },
        customdata: ordered.map(player => [player.short_term_bias, player.divergence]),
          hovertemplate: `%{y}<br>${series.name}: %{x:+.2f}bn<br>Bias: %{customdata[0]}<br>%{customdata[1]}<extra></extra>`
      }));
      const totalTrace = {
        type: "scatter",
        mode: "markers",
        name: "Risk-on exposure net change",
        x: ordered.map(player => Number(player.risk_flow_1w_notional_usd || 0) / 1e9),
        y: labels,
        marker: {
          color: "#111827",
          line: { color: "#ffffff", width: 1 },
          size: 10,
          symbol: "diamond"
        },
        customdata: ordered.map(player => [player.risk_flow_1w_direction, player.latest_change_from_date, player.latest_change_to_date]),
        hovertemplate: "%{y}<br>Risk-on exposure change: %{x:+.2f}bn<br>Direction: %{customdata[0]}<br>Week: %{customdata[1]} to %{customdata[2]}<extra></extra>"
      };
      const t = themeTokens();
      Plotly.react(chart, [...barTraces, totalTrace], {
        barmode: "group",
        margin: { l: 155, r: 24, t: 18, b: 54 },
        paper_bgcolor: t.paper,
        plot_bgcolor: t.plot,
        font: { color: t.text, family: "Inter, system-ui, sans-serif" },
        legend: { orientation: "h", x: 0, y: 1.14, bgcolor: "rgba(0,0,0,0)" },
        xaxis: {
          title: "1-week futures-equivalent notional flow ($bn); positive = risk-on contribution",
          gridcolor: t.grid,
          zerolinecolor: t.zero,
          tickformat: "+.1f"
        },
        yaxis: { automargin: true },
        hovermode: "closest"
      }, { responsive: true, displaylogo: false });
    }

    function renderCrossMarketRiskComparisonChart(players) {
      const chart = document.getElementById("crossMarketRiskCompareChart");
      if (!chart || !window.Plotly) return;
      const ordered = players.slice().sort((a, b) => Number(a.risk_flow_1w_notional_usd || 0) - Number(b.risk_flow_1w_notional_usd || 0));
      const labels = ordered.map(player => player.label);
      const series = [
        {
          name: "Latest week Δ",
          color: "#2563eb",
          values: ordered.map(player => Number(player.risk_flow_1w_notional_usd || 0) / 1e9),
          customdata: ordered.map(player => [player.risk_flow_1w_direction, player.latest_change_from_date, player.latest_change_to_date]),
          hovertemplate: "%{y}<br>Latest week change: %{x:+.2f}bn<br>Direction: %{customdata[0]}<br>Week: %{customdata[1]} to %{customdata[2]}<extra></extra>"
        },
        {
          name: "13w trend",
          color: "#d97706",
          values: ordered.map(player => Number(player.risk_net_13w_change_notional_usd || 0) / 1e9),
          customdata: ordered.map(player => [player.risk_trend_13w_direction]),
          hovertemplate: "%{y}<br>13w risk-on exposure net change: %{x:+.2f}bn<br>Direction: %{customdata[0]}<extra></extra>"
        }
      ].map(trace => ({
        type: "bar",
        orientation: "h",
        name: trace.name,
        x: trace.values,
        y: labels,
        marker: { color: trace.color },
        customdata: trace.customdata,
        hovertemplate: trace.hovertemplate
      }));
      const t = themeTokens();
      Plotly.react(chart, series, {
        barmode: "group",
        margin: { l: 155, r: 24, t: 16, b: 48 },
        paper_bgcolor: t.paper,
        plot_bgcolor: t.plot,
        font: { color: t.text, family: "Inter, system-ui, sans-serif" },
        legend: { orientation: "h", x: 0, y: 1.14, bgcolor: "rgba(0,0,0,0)" },
        xaxis: {
          title: "Risk-on exposure notional change ($bn); positive = bullish risk contribution",
          gridcolor: t.grid,
          zerolinecolor: t.zero,
          tickformat: "+.1f"
        },
        yaxis: { automargin: true },
        hovermode: "closest"
      }, { responsive: true, displaylogo: false });
    }

    function renderCrossMarketRiskTrendChart(players) {
      const chart = document.getElementById("crossMarketRiskTrendChart");
      if (!chart || !window.Plotly) return;
      const t = themeTokens();
      const compactPlot = isCompactPlot();
      const traces = players.map(player => {
        const history = (player.risk_history || []).filter(row => row.date && Number.isFinite(Number(row.risk_net_notional_usd)));
        return {
          type: "scatter",
          mode: "lines",
          name: player.label,
          x: history.map(row => row.date),
          y: history.map(row => Number(row.risk_net_notional_usd) / 1e9),
          line: { color: COLORS[player.key] || "#667085", width: 2 },
          hovertemplate: `%{x}<br>${player.label}<br>Risk-on exposure net: %{y:+.1f}bn<extra></extra>`
        };
      });
      Plotly.react(chart, traces, {
        margin: { l: compactPlot ? 48 : 72, r: compactPlot ? 16 : 32, t: compactPlot ? 70 : 58, b: compactPlot ? 42 : (state.showRangeSlider ? 84 : 54) },
        paper_bgcolor: t.paper,
        plot_bgcolor: t.plot,
        font: { color: t.text, family: "Inter, system-ui, sans-serif", size: compactPlot ? 10 : 11 },
        legend: {
          orientation: "h",
          x: 0,
          y: compactPlot ? 1.22 : 1.14,
          bgcolor: "rgba(0,0,0,0)",
          font: { size: compactPlot ? 10 : 11, color: t.text }
        },
        dragmode: state.dragMode,
        xaxis: {
          ...baseXAxis(true),
          title: compactPlot ? "" : "Date"
        },
        yaxis: {
          title: compactPlot ? "" : "Risk-on exposure net ($bn)",
          gridcolor: t.grid,
          zerolinecolor: t.zero,
          zerolinewidth: 1,
          fixedrange: false,
          tickformat: "+.0f",
          hoverformat: "+.1f",
          tickfont: { color: t.muted, size: compactPlot ? 10 : 11 },
          titlefont: { color: t.text }
        },
        hovermode: "x unified",
        hoverlabel: {
          bgcolor: t.hoverBg,
          bordercolor: t.hoverBorder,
          font: { color: t.text, size: 12 }
        }
      }, plotConfig());

      if (!chart.__riskTrendRelayoutBound && typeof chart.on === "function") {
        chart.__riskTrendRelayoutBound = true;
        chart.on("plotly_relayout", ev => {
          if (state.syncing) return;
          let xChanged = false;
          if (ev["xaxis.range[0]"] && ev["xaxis.range[1]"]) {
            state.xRange = [ev["xaxis.range[0]"], ev["xaxis.range[1]"]];
            xChanged = true;
          }
          if (ev["xaxis.autorange"]) {
            state.xRange = null;
            xChanged = true;
          }
          if (xChanged) {
            window.clearTimeout(state.rebaseTimer);
            state.rebaseTimer = window.setTimeout(() => {
              if (window.Plotly) renderMainChart();
              renderStats();
              renderThresholdStats();
            }, 120);
          }
        });
      }
    }

    function renderCrossMarketUnifiedChart(players) {
      const chart = document.getElementById("crossMarketUnifiedChart");
      if (!chart || !window.Plotly) return;
      const ordered = players.slice().sort((a, b) => Number(a.risk_flow_1w_notional_usd || 0) - Number(b.risk_flow_1w_notional_usd || 0));
      const labels = ordered.map(player => player.label);
      const metricRows = [
        {
          name: "Current net",
          color: "#64748b",
          field: "risk_net_notional_usd",
          directionField: "short_term_bias",
          description: "Current SP+NQ-VIX risk-on exposure net"
        },
        {
          name: "Latest 1w flow",
          color: "#2563eb",
          field: "risk_flow_1w_notional_usd",
          directionField: "risk_flow_1w_direction",
          description: "Latest report minus prior report"
        },
        {
          name: "13w change",
          color: "#d97706",
          field: "risk_net_13w_change_notional_usd",
          directionField: "risk_trend_13w_direction",
          description: "Current net minus 13 weeks ago"
        },
        {
          name: "26w change",
          color: "#7c3aed",
          field: "risk_net_26w_change_notional_usd",
          directionField: "risk_trend_26w_direction",
          description: "Current net minus 26 weeks ago"
        }
      ];
      const traces = metricRows.map(metric => ({
        type: "bar",
        orientation: "h",
        name: metric.name,
        x: ordered.map(player => Number(player[metric.field] || 0) / 1e9),
        y: labels,
        marker: { color: metric.color },
        customdata: ordered.map(player => [
          player[metric.directionField] || "n/a",
          player.divergence || "n/a",
          metric.description
        ]),
        hovertemplate: `%{y}<br>${metric.name}: %{x:+.2f}bn<br>Direction: %{customdata[0]}<br>%{customdata[2]}<br>%{customdata[1]}<extra></extra>`
      }));
      const t = themeTokens();
      Plotly.react(chart, traces, {
        barmode: "group",
        margin: { l: 155, r: 24, t: 22, b: 58 },
        paper_bgcolor: t.paper,
        plot_bgcolor: t.plot,
        font: { color: t.text, family: "Inter, system-ui, sans-serif" },
        legend: { orientation: "h", x: 0, y: 1.16, bgcolor: "rgba(0,0,0,0)" },
        xaxis: {
          title: "Risk-on exposure ($bn); positive = bullish contribution",
          gridcolor: t.grid,
          zerolinecolor: t.zero,
          tickformat: "+.1f"
        },
        yaxis: { automargin: true },
        hovermode: "closest"
      }, { responsive: true, displaylogo: false });
    }

    function crossMarketDatasetSummary(dataset) {
      const payload = CROSS_MARKET.datasets?.[dataset] || {};
      const players = payload.players || [];
      if (!payload.available || !players.length) return null;
      const byBias = players.slice().sort((a, b) => Number(b.short_term_bias_score) - Number(a.short_term_bias_score));
      const byFlow = players.slice().sort((a, b) => Math.abs(Number(b.risk_flow_1w_notional_usd || 0)) - Math.abs(Number(a.risk_flow_1w_notional_usd || 0)));
      return {
        dataset,
        label: DATASET_LABELS[dataset] || dataset,
        reportDate: payload.report_date,
        previousReportDate: payload.previous_report_date,
        strongest: byBias[0],
        defensive: byBias[byBias.length - 1],
        largestFlow: byFlow[0],
        players
      };
    }

    function crossMarketCombinedReadHtml() {
      const summaries = ["tff", "legacy"].map(crossMarketDatasetSummary).filter(Boolean);
      if (summaries.length < 2) return "";

      const tff = summaries.find(row => row.dataset === "tff");
      const legacy = summaries.find(row => row.dataset === "legacy");
      const bullishAgreement = tff?.strongest?.short_term_bias === "Bullish" && legacy?.strongest?.short_term_bias === "Bullish";
      const defensiveCheck = legacy?.defensive?.short_term_bias === "Bearish" ? legacy.defensive : tff?.defensive;
      const headline = bullishAgreement
        ? `Risk-on impulse is confirmed: ${tff.strongest.label} leads TFF and ${legacy.strongest.label} leads Legacy.`
        : `Mixed cross-dataset read: TFF points to ${tff?.strongest?.label || "n/a"}, while Legacy points to ${legacy?.strongest?.label || "n/a"}.`;
      const checkText = defensiveCheck
        ? `Main offset: ${defensiveCheck.label} is ${String(defensiveCheck.short_term_bias || "mixed").toLowerCase()} with ${formatNotional(defensiveCheck.risk_flow_1w_notional_usd)} one-week risk-on flow.`
        : "Main offset: n/a.";
      const rows = summaries.map(summary => {
        const strongest = summary.strongest || {};
        const defensive = summary.defensive || {};
        const largestFlow = summary.largestFlow || {};
        return `
          <tr>
            <td><strong>${summary.label}</strong><div class="bt-sub">${summary.previousReportDate || "n/a"} to ${summary.reportDate || "n/a"}</div></td>
            <td><span class="${biasClass(strongest.short_term_bias)}">${strongest.label || "n/a"} ${String(strongest.short_term_bias || "").toLowerCase()}</span><div class="bt-sub">risk flow ${formatNotional(strongest.risk_flow_1w_notional_usd)}</div></td>
            <td><span class="${biasClass(defensive.short_term_bias)}">${defensive.label || "n/a"} ${String(defensive.short_term_bias || "").toLowerCase()}</span><div class="bt-sub">risk flow ${formatNotional(defensive.risk_flow_1w_notional_usd)}</div></td>
            <td><span class="${scoreClass(largestFlow.risk_flow_1w_notional_usd)}">${largestFlow.label || "n/a"}</span><div class="bt-sub">${formatNotional(largestFlow.risk_flow_1w_notional_usd)} latest risk-on flow</div></td>
          </tr>
        `;
      }).join("");

      return `
        <div class="cross-market-synthesis">
          <div class="synthesis-main">
            <div class="snapshot-kicker">Combined cross-market synthesis</div>
            <div class="snapshot-status">${headline}</div>
            <div class="snapshot-body">${checkText} Legacy and TFF are shown together as separate lenses; the categories are not forced into a false one-to-one mapping.</div>
          </div>
          <div class="synthesis-table-wrap">
            <table class="factor-table synthesis-table">
              <thead><tr><th>Lens</th><th>Strongest risk-on read</th><th>Most defensive read</th><th>Largest one-week impulse</th></tr></thead>
              <tbody>${rows}</tbody>
            </table>
          </div>
        </div>
      `;
    }

    function crossMarketNetPredictivityHtml(datasetKey) {
      const payload = CROSS_MARKET.net_position_predictivity || {};
      const rows = (payload.rows || [])
        .filter(row => row.dataset === datasetKey)
        .slice()
        .sort((a, b) => {
          const winnerRank = { combined: 0, single: 1, tie: 2 };
          const aw = winnerRank[a.winner] ?? 3;
          const bw = winnerRank[b.winner] ?? 3;
          if (aw !== bw) return aw - bw;
          return Number(b.strongest_abs_edge_pp || 0) - Number(a.strongest_abs_edge_pp || 0);
        })
        .slice(0, 6);
      if (!payload.available || !rows.length) return "";

      const countMap = {};
      for (const row of payload.counts || []) {
        if (row.dataset !== datasetKey) continue;
        countMap[row.winner] = Number(row.count || 0);
      }
      const winnerLabel = row => row.winner === "combined"
        ? "Combined"
        : row.winner === "single"
          ? row.best_single_source_label
          : "Tie";
      const sideLabel = side => side === "positive"
        ? "positive net stronger"
        : side === "negative"
          ? "negative net stronger"
          : "flat";
      const tableRows = rows.map(row => {
        const winner = winnerLabel(row);
        const activeSide = row.winner === "single" ? row.best_single_better_side : row.combined_better_side;
        return `
          <tr>
            <td><strong>${row.player}</strong><div class="bt-sub">${row.target} ${row.horizon}</div></td>
            <td>${winner}<div class="bt-sub">${sideLabel(activeSide)}</div></td>
            <td class="${scoreClass(row.combined_side_edge_pp)}">${formatSignedPp(row.combined_side_edge_pp, 1)}<div class="bt-sub">p ${Number.isFinite(Number(row.combined_hac_p)) ? Number(row.combined_hac_p).toFixed(3) : "n/a"}</div></td>
            <td class="${scoreClass(row.best_single_side_edge_pp)}">${row.best_single_source_label}: ${formatSignedPp(row.best_single_side_edge_pp, 1)}<div class="bt-sub">p ${Number.isFinite(Number(row.best_single_hac_p)) ? Number(row.best_single_hac_p).toFixed(3) : "n/a"}</div></td>
            <td class="${scoreClass(row.combined_minus_best_single_abs_edge_pp)}">${formatSignedPp(row.combined_minus_best_single_abs_edge_pp, 1)}</td>
          </tr>
        `;
      }).join("");

      return `
        <div class="cross-market-table-wrap net-predictivity-wrap">
          <div class="insight-head">
            <span>Net-position predictivity: combined vs single</span>
            <small>Wins in ${DATASET_LABELS[datasetKey]}: combined ${countMap.combined || 0}, single ${countMap.single || 0}, tie ${countMap.tie || 0}</small>
          </div>
          <table class="factor-table model-comparison-table">
            <thead><tr><th>Player / target</th><th>Winner</th><th>Combined SP+NQ-VIX edge</th><th>Best single edge</th><th>Combined minus best single</th></tr></thead>
            <tbody>${tableRows}</tbody>
          </table>
          <div class="regime-sub">${payload.methodology || ""}</div>
        </div>
      `;
    }

    function renderCrossMarketPanel() {
      if (!els.crossMarketPanel) return;
      const payload = CROSS_MARKET.datasets?.[state.dataset] || {};
      const players = payload.players || [];
      if (!payload.available || !players.length) {
        els.crossMarketPanel.innerHTML = `<p class="research-copy">Cross-market ${DATASET_LABELS[state.dataset]} positioning is unavailable.</p>`;
        return;
      }
      const sorted = players.slice().sort((a, b) => Number(b.short_term_bias_score) - Number(a.short_term_bias_score));
      const bullish = sorted[0];
      const bearish = sorted[sorted.length - 1];
      const latestWeek = payload.previous_report_date
        ? `${payload.previous_report_date} → ${payload.report_date}`
        : payload.report_date;
      const rows = players.map(player => {
        const sp = player.markets?.sp500 || {};
        const nq = player.markets?.nq || {};
        const vix = player.markets?.vix || {};
        return `
          <tr>
            <td><div class="factor-name"><span class="swatch" style="background:${COLORS[player.key] || "#667085"}"></span><span>${player.label}</span></div></td>
            <td><strong class="${biasClass(player.short_term_bias)}">${player.short_term_bias}</strong><div class="bt-sub">score ${formatSigned(player.short_term_bias_score)}</div></td>
            <td>${marketFlowCell(sp, player.sp500_flow_1w_direction)}</td>
            <td>${marketFlowCell(nq, player.nq_flow_1w_direction)}</td>
            <td>
              <div class="market-flow-cell combined-flow-cell">
                <div class="market-flow-line"><span>Net</span><strong class="${scoreClass(player.equity_net_notional_usd)}">${formatNotional(player.equity_net_notional_usd)}</strong></div>
                <div class="market-flow-line"><span>1w Δ</span><strong class="${scoreClass(player.equity_flow_1w_notional_usd)}">${formatNotional(player.equity_flow_1w_notional_usd)}</strong></div>
                ${directionBadge(player.equity_flow_1w_direction)}
              </div>
            </td>
            <td>${vixFlowCell(vix, player)}</td>
            <td>${latestTotalRiskDeltaCell(player)}</td>
            <td>${totalRiskTrendCell(player)}</td>
            <td>${player.divergence}</td>
          </tr>
        `;
      }).join("");
      const methodology = CROSS_MARKET.methodology || {};
      const sourceUrl = CROSS_MARKET.source_links?.[state.dataset] || "#";
      const datasetSwitch = ["tff", "legacy"].map(dataset => {
        const active = dataset === state.dataset;
        const available = Boolean(CROSS_MARKET.datasets?.[dataset]?.available);
        return `
          <button class="cross-market-dataset-button ${active ? "active" : ""}" type="button" data-cross-market-dataset="${dataset}" aria-pressed="${active}" ${available ? "" : "disabled"}>
            ${DATASET_LABELS[dataset] || dataset}
          </button>
        `;
      }).join("");
      els.crossMarketPanel.innerHTML = `
        <div class="cross-market-hero">
          <div>
            <div class="cross-market-title-row">
              <div class="snapshot-kicker">${DATASET_LABELS[state.dataset]} cross-market read | report ${payload.report_date}</div>
              <div class="cross-market-dataset-switch" aria-label="Cross-market COT report">${datasetSwitch}</div>
            </div>
            <div class="snapshot-status">Latest net-change week: ${latestWeek}</div>
            <div class="snapshot-body">Strongest flow bias: <span class="${biasClass(bullish.short_term_bias)}">${bullish.label} ${bullish.short_term_bias.toLowerCase()}</span>. Most defensive: <span class="${biasClass(bearish.short_term_bias)}">${bearish.label} ${bearish.short_term_bias.toLowerCase()}</span>. Risk-on exposure uses SP + NQ - VIX.</div>
          </div>
          <div class="cross-market-method">
            <strong>What value means</strong>
            <span>${methodology.notional || ""}</span>
          </div>
        </div>
        ${crossMarketCombinedReadHtml()}
        <div class="cross-market-grid">
          <div class="cross-market-chart-wrap">
            <div class="insight-head"><span>Risk-on exposure map</span><small>${latestWeek}; current net, latest flow, and 13w/26w trend in one view</small></div>
            <div id="crossMarketUnifiedChart" class="cross-market-unified-chart"></div>
          </div>
          <div class="cross-market-notes">
            <div class="insight-head"><span>Calculation guardrails</span><small>avoid false precision</small></div>
            <ul class="macro-list">
              <li>${methodology.equity_total || ""}</li>
              <li>${methodology.vix || ""}</li>
              <li>${methodology.bias || ""}</li>
              <li>${methodology.market_direction || ""}</li>
              <li>${methodology.equity_flow_direction || ""}</li>
              <li>${methodology.risk_flow_direction || ""}</li>
              <li>${methodology.risk_trend || ""}</li>
              <li><strong>${methodology.zero_sum || ""}</strong></li>
              <li><a href="${sourceUrl}" target="_blank" rel="noopener noreferrer">Current CFTC ${DATASET_LABELS[state.dataset]} source rows</a></li>
            </ul>
          </div>
        </div>
        ${crossMarketNetPredictivityHtml(state.dataset)}
        <div class="cross-market-table-wrap">
          <table class="factor-table cross-market-table">
            <thead><tr><th>Player</th><th>Composite risk bias</th><th>S&amp;P 500<br>net + 1w change</th><th>NASDAQ-100<br>net + 1w change</th><th>SP+NQ combined<br>net + 1w change</th><th>VIX flow<br>raw + risk effect</th><th>Latest risk-on exposure<br>one-week flow</th><th>Long-term risk-on exposure<br>net + 13w/26w</th><th>SP/NQ split</th></tr></thead>
            <tbody>${rows}</tbody>
          </table>
        </div>
        <div class="regime-sub">Direction is per player. Summing every player's flow is mechanically near zero because each futures long has an offsetting short. Equity net and 1w change combine SP and NQ futures-equivalent notionals; risk-on exposure subtracts VIX because VIX buying is defensive.</div>
      `;
      els.crossMarketPanel.querySelectorAll("[data-cross-market-dataset]").forEach(button => {
        button.addEventListener("click", () => {
          const dataset = button.getAttribute("data-cross-market-dataset");
          if (!dataset || dataset === state.dataset || !CROSS_MARKET.datasets?.[dataset]?.available) return;
          state.dataset = dataset;
          els.dataset.value = dataset;
          ensureActiveCategories(true);
          render();
        });
      });
      renderCrossMarketUnifiedChart(players);
    }

    function weeklyDeskSignalClass(signal) {
      if (signal === "Strong") return "strong";
      if (signal === "Elevated") return "elevated";
      if (signal === "Watch") return "watch";
      return "context";
    }

    function weeklyDeskDirectionClass(direction) {
      if (direction === "Bullish") return "score-pos";
      if (direction === "Bearish") return "score-neg";
      return "";
    }

    function weeklyDeskEdgeHtml(edge) {
      if (!edge || !edge.available) {
        return `<span class="desk-edge-chip neutral">No tested edge</span>`;
      }
      const cls = edge.tone === "supportive" ? "supportive" : edge.tone === "warning" ? "warning" : "neutral";
      const p = Number.isFinite(Number(edge.hac_p)) ? `p ${Number(edge.hac_p).toFixed(3)}` : "p n/a";
      const spread = Number.isFinite(Number(edge.top_minus_bottom)) ? `${formatSignedPp(edge.top_minus_bottom, 1)} top-bottom` : "bucket spread n/a";
      return `<span class="desk-edge-chip ${cls}">${edge.target} ${edge.horizon}: ${spread}, ${p}</span>`;
    }

    function weeklyDeskPriceHtml(payload) {
      if (!payload || !payload.available) return `<span class="desk-mini-muted">Price response n/a</span>`;
      const cls = payload.confirms ? "score-pos" : payload.contradicts ? "score-neg" : "";
      const label = payload.confirms ? "confirmed" : payload.contradicts ? "contradicted" : "mixed";
      return `<span class="${cls}">${formatSignedPct(payload.change_pct)} since report, ${label}</span>`;
    }

    function weeklyDeskPeerHtml(peer) {
      if (!peer || !peer.total) return `<span class="desk-mini-muted">No peer read</span>`;
      const cls = peer.label === "Confirmed" ? "score-pos" : peer.label === "Divergent" ? "score-neg" : "";
      return `<span class="${cls}">${peer.label}: ${peer.support}/${peer.total} peers</span>`;
    }

    function formatDeskPrice(value) {
      const n = Number(value);
      if (!Number.isFinite(n)) return "n/a";
      return n.toLocaleString(undefined, { maximumFractionDigits: n >= 100 ? 0 : 2 });
    }

    function weeklyDeskDominantDirection(rows) {
      const bull = rows
        .filter(row => row.direction === "Bullish")
        .reduce((sum, row) => sum + Number(row.composite || 0), 0);
      const bear = rows
        .filter(row => row.direction === "Bearish")
        .reduce((sum, row) => sum + Number(row.composite || 0), 0);
      if (bull > bear * 1.15) return { label: "Bullish", cls: "score-pos", bull, bear };
      if (bear > bull * 1.15) return { label: "Bearish", cls: "score-neg", bull, bear };
      return { label: "Mixed", cls: "", bull, bear };
    }

    function weeklyDeskEvidenceLabel(rows) {
      const edge = rows.find(row => row.predictive_edge?.available);
      if (edge) return weeklyDeskEdgeHtml(edge.predictive_edge);
      const retailCount = rows.filter(row => row.retail_divergence).length;
      if (retailCount) return `<span class="desk-edge-chip warning">${retailCount} retail divergence${retailCount === 1 ? "" : "s"}</span>`;
      return `<span class="desk-edge-chip neutral">No strong edge flag</span>`;
    }

    function weeklyDeskComponentClass(score) {
      const n = Number(score);
      if (!Number.isFinite(n)) return "";
      if (n >= 70) return "score-pos";
      if (n < 40) return "score-neg";
      return "";
    }

    function weeklyDeskComponentGrid(row) {
      const components = row?.score_components || [];
      if (!components.length) return "";
      return `
        <div class="weekly-score-components">
          ${components.map(component => `
            <div class="weekly-score-component">
              <span>${component.label}</span>
              <strong class="${weeklyDeskComponentClass(component.score)}">${Number(component.score).toFixed(0)}</strong>
            </div>
          `).join("")}
        </div>
      `;
    }

    function weeklyDeskContributorHtml(row) {
      const contributors = (row?.top_contributors || [])
        .filter(item => Number.isFinite(Number(item.value)))
        .sort((a, b) => Math.abs(Number(b.value)) - Math.abs(Number(a.value)))
        .slice(0, 3);
      if (!contributors.length) return `<span class="desk-mini-muted">No contribution rows</span>`;
      return contributors.map(item => `
        <div class="desk-contrib-row">
          <span>${item.label}</span>
          <strong class="${scoreClass(item.value)}">${formatSigned(item.value, 1)}</strong>
        </div>
      `).join("");
    }

    function weeklyDeskVerdictHtml(rows, selected) {
      if (!rows.length || !selected) return "";
      const leader = rows[0];
      const dominant = weeklyDeskDominantDirection(rows);
      const price = selected.price_confirmation || {};
      const priceCls = price.confirms ? "score-pos" : price.contradicts ? "score-neg" : "";
      const priceText = price.available
        ? `${formatSignedPct(price.change_pct)} since report`
        : "Price response n/a";
      const friction = [
        selected.retail_divergence ? "small traders opposite" : "small traders aligned/quiet",
        selected.peer_confirmation?.label ? `${selected.peer_confirmation.label.toLowerCase()} peers` : "peer read n/a",
        price.available ? `${price.confirms ? "price confirms" : price.contradicts ? "price contradicts" : "price mixed"}` : "price n/a"
      ].join(" | ");
      return `
        <div class="weekly-verdict-strip">
          <div class="weekly-verdict-card primary">
            <div class="brief-card-head"><span>Selected read</span><strong class="${dominant.cls}">${dominant.label}</strong></div>
            <div class="brief-card-main">${leader.market_label} ${leader.dataset_label}</div>
            <div class="brief-card-sub">Score-weighted across ${rows.length} players; leader is ${leader.player_label} (${Number(leader.composite).toFixed(0)}).</div>
          </div>
          <div class="weekly-verdict-card">
            <div class="brief-card-head"><span>Driver</span><strong>${Number(leader.composite).toFixed(0)}</strong></div>
            <div class="brief-card-main ${weeklyDeskDirectionClass(leader.direction)}">${leader.player_label} ${leader.direction}</div>
            <div class="brief-card-sub">Net/OI ${formatPct(leader.latest_net_oi_pct)} | z ${formatSigned(leader.z26)} | gas ${Number.isFinite(Number(leader.gas)) ? Number(leader.gas).toFixed(1) : "n/a"}</div>
          </div>
          <div class="weekly-verdict-card">
            <div class="brief-card-head"><span>Evidence</span><strong>${leader.signal}</strong></div>
            <div class="brief-card-main">${leader.evidence_grade || "Unknown"} confidence</div>
            <div class="brief-card-sub">${weeklyDeskEvidenceLabel(rows)}<br>${friction}</div>
          </div>
          <div class="weekly-verdict-card">
            <div class="brief-card-head"><span>Top contributors</span><strong>${Number(leader.raw_action_score || leader.composite).toFixed(0)}</strong></div>
            <div class="brief-card-main">${leader.movement_type || "Flow split n/a"}</div>
            <div class="brief-card-sub">${weeklyDeskContributorHtml(leader)}</div>
          </div>
        </div>
        ${weeklyDeskComponentGrid(leader)}
      `;
    }

    function weeklyDeskPriceResponseHtml(row) {
      const price = row?.price_confirmation || {};
      if (!price.available) return "";
      const anchorCls = scoreClass(price.anchor_distance_pct);
      return `
        <div class="weekly-price-panel">
          <div class="insight-head"><span>Anchored price response</span><small>selected setup from COT report date to latest price</small></div>
          <div class="weekly-price-grid">
            <div class="weekly-price-card">
              <div class="scorebox-label">Since report</div>
              <div class="weekly-price-value ${scoreClass(price.change_pct)}">${formatSignedPct(price.change_pct)}</div>
              <div class="desk-row-sub">${price.report_date} to ${price.latest_date}</div>
            </div>
            <div class="weekly-price-card">
              <div class="scorebox-label">Vs anchored mean</div>
              <div class="weekly-price-value ${anchorCls}">${formatSignedPct(price.anchor_distance_pct)}</div>
              <div class="desk-row-sub">Mean ${formatDeskPrice(price.anchor_mean_price)} across ${price.post_report_observations || 0} observations</div>
            </div>
            <div class="weekly-price-card">
              <div class="scorebox-label">Post-report range</div>
              <div class="weekly-price-value">${formatSignedPct(price.post_report_low_pct)} / ${formatSignedPct(price.post_report_high_pct)}</div>
              <div class="desk-row-sub">Low ${formatDeskPrice(price.post_report_low_price)} | high ${formatDeskPrice(price.post_report_high_price)}</div>
            </div>
            <div class="weekly-price-card">
              <div class="scorebox-label">Interpretation</div>
              <div class="weekly-price-value ${price.confirms ? "score-pos" : price.contradicts ? "score-neg" : ""}">${price.confirms ? "Confirms positioning" : price.contradicts ? "Fades positioning" : "Mixed response"}</div>
              <div class="desk-row-sub">${WEEKLY_DESK.methodology?.price || ""}</div>
            </div>
          </div>
        </div>
      `;
    }

    function weeklyDeskRowHtml(row) {
      const signalClass = weeklyDeskSignalClass(row.signal);
      return `
        <tr>
          <td>
            <div class="desk-row-main">${row.market_label}</div>
            <div class="desk-row-sub">${row.dataset_label}</div>
          </td>
          <td>
            <div class="factor-name">
              <span class="swatch" style="background:${COLORS[row.player_key] || "#667085"}"></span>
              <span>${row.player_label}</span>
            </div>
          </td>
          <td><span class="desk-score-pill ${signalClass}">${Number(row.composite).toFixed(0)}</span><div class="desk-row-sub">${row.signal}</div></td>
          <td><strong class="${weeklyDeskDirectionClass(row.direction)}">${row.direction}</strong><div class="desk-row-sub">${row.movement_type || "Flow split n/a"}</div></td>
          <td>
            <div class="desk-score-stack">
              <span>T ${Number(row.timing_score).toFixed(0)}</span>
              <span>R ${Number(row.positioning_regime_score).toFixed(0)}</span>
              <span>X ${Number(row.risk_on_exposure_score).toFixed(0)}</span>
              <span>C ${Number(row.confidence_score).toFixed(0)}</span>
            </div>
            <div class="desk-row-sub">${row.evidence_grade || "Unknown"} confidence</div>
          </td>
          <td>${Number.isFinite(Number(row.percentile)) ? `${Number(row.percentile).toFixed(1)}%` : "n/a"}<div class="desk-row-sub">z ${formatSigned(row.z26)}</div></td>
          <td class="${scoreClass(row.weekly_change)}">${signedNumber(row.weekly_change)}<div class="desk-row-sub">signed pctile ${Number.isFinite(Number(row.weekly_change_percentile)) ? `${Number(row.weekly_change_percentile).toFixed(1)}%` : "n/a"} | size pctile ${Number.isFinite(Number(row.weekly_change_magnitude_percentile)) ? `${Number(row.weekly_change_magnitude_percentile).toFixed(1)}%` : "n/a"}</div><div class="desk-row-sub">long ${signedNumber(row.long_change)} | short ${signedNumber(row.short_change)}</div></td>
          <td>${row.retail_divergence ? `<span class="desk-edge-chip warning">small traders opposite</span>` : `<span class="desk-mini-muted">small traders aligned/quiet</span>`}</td>
          <td>${weeklyDeskPriceHtml(row.price_confirmation)}<div class="desk-row-sub">${row.price_divergence ? "price divergence active" : "no major price divergence"}</div></td>
          <td>${weeklyDeskEdgeHtml(row.predictive_edge)}</td>
        </tr>
      `;
    }

    function renderWeeklyDeskPanel() {
      if (!els.weeklyDeskPanel) return;
      const rows = WEEKLY_DESK.rows || [];
      if (!WEEKLY_DESK.available || !rows.length) {
        els.weeklyDeskPanel.innerHTML = `<p class="research-copy">Weekly desk data is unavailable. Run the dashboard builder after the COT outputs and predictivity CSVs exist.</p>`;
        return;
      }

      const selectedRows = rows
        .filter(row => row.dataset === state.dataset && row.market === state.market)
        .sort((a, b) => Number(b.composite) - Number(a.composite));
      const topRows = rows.slice(0, 10);
      const selected = selectedRows[0] || topRows[0];
      const top = topRows[0];
      const selectedEdge = selectedRows.find(row => row.predictive_edge?.available)?.predictive_edge || selected?.predictive_edge;
      const selectedPrice = selected?.price_confirmation || {};
      const selectedPeer = selected?.peer_confirmation || {};
      const marketTitle = `${MARKET_LABELS[state.market]} ${DATASET_LABELS[state.dataset]}`;

      const selectedCards = selectedRows.slice(0, 3).map(row => `
        <div class="weekly-brief-card ${weeklyDeskSignalClass(row.signal)}">
          <div class="brief-card-head">
            <span>${row.player_label}</span>
            <strong>${Number(row.composite).toFixed(0)}</strong>
          </div>
          <div class="brief-card-main ${weeklyDeskDirectionClass(row.direction)}">${row.direction}</div>
          <div class="brief-card-sub">Net/OI ${formatPct(row.latest_net_oi_pct)} | percentile ${Number.isFinite(Number(row.percentile)) ? `${Number(row.percentile).toFixed(1)}%` : "n/a"}</div>
          <div class="brief-card-sub">${row.movement_type || "Flow split n/a"} | 1w pctile ${Number.isFinite(Number(row.weekly_change_percentile)) ? `${Number(row.weekly_change_percentile).toFixed(1)}%` : "n/a"}</div>
          <div class="brief-card-sub">Impulse size pctile ${Number.isFinite(Number(row.weekly_change_magnitude_percentile)) ? `${Number(row.weekly_change_magnitude_percentile).toFixed(1)}%` : "n/a"} | confidence ${Number(row.confidence_score).toFixed(0)}</div>
          <div class="brief-card-edge">${weeklyDeskEdgeHtml(row.predictive_edge)}</div>
        </div>
      `).join("");

      els.weeklyDeskPanel.innerHTML = `
        <div class="weekly-desk-hero">
          <div>
            <div class="snapshot-kicker">Local COT weekly desk | ${selected?.report_date || "n/a"}</div>
            <div class="snapshot-status">${WEEKLY_DESK.headline}</div>
            <div class="snapshot-body">Default read is evidence-first: timing, medium-term regime, risk-on exposure, and confidence are scored separately before the final setup score is shown.</div>
          </div>
          <div class="weekly-desk-hero-card">
            <div class="scorebox-label">Top setup</div>
            <div class="weekly-top-line">${top.market_label} / ${top.player_label}</div>
            <div><span class="desk-score-pill ${weeklyDeskSignalClass(top.signal)}">${Number(top.composite).toFixed(0)}</span> <strong class="${weeklyDeskDirectionClass(top.direction)}">${top.direction}</strong> <span class="desk-mini-muted">${top.evidence_grade || "Unknown"} confidence</span></div>
          </div>
        </div>

        <div class="weekly-brief-grid">
          <div class="weekly-brief-main">
            <div class="insight-head"><span>${marketTitle} brief</span><small>selected by current dashboard controls</small></div>
            ${weeklyDeskVerdictHtml(selectedRows, selected)}
            <div class="weekly-brief-cards">${selectedCards || `<div class="snapshot-empty">No selected-market desk rows available.</div>`}</div>
          </div>
          <div class="weekly-brief-side">
            <div class="insight-head"><span>Confirmation chain</span><small>price, peers, predictive edge</small></div>
          <div class="desk-confirm-row"><span>Price since report</span><strong>${weeklyDeskPriceHtml(selectedPrice)}</strong></div>
          <div class="desk-confirm-row"><span>Peer confirmation</span><strong>${weeklyDeskPeerHtml(selectedPeer)}</strong></div>
          <div class="desk-confirm-row"><span>Backtested edge</span><strong>${weeklyDeskEdgeHtml(selectedEdge)}</strong></div>
          <div class="desk-confirm-row"><span>Position flow type</span><strong>${selected?.movement_type || "Flow split n/a"}</strong></div>
            <div class="desk-method-note">${WEEKLY_DESK.methodology?.scope || ""}</div>
          </div>
        </div>

        ${weeklyDeskPriceResponseHtml(selected)}

        <div class="weekly-scanner-block">
          <div class="insight-head"><span>Top local setup scanner</span><small>confidence-gated 0-100 score with component scores</small></div>
          <div class="weekly-scanner-table-wrap">
            <table class="factor-table weekly-scanner-table">
              <thead>
                <tr>
                  <th>Market</th>
                  <th>Player</th>
                  <th>Score</th>
                  <th>Bias</th>
                  <th>Components</th>
                  <th>Crowding</th>
                  <th>1w impulse</th>
                  <th>Small traders</th>
                  <th>Price response</th>
                  <th>Predictive edge</th>
                </tr>
              </thead>
              <tbody>${topRows.map(weeklyDeskRowHtml).join("")}</tbody>
            </table>
          </div>
          <div class="desk-method-note">${WEEKLY_DESK.methodology?.score || ""}</div>
        </div>
      `;
    }

    function latestHoldingDeltasForMacro() {
      return holdingDeltaRows()
        .slice()
        .sort((a, b) => Math.abs(b.netPctDelta) - Math.abs(a.netPctDelta));
    }

    function factorDelta(key) {
      const rows = latestTwoFactorRecords(key);
      if (!rows) return null;
      const [previous, latest] = rows;
      return {
        previousDate: previous.date,
        latestDate: latest.date,
        previousValue: Number(previous.value),
        latestValue: Number(latest.value),
        delta: Number(latest.value) - Number(previous.value)
      };
    }

    function latestLiquidityRows(key, count = 2) {
      const byDate = new Map();
      for (const row of LIQUIDITY_DATA.definitions?.[key]?.records || []) {
        if (!row.date || !Number.isFinite(Number(row.value))) continue;
        byDate.set(row.date, row);
      }
      return Array.from(byDate.values())
        .sort((a, b) => String(a.date).localeCompare(String(b.date)))
        .slice(-count);
    }

    function liquidityDelta(key, lookback = 1) {
      const rows = latestLiquidityRows(key, lookback + 1);
      if (rows.length < lookback + 1) return null;
      const previous = rows[0];
      const latest = rows[rows.length - 1];
      return {
        key,
        label: LIQUIDITY_DATA.definitions?.[key]?.label || key,
        source: LIQUIDITY_DATA.definitions?.[key]?.source || "",
        polarity: LIQUIDITY_DATA.definitions?.[key]?.polarity || "positive",
        previousDate: previous.date,
        latestDate: latest.date,
        previousValue: Number(previous.value),
        latestValue: Number(latest.value),
        delta: Number(latest.value) - Number(previous.value)
      };
    }

    function formatUsdBn(value) {
      const n = Number(value);
      if (!Number.isFinite(n)) return "n/a";
      return `$${n.toLocaleString(undefined, { maximumFractionDigits: 0 })}bn`;
    }

    function formatUsdBnDelta(value) {
      const n = Number(value);
      if (!Number.isFinite(n)) return "n/a";
      return `${n > 0 ? "+" : ""}$${n.toLocaleString(undefined, { maximumFractionDigits: 0 })}bn`;
    }

    function formatUsdMn(value) {
      const n = Number(value);
      if (!Number.isFinite(n)) return "n/a";
      return `${n > 0 ? "+" : ""}$${n.toLocaleString(undefined, { maximumFractionDigits: 0 })}mn`;
    }

    function formatNotional(value, signed = true) {
      if (value == null) return "n/a";
      const n = Number(value);
      if (!Number.isFinite(n)) return "n/a";
      const abs = Math.abs(n);
      const prefix = signed && n > 0 ? "+" : (n < 0 ? "-" : "");
      const amount = abs >= 1e12
        ? `${(abs / 1e12).toFixed(2)}tn`
        : abs >= 1e9
          ? `${(abs / 1e9).toFixed(1)}bn`
          : abs >= 1e6
            ? `${(abs / 1e6).toFixed(1)}mn`
            : abs.toLocaleString(undefined, { maximumFractionDigits: 0 });
      return `${prefix}$${amount}`;
    }

    function formatRate(value) {
      const n = Number(value);
      if (!Number.isFinite(n)) return "n/a";
      return `${n.toFixed(2)}%`;
    }

    function formatSpread(value) {
      const n = Number(value);
      if (!Number.isFinite(n)) return "n/a";
      return `${n > 0 ? "+" : ""}${(n * 100).toFixed(0)} bps`;
    }

    function latestFundingRows(key, count = 2) {
      const byDate = new Map();
      const records = LIQUIDITY_DATA.funding?.definitions?.[key]?.records || [];
      for (const row of records) {
        if (!row.date || !Number.isFinite(Number(row.value))) continue;
        byDate.set(row.date, row);
      }
      return Array.from(byDate.values())
        .sort((a, b) => String(a.date).localeCompare(String(b.date)))
        .slice(-count);
    }

    function fundingDelta(key, lookback = 1) {
      const rows = latestFundingRows(key, lookback + 1);
      if (rows.length < lookback + 1) return null;
      const previous = rows[0];
      const latest = rows[rows.length - 1];
      const def = LIQUIDITY_DATA.funding?.definitions?.[key] || {};
      return {
        key,
        label: def.label || key,
        source: def.source || "",
        polarity: def.polarity || "negative",
        previousDate: previous.date,
        latestDate: latest.date,
        previousValue: Number(previous.value),
        latestValue: Number(latest.value),
        delta: Number(latest.value) - Number(previous.value)
      };
    }

    function fundingCard(key, title, formatter = formatRate) {
      const row = fundingDelta(key, 1);
      if (!row) {
        return `
          <div class="liquidity-card">
            <div class="delta-label">${title}</div>
            <div class="delta-main">n/a</div>
            <div class="delta-sub">No funding data available</div>
          </div>
        `;
      }
      const changeFormatter = key === "sofr_iorb_spread" ? formatSpread : value => `${value > 0 ? "+" : ""}${value.toFixed(2)}pp`;
      return `
        <div class="liquidity-card">
          <div class="delta-label">${title}</div>
          <div class="delta-main">${formatter(row.latestValue)}</div>
          <div class="delta-change ${directionClass(row.delta, row.polarity === "negative")}">${changeFormatter(row.delta)}</div>
          <div class="delta-sub">${row.previousDate} to ${row.latestDate}</div>
        </div>
      `;
    }

    function liquidityClass(row) {
      if (!row) return "";
      return directionClass(row.delta, row.polarity === "negative");
    }

    function liquidityCard(key, title, lookback = 1) {
      const row = liquidityDelta(key, lookback);
      if (!row) {
        return `
          <div class="liquidity-card">
            <div class="delta-label">${title}</div>
            <div class="delta-main">n/a</div>
            <div class="delta-sub">No liquidity data available</div>
          </div>
        `;
      }
      return `
        <div class="liquidity-card">
          <div class="delta-label">${title}</div>
          <div class="delta-main">${formatUsdBn(row.latestValue)}</div>
          <div class="delta-change ${liquidityClass(row)}">${formatUsdBnDelta(row.delta)}</div>
          <div class="delta-sub">${row.previousDate} to ${row.latestDate}</div>
        </div>
      `;
    }

    function liquidityPosture() {
      const net1 = liquidityDelta("net_liquidity", 1);
      const net4 = liquidityDelta("net_liquidity", 4);
      const rrp = liquidityDelta("reverse_repo", 1);
      const tga = liquidityDelta("treasury_cash", 1);
      const reserves = liquidityDelta("bank_reserves", 1);
      const vix = factorDelta("fred_vix");
      const netImpulse = net4?.delta ?? net1?.delta ?? 0;
      const vixImpulse = vix?.delta ?? 0;
      let label = "Neutral liquidity impulse";
      let detail = "Net liquidity is not giving a strong directional push; defer to COT, VIX, and price trend.";
      let cls = "amber";
      if (netImpulse > 50 && vixImpulse <= 0) {
        label = "Liquidity tailwind";
        detail = "Net liquidity is expanding while volatility is not rising. That supports holding risk, but still does not justify chasing extended price.";
        cls = "green";
      } else if (netImpulse > 50 && vixImpulse > 0) {
        label = "Liquidity support, volatility stress";
        detail = "Liquidity is improving, but VIX is rising. Treat this as pullback-entry context only after price stabilizes.";
        cls = "amber";
      } else if (netImpulse < -50 && vixImpulse > 0) {
        label = "Liquidity drain with stress";
        detail = "Net liquidity is falling and volatility is rising. Defense, hedges, or smaller risk are favored.";
        cls = "red";
      } else if (netImpulse < -50) {
        label = "Liquidity headwind";
        detail = "Net liquidity is contracting. Do not add risk without strong price confirmation.";
        cls = "red";
      }
      const drivers = [];
      if (rrp) drivers.push(`RRP ${formatUsdBnDelta(rrp.delta)} (${rrp.polarity === "negative" ? "higher RRP drains liquidity" : ""})`);
      if (tga) drivers.push(`TGA ${formatUsdBnDelta(tga.delta)} (higher Treasury cash drains liquidity)`);
      if (reserves) drivers.push(`Reserves ${formatUsdBnDelta(reserves.delta)}`);
      if (vix) drivers.push(`VIX ${signedPoints(vix.delta)}`);
      return { label, detail, cls, net1, net4, rrp, tga, reserves, vix, drivers };
    }

    function renderFundingStressChart() {
      const el = document.getElementById("fundingStressChart");
      if (!el) return;
      const funding = LIQUIDITY_DATA.funding?.definitions || {};
      const sofrRows = funding.sofr?.records || [];
      const effrRows = funding.effr?.records || [];
      const iorbRows = funding.iorb?.records || [];
      const spreadRows = funding.sofr_iorb_spread?.records || [];
      const effrSpreadRows = funding.effr_iorb_spread?.records || [];
      const calendarRows = MACRO_MONITOR.funding_calendar?.daily || [];
      if (!window.Plotly || !spreadRows.length) {
        el.innerHTML = `<div class="plotly-missing">Funding chart requires SOFR and IORB records.</div>`;
        return;
      }
      const t = themeTokens();
      const traces = [
        {
          type: "bar",
          x: calendarRows.map(row => row.date),
          y: calendarRows.map(row => Number(row.treasury_issuance_bn) || 0),
          name: "Treasury issuance",
          yaxis: "y3",
          marker: { color: "rgba(100, 116, 139, 0.34)" },
          hovertemplate: "<b>Treasury issuance</b><br>%{x|%Y-%m-%d}<br>$%{y:.0f}bn<extra></extra>"
        },
        {
          type: "scatter",
          mode: "lines",
          x: sofrRows.map(row => row.date),
          y: sofrRows.map(row => row.value),
          name: "SOFR",
          line: { color: COLORS.sofr || "#2563eb", width: 2.2 },
          hovertemplate: "<b>SOFR</b><br>%{x|%Y-%m-%d}<br>%{y:.2f}%<extra></extra>"
        },
        {
          type: "scatter",
          mode: "lines",
          x: iorbRows.map(row => row.date),
          y: iorbRows.map(row => row.value),
          name: "IORB",
          line: { color: COLORS.iorb || "#dc2626", width: 2.2 },
          hovertemplate: "<b>IORB</b><br>%{x|%Y-%m-%d}<br>%{y:.2f}%<extra></extra>"
        },
        {
          type: "scatter",
          mode: "lines",
          x: effrRows.map(row => row.date),
          y: effrRows.map(row => row.value),
          name: "EFFR",
          line: { color: COLORS.effr || "#0891b2", width: 1.8, dash: "dot" },
          hovertemplate: "<b>EFFR</b><br>%{x|%Y-%m-%d}<br>%{y:.2f}%<extra></extra>"
        },
        {
          type: "scatter",
          mode: "lines",
          x: spreadRows.map(row => row.date),
          y: spreadRows.map(row => Number(row.value) * 100),
          name: "SOFR - IORB",
          yaxis: "y2",
          line: { color: COLORS.sofr_iorb_spread || "#f97316", width: 2.4 },
          hovertemplate: "<b>SOFR - IORB</b><br>%{x|%Y-%m-%d}<br>%{y:.0f} bps<extra></extra>"
        },
        {
          type: "scatter",
          mode: "lines",
          x: effrSpreadRows.map(row => row.date),
          y: effrSpreadRows.map(row => Number(row.value) * 100),
          name: "EFFR - IORB",
          yaxis: "y2",
          line: { color: COLORS.effr_iorb_spread || "#f59e0b", width: 1.8, dash: "dash" },
          hovertemplate: "<b>EFFR - IORB</b><br>%{x|%Y-%m-%d}<br>%{y:.0f} bps<extra></extra>"
        }
      ];
      Plotly.react(el, traces, {
        paper_bgcolor: t.paper,
        plot_bgcolor: t.plot,
        font: { color: t.text, size: 11 },
        hovermode: "x unified",
        dragmode: state.dragMode,
        hoverlabel: { bgcolor: t.hoverBg, bordercolor: t.hoverBorder, font: { color: t.text, size: 12 } },
        legend: { orientation: "h", x: 0, y: 1.22, font: { color: t.text, size: 11 }, bgcolor: t.legendBg },
        margin: { l: 42, r: 72, t: 56, b: state.showRangeSlider && !isCompactPlot() ? 76 : 44 },
        xaxis: { ...baseXAxis(true) },
        yaxis: { title: "Rate", ticksuffix: "%", gridcolor: t.grid, tickfont: { color: t.muted }, titlefont: { color: t.text } },
        yaxis2: { title: "Spread bps", overlaying: "y", side: "right", showgrid: false, tickfont: { color: t.muted }, titlefont: { color: t.text }, zeroline: true, zerolinecolor: t.zero },
        yaxis3: { title: "Issuance $bn", overlaying: "y", side: "right", position: 0.94, showgrid: false, visible: false },
        shapes: [
          { type: "line", xref: "paper", x0: 0, x1: 1, yref: "y2", y0: 0, y1: 0, line: { color: t.zero, width: 1, dash: "dash" } }
        ]
      }, plotConfig());
    }

    function fundingCalendarHtml() {
      const calendar = MACRO_MONITOR.funding_calendar || {};
      const upcoming = calendar.upcoming || [];
      const rows = upcoming.map(row => `
        <tr>
          <td>${row.date}<div class="factor-sub">${row.issuer}</div></td>
          <td>${row.label}</td>
          <td>${row.amount_bn === null || row.amount_bn === undefined ? "scheduled" : formatUsdBn(row.amount_bn)}</td>
        </tr>
      `).join("");
      const notes = (calendar.source_notes || []).map(note => `<li>${note}</li>`).join("");
      return `
        <div class="delta-section">
          <div class="insight-head">
            <span>Funding calendar</span>
            <small>${calendar.as_of || "n/a"} + 14d</small>
          </div>
          <table class="factor-table update-delta-table compact">
            <thead><tr><th>Date</th><th>Event</th><th>Amount</th></tr></thead>
            <tbody>${rows || `<tr><td colspan="3">No near-term funding events available.</td></tr>`}</tbody>
          </table>
          <ul class="macro-list macro-note-list funding-note-list">${notes}</ul>
        </div>
      `;
    }

    function renderLiquidityPanel() {
      if (!els.liquidityPanel) return;
      const definitions = LIQUIDITY_DATA.definitions || {};
      if (!definitions.net_liquidity?.records?.length) {
        els.liquidityPanel.innerHTML = `<p class="research-copy">No liquidity data available. Rebuild the dashboard with FRED liquidity series enabled.</p>`;
        return;
      }
      const posture = liquidityPosture();
      const net = posture.net1;
      const net4 = posture.net4;
      const latestNet = latestLiquidityRows("net_liquidity", 1)[0];
      const plumbingScore = Number(MACRO_MONITOR.latest?.liquidity_plumbing_score);
      const plumbingLabel = !Number.isFinite(plumbingScore)
        ? "n/a"
        : plumbingScore >= 70
          ? "Ample / easy"
          : plumbingScore >= 55
            ? "Supportive"
            : plumbingScore >= 45
              ? "Balanced"
              : plumbingScore >= 30
                ? "Restrictive"
                : "Stressed / scarce";
      const componentRows = ["fed_balance_sheet", "treasury_cash", "reverse_repo", "bank_reserves", "bank_treasury_agency"].map(key => {
        const row = liquidityDelta(key, 1);
        if (!row) return "";
        return `
          <tr>
            <td>${row.label}<div class="factor-sub">${row.source}</div></td>
            <td>${formatUsdBn(row.latestValue)}</td>
            <td class="${liquidityClass(row)}">${formatUsdBnDelta(row.delta)}</td>
            <td>${row.latestDate}</td>
          </tr>
        `;
      }).join("");
      const fundingRows = ["sofr", "effr", "iorb", "sofr_iorb_spread", "effr_iorb_spread"].map(key => {
        const row = fundingDelta(key, 1);
        if (!row) return "";
        const isSpread = key.includes("_iorb_spread");
        return `
          <tr>
            <td>${row.label}<div class="factor-sub">${row.source}</div></td>
            <td>${isSpread ? formatSpread(row.latestValue) : formatRate(row.latestValue)}</td>
            <td class="${directionClass(row.delta, row.polarity === "negative")}">${isSpread ? formatSpread(row.delta) : `${row.delta > 0 ? "+" : ""}${row.delta.toFixed(2)}pp`}</td>
            <td>${row.latestDate}</td>
          </tr>
        `;
      }).join("");
      els.liquidityPanel.innerHTML = `
        <div class="liquidity-hero ${posture.cls}">
          <div>
            <div class="snapshot-kicker">US liquidity proxy</div>
            <div class="snapshot-status">${posture.label}</div>
            <div class="snapshot-body">${posture.detail}</div>
            <div class="liquidity-driver-line">${posture.drivers.join(" | ")}</div>
          </div>
          <div class="liquidity-score-stack">
            <div class="snapshot-scorebox ${scorecardClass(plumbingScore)}">
              <div class="scorebox-label">Fed / bank plumbing score</div>
              <div class="scorebox-value">${Number.isFinite(plumbingScore) ? plumbingScore.toFixed(0) : "n/a"}<span class="scorebox-denominator"> / 100</span></div>
              <div class="scorebox-sub">${plumbingLabel}</div>
            </div>
            <div class="snapshot-scorebox">
              <div class="scorebox-label">Net liquidity</div>
              <div class="scorebox-value">${formatUsdBn(latestNet?.value)}</div>
              <div class="scorebox-sub">${latestNet?.date || "n/a"}</div>
            </div>
          </div>
        </div>
        <div class="liquidity-card-grid">
          ${liquidityCard("net_liquidity", "1-observation net change", 1)}
          ${liquidityCard("net_liquidity", "4-observation net change", 4)}
          ${liquidityCard("bank_reserves", "Bank reserves", 1)}
          ${liquidityCard("reverse_repo", "Reverse repo", 1)}
          ${liquidityCard("treasury_cash", "Treasury cash / TGA", 1)}
          ${liquidityCard("bank_treasury_agency", "Bank UST/agency", 1)}
          ${fundingCard("sofr", "SOFR")}
          ${fundingCard("effr", "EFFR")}
          ${fundingCard("iorb", "IORB")}
          ${fundingCard("sofr_iorb_spread", "SOFR - IORB", formatSpread)}
          ${fundingCard("effr_iorb_spread", "EFFR - IORB", formatSpread)}
        </div>
        <div class="delta-section">
          <div class="insight-head">
            <span>Repo funding stress</span>
            <small>SOFR, IORB, spread, and Treasury settlement bars</small>
          </div>
          <div id="fundingStressChart" class="funding-stress-chart"></div>
        </div>
        <div class="delta-section">
          <div class="insight-head">
            <span>Liquidity components</span>
            <small>USD billions; net liquidity = Fed balance sheet - RRP - TGA</small>
          </div>
          <table class="factor-table update-delta-table">
            <thead><tr><th>Series</th><th>Latest</th><th>Change</th><th>Date</th></tr></thead>
            <tbody>${componentRows}</tbody>
          </table>
        </div>
        <div class="delta-section">
          <div class="insight-head">
            <span>Funding rates</span>
            <small>positive SOFR-IORB spread is funding pressure</small>
          </div>
          <table class="factor-table update-delta-table">
            <thead><tr><th>Series</th><th>Latest</th><th>Change</th><th>Date</th></tr></thead>
            <tbody>${fundingRows}</tbody>
          </table>
        </div>
        ${fundingCalendarHtml()}
      `;
      renderFundingStressChart();
    }

    function macroStatusClass(label) {
      const text = String(label || "").toLowerCase();
      if (text.includes("strong") || text.includes("supportive")) return "green";
      if (text.includes("risk-off") || text.includes("defensive")) return "red";
      return "amber";
    }

    function macroFormat(value, unit = "number", decimals = 1) {
      if (value === null || value === undefined) return "n/a";
      const n = Number(value);
      if (!Number.isFinite(n)) return "n/a";
      if (unit === "usd_bn") return formatUsdBn(n);
      if (unit === "usd_m") return formatUsdMn(n);
      if (unit === "rate") return `${n > 0 ? "+" : ""}${n.toFixed(2)}%`;
      if (unit === "pp") return `${n > 0 ? "+" : ""}${n.toFixed(2)}pp`;
      if (unit === "pct") return `${n > 0 ? "+" : ""}${n.toFixed(2)}%`;
      if (unit === "score") return n.toFixed(0);
      return `${n > 0 ? "+" : ""}${n.toFixed(decimals)}`;
    }

    function macroLevel(value, unit = "number", decimals = 1) {
      if (value === null || value === undefined) return "n/a";
      const n = Number(value);
      if (!Number.isFinite(n)) return "n/a";
      if (unit === "usd_bn") return formatUsdBn(n);
      if (unit === "usd_m") return formatUsdMn(n);
      if (unit === "score") return n.toFixed(0);
      if (unit === "rate") return `${n.toFixed(decimals)}%`;
      if (unit === "pct" || unit === "pp") return `${n.toFixed(decimals)}%`;
      return n.toLocaleString(undefined, { maximumFractionDigits: decimals });
    }

    function macroDriverList(rows, emptyText) {
      if (!rows?.length) return `<li>${emptyText}</li>`;
      return rows.map(row => `
        <li>
          <strong>${row.label}</strong>
          <span class="${scoreClass(row.contribution)}">${formatSigned(row.contribution)} pts</span>
          <span class="macro-muted">score ${Number(row.score).toFixed(0)}${row.delta === null ? "" : ` | ${row.delta_label || "4w"} ${macroFormat(row.delta, row.unit)}`}</span>
        </li>
      `).join("");
    }

    function macroMiniMetric(label, value, unit, cls = "") {
      return `
        <div class="macro-metric ${cls}">
          <div class="delta-label">${label}</div>
          <div class="delta-main">${macroLevel(value, unit)}</div>
        </div>
      `;
    }

    function macroDataRows(items) {
      return items.map(item => `
        <tr>
          <td>${item.label}<div class="factor-sub">${item.source || ""}</div></td>
          <td>${macroLevel(item.value, item.unit, item.decimals ?? 1)}</td>
          <td class="${directionClass(item.change, item.invert)}">${macroFormat(item.change, item.changeUnit || item.unit)}</td>
          <td>${item.note || ""}</td>
        </tr>
      `).join("");
    }

    function scorecardClass(value) {
      const n = Number(value);
      if (!Number.isFinite(n)) return "";
      if (n >= 65) return "green";
      if (n <= 40) return "red";
      return "amber";
    }

    function regimePointClass(value) {
      const n = Number(value);
      if (!Number.isFinite(n)) return "";
      if (n >= 0.5) return "green";
      if (n <= -0.5) return "red";
      return "amber";
    }

    function componentScoreGrid() {
      const groups = MACRO_MONITOR.score_groups || [];
      return groups.map(row => `
        <div class="component-score ${scorecardClass(row.score)}">
          <div class="delta-label">${row.label}</div>
          <div class="component-score-main">${Number.isFinite(Number(row.score)) ? Number(row.score).toFixed(0) : "n/a"}</div>
          <div class="delta-sub">${row.label_state || "n/a"} | weight ${row.weight}</div>
        </div>
      `).join("");
    }

    function forwardPathRows() {
      const rows = MACRO_MONITOR.forward_path?.horizons || [];
      return rows.map(row => `
        <tr>
          <td>${row.horizon}</td>
          <td class="${directionClass(row.expected_liquidity_impulse_bn)}">${macroFormat(row.expected_liquidity_impulse_bn, "usd_bn")}</td>
          <td>${row.state}</td>
          <td>${row.main_driver}</td>
        </tr>
      `).join("");
    }

    function analogRowsHtml() {
      const analog = MACRO_MONITOR.historical_analogs || {};
      if (!analog.available) return `<p class="research-copy">${analog.reason || "Historical analogs are unavailable."}</p>`;
      return `
        <table class="factor-table compact">
          <thead><tr><th>Market</th><th>Horizon</th><th>Obs.</th><th>Avg</th><th>Median</th><th>Hit rate</th></tr></thead>
          <tbody>
            ${(analog.rows || []).map(row => `
              <tr>
                <td>${row.market_label}</td>
                <td>${row.horizon}</td>
                <td>${row.observations}</td>
                <td class="${directionClass(row.avg_return_pct)}">${macroFormat(row.avg_return_pct, "pct")}</td>
                <td class="${directionClass(row.median_return_pct)}">${macroFormat(row.median_return_pct, "pct")}</td>
                <td>${Number.isFinite(Number(row.hit_rate_pct)) ? `${Number(row.hit_rate_pct).toFixed(1)}%` : "n/a"}</td>
              </tr>
            `).join("")}
          </tbody>
        </table>
        <div class="factor-sub">${analog.method || ""}</div>
      `;
    }

    function freshnessRowsHtml(limit = 10) {
      const rows = MACRO_MONITOR.freshness?.rows || [];
      const prioritized = rows
        .slice()
        .sort((a, b) => {
          const rank = { stale: 0, missing: 1, fresh: 2 };
          return (rank[a.status] ?? 3) - (rank[b.status] ?? 3);
        })
        .slice(0, limit);
      return prioritized.map(row => `
        <tr>
          <td>${row.label}<div class="factor-sub">${row.source || ""}</div></td>
          <td>${row.last_date || "n/a"}</td>
          <td>${row.age_days === null || row.age_days === undefined ? "n/a" : `${row.age_days}d`}</td>
          <td><span class="freshness-status ${row.status}">${row.status}</span></td>
        </tr>
      `).join("");
    }

    function forwardAssetOutlookHtml() {
      const latest = MACRO_MONITOR.latest || {};
      const prediction = MACRO_MONITOR.prediction || {};
      const confidence = MACRO_MONITOR.confidence || {};
      const oneMonth = (MACRO_MONITOR.forward_path?.horizons || [])
        .find(row => row.horizon === "1 month");
      const score = Number(latest.liquidity_score);
      const bias = String(prediction.equity_bias_1m || "mixed").toLowerCase();
      const cls = bias === "positive" ? "green" : bias === "negative" ? "red" : "amber";
      const arrow = bias === "positive" ? "UP" : bias === "negative" ? "DOWN / DEFENSIVE" : "MIXED";
      const primaryAsset = prediction.best_affected_asset || "S&P 500 / broad risk";
      const action = bias === "positive"
        ? "Favor SPX and NQ exposure; add on controlled pullbacks while credit and funding remain calm."
        : bias === "negative"
          ? "Favor defense and smaller high-beta exposure; SPX/NQ rallies are more vulnerable to fading."
          : "Keep exposure balanced and require price confirmation before adding directional risk.";
      const invalidation = Number.isFinite(score) && score < 45
        ? "Upgrade toward neutral above 45; bullish confirmation requires above 55 with calm credit and repo spreads."
        : Number.isFinite(score) && score >= 55
          ? "Downgrade below 55; defensive below 45, especially if credit or repo spreads widen."
          : "A break above 55 turns supportive; below 45 turns defensive.";
      return `
        <section class="forward-asset-outlook ${cls}" aria-label="Forward asset outlook">
          <div class="forward-outlook-head">
            <div>
              <div class="snapshot-kicker">Forward asset outlook | next 1 month</div>
              <div class="forward-outlook-title">${primaryAsset}: ${arrow}</div>
              <div class="forward-outlook-action">${action}</div>
            </div>
            <div class="forward-outlook-bias">${bias.toUpperCase()}</div>
          </div>
          <div class="forward-outlook-grid">
            <div><span>Primary exposure</span><strong>${primaryAsset}</strong></div>
            <div><span>NQ / growth</span><strong>${bias === "negative" ? "Higher downside sensitivity" : bias === "positive" ? "Preferred high-beta expression" : "Wait for confirmation"}</strong></div>
            <div><span>Expected liquidity impulse</span><strong>${macroFormat(oneMonth?.expected_liquidity_impulse_bn, "usd_bn")}</strong></div>
            <div><span>Forecast confidence</span><strong>${confidence.label || prediction.confidence || "n/a"} (${confidence.score || "n/a"}/100)</strong></div>
          </div>
          <div class="forward-outlook-foot"><strong>Invalidation:</strong> ${invalidation} <span>Liquidity-conditioned forecast, not a guaranteed return target.</span></div>
        </section>
      `;
    }

    function renderMacroScorecard() {
      if (!els.macroScorecardPanel) return;
      if (!MACRO_MONITOR.available) {
        els.macroScorecardPanel.innerHTML = `<p class="research-copy">Macro scorecard unavailable: ${MACRO_MONITOR.error || "unknown error"}</p>`;
        return;
      }
      const latest = MACRO_MONITOR.latest || {};
      const prediction = MACRO_MONITOR.prediction || {};
      const confidence = MACRO_MONITOR.confidence || {};
      const forward = MACRO_MONITOR.forward_path || {};
      const positives = (forward.bullish_drivers || []).map(item => `<li>${item}</li>`).join("") || "<li>No dominant bullish driver.</li>";
      const negatives = (forward.bearish_drivers || []).map(item => `<li>${item}</li>`).join("") || "<li>No dominant bearish driver.</li>";
      const freshness = MACRO_MONITOR.freshness || {};
      els.macroScorecardPanel.innerHTML = `
        <div class="scorecard-hero ${regimePointClass(latest.macro_regime_score)}">
          <div>
            <div class="snapshot-kicker">Unified macro liquidity regime</div>
            <div class="scorecard-title">${latest.macro_regime_score_label || latest.regime_label || "n/a"}</div>
            <div class="snapshot-body">${prediction.trading_implication || ""}</div>
            <div class="trigger-row">
              <span class="trigger-pill">SPX: ${prediction.equity_bias_1m || "n/a"}</span>
              <span class="trigger-pill">NQ/growth: ${prediction.best_affected_asset || "n/a"}</span>
              <span class="trigger-pill">Freshness: ${freshness.status || "n/a"}</span>
              <span class="trigger-pill">Price/COT score weight: 0%</span>
            </div>
          </div>
          <div class="scorecard-scorebox">
            <div class="scorebox-label">Unified regime score</div>
            <div class="scorecard-score">${Number.isFinite(Number(latest.macro_regime_score)) ? Number(latest.macro_regime_score).toFixed(2) : "n/a"}</div>
            <div class="scorebox-sub">Scale -2 restrictive to +2 supportive</div>
            <div class="scorebox-label confidence-label">Confidence</div>
            <div class="confidence-meter"><span style="width:${Number(confidence.score || 0)}%"></span></div>
            <div class="scorebox-sub">${confidence.score || "n/a"} / 100 - ${confidence.label || "n/a"}</div>
          </div>
        </div>
        ${forwardAssetOutlookHtml()}
        <div class="scorecard-grid">
          <div class="macro-card">
            <div class="insight-head"><span>Biggest positive drivers</span><small>weighted components</small></div>
            <ul class="macro-list">${positives}</ul>
          </div>
          <div class="macro-card">
            <div class="insight-head"><span>Biggest negative drivers</span><small>weighted components</small></div>
            <ul class="macro-list">${negatives}</ul>
          </div>
          <div class="macro-card">
            <div class="insight-head"><span>Forward expected path</span><small>liquidity impulse proxy</small></div>
            <table class="factor-table compact"><thead><tr><th>Horizon</th><th>Impulse</th><th>State</th><th>Driver</th></tr></thead><tbody>${forwardPathRows()}</tbody></table>
            <div class="factor-sub">${forward.caveat || ""}</div>
          </div>
          <div class="macro-card">
            <div class="insight-head"><span>Regime triggers</span><small>what changes the read</small></div>
            <ul class="macro-list">
              ${(forward.improves_if || []).slice(0, 2).map(item => `<li>Improves if: ${item}</li>`).join("")}
              ${(forward.deteriorates_if || []).slice(0, 2).map(item => `<li>Deteriorates if: ${item}</li>`).join("")}
            </ul>
          </div>
        </div>
        <div class="component-score-grid">${componentScoreGrid()}</div>
        <div class="scorecard-grid">
          <div class="macro-card">
            <div class="insight-head"><span>Historical analogs</span><small>similar component-score regimes</small></div>
            ${analogRowsHtml()}
          </div>
          <div class="macro-card">
            <div class="insight-head"><span>Data freshness</span><small>${freshness.warning || "n/a"}</small></div>
            <table class="factor-table compact"><thead><tr><th>Source</th><th>Latest</th><th>Age</th><th>Status</th></tr></thead><tbody>${freshnessRowsHtml()}</tbody></table>
          </div>
        </div>
      `;
    }

    function macroBacktestTable(market) {
      const rows = (MACRO_MONITOR.backtest?.rows || []).filter(row => row.market === market);
      if (!rows.length) return `<p class="research-copy">No macro score backtest rows are available.</p>`;
      return `
        <table class="factor-table macro-backtest-table">
          <thead>
            <tr>
              <th>Score bucket</th>
              <th>Horizon</th>
              <th>Avg</th>
              <th>Median</th>
              <th>Win</th>
              <th>Worst</th>
              <th>N</th>
            </tr>
          </thead>
          <tbody>
            ${rows.map(row => `
              <tr>
                <td>${row.bucket}</td>
                <td>${row.horizon}</td>
                <td class="${scoreClass(row.avg_forward_return)}">${formatSignedPct(row.avg_forward_return)}</td>
                <td class="${scoreClass(row.median_forward_return)}">${formatSignedPct(row.median_forward_return)}</td>
                <td>${row.win_rate === null || row.win_rate === undefined ? "n/a" : `${Number(row.win_rate).toFixed(1)}%`}</td>
                <td class="${scoreClass(row.worst_forward_return)}">${formatSignedPct(row.worst_forward_return)}</td>
                <td>${row.observations}</td>
              </tr>
            `).join("")}
          </tbody>
        </table>
      `;
    }

    function macroAlertsHtml() {
      const rows = MACRO_MONITOR.alerts || [];
      if (!rows.length) return `<p class="research-copy">No alert definitions are available.</p>`;
      return `
        <div class="macro-alert-grid">
          ${rows.map(row => `
            <div class="macro-alert ${row.triggered ? row.severity : "muted"}">
              <div class="regime-head">
                <div class="regime-market">${row.label}</div>
                <div class="regime-status ${row.triggered ? row.severity : "amber"}">${row.triggered ? "Triggered" : "Clear"}</div>
              </div>
              <div class="macro-alert-value">${macroFormat(row.actual, row.unit)} <span>${row.threshold}</span></div>
              <div class="factor-sub">${row.detail}</div>
            </div>
          `).join("")}
        </div>
      `;
    }

    function macroSourceMapHtml() {
      const rows = MACRO_MONITOR.source_map || [];
      return `
        <table class="factor-table compact macro-source-table">
          <thead><tr><th>Column</th><th>Source</th><th>Freq.</th><th>Unit</th><th>Use</th></tr></thead>
          <tbody>
            ${rows.map(row => `
              <tr>
                <td>${row.column}<div class="factor-sub">${row.label}</div></td>
                <td>${row.url ? `<a href="${row.url}" target="_blank" rel="noopener">${row.source}</a>` : row.source}</td>
                <td>${row.frequency}</td>
                <td>${row.unit}</td>
                <td>${row.use}</td>
              </tr>
            `).join("")}
          </tbody>
        </table>
      `;
    }

    function splitCsvLine(line) {
      const values = [];
      let current = "";
      let quoted = false;
      for (let i = 0; i < line.length; i += 1) {
        const ch = line[i];
        const next = line[i + 1];
        if (ch === '"' && quoted && next === '"') {
          current += '"';
          i += 1;
        } else if (ch === '"') {
          quoted = !quoted;
        } else if (ch === "," && !quoted) {
          values.push(current.trim());
          current = "";
        } else {
          current += ch;
        }
      }
      values.push(current.trim());
      return values;
    }

    function parseTspCsv(text) {
      const lines = text.split(/\r?\n/).map(line => line.trim()).filter(Boolean);
      if (lines.length < 2) throw new Error("CSV needs a header row and at least one data row.");
      const headers = splitCsvLine(lines[0]).map(h => h.toLowerCase());
      const required = ["date", "g_fund_assets", "f_fund_assets", "c_fund_assets", "s_fund_assets", "i_fund_assets"];
      for (const key of required) {
        if (!headers.includes(key)) throw new Error(`Missing column: ${key}`);
      }
      const rows = lines.slice(1).map(line => {
        const values = splitCsvLine(line);
        const row = Object.fromEntries(headers.map((header, index) => [header, values[index]]));
        for (const key of required.slice(1)) row[key] = Number(String(row[key]).replace(/[$,]/g, ""));
        row.date = String(row.date || "");
        row.total = required.slice(1).reduce((sum, key) => sum + (Number(row[key]) || 0), 0);
        row.g_share = row.total ? row.g_fund_assets / row.total * 100 : NaN;
        row.equity_share = row.total ? (row.c_fund_assets + row.s_fund_assets + row.i_fund_assets) / row.total * 100 : NaN;
        return row;
      }).filter(row => row.date && Number.isFinite(row.total) && row.total > 0);
      rows.sort((a, b) => a.date.localeCompare(b.date));
      if (!rows.length) throw new Error("No usable TSP rows were found.");
      return rows;
    }

    function tspSummary(rows) {
      if (!rows?.length) return null;
      const latest = rows[rows.length - 1];
      const prev1 = rows[Math.max(0, rows.length - 2)];
      const prev3 = rows[Math.max(0, rows.length - 4)];
      const gShare = row => Number(row.g_share ?? row.g_fund_share);
      const equityShare = row => Number(row.equity_share);
      const g1 = gShare(latest) - gShare(prev1);
      const g3 = gShare(latest) - gShare(prev3);
      const eq1 = equityShare(latest) - equityShare(prev1);
      const eq3 = equityShare(latest) - equityShare(prev3);
      const flowSignal = Number(latest.retirement_flow_signal);
      const score = Number.isFinite(Number(latest.score_retirement_proxy))
        ? Number(latest.score_retirement_proxy)
        : Math.max(0, Math.min(100, 50 + eq1 * 4 - g1 * 4));
      return {
        latest: {
          ...latest,
          g_share: gShare(latest),
          equity_share: equityShare(latest),
        },
        g1,
        g3,
        eq1,
        eq3,
        flowSignal,
        score
      };
    }

    function tspUploadControl() {
      return `
        <details class="macro-upload-details">
          <summary>Upload CSV override</summary>
          <label class="section-label" for="tspUpload">TSP / 401(k) manual CSV</label>
          <input id="tspUpload" type="file" accept=".csv,text/csv">
          <p class="factor-sub">Expected columns: date,g_fund_assets,f_fund_assets,c_fund_assets,s_fund_assets,i_fund_assets. Manual upload overrides this panel only.</p>
          ${state.tspError ? `<p class="score-neg">${state.tspError}</p>` : ""}
        </details>
      `;
    }

    function renderTspBox() {
      const auto = MACRO_MONITOR.retirement_proxy || {};
      const autoRows = auto.records || [];
      const usingManual = Boolean(state.tspRows?.length);
      const summary = tspSummary(usingManual ? state.tspRows : autoRows);
      if (!summary) {
        return `
          <div class="macro-upload-box">
            <div class="regime-head">
              <div class="regime-market">Automatic TSP feed unavailable</div>
              <div class="regime-status amber">Fallback</div>
            </div>
            <p class="factor-sub">The dashboard will use a neutral 50 retirement-flow score until FRTIB reports can be parsed or a CSV override is uploaded.</p>
            ${tspUploadControl()}
          </div>
        `;
      }
      const sourceLink = summary.latest.source_url && !usingManual
        ? `<a href="${summary.latest.source_url}" target="_blank" rel="noopener">FRTIB report</a>`
        : "";
      const hasFlowSignal = Number.isFinite(Number(summary.flowSignal));
      return `
        <div class="macro-upload-box">
          <div class="regime-head">
            <div class="regime-market">${usingManual ? "Manual CSV override" : "Automatic FRTIB feed"}</div>
            <div class="regime-status ${summary.score >= 55 ? "green" : summary.score < 45 ? "red" : "amber"}">score ${Number(summary.score).toFixed(0)}</div>
          </div>
          <div class="macro-metric-grid">
            ${macroMiniMetric("Proxy score", summary.score, "score", scoreClass(summary.score - 50))}
            ${macroMiniMetric("G Fund share", summary.latest.g_share, "pct")}
            ${macroMiniMetric("Equity share", summary.latest.equity_share, "pct")}
            ${hasFlowSignal
              ? macroMiniMetric("Net equity IFT", summary.flowSignal, "usd_m", directionClass(summary.flowSignal))
              : macroMiniMetric("Equity 1m chg", summary.eq1, "pct", directionClass(summary.eq1))}
          </div>
          <p class="factor-sub">Latest ${summary.latest.date}${sourceLink ? ` from ${sourceLink}` : ""}. G share ${macroFormat(summary.g1, "pct")} 1m; equity share ${macroFormat(summary.eq1, "pct")} 1m. ${usingManual ? "Manual CSV changes this panel only; the generated macro score uses the build-time feed." : "This feed is used in the generated macro score."}</p>
          ${tspUploadControl()}
        </div>
      `;
    }

    async function handleTspUpload(file) {
      if (!file) return;
      try {
        state.tspRows = parseTspCsv(await file.text());
        state.tspError = null;
      } catch (err) {
        state.tspRows = null;
        state.tspError = err?.message || "Could not parse TSP CSV.";
      }
      renderMacroMonitorPanel();
    }

    function macroCotPositioningHtml() {
      const cotRegime = evaluateRegime(state.market);
      const biggest = latestHoldingDeltasForMacro().slice(0, 4);
      const tspMode = state.tspRows?.length
        ? "manual override"
        : (MACRO_MONITOR.retirement_proxy?.available ? "automatic FRTIB" : "CSV fallback");
      return `
        <div class="macro-card">
          <div class="insight-head"><span>COT positioning context</span><small>${MARKET_LABELS[state.market]}</small></div>
          <div class="snapshot-status">${cotRegime.status.text}</div>
          <div class="factor-sub">COT score ${formatSigned(cotRegime.score)} from active percentile triggers. Use it as positioning context, not a fast macro timing signal.</div>
          <ul class="macro-list">
            ${biggest.map(row => `<li>${row.label}: <span class="${directionClass(row.netPctDelta)}">${signedPoints(row.netPctDelta)}</span> net/OI latest change</li>`).join("") || "<li>No COT shift data available.</li>"}
          </ul>
        </div>
        <div class="macro-card">
          <div class="insight-head"><span>Retirement-flow proxy</span><small>${tspMode}</small></div>
          ${renderTspBox()}
        </div>
      `;
    }

    function renderMacroScoreChart() {
      const el = document.getElementById("macroScoreChart");
      if (!el) return;
      const records = MACRO_MONITOR.records || [];
      if (!window.Plotly || !records.length) {
        el.innerHTML = `<div class="plotly-missing">Macro score chart requires Plotly and macro records.</div>`;
        return;
      }
      const t = themeTokens();
      const firstSp = records.find(row => Number.isFinite(Number(row.sp500)))?.sp500;
      const firstNq = records.find(row => Number.isFinite(Number(row.nasdaq)))?.nasdaq;
      const traces = [
        {
          type: "scatter",
          mode: "lines",
          x: records.map(row => row.date),
          y: records.map(row => row.liquidity_score),
          name: "Liquidity score",
          line: { color: COLORS.macro_score || "#f59e0b", width: 2.5 },
          hovertemplate: "<b>Macro score</b><br>%{x|%Y-%m-%d}<br>%{y:.1f}<extra></extra>"
        },
        {
          type: "scatter",
          mode: "lines",
          x: records.map(row => row.date),
          y: records.map(row => Number(row.sp500) / Number(firstSp) * 100),
          name: "S&P 500 indexed",
          yaxis: "y2",
          line: { color: t.sp500, width: 1.8 },
          hovertemplate: "<b>S&P 500 indexed</b><br>%{x|%Y-%m-%d}<br>%{y:.1f}<extra></extra>"
        },
        {
          type: "scatter",
          mode: "lines",
          x: records.map(row => row.date),
          y: records.map(row => Number(row.nasdaq) / Number(firstNq) * 100),
          name: "Nasdaq-100 indexed",
          yaxis: "y2",
          line: { color: t.nq, width: 1.8, dash: "dot" },
          hovertemplate: "<b>Nasdaq-100 indexed</b><br>%{x|%Y-%m-%d}<br>%{y:.1f}<extra></extra>"
        }
      ];
      Plotly.react(el, traces, {
        paper_bgcolor: t.paper,
        plot_bgcolor: t.plot,
        font: { color: t.text, size: 11 },
        hovermode: "x unified",
        hoverlabel: { bgcolor: t.hoverBg, bordercolor: t.hoverBorder, font: { color: t.text, size: 12 } },
        legend: { orientation: "h", x: 0, y: 1.16, font: { color: t.text, size: 11 }, bgcolor: t.legendBg },
        margin: { l: 42, r: 46, t: 30, b: 34 },
        xaxis: { showgrid: true, gridcolor: t.grid, tickfont: { color: t.muted }, tickformat: "%Y" },
        yaxis: { title: "Score", range: [0, 100], gridcolor: t.grid, tickfont: { color: t.muted }, titlefont: { color: t.text } },
        yaxis2: { title: "Indexed price", overlaying: "y", side: "right", showgrid: false, tickfont: { color: t.muted }, titlefont: { color: t.text } },
        shapes: [
          { type: "line", xref: "paper", x0: 0, x1: 1, y0: 45, y1: 45, line: { color: t.zero, width: 1, dash: "dash" } },
          { type: "line", xref: "paper", x0: 0, x1: 1, y0: 55, y1: 55, line: { color: t.zero, width: 1, dash: "dash" } }
        ]
      }, plotConfig());
    }

    function renderMacroMonitorPanel() {
      if (!els.macroMonitorPanel) return;
      if (!MACRO_MONITOR.available) {
        els.macroMonitorPanel.innerHTML = `<p class="research-copy">Macro monitor data is unavailable: ${MACRO_MONITOR.error || "unknown error"}</p>`;
        return;
      }
      const latest = MACRO_MONITOR.latest || {};
      const prediction = MACRO_MONITOR.prediction || {};
      const cls = macroStatusClass(latest.regime_label);
      const liquidityRows = macroDataRows([
        { label: "Fed total assets", source: "WALCL", value: latest.walcl, unit: "usd_bn", change: null, note: "Fed balance sheet" },
        { label: "TGA", source: "WDTGAL", value: latest.tga, unit: "usd_bn", change: latest.tga_4w_change, invert: true, note: "Higher drains liquidity" },
        { label: "Reverse repo", source: "RRPONTSYD", value: latest.rrp, unit: "usd_bn", change: latest.rrp_4w_change, invert: true, note: "Falling is supportive until near zero" },
        { label: "Bank reserves", source: "WRESBAL", value: latest.bank_reserves, unit: "usd_bn", change: latest.bank_reserves_4w_change, note: "Falling fast is funding-risk" },
        { label: "Bank UST/agency", source: "Fed H.8 B1003NCBA", value: latest.bank_treasury_agency, unit: "usd_bn", change: latest.bank_treasury_agency_4w_change, invert: true, note: "SLR balance-sheet load proxy" },
        { label: "Reserves / bank assets", source: "WRESBAL / Fed H.8 assets", value: latest.reserves_to_bank_assets_pct, unit: "pct", change: latest.reserves_to_bank_assets_4w_change, note: "Reserve abundance ratio" },
        { label: "Net liquidity", source: "WALCL - WDTGAL - RRPONTSYD", value: latest.net_liquidity, unit: "usd_bn", change: latest.net_liquidity_4w_change, note: `13w ${macroFormat(latest.net_liquidity_13w_change, "usd_bn")}` }
      ]);
      const fundingRows = macroDataRows([
        { label: "SOFR", source: "OFR / NY Fed", value: latest.sofr, unit: "rate", change: latest.sofr_4w_change, changeUnit: "pp", invert: true, note: "Repo cash rate" },
        { label: "EFFR", source: "OFR / NY Fed", value: latest.effr, unit: "rate", change: latest.effr_4w_change, changeUnit: "pp", invert: true, note: "Unsecured overnight rate" },
        { label: "IORB", source: "Fed DDP", value: latest.iorb, unit: "rate", change: latest.iorb_4w_change, changeUnit: "pp", note: "Administered reserve rate" },
        { label: "SOFR - IORB", source: "Derived", value: latest.sofr_iorb_spread, unit: "pp", change: latest.sofr_iorb_spread_4w_change, changeUnit: "pp", invert: true, note: "Positive = funding pressure" },
        { label: "EFFR - IORB", source: "Derived", value: latest.effr_iorb_spread, unit: "pp", change: latest.effr_iorb_spread_4w_change, changeUnit: "pp", invert: true, note: "Fed funds pressure" },
        { label: "SLR load proxy", source: "WRESBAL + H.8 UST/agency", value: latest.slr_balance_sheet_load, unit: "usd_bn", change: latest.slr_balance_sheet_load_4w_change, invert: true, note: "Regulatory balance-sheet load" },
        { label: "Treasury issuance next 7d", source: "Fiscal Data", value: latest.treasury_issuance_next_7d, unit: "usd_bn", change: latest.treasury_issuance_7d, invert: true, note: "Settlement cash absorption" }
      ]);
      const stressRows = macroDataRows([
        { label: "10Y real yield", source: "DFII10", value: latest.real_yield_10y, unit: "pp", change: latest.real_yield_4w_change, invert: true, note: "Nasdaq duration pressure" },
        { label: "5Y real yield", source: "DFII5", value: latest.real_yield_5y, unit: "pp", change: latest.real_yield_5y_4w_change, invert: true, note: "Front/intermediate real-rate pressure" },
        { label: "10Y nominal", source: "DGS10", value: latest.nominal_yield_10y, unit: "pp", change: null, invert: true, note: `10Y-2Y ${macroFormat(latest.yield_curve_10y_2y, "pp")}` },
        { label: "30Y nominal", source: "DGS30", value: latest.nominal_yield_30y, unit: "pp", change: latest.nominal_yield_30y_4w_change, invert: true, note: `30Y-10Y ${macroFormat(latest.yield_curve_30y_10y, "pp")}` },
        { label: "10Y-3M curve", source: "DGS10 - DGS3MO", value: latest.yield_curve_10y_3m, unit: "pp", change: null, note: "Policy restriction / recession signal" },
        { label: "HY OAS", source: "BAMLH0A0HYM2", value: latest.hy_oas, unit: "pp", change: latest.hy_oas_4w_change, invert: true, note: latest.credit_override ? "Score capped by credit override" : "Credit calm/no override" },
        { label: "IG OAS", source: "BAMLC0A0CM", value: latest.ig_oas, unit: "pp", change: latest.ig_oas_4w_change, invert: true, note: "Higher-quality credit confirmation" },
        { label: "Broad dollar", source: "DTWEXBGS", value: latest.dollar_index, unit: "number", change: latest.dollar_4w_change, invert: true, note: "Global liquidity pressure" },
        { label: "VIX", source: "VIXCLS", value: latest.vix, unit: "number", change: latest.vix_4w_change, invert: true, note: "Vol/deleveraging" },
        { label: "S&P 500 trend", source: "SP500", value: latest.sp500_13w_change_pct, unit: "pct", change: latest.sp500_13w_change_pct, note: "13w trend factor" }
      ]);

      els.macroMonitorPanel.innerHTML = `
        <div class="macro-page-grid">
          <section class="macro-page macro-page-wide">
            <div class="macro-page-title"><span>1. Composite Market Regime Overview</span><small>All seven score blocks | ${latest.date || "n/a"}</small></div>
            <div class="snapshot-hero ${cls}">
              <div>
                <div class="snapshot-kicker">Full composite regime score</div>
                <div class="snapshot-status">${Number(latest.liquidity_score).toFixed(0)} / 100 - ${latest.regime_label}</div>
                <div class="snapshot-body">${prediction.trading_implication || ""}</div>
                <div class="trigger-row">
                  <span class="trigger-pill">1m equity bias: ${prediction.equity_bias_1m || "n/a"}</span>
                  <span class="trigger-pill">Confidence: ${prediction.confidence || "n/a"}</span>
                  <span class="trigger-pill">Best affected: ${prediction.best_affected_asset || "n/a"}</span>
                </div>
              </div>
              <div class="snapshot-scorebox">
                <div class="scorebox-label">Main risk</div>
                <div class="macro-invalid">${prediction.main_risk || "n/a"}</div>
                <div class="scorebox-sub">${prediction.worst_scenario || ""}</div>
              </div>
            </div>
            <div id="macroScoreChart" class="macro-score-chart"></div>
            <div class="macro-grid">
              <div class="macro-card">
                <div class="insight-head"><span>Top positives</span><small>weighted score drivers</small></div>
                <ul class="macro-list">${macroDriverList(MACRO_MONITOR.positive_drivers, "No dominant positive driver.")}</ul>
              </div>
              <div class="macro-card">
                <div class="insight-head"><span>Top negatives</span><small>weighted score drivers</small></div>
                <ul class="macro-list">${macroDriverList(MACRO_MONITOR.negative_drivers, "No dominant negative driver.")}</ul>
              </div>
            </div>
          </section>

          <section class="macro-page">
            <div class="macro-page-title"><span>2. Fed Net Liquidity</span><small>4w / 13w impulse</small></div>
            <div class="macro-metric-grid">
              ${macroMiniMetric("Net liquidity", latest.net_liquidity, "usd_bn")}
              ${macroMiniMetric("Net 4w", latest.net_liquidity_4w_change, "usd_bn", directionClass(latest.net_liquidity_4w_change))}
              ${macroMiniMetric("Net 13w", latest.net_liquidity_13w_change, "usd_bn", directionClass(latest.net_liquidity_13w_change))}
              ${macroMiniMetric("Reserves 4w", latest.bank_reserves_4w_change, "usd_bn", directionClass(latest.bank_reserves_4w_change))}
            </div>
            <table class="factor-table compact"><thead><tr><th>Series</th><th>Latest</th><th>4w change</th><th>Signal</th></tr></thead><tbody>${liquidityRows}</tbody></table>
          </section>

          <section class="macro-page">
            <div class="macro-page-title"><span>3. Repo Funding / SLR</span><small>money-market plumbing</small></div>
            <table class="factor-table compact"><thead><tr><th>Factor</th><th>Latest</th><th>Change</th><th>Signal</th></tr></thead><tbody>${fundingRows}</tbody></table>
          </section>

          <section class="macro-page">
            <div class="macro-page-title"><span>4. Rates, Credit, Dollar, Vol</span><small>false-signal filter</small></div>
            <table class="factor-table compact"><thead><tr><th>Factor</th><th>Latest</th><th>4w change</th><th>Signal</th></tr></thead><tbody>${stressRows}</tbody></table>
          </section>

          <section class="macro-page">
            <div class="macro-page-title"><span>5. Positioning / TSP Liquidity</span><small>COT + automatic TSP feed</small></div>
            <div class="macro-grid">${macroCotPositioningHtml()}</div>
          </section>

          <section class="macro-page macro-page-wide">
            <div class="macro-page-title"><span>6. Backtest</span><small>forward return by score bucket</small></div>
            <div class="research-grid">
              <div class="research-band"><div class="research-title">S&P 500 next 20d / 60d</div>${macroBacktestTable("sp500")}</div>
              <div class="research-band"><div class="research-title">Nasdaq-100 next 20d / 60d</div>${macroBacktestTable("nasdaq")}</div>
            </div>
          </section>

          <section class="macro-page macro-page-wide">
            <div class="macro-page-title"><span>7. Alerts</span><small>current rule state</small></div>
            ${macroAlertsHtml()}
          </section>

          <section class="macro-page macro-page-wide">
            <div class="macro-page-title"><span>Data Sources and Columns</span><small>FRED-first implementation</small></div>
            ${macroSourceMapHtml()}
            <ul class="macro-list macro-note-list">${(MACRO_MONITOR.notes || []).map(note => `<li>${note}</li>`).join("")}</ul>
          </section>
        </div>
      `;
      renderMacroScoreChart();
    }

    function currentBacktestBucketRow(horizon = "4w") {
      const payload = REGIME_BACKTEST.datasets?.[state.dataset] || {};
      const latest = payload.latest?.[state.market];
      if (!latest) return null;
      return (payload.bucket_summary || []).find(row => (
        row.market === state.market && row.horizon === horizon && row.bucket === latest.bucket
      )) || null;
    }

    function macroLensRead() {
      const fullRegime = evaluateRegime(state.market);
      const cotOnly = REGIME_BACKTEST.datasets?.[state.dataset]?.latest?.[state.market];
      const bucket = cotOnly?.bucket || fullRegime.status.label;
      const vix = factorDelta("fred_vix");
      const cnnVix = factorDelta("cnn_vix");
      const fearGreed = factorDelta("cnn_fear_greed");
      const holdings = latestHoldingDeltasForMacro();
      const liquidity = liquidityPosture();
      const biggest = holdings[0];
      const backtest = currentBacktestBucketRow("4w");
      const riskOn = bucket === "Risk-On";
      const caution = bucket === "Caution";
      const mixed = bucket === "Mixed";
      const vixRising = (vix?.delta || 0) > 0 || (cnnVix?.delta || 0) > 0;
      const vixFalling = (vix?.delta || 0) < 0 && (cnnVix?.delta || 0) <= 0;
      const sentimentRising = (fearGreed?.delta || 0) > 0;

      let bottomLine = "No strong macro edge: let price trend and liquidity confirmation dominate.";
      let posture = "Hold baseline exposure; avoid forcing a trade from COT alone.";
      let invalidation = "A clean break in price trend or a reversal in holdings/VIX would override the current read.";
      if (riskOn && vixFalling) {
        bottomLine = "Risk can be held, but this is not a chase signal.";
        posture = "Hold or add only on pullbacks; do not pay up after a straight-line move.";
        invalidation = "Rising VIX plus a deterioration in the supportive COT category turns this into wait mode.";
      } else if (riskOn && vixRising) {
        bottomLine = "Risk-On COT with VIX stress is a pullback-entry setup, not a blind buy.";
        posture = "Wait for price stabilization; use the pullback if holdings remain supportive.";
        invalidation = "If stress persists and supportive holdings unwind, reduce risk.";
      } else if (caution && vixFalling) {
        bottomLine = "Caution with falling VIX is a complacency setup.";
        posture = "Do not add risk just because volatility is quiet; trim rallies or demand price confirmation.";
        invalidation = "A reset in crowded holdings or a new panic-reset signal can repair the setup.";
      } else if (caution && vixRising) {
        bottomLine = "Caution plus VIX stress argues for defense first.";
        posture = "Reduce exposure or hedge; wait for panic/reset evidence before adding.";
        invalidation = "A fast volatility reversal plus improving COT score can move this back to mixed.";
      } else if (mixed) {
        bottomLine = "Mixed COT means the macro lens defers to price and liquidity.";
        posture = "Keep baseline risk; only add if price confirms and volatility is not deteriorating.";
        invalidation = "A score move through +2 or -2 changes the posture.";
      }

      const why = [
        cotOnly
          ? `COT-only tradable score is ${formatSigned(cotOnly.score)} (${cotOnly.bucket}) from ${cotOnly.signal_date}.`
          : `Dashboard score is ${formatSigned(fullRegime.score)} (${fullRegime.status.label}).`,
        biggest
          ? `Largest latest holdings shift is ${biggest.label}: ${signedPoints(biggest.netPctDelta)} net/OI.`
          : "No holdings shift is available.",
        vix
          ? `FRED VIX changed ${signedPoints(vix.delta)} from ${vix.previousDate} to ${vix.latestDate}.`
          : "FRED VIX delta is unavailable.",
        liquidity.net4
          ? `Net liquidity 4-observation impulse is ${formatUsdBnDelta(liquidity.net4.delta)}.`
          : "Net liquidity impulse is unavailable.",
        backtest
          ? `Historically this bucket averaged ${formatSignedPct(backtest.avg_return_pct)} over 4w with ${Number(backtest.hit_rate_pct).toFixed(1)}% hit rate.`
          : "Backtest bucket evidence is unavailable."
      ];

      return {
        bottomLine,
        posture,
        invalidation,
        why,
        vix,
        cnnVix,
        fearGreed,
        backtest,
        principles: MACRO_LENS.principles || [],
        sourceNote: MACRO_LENS.source_note || ""
      };
    }

    function renderMacroLensPanel() {
      if (!els.macroLensPanel) return;
      const read = macroLensRead();
      const links = (MACRO_LENS.source_links || []).map(link => `
        <a href="${link.url}" target="_blank" rel="noopener noreferrer">${link.label}</a>
      `).join("");
      els.macroLensPanel.innerHTML = `
        <div class="macro-hero">
          <div>
            <div class="snapshot-kicker">${MARKET_LABELS[state.market]} macro posture</div>
            <div class="snapshot-status">${read.bottomLine}</div>
            <div class="snapshot-body">${read.posture}</div>
          </div>
          <div class="macro-badge">
            <div class="delta-label">Invalidation</div>
            <div class="macro-invalid">${read.invalidation}</div>
          </div>
        </div>
        <div class="macro-grid">
          <div class="macro-card">
            <div class="insight-head"><span>Why this matters</span><small>local data read</small></div>
            <ul class="macro-list">
              ${read.why.map(item => `<li>${item}</li>`).join("")}
            </ul>
          </div>
          <div class="macro-card">
            <div class="insight-head"><span>Framework</span><small>Herman Jin-inspired, not imitation</small></div>
            <ul class="macro-list">
              ${read.principles.slice(0, 5).map(item => `<li>${item}</li>`).join("")}
            </ul>
          </div>
        </div>
        <div class="macro-source">
          <strong>Source note:</strong> ${read.sourceNote}
          <div class="macro-links">${links}</div>
        </div>
      `;
    }

    function edgeBucketCard(title, row) {
      if (!row) {
        return `
          <div class="edge-card muted">
            <div class="edge-label">${title}</div>
            <div class="edge-title">No configured bucket</div>
            <div class="edge-metrics"><span>13w n/a</span><span>26w n/a</span><span>52w n/a</span></div>
          </div>
        `;
      }
      return `
        <div class="edge-card">
          <div class="edge-label">${title}</div>
          <div class="edge-title">${row.signal}</div>
          <div class="edge-metrics">
            <span class="${scoreClass(row["13w"])}">13w ${formatSignedPct(row["13w"])}</span>
            <span class="${scoreClass(row["26w"])}">26w ${formatSignedPct(row["26w"])}</span>
            <span class="${scoreClass(row["52w"])}">52w ${formatSignedPct(row["52w"])}</span>
          </div>
        </div>
      `;
    }

    function renderAnalyticSnapshot() {
      if (!els.analyticSnapshot) return;
      const research = RESEARCH[state.market] || {};
      const regime = evaluateRegime(state.market);
      const cotRows = currentSnapshotRowsForMarket(state.market)
        .map(row => ({
          ...row,
          contribution: regimeContributionForRow(state.market, row),
          distance: Math.abs(Number(row.percentile) - 50)
        }))
        .sort((a, b) => b.distance - a.distance)
        .slice(0, 3);
      const factorRows = Object.values(FACTOR_DATA.stats?.[state.market] || {})
        .map(row => {
          const percentile = Number(row.percentile);
          const contribution = regimeContributionForRow(state.market, {
            key: row.key,
            source: "factor",
            percentile
          });
          return {
            ...row,
            percentile,
            contribution,
            distance: Number.isFinite(percentile) ? Math.abs(percentile - 50) : -1
          };
        })
        .sort((a, b) => b.distance - a.distance)
        .slice(0, 3);
      const activeHits = regime.hits.slice(0, 4);
      const datasetBottomLine = state.dataset === "tff"
        ? (research.bottom_line || "No configured market summary.")
        : "Legacy model uses non-commercial, commercial, and non-reportable net/OI extremes. Total reportable is excluded to avoid scoring an aggregate twice.";
      const legacyBacktest4w = state.dataset === "legacy" ? currentBacktestBucketRow("4w") : null;

      const cotHtml = cotRows.map(row => `
        <div class="snapshot-mini-row">
          <div class="snapshot-mini-name">
            <span class="swatch" style="background:${COLORS[row.key] || "#667085"}"></span>
            <span>${row.label}</span>
          </div>
          <span class="zone-pill ${row.zone.cls}">${Math.round(row.percentile)}%</span>
          <span class="${scoreClass(row.contribution)}">${formatSigned(row.contribution)}</span>
          <span class="snapshot-mini-note">${row.signal}</span>
        </div>
      `).join("");

      const factorHtml = factorRows.length ? factorRows.map(row => {
        const bucket = row.bucket || percentileZone(row.percentile);
        const expected = row.expected_return || {};
        return `
          <div class="snapshot-mini-row">
            <div class="snapshot-mini-name">
              <span class="swatch" style="background:${COLORS[row.key] || "#667085"}"></span>
              <span>${row.label}</span>
            </div>
            <span class="zone-pill ${bucket.cls || ""}">${Number.isFinite(row.percentile) ? `${Math.round(row.percentile)}%` : "n/a"}</span>
            <span class="${scoreClass(row.contribution)}">${formatSigned(row.contribution)}</span>
            <span class="snapshot-mini-note">4w ${formatSignedPct(expected["4w"])} | 26w ${formatSignedPct(expected["26w"])}</span>
          </div>
        `;
      }).join("") : `<div class="snapshot-empty">No factor statistics available.</div>`;

      const hitHtml = activeHits.length ? activeHits.map(hit => `
        <span class="trigger-pill ${hit.weight >= 0 ? "pos" : "neg"}">
          ${hit.sourceLabel} ${hit.label}: ${Math.round(hit.percentile)}%, ${formatSigned(hit.weight)}
        </span>
      `).join("") : `<span class="trigger-pill">No active extreme triggers</span>`;

      els.analyticSnapshot.innerHTML = `
        <div class="snapshot-hero ${regime.status.cls}">
          <div>
            <div class="snapshot-kicker">${MARKET_LABELS[state.market]} ${DATASET_LABELS[state.dataset]} current read</div>
            <div class="snapshot-status">${regime.status.text}</div>
            <div class="snapshot-body">${datasetBottomLine}</div>
          </div>
          <div class="snapshot-scorebox">
            <div class="scorebox-label">Regime score</div>
            <div class="scorebox-value ${scoreClass(regime.score)}">${formatSigned(regime.score)}</div>
            <div class="scorebox-sub">${regime.highConviction} high-conviction trigger${regime.highConviction === 1 ? "" : "s"}</div>
          </div>
        </div>
        <div class="trigger-row">${hitHtml}</div>
        <div class="snapshot-grid">
          <div class="insight-card">
            <div class="insight-head">
              <span>Positioning extremes</span>
              <small>${DATASET_LABELS[state.dataset]} net/OI ranks</small>
            </div>
            <div class="snapshot-mini-table">${cotHtml}</div>
          </div>
          <div class="insight-card">
            <div class="insight-head">
              <span>Factor state</span>
              <small>Current bucket edge</small>
            </div>
            <div class="snapshot-mini-table">${factorHtml}</div>
          </div>
          <div class="insight-card edge-card-wrap">
            <div class="insight-head">
              <span>Historical edge</span>
              <small>${state.dataset === "legacy" ? "current Legacy regime bucket" : "Extreme-bucket forward returns"}</small>
            </div>
            <div class="edge-grid">
              ${state.dataset === "legacy" ? `
                <div class="edge-card">
                  <div class="edge-label">4-week Legacy profile</div>
                  <div class="edge-title">${legacyBacktest4w?.bucket || "n/a"}</div>
                  <div class="edge-metrics">
                    <span class="${scoreClass(legacyBacktest4w?.avg_return_pct)}">Average ${formatSignedPct(legacyBacktest4w?.avg_return_pct)}</span>
                    <span>${Number.isFinite(Number(legacyBacktest4w?.hit_rate_pct)) ? `${Number(legacyBacktest4w.hit_rate_pct).toFixed(1)}% hit rate` : "Hit rate n/a"}</span>
                  </div>
                </div>
                <div class="edge-card">
                  <div class="edge-label">Versus unconditional</div>
                  <div class="edge-title ${scoreClass(legacyBacktest4w?.diff_vs_unconditional_pct)}">${formatSignedPct(legacyBacktest4w?.diff_vs_unconditional_pct)}</div>
                  <div class="edge-metrics"><span>Walk-forward, post-release close</span></div>
                </div>
              ` : `
                ${edgeBucketCard("Best current bucket", research.extremes?.best?.[0])}
                ${edgeBucketCard("Weakest current bucket", research.extremes?.worst?.[0])}
              `}
            </div>
          </div>
        </div>
      `;
    }

    function renderNetTable() {
      const data = currentDataset();
      const latest = data.records[data.records.length - 1];
      const values = currentCategoryKeys().map(key => {
        const net = Number(latest[fieldFor(key, "net_oi_pct")]);
        const longPct = Number(latest[fieldFor(key, "long")]) / Number(latest.open_interest) * 100;
        const shortPct = Number(latest[fieldFor(key, "short_oi_pct")]);
        const history = data.records
          .map(r => Number(r[fieldFor(key, "net_oi_pct")]))
          .filter(v => Number.isFinite(v));
        const low = Math.min(...history);
        const high = Math.max(...history);
        const spread = high - low || 1;
        const percentile = (net - low) / spread * 100;
        return { key, label: data.categories[key], net, longPct, shortPct, low, high, percentile };
      }).filter(row => Number.isFinite(row.net));

      if (!values.length) {
        els.netTable.innerHTML = `<div class="note">No category data available.</div>`;
        return;
      }

      const rows = values.map(row => {
        const spread = row.high - row.low || 1;
        const markerLeft = Math.max(0, Math.min(100, (row.net - row.low) / spread * 100));
        const zeroLeft = row.low <= 0 && row.high >= 0 ? (0 - row.low) / spread * 100 : null;
        const fillStart = zeroLeft === null ? (row.net >= 0 ? 0 : markerLeft) : Math.min(zeroLeft, markerLeft);
        const fillEnd = zeroLeft === null ? markerLeft : Math.max(zeroLeft, markerLeft);
        const fillWidth = Math.max(1, fillEnd - fillStart);
        const badgeLeft = Math.max(8, Math.min(92, markerLeft));
        const color = COLORS[row.key] || "#667085";
        return `
          <div class="net-row">
            <div class="net-name">
              <span class="swatch" style="background:${color}"></span>
              <span class="net-name-main">${row.label}</span>
              <span class="net-name-sub">Long/OI ${formatPct(row.longPct)} | Short/OI ${formatPct(row.shortPct)}</span>
            </div>
            <div class="net-value">${formatPct(row.net)}</div>
            <div class="hist-cell">
              <div class="hist-track" title="Historical net/OI range: ${formatPct(row.low)} to ${formatPct(row.high)}">
                ${zeroLeft === null ? "" : `<div class="hist-zero" style="left:${zeroLeft}%"></div>`}
                <div class="hist-fill" style="left:${fillStart}%;width:${fillWidth}%;background:${color}"></div>
                <div class="hist-badge" style="left:${badgeLeft}%;background:${color}">${formatPct(row.net)}</div>
                <div class="hist-marker" style="left:${markerLeft}%;background:${color}"></div>
              </div>
              <div class="range-labels"><span>${formatPct(row.low)}</span><span>${formatPct(row.high)}</span></div>
            </div>
            <div class="net-value">${Math.round(row.percentile)}%</div>
          </div>
        `;
      }).join("");

      els.netTable.innerHTML = `
        <div class="oi-line">
          <span>Latest open interest</span>
          <strong>${Number(latest.open_interest).toLocaleString()}</strong>
        </div>
        <div class="net-row header">
          <div>Category</div>
          <div class="net-value">Net/OI</div>
          <div>Historical net/OI extreme</div>
          <div class="net-value">Rank</div>
        </div>
        ${rows}
      `;
    }

    function formatCorr(value) {
      if (value === null || value === undefined) return "n/a";
      const n = Number(value);
      if (!Number.isFinite(n)) return "n/a";
      return `${n > 0 ? "+" : ""}${n.toFixed(3)}`;
    }

    function formatSignedPct(value) {
      if (value === null || value === undefined) return "n/a";
      const n = Number(value);
      if (!Number.isFinite(n)) return "n/a";
      return `${n > 0 ? "+" : ""}${n.toFixed(2)}%`;
    }

    function formatSignedPp(value, decimals = 1) {
      if (value === null || value === undefined) return "n/a";
      const n = Number(value);
      if (!Number.isFinite(n)) return "n/a";
      return `${n > 0 ? "+" : ""}${n.toFixed(decimals)}pp`;
    }

    function scoreClass(value) {
      const n = Number(value);
      if (!Number.isFinite(n) || n === 0) return "";
      return n > 0 ? "score-pos" : "score-neg";
    }

    function percentileZone(percentile) {
      if (percentile >= 90) return { label: "Top 10%", cls: "high" };
      if (percentile <= 10) return { label: "Bottom 10%", cls: "low" };
      if (percentile >= 80) return { label: "Elevated", cls: "high" };
      if (percentile <= 20) return { label: "Depressed", cls: "low" };
      return { label: "Middle range", cls: "" };
    }

    function liveSignal(market, key, percentile) {
      if (key === "dealer") return "Structural offset; ignored directionally";
      const top = percentile >= 90;
      const low = percentile <= 10;
      const elevated = percentile >= 80;
      if (key === "noncommercial" && low) return "Contrarian squeeze support";
      if (key === "noncommercial" && top) return "Speculative long crowding";
      if (key === "commercial" && top) return "Contrarian commercial support";
      if (key === "commercial" && low) return "Commercial hedge pressure";
      if (key === "nonreportable" && low) return "Small-trader reset";
      if (key === "nonreportable" && top) return "Small-trader crowding";
      if (market === "nq") {
        if (key === "other_reportable" && low) return "Strong bullish reset";
        if (key === "other_reportable" && elevated) return "Medium-term caution";
        if (key === "lev_money" && low) return "Potential squeeze fuel";
        if (key === "asset_mgr" && top) return "Trend sponsorship";
        if (key === "non_reportable" && elevated) return "Late-cycle participation";
      }
      if (market === "sp500") {
        if (key === "asset_mgr" && top) return "Crowding warning";
        if (key === "lev_money" && top) return "Long-term warning";
        if (key === "non_reportable" && top) return "Crowding warning";
        if (key === "non_reportable" && low) return "Bullish reset";
        if (key === "other_reportable" && top) return "Constructive extreme";
      }
      return "Context only";
    }

    function percentileRankFromHistory(history, value) {
      const clean = history.filter(Number.isFinite).sort((a, b) => a - b);
      if (!clean.length || !Number.isFinite(value)) return NaN;
      let lt = 0;
      let eq = 0;
      for (const v of clean) {
        if (v < value) lt += 1;
        else if (v === value) eq += 1;
      }
      const avgRank = ((lt + 1) + (lt + Math.max(eq, 1))) / 2;
      return avgRank / clean.length * 100;
    }

    function snapshotRowsForMarketAt(dataset, market, index, options = {}) {
      const data = COT_DATA[dataset][market];
      const records = data.records;
      const latest = records[index];
      const historyEnd = options.expanding ? index + 1 : records.length;
      return Object.keys(data.categories).map(key => {
        const net = Number(latest[fieldFor(key, "net_oi_pct")]);
        const history = records
          .slice(0, historyEnd)
          .map(r => Number(r[fieldFor(key, "net_oi_pct")]))
          .filter(v => Number.isFinite(v));
        const percentile = percentileRankFromHistory(history, net);
        const zone = percentileZone(percentile);
        return {
          key,
          label: data.categories[key],
          source: "cot",
          sourceLabel: "COT",
          net,
          percentile,
          zone,
          signal: liveSignal(market, key, percentile)
        };
      }).filter(row => Number.isFinite(row.net));
    }

    function factorValueAtDate(factorKey, date) {
      const records = FACTOR_DATA.definitions?.[factorKey]?.records || [];
      let low = 0;
      let high = records.length - 1;
      let best = null;
      while (low <= high) {
        const mid = Math.floor((low + high) / 2);
        const row = records[mid];
        if (row.date <= date) {
          best = row;
          low = mid + 1;
        } else {
          high = mid - 1;
        }
      }
      return best ? Number(best.value) : NaN;
    }

    function factorRowsForMarketAt(dataset, market, index, options = {}) {
      const records = COT_DATA[dataset][market].records;
      const cotDate = records[index].date;
      const historyEnd = options.expanding ? index + 1 : records.length;
      return Object.entries(FACTOR_DATA.definitions || {}).map(([key, factor]) => {
        const value = factorValueAtDate(key, cotDate);
        const history = records
          .slice(0, historyEnd)
          .map(r => factorValueAtDate(key, r.date))
          .filter(Number.isFinite);
        const percentile = percentileRankFromHistory(history, value);
        const zone = percentileZone(percentile);
        return {
          key,
          label: factor.label,
          source: "factor",
          sourceLabel: "Factor",
          value,
          percentile,
          zone,
          signal: factor.label
        };
      }).filter(row => Number.isFinite(row.value));
    }

    function combinedRowsForMarketAt(dataset, market, index, options = {}) {
      return [
        ...snapshotRowsForMarketAt(dataset, market, index, options),
        ...factorRowsForMarketAt(dataset, market, index, options)
      ];
    }

    function currentSnapshotRowsForMarket(market, dataset = state.dataset) {
      const records = COT_DATA[dataset][market].records;
      return snapshotRowsForMarketAt(dataset, market, records.length - 1, { expanding: false });
    }

    function currentTffSnapshotRowsForMarket(market) {
      return currentSnapshotRowsForMarket(market, "tff");
    }

    function currentTffSnapshotRows() {
      return currentTffSnapshotRowsForMarket(state.market);
    }

    function formatSigned(value, decimals = 2) {
      const n = Number(value);
      if (!Number.isFinite(n)) return "n/a";
      return `${n > 0 ? "+" : ""}${n.toFixed(decimals)}`;
    }

    function regimeStatusFromScore(score) {
      if (score >= 2) return { bucket: "green", cls: "green", text: "Risk-On Bias", label: "Risk-On" };
      if (score <= -2) return { bucket: "red", cls: "red", text: "Caution Bias", label: "Caution" };
      return { bucket: "amber", cls: "amber", text: "Neutral / Mixed", label: "Mixed" };
    }

    function roleLabel(role) {
      return role === "entry_signal" ? "Entry" : "Risk";
    }

    function ruleSource(rule) {
      return rule.source || "cot";
    }

    function ruleMatchesRow(rule, row) {
      return rule.key === row.key && ruleSource(rule) === (row.source || "cot");
    }

    function ruleTriggered(rule, row) {
      if (!Number.isFinite(row.percentile)) return false;
      return rule.side === "high"
        ? row.percentile >= rule.threshold
        : row.percentile <= rule.threshold;
    }

    function regimeRulesFor(market, dataset = state.dataset) {
      return REGIME_RULES?.[dataset]?.[market] || [];
    }

    function activeRulesForRow(market, row, dataset = state.dataset) {
      return regimeRulesFor(market, dataset).filter(rule => ruleMatchesRow(rule, row) && ruleTriggered(rule, row));
    }

    function regimeContributionForRow(market, row, dataset = state.dataset) {
      return activeRulesForRow(market, row, dataset).reduce((sum, rule) => sum + Number(rule.weight || 0), 0);
    }

    function evaluateRegimeFromRows(market, rows, dataset = state.dataset) {
      const rules = regimeRulesFor(market, dataset);
      const hits = [];
      let score = 0;

      for (const rule of rules) {
        const row = rows.find(candidate => ruleMatchesRow(rule, candidate));
        if (!row || !ruleTriggered(rule, row)) continue;
        score += rule.weight;
        hits.push({
          key: rule.key,
          source: row.source || "cot",
          sourceLabel: row.sourceLabel || "COT",
          label: row.label,
          percentile: row.percentile,
          weight: rule.weight,
          reason: rule.reason,
          role: rule.role || "risk_filter"
        });
      }

      const status = regimeStatusFromScore(score);
      const meter = Math.max(0, Math.min(100, (score + 6) / 12 * 100));
      const highConviction = hits.filter(h => Math.abs(h.weight) >= 1.5).length;
      return { score, status, meter, hits, highConviction };
    }

    function evaluateRegime(market) {
      const records = COT_DATA[state.dataset][market].records;
      return evaluateRegimeFromRows(
        market,
        combinedRowsForMarketAt(state.dataset, market, records.length - 1, { expanding: false }),
        state.dataset
      );
    }

    function forwardReturn(records, index, weeks) {
      const end = index + weeks;
      if (end >= records.length) return null;
      const startPrice = Number(records[index].price);
      const endPrice = Number(records[end].price);
      if (!Number.isFinite(startPrice) || !Number.isFinite(endPrice) || startPrice === 0) return null;
      return (endPrice / startPrice - 1) * 100;
    }

    function maxDrawdown(records, index, weeks) {
      const end = index + weeks;
      if (end >= records.length) return null;
      const startPrice = Number(records[index].price);
      if (!Number.isFinite(startPrice) || startPrice === 0) return null;
      const lows = records.slice(index, end + 1).map(r => Number(r.price)).filter(Number.isFinite);
      if (!lows.length) return null;
      return (Math.min(...lows) / startPrice - 1) * 100;
    }

    function regimeHistory(market) {
      const records = COT_DATA[state.dataset][market].records;
      return records.map((record, index) => {
        const result = evaluateRegimeFromRows(
          market,
          combinedRowsForMarketAt(state.dataset, market, index, { expanding: true }),
          state.dataset
        );
        return {
          date: record.date,
          score: result.score,
          bucket: result.status.bucket,
          bucketLabel: result.status.label,
          lookback: index + 1,
          forward13: forwardReturn(records, index, 13),
          forward26: forwardReturn(records, index, 26),
          forward52: forwardReturn(records, index, 52),
          drawdown26: maxDrawdown(records, index, 26)
        };
      });
    }

    function average(values) {
      const clean = values.filter(Number.isFinite);
      if (!clean.length) return null;
      return clean.reduce((sum, value) => sum + value, 0) / clean.length;
    }

    function hitRate(values) {
      const clean = values.filter(Number.isFinite);
      if (!clean.length) return null;
      return clean.filter(value => value > 0).length / clean.length * 100;
    }

    function regimeStatsForMarket(market) {
      const histories = regimeHistory(market).filter(row => row.lookback >= 104);
      const buckets = [
        ["green", "Risk-On"],
        ["amber", "Mixed"],
        ["red", "Caution"]
      ];
      return buckets.map(([bucket, label]) => {
        const rows = histories.filter(row => row.bucket === bucket);
        return {
          market,
          label,
          count: rows.filter(row => Number.isFinite(row.forward26)).length,
          avg13: average(rows.map(row => row.forward13)),
          avg26: average(rows.map(row => row.forward26)),
          avg52: average(rows.map(row => row.forward52)),
          hit26: hitRate(rows.map(row => row.forward26)),
          dd26: average(rows.map(row => row.drawdown26))
        };
      });
    }

    function renderRegimeStatsTable() {
      const rows = ["sp500", "nq"].flatMap(regimeStatsForMarket);
      return `
        <table class="regime-stats-table">
          <thead>
            <tr>
              <th>Market / Regime</th>
              <th>N</th>
              <th>13w avg</th>
              <th>26w avg</th>
              <th>52w avg</th>
              <th>26w hit</th>
              <th>26w avg DD</th>
            </tr>
          </thead>
          <tbody>
            ${rows.map(row => `
              <tr>
                <td>${MARKET_LABELS[row.market]} ${row.label}</td>
                <td>${row.count}</td>
                <td class="${scoreClass(row.avg13)}">${formatSignedPct(row.avg13)}</td>
                <td class="${scoreClass(row.avg26)}">${formatSignedPct(row.avg26)}</td>
                <td class="${scoreClass(row.avg52)}">${formatSignedPct(row.avg52)}</td>
                <td>${row.hit26 === null ? "n/a" : `${row.hit26.toFixed(1)}%`}</td>
                <td class="${scoreClass(row.dd26)}">${formatSignedPct(row.dd26)}</td>
              </tr>
            `).join("")}
          </tbody>
        </table>
      `;
    }

    function renderRegimeHistoryChart() {
      const el = document.getElementById("regimeHistoryChart");
      if (!el) return;
      if (!window.Plotly) {
        el.innerHTML = `<div class="plotly-missing">Regime history chart requires Plotly. The evidence tables remain available.</div>`;
        return;
      }
      const t = themeTokens();
      const traces = ["sp500", "nq"].map(market => {
        const history = regimeHistory(market);
        return {
          type: "scatter",
          mode: "lines",
          x: history.map(row => row.date),
          y: history.map(row => row.score),
          name: `${MARKET_LABELS[market]} regime score`,
          line: {
            color: market === "sp500" ? t.sp500 : t.nq,
            width: 2
          },
          hovertemplate: `<b>${MARKET_LABELS[market]}</b><br>%{x|%Y-%m-%d}<br>Score: %{y:.2f}<extra></extra>`
        };
      });
      Plotly.react(el, traces, {
        paper_bgcolor: t.paper,
        plot_bgcolor: t.plot,
        font: { color: t.text, size: 11 },
        hovermode: "x unified",
        hoverlabel: { bgcolor: t.hoverBg, bordercolor: t.hoverBorder, font: { color: t.text, size: 12 } },
        showlegend: true,
        legend: { orientation: "h", x: 0, y: 1.16, font: { size: 11, color: t.text }, bgcolor: t.legendBg },
        margin: { l: 42, r: 16, t: 28, b: 34 },
        xaxis: {
          showgrid: true,
          gridcolor: t.grid,
          tickfont: { color: t.muted },
          tickformat: "%Y"
        },
        yaxis: {
          title: "Score",
          zeroline: true,
          zerolinecolor: t.zero,
          gridcolor: t.grid,
          tickfont: { color: t.muted },
          titlefont: { color: t.text }
        }
      }, plotConfig());
    }

    function renderRegimePanel() {
      const cards = ["sp500", "nq"].map(market => {
        const result = evaluateRegime(market);
        const active = market === state.market ? " active" : "";
        const rows = result.hits
          .sort((a, b) => Math.abs(b.weight) - Math.abs(a.weight))
          .map(hit => `
            <div class="regime-row">
              <span>${hit.reason}</span>
              <span class="regime-source">${hit.sourceLabel}</span>
              <span class="regime-pct">${Math.round(hit.percentile)}%</span>
              <span class="regime-role">${roleLabel(hit.role)}</span>
              <span class="regime-weight ${hit.weight >= 0 ? "pos" : "neg"}">${formatSigned(hit.weight)}</span>
            </div>
          `).join("");
        const rowsHtml = rows || `<div class="regime-sub">No active extreme triggers.</div>`;
        return `
          <div class="regime-card${active}">
            <div class="regime-head">
              <div class="regime-market">${MARKET_LABELS[market]}</div>
              <div class="regime-status ${result.status.cls}">${result.status.text}</div>
            </div>
            <div class="regime-score">
              <span>Score: <strong>${formatSigned(result.score)}</strong></span>
              <span>High-conviction triggers: <strong>${result.highConviction}</strong></span>
            </div>
            <div class="regime-meter">
              <div class="regime-meter-fill" style="width:${result.meter}%"></div>
              <div class="regime-meter-mid"></div>
            </div>
            <div class="regime-rows">${rowsHtml}</div>
            <div class="regime-sub">Rules standardize COT positioning, research-signal buckets, and factor percentiles into one score. This is a lagged context filter, not a fast timing signal.</div>
          </div>
        `;
      }).join("");

      const datasetNote = `<div class="regime-dataset-banner">Active scoring model: <strong>${DATASET_LABELS[state.dataset]}</strong></div>`;

      els.regimePanel.innerHTML = `
        ${datasetNote}
        <div class="regime-guide">
          <div class="regime-guide-title">How to read the score</div>
          <div class="regime-guide-grid">
            <div class="regime-guide-item green"><strong>+2 or higher: Risk-On Bias</strong><br>Constructive percentile extremes are active. This supports risk exposure, but still needs price confirmation.</div>
            <div class="regime-guide-item amber"><strong>Between -2 and +2: Neutral / Mixed</strong><br>Signals conflict or no strong top/bottom OI extreme is active. Treat it as context, not a directional call.</div>
            <div class="regime-guide-item red"><strong>-2 or lower: Caution Bias</strong><br>Crowding or weaker-forward-return extremes are active. This is mainly a risk filter and position-sizing warning.</div>
          </div>
          <p class="regime-guide-copy">Each score is the sum of active standardized rules across COT net/OI percentiles and factor percentiles. A rule only contributes when the current value is in its configured high or low percentile bucket. Entry labels mark constructive reset/contrarian conditions; Risk labels mark crowding, complacency, or weaker-forward-return conditions.</p>
        </div>
        <div class="regime-grid">${cards}</div>
        <div class="regime-detail-grid">
          <div class="regime-detail-card">
            <div class="research-title">Signal history</div>
            <div id="regimeHistoryChart" class="regime-history-chart"></div>
          </div>
          <div class="regime-detail-card">
            <div class="research-title">Forward returns by regime score bucket</div>
            ${renderRegimeStatsTable()}
            <div class="regime-sub">Stats use expanding percentile ranks with at least 104 weeks of prior context. Returns and drawdown are based on weekly COT-aligned prices, with COT and factor rules scored through the same engine.</div>
          </div>
        </div>
      `;
      renderRegimeHistoryChart();
    }

    function backtestRowsFor(market, horizon = null, bucket = null, dataset = state.dataset) {
      const payload = REGIME_BACKTEST.datasets?.[dataset] || {};
      return (payload.bucket_summary || []).filter(row => (
        row.market === market
        && (!horizon || row.horizon === horizon)
        && (!bucket || row.bucket === bucket)
      ));
    }

    function backtestPredictivityRow(market, horizon, dataset = state.dataset) {
      const payload = REGIME_BACKTEST.datasets?.[dataset] || {};
      return (payload.predictivity_summary || []).find(row => row.market === market && row.horizon === horizon) || {};
    }

    function evidencePill(label) {
      const cls = label === "Supported" || label === "Tentative" || label === "Weak"
        ? "pos"
        : label === "Contradictory" ? "neg" : "";
      return `<span class="trigger-pill ${cls}">${label || "Unclear"}</span>`;
    }

    function modelComparisonTable(market) {
      const horizons = ["1w", "4w", "13w", "26w"];
      const rows = horizons.flatMap(horizon => ["tff", "legacy"].map(dataset => {
        const row = backtestPredictivityRow(market, horizon, dataset);
        const edgeP = Number(row.risk_on_minus_caution_hac_p_value);
        const scoreP = Number(row.score_return_hac_p_value);
        const accuracy = Number(row.drift_adjusted_accuracy_pct);
        return `
          <tr>
            <td>${horizon}</td>
            <td>${DATASET_LABELS[dataset]}</td>
            <td>${evidencePill(row.evidence_grade)}</td>
            <td class="${scoreClass(row.score_return_corr)}">${formatCorr(row.score_return_corr)}</td>
            <td>${Number.isFinite(scoreP) ? scoreP.toFixed(3) : "n/a"}</td>
            <td class="${scoreClass(row.risk_on_minus_caution_avg_return_pct)}">${formatSignedPct(row.risk_on_minus_caution_avg_return_pct)}</td>
            <td>${Number.isFinite(edgeP) ? edgeP.toFixed(3) : "n/a"}</td>
            <td>${Number.isFinite(accuracy) ? `${accuracy.toFixed(1)}%` : "n/a"}</td>
            <td>${row.minimum_directional_bucket_observations ?? "n/a"}</td>
          </tr>
        `;
      })).join("");
      return `
        <table class="factor-table regime-backtest-table model-comparison-table">
          <thead><tr><th>Horizon</th><th>Model</th><th>Evidence</th><th>Score r</th><th>Score HAC p</th><th>Risk-On - Caution</th><th>Edge HAC p</th><th>Drift-adjusted hit</th><th>Min bucket N</th></tr></thead>
          <tbody>${rows}</tbody>
        </table>
      `;
    }

    function metricTriplet(row) {
      if (!row) return "n/a";
      return `
        <div class="bt-return ${scoreClass(row.avg_return_pct)}">${formatSignedPct(row.avg_return_pct)}</div>
        <div class="bt-sub">${Number(row.hit_rate_pct).toFixed(0)}% hit | DD ${formatSignedPct(row.avg_drawdown_pct)}</div>
      `;
    }

    function renderRegimeBacktestPanel() {
      if (!els.regimeBacktestPanel) return;
      const datasetBacktest = REGIME_BACKTEST.datasets?.[state.dataset] || {};
      if (!datasetBacktest.available) {
        const script = state.dataset === "legacy" ? "cot_legacy_regime_score_backtest.py" : "cot_regime_score_backtest.py";
        els.regimeBacktestPanel.innerHTML = `<p class="research-copy">Run ${script} to generate ${DATASET_LABELS[state.dataset]} backtest evidence.</p>`;
        return;
      }
      const latest = datasetBacktest.latest?.[state.market];
      if (!latest) {
        els.regimeBacktestPanel.innerHTML = `<p class="research-copy">No backtest history is available for ${MARKET_LABELS[state.market]}.</p>`;
        return;
      }
      const horizons = ["1d", "2d", "3d", "1w", "2w", "4w", "13w", "26w", "52w"];
      const buckets = ["Risk-On", "Mixed", "Caution"];
      const bucketRows = horizons.map(horizon => {
        const rows = Object.fromEntries(backtestRowsFor(state.market, horizon).map(row => [row.bucket, row]));
        const pred = backtestPredictivityRow(state.market, horizon);
        return `
          <tr>
            <td>${horizon}</td>
            ${buckets.map(bucket => `<td>${metricTriplet(rows[bucket])}</td>`).join("")}
            <td class="${scoreClass(pred.score_return_corr)}">${formatCorr(pred.score_return_corr)}</td>
            <td>${pred.score_return_hac_p_value === null || pred.score_return_hac_p_value === undefined ? "n/a" : Number(pred.score_return_hac_p_value).toFixed(3)}</td>
            <td>${evidencePill(pred.evidence_grade)}</td>
          </tr>
        `;
      }).join("");
      const currentRows = backtestRowsFor(state.market, null, latest.bucket);
      const staleWarning = latest.is_stale
        ? `<div class="data-warning">Backtest snapshot is stale: showing report ${latest.report_date}; latest actionable report is ${latest.expected_report_date}. Refresh the dashboard before using this regime.</div>`
        : "";
      const currentProfile = horizons.map(horizon => {
        const row = currentRows.find(item => item.horizon === horizon);
        if (!row) return "";
        return `
          <tr>
            <td>${horizon}</td>
            <td>${row.observations}</td>
            <td class="${scoreClass(row.avg_return_pct)}">${formatSignedPct(row.avg_return_pct)}</td>
            <td>${Number(row.hit_rate_pct).toFixed(1)}%</td>
            <td class="${scoreClass(row.avg_drawdown_pct)}">${formatSignedPct(row.avg_drawdown_pct)}</td>
            <td class="${scoreClass(row.worst_drawdown_pct)}">${formatSignedPct(row.worst_drawdown_pct)}</td>
            <td class="${scoreClass(row.diff_vs_unconditional_pct)}">${formatSignedPct(row.diff_vs_unconditional_pct)}</td>
          </tr>
        `;
      }).join("");

      els.regimeBacktestPanel.innerHTML = `
        ${staleWarning}
        <div class="bt-hero">
          <div>
            <div class="snapshot-kicker">${MARKET_LABELS[state.market]} ${DATASET_LABELS[state.dataset]} COT-only tradable regime</div>
            <div class="snapshot-status">${latest.bucket} <span class="${scoreClass(latest.score)}">${formatSigned(latest.score)}</span></div>
            <div class="snapshot-body">Report ${latest.report_date}, signal close ${latest.signal_date}. Percentiles use an expanding ${latest.lookback_weeks}-week history at this point; returns start from the post-release close.</div>
          </div>
          <div class="snapshot-scorebox">
            <div class="scorebox-label">Active triggers</div>
            <div class="scorebox-value">${latest.trigger_count}</div>
            <div class="scorebox-sub">${latest.high_conviction_triggers} high conviction</div>
          </div>
        </div>
        <div class="backtest-reading-guide">
          <div><strong>What is actually walk-forward?</strong><span>Each report's percentile uses only history available at that date, and returns start after publication. The rule weights are fixed research choices, so this is not a sealed out-of-sample model-selection test.</span></div>
          <div><strong>Why HAC p-values?</strong><span>Long-horizon weekly forecasts overlap. Newey-West HAC adjusts the test for that dependence; the older unadjusted permutation p-value can overstate confidence.</span></div>
          <div><strong>Why drift-adjusted hit rate?</strong><span>It asks whether the score predicted above/below the prior expanding market return, avoiding a false “edge” from equities simply rising most of the time.</span></div>
        </div>
        <div class="research-grid">
          <div class="research-band">
            <div class="research-title">Expected forward returns by regime bucket</div>
            <table class="factor-table regime-backtest-table">
              <thead>
                <tr>
                  <th>Horizon</th>
                  <th>Risk-On</th>
                  <th>Mixed</th>
                  <th>Caution</th>
                  <th>Score r</th>
                  <th>HAC p</th>
                  <th>Evidence</th>
                </tr>
              </thead>
              <tbody>${bucketRows}</tbody>
            </table>
          </div>
          <div class="research-band">
            <div class="research-title">Current bucket profile: ${latest.bucket}</div>
            <table class="factor-table compact regime-backtest-table">
              <thead>
                <tr>
                  <th>Horizon</th>
                  <th>N</th>
                  <th>Avg</th>
                  <th>Hit</th>
                  <th>Avg DD</th>
                  <th>Worst DD</th>
                  <th>Vs all</th>
                </tr>
              </thead>
              <tbody>${currentProfile}</tbody>
            </table>
          </div>
          <div class="research-band model-comparison-band">
            <div class="research-title">Legacy versus TFF predictive evidence</div>
            ${modelComparisonTable(state.market)}
            <div class="regime-sub"><strong>Classification warning:</strong> Legacy Noncommercial is a broad reportable-speculator group. It is not equivalent to TFF Asset Managers or Leveraged Funds. TFF separates traders by business purpose; Legacy is a coarser parallel taxonomy over the same market, so the two model results are related rather than independent confirmation.</div>
          </div>
        </div>
      `;
    }

    function formatFactorValue(row) {
      const value = Number(row.latest_value);
      if (!Number.isFinite(value)) return "n/a";
      if (row.format === "score") return value.toFixed(1);
      return value.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    }

    function factorPredictivityTable() {
      const stats = FACTOR_DATA.stats?.[state.market] || {};
      const rows = Object.values(stats);
      if (!rows.length) {
        return `<p class="research-copy">No factor statistics are available for ${MARKET_LABELS[state.market]}.</p>`;
      }

      return `
        <table class="factor-table">
          <thead>
            <tr>
              <th>Factor</th>
              <th>Latest</th>
              <th>Rank</th>
              <th>1w k</th>
              <th>4w k</th>
              <th>Current bucket</th>
              <th>Score</th>
              <th>1w exp</th>
              <th>1w avg DD</th>
              <th>1w worst DD</th>
              <th>4w exp</th>
              <th>4w avg DD</th>
              <th>4w worst DD</th>
              <th>13w exp</th>
              <th>26w exp</th>
              <th>N</th>
            </tr>
          </thead>
          <tbody>
            ${rows.map(row => {
              const bucket = row.bucket || { label: "n/a", cls: "" };
              const expected = row.expected_return || {};
              const drawdown = row.expected_drawdown || {};
              const worstDrawdown = row.expected_worst_drawdown || {};
              const scoreRow = {
                key: row.key,
                source: "factor",
                percentile: Number(row.percentile)
              };
              const contribution = regimeContributionForRow(state.market, scoreRow);
              return `
                <tr>
                  <td>
                    <div class="factor-name">
                      <span class="swatch" style="background:${COLORS[row.key] || "#667085"}"></span>
                      <span>${row.label}</span>
                    </div>
                    <div class="factor-sub">${row.source} | ${row.sample_start} to ${row.sample_end} | latest ${row.latest_date}</div>
                  </td>
                  <td>${formatFactorValue(row)}</td>
                  <td><span class="zone-pill ${bucket.cls}">${Number.isFinite(Number(row.percentile)) ? `${Math.round(Number(row.percentile))}%` : "n/a"}</span></td>
                  <td class="${scoreClass(row.forward_corr?.["1w"])}">${formatCorr(row.forward_corr?.["1w"])}</td>
                  <td class="${scoreClass(row.forward_corr?.["4w"])}">${formatCorr(row.forward_corr?.["4w"])}</td>
                  <td><span class="zone-pill ${bucket.cls}">${bucket.label}</span></td>
                  <td class="${scoreClass(contribution)}">${formatSigned(contribution)}</td>
                  <td class="${scoreClass(expected["1w"])}">${formatSignedPct(expected["1w"])}</td>
                  <td class="${scoreClass(drawdown["1w"])}">${formatSignedPct(drawdown["1w"])}</td>
                  <td class="${scoreClass(worstDrawdown["1w"])}">${formatSignedPct(worstDrawdown["1w"])}</td>
                  <td class="${scoreClass(expected["4w"])}">${formatSignedPct(expected["4w"])}</td>
                  <td class="${scoreClass(drawdown["4w"])}">${formatSignedPct(drawdown["4w"])}</td>
                  <td class="${scoreClass(worstDrawdown["4w"])}">${formatSignedPct(worstDrawdown["4w"])}</td>
                  <td class="${scoreClass(expected["13w"])}">${formatSignedPct(expected["13w"])}</td>
                  <td class="${scoreClass(expected["26w"])}">${formatSignedPct(expected["26w"])}</td>
                  <td>${expected.n ?? 0}</td>
                </tr>
              `;
            }).join("")}
          </tbody>
        </table>
      `;
    }

    function factorExtremeTable() {
      const stats = FACTOR_DATA.stats?.[state.market] || {};
      const rows = [];
      for (const row of Object.values(stats)) {
        for (const [bucketKey, label] of [["bottom_10", "Bottom 10%"], ["top_10", "Top 10%"]]) {
          const expected = row.extreme_returns?.[bucketKey] || {};
          rows.push({
            factor: row.label,
            key: row.key,
            label,
            expected
          });
        }
      }
      if (!rows.length) return "";
      return `
        <table class="factor-table compact">
          <thead>
            <tr>
              <th>Factor bucket</th>
              <th>1w avg</th>
              <th>1w avg DD</th>
              <th>1w worst DD</th>
              <th>4w avg</th>
              <th>4w avg DD</th>
              <th>4w worst DD</th>
              <th>13w avg</th>
              <th>26w avg</th>
              <th>N</th>
            </tr>
          </thead>
          <tbody>
            ${rows.map(row => `
              <tr>
                <td><span class="swatch" style="background:${COLORS[row.key] || "#667085"}"></span> ${row.factor} ${row.label}</td>
                <td class="${scoreClass(row.expected["1w"])}">${formatSignedPct(row.expected["1w"])}</td>
                <td class="${scoreClass(row.expected.drawdown?.["1w"])}">${formatSignedPct(row.expected.drawdown?.["1w"])}</td>
                <td class="${scoreClass(row.expected.worst_drawdown?.["1w"])}">${formatSignedPct(row.expected.worst_drawdown?.["1w"])}</td>
                <td class="${scoreClass(row.expected["4w"])}">${formatSignedPct(row.expected["4w"])}</td>
                <td class="${scoreClass(row.expected.drawdown?.["4w"])}">${formatSignedPct(row.expected.drawdown?.["4w"])}</td>
                <td class="${scoreClass(row.expected.worst_drawdown?.["4w"])}">${formatSignedPct(row.expected.worst_drawdown?.["4w"])}</td>
                <td class="${scoreClass(row.expected["13w"])}">${formatSignedPct(row.expected["13w"])}</td>
                <td class="${scoreClass(row.expected["26w"])}">${formatSignedPct(row.expected["26w"])}</td>
                <td>${row.expected.n ?? 0}</td>
              </tr>
            `).join("")}
          </tbody>
        </table>
      `;
    }

    function sentimentReturnTable() {
      const payload = FACTOR_DATA.sentiment_return_stats || {};
      const rows = payload.markets?.[state.market] || [];
      const horizons = payload.horizons || ["1d", "2d", "3d", "4d", "5d", "6d", "7d", "2w", "3w"];
      if (!rows.length) {
        return `<p class="research-copy">No CNN Fear & Greed bucket return statistics are available for ${MARKET_LABELS[state.market]}.</p>`;
      }

      return `
        <table class="factor-table sentiment-return-table">
          <thead>
            <tr>
              <th>Fear & Greed bucket</th>
              <th>Obs</th>
              <th>Episodes</th>
              ${horizons.map(horizon => `<th>${horizon}</th>`).join("")}
            </tr>
          </thead>
          <tbody>
            ${rows.map(row => {
              const isBaseline = row.key === "baseline_all";
              return `
              <tr class="${isBaseline ? "baseline-row" : ""}">
                <td>
                  <div class="factor-name">
                    <span class="swatch" style="background:${isBaseline ? "#98a2b3" : (COLORS.cnn_fear_greed || "#f59e0b")}"></span>
                    <span>${row.label}</span>
                  </div>
                </td>
                <td>${row.observations ?? 0}</td>
                <td>${row.episodes ?? "all"}</td>
                ${horizons.map(horizon => `
                  <td>
                    <div class="${scoreClass(row[`avg_${horizon}`])}">${formatSignedPct(row[`avg_${horizon}`])}</div>
                    <div class="factor-sub">DD <span class="${scoreClass(row[`avg_drawdown_${horizon}`])}">${formatSignedPct(row[`avg_drawdown_${horizon}`])}</span>${isBaseline ? "" : ` | ${formatSignedPp(row[`drawdown_edge_${horizon}`])}`}</div>
                    <div class="factor-sub">
                      ${row[`win_rate_${horizon}`] === null || row[`win_rate_${horizon}`] === undefined ? "n/a" : `${Number(row[`win_rate_${horizon}`]).toFixed(1)}% win`}
                      ${isBaseline ? "" : `<br><span class="${scoreClass(row[`win_edge_${horizon}`])}">${formatSignedPp(row[`win_edge_${horizon}`])} win edge</span>`}
                    </div>
                  </td>
                `).join("")}
              </tr>
            `;
            }).join("")}
          </tbody>
        </table>
      `;
    }

    function renderFactorPanel() {
      els.factorPanel.innerHTML = `
        <div class="research-band">
          <div class="research-title">${MARKET_LABELS[state.market]} CNN Fear & Greed bucket returns</div>
          ${sentimentReturnTable()}
          <p class="research-copy">The first number is average forward return. DD is the average adverse move from signal close to the lowest close inside that horizon. Raw win rate is the share of observations where forward return is above 0; win edge compares that rate with the baseline row for the same market and horizon. Episodes count contiguous runs in each mutually exclusive bucket: IHaveToSell 0-7, Panican 7-10, Extreme Fear 10-25, Fear 25-45, Neutral 45-55, Greed 55-75, and Extreme Greed 75-100. Horizons are standardized as 1d through 7d, then 2w and 3w.</p>
        </div>
        <div class="research-band">
          <div class="research-title">${MARKET_LABELS[state.market]} factor predictivity and expected returns</div>
          ${factorPredictivityTable()}
          <p class="research-copy">Predictivity k uses daily FRED price data and daily factor readings. The 1w and 4w windows mean roughly 5 and 20 trading days. Avg DD is the average long-position adverse move inside the forward window; worst DD shows the worst historical adverse move in that bucket.</p>
        </div>
        <div class="research-band">
          <div class="research-title">Top/bottom 10% factor buckets</div>
          ${factorExtremeTable()}
        </div>
      `;
    }

    function correlationTable(title, values) {
      const rows = Object.entries(values).map(([key, value]) => `
        <tr>
          <td><span class="swatch" style="background:${COLORS[key] || "#667085"}"></span> ${COT_DATA.tff[state.market].categories[key] || key}</td>
          <td class="${scoreClass(value)}">${formatCorr(value)}</td>
        </tr>
      `).join("");
      return `
        <div class="research-band">
          <div class="research-title">${title}</div>
          <table class="finding-table">
            <thead><tr><th>Category</th><th>k</th></tr></thead>
            <tbody>${rows}</tbody>
          </table>
        </div>
      `;
    }

    function forwardTable(forward) {
      const cols = ["1w", "4w", "13w", "26w", "52w"];
      const rows = Object.entries(forward).map(([key, values]) => `
        <tr>
          <td><span class="swatch" style="background:${COLORS[key] || "#667085"}"></span> ${COT_DATA.tff[state.market].categories[key] || key}</td>
          ${cols.map(col => `<td class="${scoreClass(values[col])}">${formatCorr(values[col])}</td>`).join("")}
        </tr>
      `).join("");
      return `
        <div class="research-band">
          <div class="research-title">Forward-return correlation: current net/OI vs later return</div>
          <table class="finding-table">
            <thead><tr><th>Category</th>${cols.map(col => `<th>${col}</th>`).join("")}</tr></thead>
            <tbody>${rows}</tbody>
          </table>
          <p class="research-copy">Plain correlations are weak at 1-4 weeks; the useful information comes from medium-term signs and extreme buckets.</p>
        </div>
      `;
    }

    function extremesTable(title, rows) {
      if (!rows.length) return "";
      const body = rows.map(row => `
        <tr>
          <td>${row.signal}</td>
          <td class="${scoreClass(row["13w"])}">${formatSignedPct(row["13w"])}</td>
          <td class="${scoreClass(row["26w"])}">${formatSignedPct(row["26w"])}</td>
          <td class="${scoreClass(row["52w"])}">${formatSignedPct(row["52w"])}</td>
        </tr>
      `).join("");
      return `
        <div class="research-band">
          <div class="research-title">${title}</div>
          <table class="finding-table">
            <thead><tr><th>Extreme bucket</th><th>13w avg</th><th>26w avg</th><th>52w avg</th></tr></thead>
            <tbody>${body}</tbody>
          </table>
        </div>
      `;
    }

    function renderResearchPanel() {
      const research = RESEARCH[state.market];
      if (!research) {
        els.researchPanel.innerHTML = `<p class="research-copy">No research findings are configured for this market.</p>`;
        return;
      }

      const snapshotRows = currentTffSnapshotRows().map(row => `
        <div class="snapshot-row">
          <div class="snapshot-name">
            <span class="swatch" style="background:${COLORS[row.key] || "#667085"}"></span>
            <span>${row.label}</span>
          </div>
          <div class="num-cell">${formatPct(row.net)}</div>
          <div class="num-cell"><span class="zone-pill ${row.zone.cls}">${Math.round(row.percentile)}% - ${row.zone.label}</span></div>
          <div class="snapshot-signal">${row.signal}</div>
          <div class="num-cell ${scoreClass(regimeContributionForRow(state.market, row, "tff"))}">${formatSigned(regimeContributionForRow(state.market, row, "tff"))}</div>
        </div>
      `).join("");

      const datasetNote = state.dataset === "tff"
        ? ""
        : `<p class="research-copy">These findings use TFF Detailed categories even while the chart is currently set to Legacy.</p>`;
      const meta = research._meta || {};
      const generatedNote = meta.sample_end
        ? `<p class="research-copy">Research tables are auto-generated from current TFF exact consolidated data: ${meta.sample_start || "n/a"} to ${meta.sample_end}, ${meta.rows || 0} rows.</p>`
        : "";

      els.researchPanel.innerHTML = `
        ${datasetNote}
        ${generatedNote}
        <div class="research-band">
          <div class="research-title">Live current positioning read</div>
          <div class="snapshot-row header">
            <div>Category</div>
            <div class="num-cell">Net/OI</div>
            <div class="num-cell">Percentile</div>
            <div class="snapshot-signal">Research signal</div>
            <div class="num-cell">Score</div>
          </div>
          ${snapshotRows}
        </div>

        <div class="research-grid">
          ${correlationTable("Same-week PA correlation: weekly dNet/OI vs weekly return", research.same_week)}
          <div class="research-band">
            <div class="research-title">Useful signal ranking</div>
            <ul class="takeaway-list">
              ${research.takeaways.map(item => `<li>${item}</li>`).join("")}
            </ul>
          </div>
        </div>

        ${forwardTable(research.forward)}

        <div class="research-grid">
          ${extremesTable(`${MARKET_LABELS[state.market]} best extreme buckets`, research.extremes.best)}
          ${extremesTable(`${MARKET_LABELS[state.market]} weakest extreme buckets`, research.extremes.worst)}
        </div>

        <div class="research-band">
          <div class="research-title">Bottom line</div>
          <p class="research-copy">${research.bottom_line}</p>
        </div>
      `;
    }

    function categoryTrace(records, category, label, metric) {
      const field = fieldFor(category, metric);
      const s = lineSetting(category);
      return {
        type: "scatter",
        mode: "lines",
        x: records.map(r => r.date),
        y: records.map(r => r[field]),
        name: label,
        showlegend: false,
        opacity: s.opacity,
        line: { color: s.color, width: s.width, dash: s.dash },
        hovertemplate: `<b>${label}</b><br>%{x|%Y-%m-%d}<br>${metricLabels[metric]}: %{y:,.2f}<extra></extra>`
      };
    }

    function cleanDate(value) {
      return String(value || "").slice(0, 10);
    }

    function maxDate(dates) {
      return dates.filter(Boolean).map(cleanDate).sort().at(-1) || null;
    }

    function latestVisibleDataDate() {
      const cotRecords = currentDataset().records;
      const dates = [cotRecords[cotRecords.length - 1]?.date];
      for (const key of activePriceKeys()) {
        const records = PRICE_DATA[key]?.records || [];
        dates.push(records[records.length - 1]?.date);
      }
      for (const key of activeFactorKeys()) {
        const records = FACTOR_DATA.definitions?.[key]?.records || [];
        dates.push(records[records.length - 1]?.date);
      }
      return maxDate(dates);
    }

    function visibleDateRange() {
      const records = currentDataset().records;
      return {
        start: cleanDate(state.xRange?.[0] || records[0]?.date),
        end: cleanDate(state.xRange?.[1] || latestVisibleDataDate() || records[records.length - 1]?.date)
      };
    }

    function inVisibleRange(date, range = visibleDateRange()) {
      const d = cleanDate(date);
      return (!range.start || d >= range.start) && (!range.end || d <= range.end);
    }

    function priceRecordsFor(priceKey) {
      const p = PRICE_DATA[priceKey];
      const cotRecords = currentDataset().records;
      const startDate = cotRecords[0].date;
      return p.records.filter(r => r.date >= startDate);
    }

    function visiblePriceBaseDate() {
      const keys = activePriceKeys();
      if (!keys.length) return null;
      const range = visibleDateRange();
      const recordsByKey = Object.fromEntries(keys.map(key => [key, priceRecordsFor(key)]));
      const candidateDates = [...new Set(
        Object.values(recordsByKey).flatMap(records => records
          .filter(record => inVisibleRange(record.date, range) && Number.isFinite(Number(record.price)))
          .map(record => record.date))
      )].sort();
      return candidateDates.find(date => keys.every(key => recordsByKey[key].some(record => (
        record.date === date && Number.isFinite(Number(record.price))
      )))) || candidateDates[0] || null;
    }

    function priceSeries(priceKey) {
      const priceRecords = priceRecordsFor(priceKey);
      const rawPrices = priceRecords.map(r => r.price);
      const visible = visibleDateRange();
      const sharedBaseDate = visiblePriceBaseDate();
      const sharedBase = priceRecords.find(r => r.date === sharedBaseDate && Number.isFinite(Number(r.price)));
      const firstVisible = priceRecords.find(r => inVisibleRange(r.date, visible) && Number.isFinite(Number(r.price)));
      const firstAny = priceRecords.find(r => Number.isFinite(Number(r.price)));
      const baseRecord = sharedBase || firstVisible || firstAny;
      const base = Number(baseRecord?.price);
      const values = state.priceScale === "indexed" && Number.isFinite(base) && base !== 0
        ? rawPrices.map(v => v === null || v === undefined ? null : v / base * 100)
        : rawPrices;
      return { priceRecords, rawPrices, values, baseDate: baseRecord?.date || null };
    }

    function priceTrace(priceKey, halo = false) {
      const p = PRICE_DATA[priceKey];
      const { priceRecords, rawPrices, values, baseDate } = priceSeries(priceKey);
      const isIndexedPrice = state.priceScale === "indexed";
      const priceLabel = isIndexedPrice ? "Price index" : "Price";
      const t = themeTokens();
      const s = lineSetting(`${priceKey}_price`);
      const isSp500 = priceKey === "sp500";
      const traceName = halo ? `${p.label} halo` : p.label;
      const customdata = priceRecords.map((record, index) => [rawPrices[index], baseDate || "n/a"]);
      return {
        type: "scatter",
        mode: "lines",
        x: priceRecords.map(r => r.date),
        y: values,
        customdata: halo ? undefined : customdata,
        name: traceName,
        yaxis: !isIndexedPrice && !isCompactPlot() && state.showSp500 && state.showNq && priceKey === "nq" ? "y4" : "y2",
        showlegend: !halo,
        hoverinfo: halo ? "skip" : "x+y+name",
        opacity: halo ? Math.min(0.55, s.opacity) : s.opacity,
        line: {
          color: halo ? (isSp500 ? t.haloSp500 : t.haloNq) : s.color,
          width: halo ? Math.max(7, s.width + 4) : s.width,
          dash: s.dash
        },
        hovertemplate: halo ? null : `<b>${p.label}</b><br>%{x|%Y-%m-%d}<br>${priceLabel}: %{y:,.2f}${isIndexedPrice ? "<br>Raw price: %{customdata[0]:,.2f}<br>Index base: %{customdata[1]}" : ""}<extra></extra>`
      };
    }

    function buildPriceTraces() {
      const traces = [];
      if (state.showSp500) traces.push(priceTrace("sp500", true), priceTrace("sp500"));
      if (state.showNq) traces.push(priceTrace("nq", true), priceTrace("nq"));
      return traces;
    }

    function activePriceKeys() {
      const keys = [];
      if (state.showSp500) keys.push("sp500");
      if (state.showNq) keys.push("nq");
      return keys;
    }

    function factorTrace(factorKey, halo = false) {
      const factor = FACTOR_DATA.definitions[factorKey];
      const cotRecords = currentDataset().records;
      const startDate = cotRecords[0].date;
      const factorRecords = (factor.records || []).filter(r => r.date >= startDate);
      const s = lineSetting(factorKey);
      const haloColor = s.color.startsWith("#")
        ? `${s.color}22`
        : "rgba(124, 58, 237, 0.14)";
      return {
        type: "scatter",
        mode: "lines",
        x: factorRecords.map(r => r.date),
        y: factorRecords.map(r => r.value),
        name: halo ? `${factor.label} halo` : factor.label,
        yaxis: "y3",
        showlegend: !halo,
        hoverinfo: halo ? "skip" : "x+y+name",
        opacity: halo ? Math.min(0.35, s.opacity) : s.opacity,
        line: {
          color: halo ? haloColor : s.color,
          width: halo ? Math.max(6, s.width + 3) : s.width,
          dash: s.dash
        },
        hovertemplate: halo ? null : `<b>${factor.label}</b><br>%{x|%Y-%m-%d}<br>Value: %{y:,.2f}<extra></extra>`
      };
    }

    function nearestPriorFactorValue(factorRecords, date) {
      let selected = null;
      for (const record of factorRecords) {
        if (record.date > date) break;
        if (Number.isFinite(Number(record.value))) selected = record;
      }
      return selected;
    }

    function thresholdRowsFor(priceKey = state.market) {
      const factor = FACTOR_DATA.definitions?.[state.thresholdFactor];
      const priceRecords = priceRecordsFor(priceKey).filter(record => Number.isFinite(Number(record.price)));
      const factorRecords = (factor?.records || [])
        .filter(record => Number.isFinite(Number(record.value)))
        .map(record => ({ date: cleanDate(record.date), value: Number(record.value) }))
        .sort((a, b) => a.date.localeCompare(b.date));
      const threshold = Number(state.thresholdValue);
      const horizon = Number(state.thresholdHorizon);
      if (!factor || !priceRecords.length || !factorRecords.length || !Number.isFinite(threshold) || !Number.isFinite(horizon)) {
        return [];
      }
      return priceRecords.map((record, index) => {
        const factorRecord = nearestPriorFactorValue(factorRecords, record.date);
        if (!factorRecord) return null;
        const value = Number(factorRecord.value);
        const matched = state.thresholdDirection === "<=" ? value <= threshold : value >= threshold;
        if (!matched) return null;
        const end = index + horizon;
        if (end >= priceRecords.length) return null;
        const startPrice = Number(record.price);
        const endPrice = Number(priceRecords[end].price);
        const windowPrices = priceRecords.slice(index, end + 1).map(row => Number(row.price)).filter(Number.isFinite);
        if (!Number.isFinite(startPrice) || !Number.isFinite(endPrice) || !windowPrices.length || startPrice === 0) return null;
        const forward = (endPrice / startPrice - 1) * 100;
        const drawdown = (Math.min(...windowPrices) / startPrice - 1) * 100;
        return {
          date: record.date,
          price: startPrice,
          factorDate: factorRecord.date,
          value,
          forward,
          drawdown
        };
      }).filter(Boolean);
    }

    function thresholdStats() {
      const rows = thresholdRowsFor(state.market);
      const hitRateValue = rows.length ? rows.filter(row => row.forward > 0).length / rows.length * 100 : null;
      return {
        rows,
        count: rows.length,
        hitRate: hitRateValue,
        avgReturn: average(rows.map(row => row.forward)),
        medianReturn: (() => {
          const clean = rows.map(row => row.forward).filter(Number.isFinite).sort((a, b) => a - b);
          if (!clean.length) return null;
          const mid = Math.floor(clean.length / 2);
          return clean.length % 2 ? clean[mid] : (clean[mid - 1] + clean[mid]) / 2;
        })(),
        avgDrawdown: average(rows.map(row => row.drawdown)),
        worstDrawdown: rows.length ? Math.min(...rows.map(row => row.drawdown).filter(Number.isFinite)) : null
      };
    }

    function renderThresholdStats() {
      const factor = FACTOR_DATA.definitions?.[state.thresholdFactor];
      const stats = thresholdStats();
      const horizonLabel = { 5: "1w", 20: "4w", 65: "13w", 130: "26w" }[Number(state.thresholdHorizon)] || `${state.thresholdHorizon}d`;
      const condition = `${factor?.label || "Factor"} ${state.thresholdDirection} ${state.thresholdValue}`;
      els.thresholdStats.innerHTML = `
        <div><strong>${condition}</strong></div>
        <div>${MARKET_LABELS[state.market]} ${horizonLabel}: <strong>${stats.count}</strong> signals</div>
        <div>Hit: <strong>${stats.hitRate === null ? "n/a" : `${stats.hitRate.toFixed(1)}%`}</strong></div>
        <div>Avg return: <span class="${scoreClass(stats.avgReturn)}">${formatSignedPct(stats.avgReturn)}</span></div>
        <div>Median return: <span class="${scoreClass(stats.medianReturn)}">${formatSignedPct(stats.medianReturn)}</span></div>
        <div>Avg DD: <span class="${scoreClass(stats.avgDrawdown)}">${formatSignedPct(stats.avgDrawdown)}</span></div>
        <div>Worst DD: <span class="${scoreClass(stats.worstDrawdown)}">${formatSignedPct(stats.worstDrawdown)}</span></div>
      `;
    }

    function thresholdMarkerTrace() {
      if (!state.showThresholdMarks) return [];
      const rows = thresholdRowsFor(state.market);
      if (!rows.length) return [];
      const t = themeTokens();
      const factor = FACTOR_DATA.definitions?.[state.thresholdFactor];
      const horizonLabel = { 5: "1w", 20: "4w", 65: "13w", 130: "26w" }[Number(state.thresholdHorizon)] || `${state.thresholdHorizon}d`;
      return [{
        type: "scatter",
        mode: "markers",
        x: rows.map(row => row.date),
        y: rows.map(row => row.value),
        yaxis: "y3",
        name: `${factor?.label || "Factor"} threshold`,
        showlegend: true,
        marker: {
          symbol: "circle-open",
          size: 15,
          color: t.threshold,
          line: { width: 2.5, color: t.threshold }
        },
        customdata: rows.map(row => [row.factorDate, row.forward, row.drawdown, row.price]),
        hovertemplate: `<b>${factor?.label || "Factor"} signal</b><br>%{x|%Y-%m-%d}<br>Value: %{y:,.2f}<br>Factor date: %{customdata[0]}<br>${horizonLabel} return: %{customdata[1]:+.2f}%<br>${horizonLabel} DD: %{customdata[2]:+.2f}%<br>Price: %{customdata[3]:,.2f}<extra></extra>`
      }];
    }

    function activeFactorKeys() {
      return Object.keys(FACTOR_DATA.definitions || {}).filter(key => state.showFactors[key]);
    }

    function visibleFactorAxisKeys() {
      const keys = new Set(activeFactorKeys());
      if (state.showThresholdMarks && state.thresholdFactor) keys.add(state.thresholdFactor);
      return [...keys].filter(key => FACTOR_DATA.definitions?.[key]);
    }

    function macroScoreRecords() {
      const cotRecords = currentDataset().records || [];
      const startDate = cotRecords[0]?.date || "";
      return (MACRO_MONITOR.records || [])
        .filter(record => record.date >= startDate && Number.isFinite(Number(record.liquidity_score)));
    }

    function macroScoreTrace(halo = false) {
      const records = macroScoreRecords();
      const s = lineSetting(MACRO_SCORE_OVERLAY_KEY);
      const t = themeTokens();
      return {
        type: "scatter",
        mode: "lines",
        x: records.map(row => row.date),
        y: records.map(row => row.liquidity_score),
        name: halo ? "Macro liquidity score halo" : "Macro liquidity score",
        yaxis: "y3",
        showlegend: !halo,
        hoverinfo: halo ? "skip" : "x+y+name",
        opacity: halo ? 0.22 : s.opacity,
        line: {
          color: halo ? (state.theme === "dark" ? "rgba(245,158,11,0.28)" : "rgba(245,158,11,0.22)") : s.color,
          width: halo ? Math.max(7, s.width + 4) : s.width,
          dash: halo ? "solid" : s.dash
        },
        customdata: halo ? undefined : records.map(row => [
          row.regime_label,
          row.net_liquidity_4w_change,
          row.hy_oas_4w_change,
          row.real_yield_4w_change,
        ]),
        hovertemplate: halo ? null : `<b>Macro liquidity score</b><br>%{x|%Y-%m-%d}<br>Score: %{y:.1f}/100<br>Regime: %{customdata[0]}<br>Net liquidity 4w: $%{customdata[1]:+.0f}bn<br>HY OAS 4w: %{customdata[2]:+.2f}pp<br>Real yield 4w: %{customdata[3]:+.2f}pp<extra></extra>`
      };
    }

    function buildFactorTraces() {
      const traces = [];
      if (state.showMacroScore && MACRO_MONITOR.available && macroScoreRecords().length) {
        traces.push(macroScoreTrace(true), macroScoreTrace(false));
      }
      traces.push(...activeFactorKeys().flatMap(key => [factorTrace(key, true), factorTrace(key)]));
      return traces;
    }

    function buildMainTraces() {
      return [...buildPositionTraces(state.metric), ...buildPriceTraces(), ...buildFactorTraces(), ...thresholdMarkerTrace()];
    }

    function zoomedRange(values, zoom) {
      const clean = values.filter(Number.isFinite);
      if (!clean.length) return undefined;
      const min = Math.min(...clean);
      const max = Math.max(...clean);
      const spread = max - min;
      const center = (min + max) / 2;
      const half = (spread > 0 ? spread : Math.max(1, Math.abs(center) * 0.02)) * 0.58 / Math.max(0.1, Number(zoom));
      return [center - half, center + half];
    }

    function visiblePriceAxisRange(priceKey = null) {
      const range = visibleDateRange();
      const keys = priceKey ? [priceKey] : activePriceKeys();
      const values = keys.flatMap(key => {
        const series = priceSeries(key);
        return series.priceRecords
          .map((record, index) => inVisibleRange(record.date, range) ? Number(series.values[index]) : NaN)
          .filter(Number.isFinite);
      });
      return zoomedRange(values, state.priceAxisZoom);
    }

    function visibleFactorAxisRange() {
      const range = visibleDateRange();
      const values = visibleFactorAxisKeys().flatMap(key => {
        const records = FACTOR_DATA.definitions?.[key]?.records || [];
        return records
          .filter(record => inVisibleRange(record.date, range))
          .map(record => Number(record.value))
          .filter(Number.isFinite);
      });
      if (state.showMacroScore) {
        values.push(...macroScoreRecords()
          .filter(record => inVisibleRange(record.date, range))
          .map(record => Number(record.liquidity_score))
          .filter(Number.isFinite));
      }
      return zoomedRange(values, state.factorAxisZoom);
    }

    function buildPositionTraces(metric) {
      const data = currentDataset();
      const records = data.records;
      return state.activeCategories
        .filter(category => records.some(r => r[fieldFor(category, metric)] !== null && r[fieldFor(category, metric)] !== undefined))
        .map(category => categoryTrace(records, category, data.categories[category], metric));
    }

    function baseXAxis(withSlider = false) {
      const t = themeTokens();
      const compactPlot = isCompactPlot();
      const sliderVisible = withSlider && state.showRangeSlider && !compactPlot;
      const rangeButtons = compactPlot
        ? [
          { count: 1, label: "1m", step: "month", stepmode: "backward" },
          { count: 6, label: "6m", step: "month", stepmode: "backward" },
          { count: 1, label: "1y", step: "year", stepmode: "backward" },
          { step: "all", label: "All" }
        ]
        : [
          { count: 10, label: "10d", step: "day", stepmode: "backward" },
          { count: 30, label: "30d", step: "day", stepmode: "backward" },
          { count: 1, label: "1m", step: "month", stepmode: "backward" },
          { count: 3, label: "3m", step: "month", stepmode: "backward" },
          { count: 6, label: "6m", step: "month", stepmode: "backward" },
          { count: 1, label: "1y", step: "year", stepmode: "backward" },
          { count: 3, label: "3y", step: "year", stepmode: "backward" },
          { count: 5, label: "5y", step: "year", stepmode: "backward" },
          { step: "all", label: "All" }
        ];
      return {
        title: compactPlot ? "" : "Date",
        range: state.xRange || undefined,
        showgrid: true,
        gridcolor: t.grid,
        fixedrange: false,
        nticks: compactPlot ? 6 : 14,
        hoverformat: "%Y-%m-%d",
        showspikes: true,
        spikemode: "across",
        spikesnap: "cursor",
        spikecolor: t.muted,
        spikedash: "dash",
        spikethickness: 1,
        tickfont: { color: t.muted },
        titlefont: { color: t.text },
        tickformatstops: [
          { dtickrange: [null, 86400000 * 14], value: "%b %d\n%Y" },
          { dtickrange: [86400000 * 14, 86400000 * 90], value: "%b %d" },
          { dtickrange: [86400000 * 90, 86400000 * 365], value: "%b %Y" },
          { dtickrange: [86400000 * 365, null], value: "%Y" }
        ],
        rangeslider: sliderVisible ? {
          visible: true,
          thickness: 0.09,
          bordercolor: t.sliderBorder,
          bgcolor: t.plot,
          yaxis: { rangemode: "match" }
        } : undefined,
        rangeselector: withSlider ? {
          x: 0,
          y: compactPlot ? 1.12 : 1.06,
          xanchor: "left",
          yanchor: "top",
          bgcolor: t.selectorBg,
          bordercolor: t.sliderBorder,
          borderwidth: 1,
          font: { size: 11, color: t.text },
          buttons: rangeButtons
        } : undefined
      };
    }

    function positionLayout(metric, withSlider, includePrice = false) {
      const t = themeTokens();
      const compactPlot = isCompactPlot();
      const includeFactors = activeFactorKeys().length > 0 || state.showThresholdMarks || (state.showMacroScore && MACRO_MONITOR.available);
      const rawPriceAxes = includePrice && state.priceScale === "raw";
      const showSpAxis = includePrice && state.showSp500;
      const showNqAxis = includePrice && state.showNq;
      const rawSplitAxes = rawPriceAxes && showSpAxis && showNqAxis && !compactPlot;
      const rightAxisCount = (includePrice ? (rawSplitAxes ? 2 : 1) : 0) + (includeFactors ? 1 : 0);
      const xDomainEnd = compactPlot ? (rightAxisCount ? 0.91 : undefined) : (rightAxisCount >= 3 ? 0.76 : (rightAxisCount === 2 ? 0.82 : undefined));
      const priceAxisPosition = compactPlot ? (includeFactors ? 0.92 : 0.98) : (rawSplitAxes ? (includeFactors ? 0.80 : 0.86) : (includeFactors ? 0.88 : 0.98));
      const nqAxisPosition = compactPlot ? 0.98 : (includeFactors ? 0.90 : 0.98);
      const factorAxisPosition = 1.0;
      const rightMargin = compactPlot ? (rightAxisCount ? 58 : 16) : (rightAxisCount >= 3 ? 228 : (rightAxisCount === 2 ? 164 : (includePrice ? 112 : 24)));
      return {
        paper_bgcolor: t.paper,
        plot_bgcolor: t.plot,
        font: { color: t.text, size: compactPlot ? 10 : 11 },
        hovermode: "closest",
        hoverdistance: -1,
        spikedistance: -1,
        dragmode: state.dragMode,
        showlegend: includePrice || includeFactors,
        hoverlabel: {
          bgcolor: t.hoverBg,
          bordercolor: t.hoverBorder,
          font: { color: t.text, size: 12 }
        },
        legend: {
          orientation: "h",
          x: 0,
          y: compactPlot ? 1.2 : 1.12,
          font: { size: compactPlot ? 10 : 11, color: t.text },
          bgcolor: t.legendBg
        },
        margin: { l: compactPlot ? 46 : 72, r: rightMargin, t: compactPlot ? 72 : (withSlider ? 58 : 28), b: compactPlot ? 42 : (withSlider ? 76 : 44) },
        xaxis: {
          ...baseXAxis(withSlider),
          domain: xDomainEnd ? [0, xDomainEnd] : undefined
        },
        yaxis: {
          title: compactPlot ? "" : metricLabels[metric],
          fixedrange: true,
          zeroline: true,
          zerolinecolor: t.zero,
          zerolinewidth: 1,
          gridcolor: t.grid,
          hoverformat: metric.endsWith("pct") ? ",.2f" : ",.0f",
          showspikes: true,
          spikemode: "across",
          spikesnap: "cursor",
          spikecolor: t.muted,
          spikedash: "dash",
          spikethickness: 1,
          tickfont: { color: t.muted, size: compactPlot ? 10 : 11 },
          titlefont: { color: t.text }
        },
        yaxis2: includePrice ? {
          title: compactPlot ? "" : (state.priceScale === "indexed" ? "Price index" : (rawSplitAxes ? "S&P price" : "Price")),
          overlaying: "y",
          side: "right",
          anchor: "free",
          position: priceAxisPosition,
          fixedrange: true,
          range: visiblePriceAxisRange(rawPriceAxes && showSpAxis && showNqAxis ? "sp500" : null),
          tickformat: state.priceScale === "indexed" ? ",.0f" : ",.0f",
          dtick: state.priceScale === "indexed" ? 100 : undefined,
          nticks: compactPlot ? 6 : (state.priceScale === "indexed" ? 8 : 12),
          hoverformat: state.priceScale === "indexed" ? ",.2f" : ",.2f",
          separatethousands: true,
          exponentformat: "none",
          tickfont: { color: rawPriceAxes && showSpAxis && showNqAxis ? themedLineColor("sp500_price") : t.text, size: compactPlot ? 10 : 11 },
          titlefont: { color: rawPriceAxes && showSpAxis && showNqAxis ? themedLineColor("sp500_price") : t.text, size: 11 },
          automargin: true,
          showgrid: false,
          zeroline: false,
          showspikes: true,
          spikemode: "across",
          spikesnap: "cursor",
          spikecolor: t.muted,
          spikedash: "dash",
          spikethickness: 1
        } : undefined,
        yaxis4: rawSplitAxes ? {
          title: compactPlot ? "" : "NQ price",
          overlaying: "y",
          side: "right",
          anchor: "free",
          position: nqAxisPosition,
          fixedrange: true,
          range: visiblePriceAxisRange("nq"),
          tickformat: ",.0f",
          nticks: compactPlot ? 6 : 12,
          hoverformat: ",.2f",
          separatethousands: true,
          exponentformat: "none",
          tickfont: { color: themedLineColor("nq_price"), size: compactPlot ? 10 : 11 },
          titlefont: { color: themedLineColor("nq_price"), size: 11 },
          automargin: true,
          showgrid: false,
          zeroline: false,
          showspikes: true,
          spikemode: "across",
          spikesnap: "cursor",
          spikecolor: themedLineColor("nq_price"),
          spikedash: "dash",
          spikethickness: 1
        } : undefined,
        yaxis3: includeFactors ? {
          title: compactPlot ? "" : "Factors",
          overlaying: "y",
          side: "right",
          anchor: "free",
          position: factorAxisPosition,
          fixedrange: true,
          range: visibleFactorAxisRange(),
          tickformat: ",.0f",
          separatethousands: true,
          exponentformat: "none",
          tickfont: { color: t.factor, size: compactPlot ? 10 : 11 },
          titlefont: { color: t.factor, size: 11 },
          showticklabels: !(compactPlot && includePrice),
          automargin: true,
          showgrid: false,
          zeroline: false,
          showspikes: true,
          spikemode: "across",
          spikesnap: "cursor",
          spikecolor: t.factor,
          spikedash: "dash",
          spikethickness: 1
        } : undefined
      };
    }

    function plotConfig() {
      return {
        responsive: true,
        displaylogo: false,
        scrollZoom: true,
        doubleClick: "reset",
        modeBarButtonsToRemove: ["select2d", "lasso2d", "autoScale2d"]
      };
    }

    function plotlyFallbackHtml() {
      const data = currentDataset();
      const latest = data.records[data.records.length - 1] || {};
      const macro = MACRO_MONITOR.latest || {};
      const regime = evaluateRegime(state.market);
      const extreme = strongestCurrentExtreme();
      return `
        <div class="plotly-missing-panel" role="status">
          <div>
            <div class="plotly-missing-kicker">Chart unavailable</div>
            <div class="plotly-missing-title">Interactive timeline requires Plotly</div>
            <p>Summary, scorecards, tables, and backtest evidence are still rendered below.</p>
          </div>
          <div class="plotly-fallback-grid">
            <div><span>Market</span><strong>${MARKET_LABELS[state.market] || state.market}</strong></div>
            <div><span>COT date</span><strong>${latest.date || "n/a"}</strong></div>
            <div><span>Price</span><strong>${Number(latest.price).toLocaleString(undefined, { maximumFractionDigits: 2 })}</strong></div>
            <div><span>Macro score</span><strong>${Number.isFinite(Number(macro.liquidity_score)) ? `${Number(macro.liquidity_score).toFixed(0)} / 100` : "n/a"}</strong></div>
            <div><span>Regime</span><strong>${regime.status.text}</strong></div>
            <div><span>Extreme</span><strong>${extreme ? `${extreme.label} ${formatPct(extreme.net)}` : "n/a"}</strong></div>
          </div>
        </div>
      `;
    }

    function renderMainChart() {
      if (window.Plotly) {
        const layout = positionLayout(state.metric, true, true);
        for (const key of ["yaxis2", "yaxis3", "yaxis4"]) {
          if (!layout[key]) delete layout[key];
        }
        Plotly.react(els.mainChart, buildMainTraces(), layout, plotConfig());
      } else {
        els.mainChart.innerHTML = plotlyFallbackHtml();
      }
    }

    function render() {
      applyTheme();
      ensureActiveCategories();
      renderThemeToggle();
      renderFreshnessLine();
      renderSummaryStrip();
      renderWeeklyDeskPanel();
      renderMacroScorecard();
      renderPrimaryControls();
      renderCategoryControls();
      renderFactorOverlayControls();
      renderViewPresetButtons();
      renderAxisZoomControls();
      renderThresholdControls();
      renderThresholdStats();
      renderLineControls();
      renderStats();
      renderFactorSidebar();
      renderAnalyticSnapshot();
      renderMacroMonitorPanel();
      renderUpdateDeltaPanel();
      renderCrossMarketPanel();
      renderLiquidityPanel();
      renderMacroLensPanel();
      renderNetTable();
      renderRegimePanel();
      renderRegimeBacktestPanel();
      renderFactorPanel();
      renderResearchPanel();
      const overlays = [
        state.showMacroScore && MACRO_MONITOR.available ? "liquidity score" : null,
        activeFactorKeys().length ? "factors" : null,
      ].filter(Boolean).join(" + ");
      els.mainTitle.textContent = `${MARKET_LABELS[state.market]} ${DATASET_LABELS[state.dataset]}: ${metricLabels[state.metric]} + price${overlays ? ` + ${overlays}` : ""}`;

      renderMainChart();
    }

    function updateStateFromControls(resetCategories = false) {
      const changedDataset = state.dataset !== els.dataset.value;
      state.dataset = els.dataset.value;
      state.market = els.market.value;
      state.metric = els.metric.value;
      state.showSp500 = els.showSp500.checked;
      state.showNq = els.showNq.checked;
      state.priceScale = els.priceScale.value;
      state.dragMode = els.dragMode.value;
      state.showRangeSlider = els.showRangeSlider.checked;
      state.thresholdFactor = els.thresholdFactor.value;
      state.thresholdDirection = els.thresholdDirection.value;
      state.thresholdValue = Number(els.thresholdValue.value);
      state.thresholdHorizon = Number(els.thresholdHorizon.value);
      state.showThresholdMarks = els.showThresholdMarks.checked;
      ensureActiveCategories(resetCategories || changedDataset);
    }

    for (const el of [
      els.dataset,
      els.market,
      els.metric,
      els.showSp500,
      els.showNq,
      els.priceScale,
      els.dragMode,
      els.showRangeSlider,
      els.thresholdFactor,
      els.thresholdDirection,
      els.thresholdValue,
      els.thresholdHorizon,
      els.showThresholdMarks
    ]) {
      el.addEventListener("change", () => {
        updateStateFromControls(el === els.dataset);
        render();
      });
    }

    for (const el of [els.priceAxisZoom, els.factorAxisZoom]) {
      el.addEventListener("input", () => {
        state.priceAxisZoom = Number(els.priceAxisZoom.value);
        state.factorAxisZoom = Number(els.factorAxisZoom.value);
        renderAxisZoomControls();
        renderMainChart();
      });
    }

    els.resetAxisZoom.addEventListener("click", () => {
      state.priceAxisZoom = 1;
      state.factorAxisZoom = 1;
      renderAxisZoomControls();
      renderMainChart();
    });

    els.categoryList.addEventListener("change", event => {
      const target = event.target;
      if (!target.matches("input[data-category]")) return;
      const category = target.getAttribute("data-category");
      if (target.checked) {
        if (!state.activeCategories.includes(category)) state.activeCategories.push(category);
      } else {
        state.activeCategories = state.activeCategories.filter(k => k !== category);
      }
      render();
    });

    els.factorOverlayList.addEventListener("change", event => {
      const target = event.target;
      if (target.matches("input[data-macro-score]")) {
        state.showMacroScore = target.checked;
        render();
        return;
      }
      if (!target.matches("input[data-factor]")) return;
      const factorKey = target.getAttribute("data-factor");
      state.showFactors[factorKey] = target.checked;
      render();
    });

    function resetFactorVisibility(visible = {}) {
      for (const key of Object.keys(FACTOR_DATA.definitions || {})) {
        state.showFactors[key] = Boolean(visible[key]);
      }
    }

    function applyViewPreset(preset) {
      state.xRange = null;
      state.lineSettings = {};
      state.priceAxisZoom = 1;
      state.factorAxisZoom = 1;
      if (preset === "cot_price") {
        state.showSp500 = true;
        state.showNq = true;
        state.showMacroScore = false;
        state.showThresholdMarks = false;
        state.priceScale = "raw";
        resetFactorVisibility({});
      } else if (preset === "macro") {
        state.showSp500 = true;
        state.showNq = false;
        state.showMacroScore = true;
        state.showThresholdMarks = false;
        state.priceScale = "indexed";
        resetFactorVisibility({});
      } else if (preset === "stress") {
        state.showSp500 = true;
        state.showNq = false;
        state.showMacroScore = false;
        state.showThresholdMarks = false;
        state.priceScale = "indexed";
        resetFactorVisibility({ cnn_vix: true, fred_vix: true, real_yield_10y: true, hy_oas: true });
      } else if (preset === "sentiment") {
        state.showSp500 = true;
        state.showNq = true;
        state.showMacroScore = false;
        state.showThresholdMarks = true;
        state.thresholdFactor = "cnn_fear_greed";
        state.priceScale = "indexed";
        resetFactorVisibility({ cnn_fear_greed: true, cnn_vix: true });
      }
      render();
      window.setTimeout(resizeCharts, 80);
    }

    for (const button of document.querySelectorAll("[data-view-preset]")) {
      button.addEventListener("click", () => applyViewPreset(button.getAttribute("data-view-preset")));
    }

    if (els.macroMonitorPanel) {
      els.macroMonitorPanel.addEventListener("change", event => {
        const target = event.target;
        if (!target.matches("#tspUpload")) return;
        handleTspUpload(target.files?.[0]);
      });
    }

    els.lineSelect.addEventListener("change", () => {
      state.selectedLine = els.lineSelect.value;
      renderLineControls();
    });

    for (const el of [els.lineColor, els.lineDash, els.lineWidth, els.lineOpacity]) {
      el.addEventListener("input", () => {
        if (!state.selectedLine) return;
        state.lineSettings[state.selectedLine] = {
          color: els.lineColor.value,
          dash: els.lineDash.value,
          width: Number(els.lineWidth.value),
          opacity: Number(els.lineOpacity.value)
        };
        renderLineControls();
        renderMainChart();
      });
    }

    els.resetLine.addEventListener("click", () => {
      if (!state.selectedLine) return;
      state.lineSettings[state.selectedLine] = defaultLineSetting(state.selectedLine);
      renderLineControls();
      render();
    });

    els.selectAll.addEventListener("click", () => {
      state.activeCategories = currentCategoryKeys();
      render();
    });

    els.clearCategories.addEventListener("click", () => {
      state.activeCategories = [];
      render();
    });

    els.reset.addEventListener("click", () => {
      state.xRange = null;
      render();
    });

    els.toggleSidebar.addEventListener("click", () => {
      state.sidebarCollapsed = !state.sidebarCollapsed;
      renderSidebarState();
      if (state.sidebarCollapsed) els.toggleSidebar.blur();
      window.setTimeout(resizeCharts, 80);
    });

    els.themeToggle.addEventListener("click", () => {
      state.theme = state.theme === "dark" ? "light" : "dark";
      state.lineSettings = {};
      render();
      window.setTimeout(resizeCharts, 80);
    });

    function setCardCollapsed(card, button, collapsed) {
      card.classList.toggle("collapsed", collapsed);
      const title = card.querySelector(".card-title")?.textContent?.trim() || "section";
      button.setAttribute("aria-expanded", String(!collapsed));
      button.setAttribute("aria-label", `${collapsed ? "Expand" : "Collapse"} ${title}`);
      button.setAttribute("title", collapsed ? "Expand section" : "Collapse section");
      if (!collapsed) window.setTimeout(resizeCharts, 80);
    }

    for (const button of document.querySelectorAll("[data-card-toggle]")) {
      const card = button.closest(".chart-card");
      if (card) setCardCollapsed(card, button, card.classList.contains("collapsed"));
      button.addEventListener("click", event => {
        const card = button.closest(".chart-card");
        if (!card) return;
        setCardCollapsed(card, button, !card.classList.contains("collapsed"));
        event.stopPropagation();
      });
    }

    for (const head of document.querySelectorAll(".card-head")) {
      head.addEventListener("click", event => {
        if (event.target instanceof Element && event.target.closest("button, a, input, select, textarea")) return;
        const card = head.closest(".chart-card");
        const button = card?.querySelector("[data-card-toggle]");
        if (!card || !button) return;
        setCardCollapsed(card, button, !card.classList.contains("collapsed"));
      });
    }

    function setupFloatingToc() {
      const toc = document.getElementById("floatingToc");
      const toggle = document.getElementById("floatingTocToggle");
      const links = document.getElementById("floatingTocLinks");
      const main = document.querySelector("main");
      if (!toc || !toggle || !links || !main) return;

      const targets = [...main.children].filter(element => (
        element.matches(".dashboard-section-title, .chart-card")
      ));
      const entries = targets.map((target, index) => {
        const isSection = target.matches(".dashboard-section-title");
        const label = isSection
          ? target.querySelector("span")?.textContent?.trim()
          : target.querySelector(".card-title")?.textContent?.trim();
        if (!label) return null;
        target.id ||= `dashboard-section-${index + 1}`;
        return { target, label, isSection };
      }).filter(Boolean);

      links.innerHTML = entries.map(({ target, label, isSection }) => (
        `<a class="floating-toc-link${isSection ? "" : " subsection"}" href="#${target.id}" data-toc-target="${target.id}">${label}</a>`
      )).join("");

      const setOpen = open => {
        toc.classList.toggle("open", open);
        toggle.setAttribute("aria-expanded", String(open));
        toggle.setAttribute("aria-label", open ? "Close dashboard contents" : "Open dashboard contents");
      };
      toggle.addEventListener("click", () => {
        const open = !toc.classList.contains("open");
        setOpen(open);
        if (!open) toggle.blur();
      });
      toc.addEventListener("keydown", event => {
        if (event.key === "Escape") {
          setOpen(false);
          toggle.focus();
        }
      });
      links.addEventListener("click", event => {
        const link = event.target.closest("a[data-toc-target]");
        if (!link) return;
        const target = document.getElementById(link.dataset.tocTarget);
        const cardToggle = target?.querySelector("[data-card-toggle]");
        if (target?.classList.contains("collapsed") && cardToggle) {
          setCardCollapsed(target, cardToggle, false);
        }
        setOpen(false);
      });

      const tocLinks = [...links.querySelectorAll("a")];
      const updateActiveLink = () => {
        const marker = window.scrollY + Math.min(180, window.innerHeight * 0.25);
        let active = entries[0]?.target.id;
        for (const entry of entries) {
          if (entry.target.offsetTop <= marker) active = entry.target.id;
          else break;
        }
        for (const link of tocLinks) {
          link.classList.toggle("active", link.dataset.tocTarget === active);
        }
      };
      window.addEventListener("scroll", updateActiveLink, { passive: true });
      updateActiveLink();
    }

    setupFloatingToc();

    renderSidebarState();
    render();
    loadRefreshStatus();
    window.setInterval(loadRefreshStatus, 60000);

    let lastMobileControls = isMobileControls();
    let resizeTimer = null;
    window.addEventListener("resize", () => {
      const mobileNow = isMobileControls();
      if (mobileNow !== lastMobileControls) {
        lastMobileControls = mobileNow;
        if (mobileNow) {
          state.sidebarCollapsed = true;
        }
      }
      renderSidebarState();
      window.clearTimeout(resizeTimer);
      resizeTimer = window.setTimeout(() => {
        renderMainChart();
        resizeCharts();
      }, 140);
    });

    if (window.Plotly && typeof els.mainChart.on === "function") {
      els.mainChart.on("plotly_relayout", ev => {
        if (state.syncing) return;
        let xChanged = false;
        if (ev["xaxis.range[0]"] && ev["xaxis.range[1]"]) {
          state.xRange = [ev["xaxis.range[0]"], ev["xaxis.range[1]"]];
          xChanged = true;
        }
        if (ev["xaxis.autorange"]) {
          state.xRange = null;
          xChanged = true;
        }
        if (xChanged) {
          window.clearTimeout(state.rebaseTimer);
          state.rebaseTimer = window.setTimeout(() => {
            if (window.Plotly) {
              renderMainChart();
            }
          }, 120);
        }
      });
    }
