(() => {
  "use strict";

  const MARKET_LABELS = {
    sp500: "S&P 500",
    nq: "Nasdaq-100",
    vix: "VIX Futures",
    rty: "Russell 2000",
    dow: "Dow Jones",
    gold: "Gold",
    silver: "Silver"
  };

  let frame = 0;
  let observer = null;
  const $ = selector => document.querySelector(selector);

  function schedule() {
    if (frame) return;
    frame = requestAnimationFrame(() => {
      frame = 0;
      coordinate();
    });
  }

  function selectedMarket() {
    return $("#instrumentTabs [data-market].active")?.dataset.market
      || $("#instrumentTabs [data-market][aria-pressed='true']")?.dataset.market
      || "sp500";
  }

  function placeResearchAfterDecisionLayer() {
    const intelligence = $("#cotIntelligence");
    const decision = $("#currentEdgeCommand");
    if (!intelligence || !decision) return;
    const live = $("#liveTrackRecordPanel");
    const anchor = live || decision;
    if (anchor.nextElementSibling !== intelligence) anchor.insertAdjacentElement("afterend", intelligence);
  }

  function syncResearchMarket(root) {
    const market = selectedMarket();
    const pill = root.querySelector("#cotIntelMarket");
    if (pill && pill.textContent !== (MARKET_LABELS[market] || market)) pill.textContent = MARKET_LABELS[market] || market;
  }

  function edgePriority(card) {
    if (card.querySelector(".cot-role.primary_directional")) return 0;
    if (card.querySelector(".cot-role.secondary_directional")) return 1;
    return 2;
  }

  function sortActiveThresholdCards(root) {
    const subtitle = [...root.querySelectorAll(".cot-subtitle")]
      .find(node => (node.textContent || "").includes("ACTIVE THRESHOLD CONDITIONS"));
    const grid = subtitle?.nextElementSibling;
    if (!grid?.classList.contains("cot-edge-grid")) return;
    grid.classList.add("cot-edge-grid-active");
    grid.setAttribute("aria-label", "Active threshold conditions, directional actors first");
    const cards = [...grid.children].filter(node => node.classList.contains("threshold"));
    const sorted = cards.map((card, index) => ({ card, index, priority: edgePriority(card) }))
      .sort((a, b) => a.priority - b.priority || a.index - b.index)
      .map(item => item.card);
    if (cards.some((card, index) => card !== sorted[index])) sorted.forEach(card => grid.appendChild(card));
  }

  function classifyEdgeCards(root) {
    root.querySelectorAll(".cot-edge-card.threshold").forEach(card => {
      const metric = [...card.querySelectorAll(".cot-edge-metrics > div")]
        .find(cell => (cell.querySelector("span")?.textContent || "").includes("Excess vs baseline"));
      const value = Number.parseFloat((metric?.querySelector("b")?.textContent || "").replace("−", "-").replace(",", "."));
      card.classList.toggle("cot-edge-positive", Number.isFinite(value) && value > 0);
      card.classList.toggle("cot-edge-negative", Number.isFinite(value) && value < 0);
    });
    const continuous = [...root.querySelectorAll(".cot-subtitle")]
      .find(node => (node.textContent || "").includes("CONTINUOUS HISTORICAL EVIDENCE"));
    continuous?.nextElementSibling?.classList.add("cot-edge-grid-secondary");
  }

  function ensureEdgeOverview(root) {
    const body = root.querySelector("#cotIntelBody");
    if (!body) return;
    const title = [...body.querySelectorAll(".cot-section-title")]
      .find(node => (node.querySelector("h3")?.textContent || "").includes("What is active this week?"));
    if (!title) return;
    const activeCards = [...body.querySelectorAll(".cot-edge-card.threshold")];
    const directional = activeCards.filter(card => card.querySelector(".cot-role.primary_directional, .cot-role.secondary_directional")).length;
    const context = Math.max(0, activeCards.length - directional);
    let overview = body.querySelector(".cot-edge-overview");
    if (!overview) {
      overview = document.createElement("div");
      overview.className = "cot-edge-overview";
      title.insertAdjacentElement("afterend", overview);
    }
    overview.innerHTML = `
      <article><span>Active now</span><strong>${activeCards.length}</strong><small>current percentile triggers</small></article>
      <article><span>Directional actors</span><strong>${directional}</strong><small>primary + secondary evidence</small></article>
      <article><span>Context actors</span><strong>${context}</strong><small>collapsed in the decision layer</small></article>`;
  }

  function enhanceResearch() {
    const root = $("#cotIntelligence");
    if (!root) return;
    root.classList.add("cot-intel-worldclass", "decision-research-surface");
    root.querySelector(".cot-ux-market-switcher")?.remove();
    const intro = root.querySelector(".cot-intel-head p");
    if (intro && !intro.dataset.decisionCopy) {
      intro.dataset.decisionCopy = "1";
      intro.textContent = "Deep research for the market selected above: actor history, thresholds, horizon evidence, robustness and provenance. Conclusions remain in the decision layer; this section is proof on demand.";
    }
    syncResearchMarket(root);
    sortActiveThresholdCards(root);
    classifyEdgeCards(root);
    ensureEdgeOverview(root);
  }

  function coordinate() {
    placeResearchAfterDecisionLayer();
    enhanceResearch();
    document.documentElement.classList.toggle("cot-worldclass-ux-ready", Boolean($("#cotIntelligence")));
  }

  function boot() {
    coordinate();
    $("#instrumentTabs")?.addEventListener("click", schedule);
    observer = new MutationObserver(schedule);
    observer.observe($("main") || document.body, { subtree: true, childList: true, attributes: true, attributeFilter: ["class", "aria-pressed"] });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot, { once: true });
  else boot();
})();