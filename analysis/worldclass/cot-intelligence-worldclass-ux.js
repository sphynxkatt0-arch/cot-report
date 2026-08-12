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
  const $$ = selector => [...document.querySelectorAll(selector)];

  function schedule() {
    if (frame) return;
    frame = window.requestAnimationFrame(() => {
      frame = 0;
      coordinate();
    });
  }

  function canonicalMarketButtons() {
    return $$("#instrumentTabs [data-market]").filter(button => MARKET_LABELS[button.dataset.market]);
  }

  function selectedMarket() {
    return $("#instrumentTabs [data-market].active")?.dataset.market
      || $("#instrumentTabs [data-market][aria-pressed='true']")?.dataset.market
      || "sp500";
  }

  function placeEvidenceAfterDecisionLayer() {
    const intelligence = $("#cotIntelligence");
    if (!intelligence) return;
    const anchor = $("#currentEdgeCommand") || $("#wcCommandCenter") || $(".instrument-bar");
    if (!anchor || anchor === intelligence) return;
    if (anchor.nextElementSibling !== intelligence) anchor.insertAdjacentElement("afterend", intelligence);
  }

  function marketButtonMarkup(button) {
    const market = button.dataset.market;
    const label = (button.textContent || "").trim() || MARKET_LABELS[market] || market;
    return `<button type="button" class="cot-ux-market-button" data-cot-ux-market="${market}" aria-pressed="false" title="Switch evidence to ${label}">${label}</button>`;
  }

  function ensureMarketSwitcher(root) {
    const canonical = canonicalMarketButtons();
    if (!canonical.length) return;

    let shell = root.querySelector(".cot-intel-navshell");
    let switcher = root.querySelector(".cot-ux-market-switcher");
    const tabs = root.querySelector(".cot-intel-tabs");

    if (!shell && tabs) {
      shell = document.createElement("div");
      shell.className = "cot-intel-navshell";
      tabs.parentNode.insertBefore(shell, tabs);
      shell.appendChild(tabs);
    }

    if (!switcher) {
      switcher = document.createElement("div");
      switcher.className = "cot-ux-market-switcher";
      switcher.setAttribute("role", "group");
      switcher.setAttribute("aria-label", "Select market for COT evidence");
      switcher.innerHTML = `
        <div class="cot-ux-market-copy">
          <span>MARKET</span>
          <strong>Select first, then read the evidence</strong>
        </div>
        <div class="cot-ux-market-buttons">${canonical.map(marketButtonMarkup).join("")}</div>`;
      switcher.addEventListener("click", event => {
        const control = event.target.closest("[data-cot-ux-market]");
        if (!control) return;
        const target = $(`#instrumentTabs [data-market="${control.dataset.cotUxMarket}"]`);
        target?.click();
        schedule();
      });
      if (shell) shell.insertAdjacentElement("afterbegin", switcher);
      else root.querySelector(".cot-intel-head")?.insertAdjacentElement("afterend", switcher);
    } else {
      const rendered = new Set($$(".cot-ux-market-button", switcher).map(button => button.dataset.cotUxMarket));
      const expected = new Set(canonical.map(button => button.dataset.market));
      const same = rendered.size === expected.size && [...expected].every(market => rendered.has(market));
      if (!same) {
        const container = switcher.querySelector(".cot-ux-market-buttons");
        if (container) container.innerHTML = canonical.map(marketButtonMarkup).join("");
      }
    }
  }

  function syncMarketSwitcher(root) {
    const market = selectedMarket();
    root.querySelectorAll("[data-cot-ux-market]").forEach(button => {
      const active = button.dataset.cotUxMarket === market;
      button.classList.toggle("active", active);
      button.setAttribute("aria-pressed", String(active));
    });
    const pill = root.querySelector("#cotIntelMarket");
    if (pill) pill.textContent = MARKET_LABELS[market] || market;
  }

  function edgePriority(card) {
    if (card.querySelector(".cot-role.primary_directional")) return 0;
    if (card.querySelector(".cot-role.secondary_directional")) return 1;
    return 2;
  }

  function sortActiveThresholdCards(root) {
    const subtitles = [...root.querySelectorAll(".cot-subtitle")];
    const subtitle = subtitles.find(node => (node.textContent || "").includes("ACTIVE THRESHOLD CONDITIONS"));
    const grid = subtitle?.nextElementSibling;
    if (!grid?.classList.contains("cot-edge-grid")) return;
    grid.classList.add("cot-edge-grid-active");
    grid.setAttribute("aria-label", "Active threshold conditions, directional actors first");
    const cards = [...grid.children].filter(node => node.classList.contains("threshold"));
    if (cards.length < 2) return;
    const sorted = cards.map((card, index) => ({ card, index, priority: edgePriority(card) }))
      .sort((a, b) => a.priority - b.priority || a.index - b.index)
      .map(item => item.card);
    if (cards.some((card, index) => card !== sorted[index])) sorted.forEach(card => grid.appendChild(card));
  }

  function classifyEdgeCards(root) {
    root.querySelectorAll(".cot-edge-card.threshold").forEach(card => {
      const metric = [...card.querySelectorAll(".cot-edge-metrics > div")]
        .find(cell => (cell.querySelector("span")?.textContent || "").includes("Excess vs baseline"));
      const text = metric?.querySelector("b")?.textContent || "";
      const value = Number.parseFloat(text.replace("−", "-").replace(",", "."));
      card.classList.toggle("cot-edge-positive", Number.isFinite(value) && value > 0);
      card.classList.toggle("cot-edge-negative", Number.isFinite(value) && value < 0);
    });

    const subtitles = [...root.querySelectorAll(".cot-subtitle")];
    const continuous = subtitles.find(node => (node.textContent || "").includes("CONTINUOUS HISTORICAL EVIDENCE"));
    const grid = continuous?.nextElementSibling;
    if (grid?.classList.contains("cot-edge-grid")) {
      grid.classList.add("cot-edge-grid-secondary");
      grid.setAttribute("aria-label", "Continuous historical evidence");
    }
  }

  function ensureEdgeOverview(root) {
    const body = root.querySelector("#cotIntelBody");
    if (!body) return;
    const title = [...body.querySelectorAll(".cot-section-title")]
      .find(node => (node.querySelector("h3")?.textContent || "").includes("What is active this week?"));
    if (!title) return;

    const activeCards = body.querySelectorAll(".cot-edge-card.threshold");
    const directional = [...activeCards].filter(card => card.querySelector(".cot-role.primary_directional, .cot-role.secondary_directional")).length;
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
      <article><span>Context actors</span><strong>${context}</strong><small>structure, hedging and aggregation</small></article>`;
  }

  function enhanceIntelligence() {
    const root = $("#cotIntelligence");
    if (!root) return;
    root.classList.add("cot-intel-worldclass");
    const intro = root.querySelector(".cot-intel-head p");
    if (intro && !intro.dataset.uxCopy) {
      intro.dataset.uxCopy = "1";
      intro.textContent = "Select the market first. Then move from current positioning to active edges, horizon evidence, actor research and prospective validation. Tuesday positions are usable only after public availability.";
    }
    ensureMarketSwitcher(root);
    syncMarketSwitcher(root);
    sortActiveThresholdCards(root);
    classifyEdgeCards(root);
    ensureEdgeOverview(root);
  }

  function coordinate() {
    placeEvidenceAfterDecisionLayer();
    enhanceIntelligence();
    document.documentElement.classList.toggle("cot-worldclass-ux-ready", Boolean($("#cotIntelligence")));
  }

  function boot() {
    coordinate();
    $("#instrumentTabs")?.addEventListener("click", schedule);
    observer = new MutationObserver(schedule);
    observer.observe($("main") || document.body, {
      subtree: true,
      childList: true,
      attributes: true,
      attributeFilter: ["class", "aria-pressed"]
    });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot, { once: true });
  else boot();
})();
