(() => {
  "use strict";

  const FINANCIAL_MARKETS = new Set(["sp500", "nq", "vix", "rty", "dow"]);
  const METALS_MARKETS = new Set(["gold", "silver"]);
  const originalFetch = window.fetch.bind(window);

  function requestedFinancialDataset() {
    const params = new URL(window.location.href).searchParams;
    const value = String(params.get("report") || params.get("dataset") || "tff").toLowerCase();
    return value === "legacy" ? "legacy" : "tff";
  }

  const financialDataset = requestedFinancialDataset();

  function datasetForMarket(market) {
    const key = String(market || "").toLowerCase();
    if (METALS_MARKETS.has(key)) return "disaggregated";
    return financialDataset;
  }

  function inferDataset(row, fallback = null) {
    const explicit = String(row?.dataset || row?.cot_dataset || row?.report_type || "").toLowerCase();
    if (["tff", "legacy", "disaggregated"].includes(explicit)) return explicit;
    const series = String(row?.series || fallback || "");
    const prefix = series.split(":")[0]?.toLowerCase();
    return ["tff", "legacy", "disaggregated"].includes(prefix) ? prefix : null;
  }

  function inferMarket(row, fallback = null) {
    const explicit = String(row?.market || "").toLowerCase();
    if (FINANCIAL_MARKETS.has(explicit) || METALS_MARKETS.has(explicit)) return explicit;
    const series = String(row?.series || fallback || "");
    const parts = series.split(":");
    return parts.length > 1 ? String(parts[1]).toLowerCase() : String(fallback || "").toLowerCase();
  }

  function matchesSelection(row, fallbackKey = null, fallbackMarket = null) {
    const market = inferMarket(row, fallbackMarket || fallbackKey);
    const dataset = inferDataset(row, fallbackKey);
    return !market || !dataset || dataset === datasetForMarket(market);
  }

  function filterKeyedObject(value, fallbackMarket = null) {
    if (!value || typeof value !== "object" || Array.isArray(value)) return value;
    return Object.fromEntries(Object.entries(value).filter(([key, row]) => matchesSelection(row, key, fallbackMarket)));
  }

  function selectionMeta() {
    return {
      financial_report: financialDataset,
      metals_report: "disaggregated",
      filtered_for_presentation: true
    };
  }

  function transformCurrent(payload) {
    if (!payload || typeof payload !== "object") return payload;
    const actorStates = filterKeyedObject(payload.actor_states || {});
    const marketSources = Object.fromEntries(Object.entries(payload.market_sources || {}).filter(([key, row]) => {
      const market = inferMarket(row, key);
      const dataset = inferDataset(row, key);
      return !market || !dataset || dataset === datasetForMarket(market);
    }));
    return { ...payload, actor_states: actorStates, market_sources: marketSources, presentation_selection: selectionMeta() };
  }

  function transformActive(payload) {
    if (!payload || typeof payload !== "object") return payload;
    let total = 0;
    const byMarket = Object.fromEntries(Object.entries(payload.by_market || {}).map(([market, block]) => {
      const rows = (block?.active_thresholds || []).filter(row => matchesSelection(row, null, market));
      total += rows.length;
      return [market, { ...block, active_thresholds: rows, active_threshold_count: rows.length }];
    }));
    return { ...payload, by_market: byMarket, active_threshold_count: total, presentation_selection: selectionMeta() };
  }

  function transformRegistry(payload) {
    if (!payload || typeof payload !== "object") return payload;
    const edges = payload.threshold_edges;
    let thresholdEdges = edges;
    if (Array.isArray(edges)) thresholdEdges = edges.filter(row => matchesSelection(row));
    else if (edges && typeof edges === "object") thresholdEdges = filterKeyedObject(edges);
    return { ...payload, threshold_edges: thresholdEdges, presentation_selection: selectionMeta() };
  }

  function transformRegime(payload) {
    if (!payload || typeof payload !== "object") return payload;
    const markets = Object.fromEntries(Object.entries(payload.markets || {}).map(([market, block]) => {
      const datasets = block?.datasets || {};
      const selected = datasetForMarket(market);
      if (FINANCIAL_MARKETS.has(market) && datasets[selected]) {
        return [market, {
          ...block,
          datasets: { ...datasets, tff: datasets[selected] },
          presentation_dataset: selected
        }];
      }
      return [market, { ...block, presentation_dataset: selected }];
    }));
    return { ...payload, markets, presentation_selection: selectionMeta() };
  }

  function liveRowMatches(row) {
    const market = inferMarket(row);
    if (!market) return true;
    const selected = datasetForMarket(market);
    const dataset = inferDataset(row);
    if (dataset) return dataset === selected;
    // Existing production live records predate explicit dataset tagging. They are
    // TFF for financial futures and Disaggregated for metals; never relabel them
    // as Legacy.
    return METALS_MARKETS.has(market) || selected === "tff";
  }

  function transformLive(payload) {
    if (!payload || typeof payload !== "object") return payload;
    const currentPredictions = (payload.current_predictions || []).filter(liveRowMatches);
    const edgeEvidence = payload.edge_evidence && typeof payload.edge_evidence === "object"
      ? { ...payload.edge_evidence, current_predictions: (payload.edge_evidence.current_predictions || []).filter(liveRowMatches) }
      : payload.edge_evidence;
    return { ...payload, current_predictions: currentPredictions, edge_evidence: edgeEvidence, presentation_selection: selectionMeta() };
  }

  function filterSeriesMap(value, market) {
    if (!value || typeof value !== "object" || Array.isArray(value)) return value;
    return Object.fromEntries(Object.entries(value).filter(([series, row]) => matchesSelection(row, series, market)));
  }

  function transformDetail(payload) {
    if (!payload || typeof payload !== "object") return payload;
    const market = String(payload.market || "").toLowerCase();
    return {
      ...payload,
      actors: (payload.actors || []).filter(row => matchesSelection(row, null, market)),
      threshold_signals: (payload.threshold_signals || []).filter(row => matchesSelection(row, row?.series, market)),
      threshold_percentile_profiles: filterSeriesMap(payload.threshold_percentile_profiles, market),
      actor_flow_x_oi_direction: filterSeriesMap(payload.actor_flow_x_oi_direction, market),
      presentation_selection: selectionMeta()
    };
  }

  function responseWithJson(response, payload) {
    const headers = new Headers(response.headers);
    headers.set("Content-Type", "application/json; charset=utf-8");
    headers.delete("Content-Length");
    headers.delete("Content-Encoding");
    return new Response(JSON.stringify(payload), {
      status: response.status,
      statusText: response.statusText,
      headers
    });
  }

  window.fetch = async (input, init) => {
    const response = await originalFetch(input, init);
    if (!response.ok) return response;
    let pathname = "";
    try {
      const raw = typeof input === "string" ? input : input?.url;
      pathname = new URL(raw, window.location.href).pathname;
    } catch (_) {
      return response;
    }

    let transform = null;
    if (/\/worldclass\/cot-current-state\.json$/.test(pathname)) transform = transformCurrent;
    else if (/\/worldclass\/cot-active-edges\.json$/.test(pathname)) transform = transformActive;
    else if (/\/worldclass\/cot-edge-registry\.json$/.test(pathname)) transform = transformRegistry;
    else if (/\/worldclass\/regime_backtest\.json$/.test(pathname)) transform = transformRegime;
    else if (/\/worldclass\/live-track-record\.json$/.test(pathname)) transform = transformLive;
    else if (/\/worldclass\/cot-edge-details(?:-v2)?\/[a-z0-9_-]+\.json$/.test(pathname)) transform = transformDetail;
    if (!transform) return response;

    try {
      return responseWithJson(response, transform(await response.clone().json()));
    } catch (error) {
      console.warn("Could not apply COT report taxonomy filter", pathname, error);
      return response;
    }
  };

  function activeMarket() {
    const fromModel = window.__COT_CURRENT_EDGE_MODEL__?.state?.market;
    if (FINANCIAL_MARKETS.has(fromModel) || METALS_MARKETS.has(fromModel)) return fromModel;
    const fromUrl = new URL(window.location.href).searchParams.get("market");
    if (FINANCIAL_MARKETS.has(fromUrl) || METALS_MARKETS.has(fromUrl)) return fromUrl;
    return document.querySelector("#instrumentTabs [data-market].active")?.dataset?.market || "sp500";
  }

  function chooseDataset(dataset) {
    if (!FINANCIAL_MARKETS.has(activeMarket()) || dataset === financialDataset) return;
    const url = new URL(window.location.href);
    url.searchParams.set("report", dataset);
    url.searchParams.delete("dataset");
    window.location.assign(url.toString());
  }

  function renderSelector() {
    const nav = document.querySelector(".decision-nav");
    if (!nav) return;
    const market = activeMarket();
    let control = document.getElementById("reportTaxonomyControl");
    if (!control) {
      control = document.createElement("div");
      control.id = "reportTaxonomyControl";
      control.className = "report-taxonomy-control";
      control.setAttribute("aria-label", "COT report type");
      nav.insertBefore(control, nav.querySelector(".decision-horizons") || null);
    }

    if (METALS_MARKETS.has(market)) {
      control.innerHTML = `<span class="report-taxonomy-label">Report type</span><span class="report-taxonomy-locked" title="Gold and Silver use CFTC Disaggregated Futures Only">Disaggregated</span>`;
      control.dataset.marketType = "metals";
      return;
    }

    control.dataset.marketType = "financial";
    control.innerHTML = `<span class="report-taxonomy-label">Report type</span><div class="report-taxonomy-buttons" role="group" aria-label="Financial futures COT report type"><button type="button" data-report-dataset="tff" class="${financialDataset === "tff" ? "active" : ""}" aria-pressed="${financialDataset === "tff"}">TFF</button><button type="button" data-report-dataset="legacy" class="${financialDataset === "legacy" ? "active" : ""}" aria-pressed="${financialDataset === "legacy"}">Legacy</button></div>`;
    control.querySelectorAll("[data-report-dataset]").forEach(button => button.addEventListener("click", () => chooseDataset(button.dataset.reportDataset)));
  }

  function canonicalizeQuery() {
    const url = new URL(window.location.href);
    if (!url.searchParams.has("dataset")) return;
    if (!url.searchParams.has("report")) url.searchParams.set("report", financialDataset);
    url.searchParams.delete("dataset");
    history.replaceState(history.state, "", url);
  }

  function bootSelector() {
    canonicalizeQuery();
    renderSelector();
    const observer = new MutationObserver(renderSelector);
    observer.observe(document.querySelector("main") || document.body, { subtree: true, childList: true, attributes: true, attributeFilter: ["class", "aria-pressed"] });
    window.addEventListener("popstate", renderSelector);
  }

  window.__COT_REPORT_TAXONOMY__ = {
    financialDataset,
    datasetForMarket,
    inferDataset,
    inferMarket,
    matchesSelection
  };

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", bootSelector, { once: true });
  else bootSelector();
})();
