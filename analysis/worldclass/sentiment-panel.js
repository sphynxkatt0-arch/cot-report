(() => {
  "use strict";

  const order = ["reddit", "x", "news", "polymarket"];
  const labels = { reddit: "Reddit", x: "X / FinTwit", news: "Financial News", polymarket: "Polymarket" };
  const finite = v => Number.isFinite(Number(v)) ? Number(v) : null;
  const esc = v => String(v ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;");
  const fmt = (v, d = 1) => finite(v) === null ? "n/a" : finite(v).toFixed(d);
  const pct = v => finite(v) === null ? "n/a" : `${finite(v).toFixed(0)}%`;
  const tone = v => finite(v) === null ? "neutral" : finite(v) >= 58 ? "positive" : finite(v) <= 42 ? "negative" : "neutral";

  function ensureRoot() {
    let root = document.getElementById("marketSentimentPanel");
    if (root) return root;
    const anchor = document.getElementById("headlineCards");
    if (!anchor) return null;
    root = document.createElement("section");
    root.id = "marketSentimentPanel";
    root.className = "panel sentiment-panel";
    root.setAttribute("aria-label", "Daily market sentiment from Reddit, X, financial news and Polymarket");
    anchor.insertAdjacentElement("afterend", root);
    return root;
  }

  function render(payload) {
    const root = ensureRoot();
    if (!root) return;
    const latest = payload?.latest;
    if (!latest) {
      root.innerHTML = `<div class="sentiment-empty">Daily sentiment is configured. The first immutable Adanos snapshot will appear after a successful scheduled collection.</div>`;
      return;
    }
    const composite = latest.composite || {};
    const sources = latest.sources || {};
    const driverRows = [];
    for (const key of order) {
      for (const driver of (sources[key]?.drivers || []).slice(0, 3)) {
        const ticker = driver?.ticker || driver?.symbol;
        if (ticker) driverRows.push({ ticker, source: labels[key], buzz: finite(driver.buzz_score), sentiment: finite(driver.sentiment_score) });
      }
    }
    driverRows.sort((a, b) => (b.buzz ?? -1) - (a.buzz ?? -1));

    root.innerHTML = `
      <div class="sentiment-topline">
        <div><span class="panel-kicker">DAILY MARKET SENTIMENT</span><h3>Media, social & prediction-market mood</h3><p class="panel-meta">Separate observational layer; it does not rewrite the COT model.</p></div>
        <div class="sentiment-date"><strong>${esc(latest.observation_date)}</strong><span>${esc(composite.state || "UNAVAILABLE")} · ${composite.available_sources ?? 0}/${composite.required_sources ?? 4} sources</span></div>
      </div>
      <div class="sentiment-summary-grid">
        <div class="sentiment-index ${tone(composite.sentiment_index)}"><strong>${fmt(composite.sentiment_index, 0)}</strong><span>${esc(composite.regime || "UNAVAILABLE")}</span><small>0 bearish · 50 neutral · 100 bullish</small></div>
        <div class="sentiment-kpi"><span>Bullish</span><strong>${pct(composite.bullish_pct)}</strong></div>
        <div class="sentiment-kpi"><span>Bearish</span><strong>${pct(composite.bearish_pct)}</strong></div>
        <div class="sentiment-kpi"><span>Buzz</span><strong>${fmt(composite.buzz_score, 0)}</strong></div>
        <div class="sentiment-kpi"><span>Disagreement</span><strong>${fmt(composite.source_disagreement, 2)}</strong></div>
      </div>
      <div class="sentiment-source-grid">
        ${order.map(key => {
          const source = sources[key] || { status: "UNAVAILABLE" };
          return `<article class="sentiment-source ${source.status === "LIVE" ? tone(source.sentiment_index) : "unavailable"}">
            <div><strong>${esc(labels[key])}</strong><span>${esc(source.status || "UNAVAILABLE")}</span></div>
            <b>${fmt(source.sentiment_index, 0)}</b>
            <small>sent ${fmt(source.sentiment_score, 2)} · bull ${pct(source.bullish_pct)} · bear ${pct(source.bearish_pct)} · buzz ${fmt(source.buzz_score, 0)}</small>
          </article>`;
        }).join("")}
      </div>
      <div class="sentiment-drivers">
        <div class="sentiment-drivers-title">Top narrative drivers</div>
        ${driverRows.slice(0, 8).map(row => `<div class="sentiment-driver"><strong>${esc(row.ticker)}</strong><span>${esc(row.source)}</span><span>Buzz ${fmt(row.buzz, 0)}</span><span>Sent ${fmt(row.sentiment, 2)}</span></div>`).join("") || `<div class="sentiment-empty">No driver detail in the latest source responses.</div>`}
      </div>`;
  }

  async function load() {
    const root = ensureRoot();
    if (!root) return;
    try {
      const response = await fetch(`worldclass/market-sentiment.json?v=${Date.now()}`, { cache: "no-store" });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      render(await response.json());
    } catch (error) {
      console.warn("Market sentiment unavailable", error);
      root.innerHTML = `<div class="sentiment-empty">Daily market sentiment is unavailable. COT and macro layers remain independent.</div>`;
    }
  }

  load();
})();
