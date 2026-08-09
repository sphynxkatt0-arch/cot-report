(() => {
  "use strict";

  const finite = value => Number.isFinite(Number(value)) ? Number(value) : null;
  const esc = value => String(value ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;");
  const fmt = (value, digits = 1) => finite(value) === null ? "n/a" : finite(value).toFixed(digits);
  const pct = (value, digits = 1) => finite(value) === null ? "n/a" : `${finite(value).toFixed(digits)}%`;
  const signed = (value, digits = 2) => finite(value) === null ? "n/a" : `${finite(value) >= 0 ? "+" : ""}${finite(value).toFixed(digits)}%`;
  const probability = value => finite(value) === null ? "n/a" : `${(finite(value) * 100).toFixed(0)}%`;
  const marketLabel = value => ({ sp500: "S&P 500", nq: "Nasdaq-100", vix: "VIX", rty: "Russell 2000", dow: "Dow", gold: "Gold", silver: "Silver" }[value] || value || "—");
  const familyLabel = value => ({ combined: "Combined", cot: "COT only", macro: "Macro only" }[value] || value || "—");

  function ensureRoot() {
    let root = document.getElementById("liveTrackRecordPanel");
    if (root) return root;
    const anchor = document.getElementById("headlineCards");
    if (!anchor) return null;
    root = document.createElement("section");
    root.id = "liveTrackRecordPanel";
    root.className = "panel live-track-panel";
    root.setAttribute("aria-label", "Immutable prospective live model track record");
    const sentiment = document.getElementById("marketSentimentPanel");
    (sentiment || anchor).insertAdjacentElement("afterend", root);
    return root;
  }

  function evidenceState(payload) {
    const integrity = String(payload?.ledger?.integrity || "UNKNOWN").toUpperCase();
    if (integrity !== "PASS") return { tone: "negative", label: integrity };
    if ((payload?.forecast_count || 0) === 0) return { tone: "neutral", label: "LEDGER READY" };
    if ((payload?.matured_signal_count || 0) === 0) return { tone: "neutral", label: "FORWARD TESTING" };
    return { tone: "positive", label: "LIVE EVIDENCE" };
  }

  function predictionRows(payload) {
    const rows = Array.isArray(payload?.current_predictions) ? payload.current_predictions : [];
    const combined = rows.filter(row => row?.model_family === "combined");
    const selected = combined.length ? combined : rows;
    return selected
      .slice()
      .sort((a, b) => String(a.market || "").localeCompare(String(b.market || "")))
      .slice(0, 10);
  }

  function latestComparison(payload) {
    const rows = Array.isArray(payload?.model_comparison) ? payload.model_comparison : [];
    if (!rows.length) return null;
    const versions = Array.isArray(payload?.model_versions) ? payload.model_versions : [];
    const latestVersion = versions.length ? versions[versions.length - 1] : null;
    return rows.find(row => row?.model_version === latestVersion && row?.horizon === "4w")
      || rows.find(row => row?.horizon === "4w")
      || rows[0];
  }

  function metricCard(label, value, sub = "") {
    return `<div class="live-track-kpi"><span>${esc(label)}</span><strong>${esc(value)}</strong>${sub ? `<small>${esc(sub)}</small>` : ""}</div>`;
  }

  function renderEmpty(root, payload) {
    const state = evidenceState(payload);
    root.innerHTML = `
      <div class="live-track-head">
        <div>
          <span class="panel-kicker">LIVE FORWARD TRACK RECORD</span>
          <h3>Prospective evidence, never backfilled</h3>
          <p class="panel-meta">Historical backtests and live outcomes stay separate. A forecast only counts here if it was immutably recorded before its outcome.</p>
        </div>
        <div class="live-track-state ${state.tone}"><strong>${esc(state.label)}</strong><span>Ledger integrity ${esc(payload?.ledger?.integrity || "UNKNOWN")}</span></div>
      </div>
      <div class="live-track-kpis">
        ${metricCard("Forecasts issued", String(payload?.forecast_count ?? 0), "prospective only")}
        ${metricCard("Weekly vintages", String(payload?.weekly_vintage_count ?? 0), "unique releases")}
        ${metricCard("Matured signals", String(payload?.matured_signal_count ?? 0), "≥1 realized horizon")}
        ${metricCard("Outcomes", String(payload?.outcome_count ?? 0), "write-once settlements")}
        ${metricCard("Open signals", String(payload?.open_signal_count ?? 0), "not complete")}
      </div>
      <div class="live-track-empty">
        <strong>The live ledger is healthy and intentionally empty.</strong>
        <span>Historical research is not retroactively relabeled as live evidence. The first eligible post-deployment CFTC release will create the first immutable forecast vintage; realized results will then settle automatically by horizon.</span>
      </div>`;
  }

  function render(payload) {
    const root = ensureRoot();
    if (!root) return;
    if (!payload || typeof payload !== "object") {
      root.innerHTML = `<div class="live-track-empty"><strong>Live track record unavailable.</strong><span>The COT and macro research layers remain independent.</span></div>`;
      return;
    }
    if ((payload.forecast_count || 0) === 0) return renderEmpty(root, payload);

    const state = evidenceState(payload);
    const predictions = predictionRows(payload);
    const comparison = latestComparison(payload);
    const families = comparison?.families || {};
    const familyOrder = ["combined", "cot", "macro"];

    root.innerHTML = `
      <div class="live-track-head">
        <div>
          <span class="panel-kicker">LIVE FORWARD TRACK RECORD</span>
          <h3>Prospective model evidence</h3>
          <p class="panel-meta">Immutable forecasts, frozen historical expectations and separately settled realized outcomes.</p>
        </div>
        <div class="live-track-state ${state.tone}"><strong>${esc(state.label)}</strong><span>${esc(payload.latest_forecast_vintage || "No vintage")} · ledger ${esc(payload?.ledger?.integrity || "UNKNOWN")}</span></div>
      </div>
      <div class="live-track-kpis">
        ${metricCard("Forecasts issued", String(payload.forecast_count ?? 0), `${payload.weekly_vintage_count ?? 0} weekly vintages`)}
        ${metricCard("Matured signals", String(payload.matured_signal_count ?? 0), `${payload.complete_signal_count ?? 0} fully complete`)}
        ${metricCard("Outcomes", String(payload.outcome_count ?? 0), `${payload.entry_count ?? 0} entries frozen`)}
        ${metricCard("Open signals", String(payload.open_signal_count ?? 0), "settle automatically")}
        ${metricCard("Model versions", esc((payload.model_versions || []).join(", ") || "n/a"), "version-separated evidence")}
      </div>
      <div class="live-track-grid">
        <div class="live-track-block">
          <div class="live-track-block-head"><strong>Current forward predictions</strong><span>Combined model shown first</span></div>
          ${predictions.length ? `<div class="live-track-table-wrap"><table class="live-track-table"><thead><tr><th>Market</th><th>Signal</th><th>4W exp.</th><th>P(+)</th><th>Confidence</th><th>Status</th></tr></thead><tbody>${predictions.map(row => `<tr><td>${esc(marketLabel(row.market))}</td><td>${esc(row.signal || "n/a")}</td><td>${signed(row.expected_4w_return_pct)}</td><td>${probability(row.probability_positive_4w)}</td><td>${esc(row.confidence || "n/a")}</td><td>${esc(row.status || "n/a")}</td></tr>`).join("")}</tbody></table></div>` : `<div class="live-track-empty compact"><span>No open predictions in the ledger.</span></div>`}
        </div>
        <div class="live-track-block">
          <div class="live-track-block-head"><strong>Champion vs challengers</strong><span>${esc(comparison?.model_version || "n/a")} · ${esc(String(comparison?.horizon || "4w").toUpperCase())}</span></div>
          ${comparison ? `<div class="live-track-family-grid">${familyOrder.map(family => {
            const metrics = families[family] || {};
            const isChampion = comparison.champion === family;
            return `<article class="live-track-family ${isChampion ? "champion" : ""}"><div><strong>${esc(familyLabel(family))}</strong><span>${isChampion ? "CHAMPION" : "CHALLENGER"}</span></div><b>${pct(metrics.directional_hit_rate_pct)}</b><small>hit rate · realized ${signed(metrics.average_realized_return_pct)} · edge ${signed(metrics.live_edge_vs_unconditional_pct)} · ${esc(metrics.sample_stage || "INSUFFICIENT SAMPLE")}</small><em>${esc(metrics?.drift?.state || "INSUFFICIENT SAMPLE")}</em></article>`;
          }).join("")}</div>` : `<div class="live-track-empty compact"><span>Model comparison activates after the first prospective forecasts are issued.</span></div>`}
        </div>
      </div>
      <div class="live-track-audit"><span>Manifest head</span><code>${esc(payload?.ledger?.latest_manifest_hash || "GENESIS")}</code><span>Generated ${esc(payload.generated_at_utc || "n/a")}</span></div>`;
  }

  async function load() {
    const root = ensureRoot();
    if (!root) return;
    root.innerHTML = `<div class="live-track-empty"><span>Loading prospective live evidence…</span></div>`;
    try {
      const response = await fetch(`worldclass/live-track-record.json?v=${Date.now()}`, { cache: "no-store" });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      render(await response.json());
    } catch (error) {
      console.warn("Live track record unavailable", error);
      root.innerHTML = `<div class="live-track-empty"><strong>Live track record unavailable.</strong><span>COT, macro and historical research remain available and are not substituted with fabricated live evidence.</span></div>`;
    }
  }

  load();
})();
