(() => {
  "use strict";

  const CACHE_KEY = "cot-macro-live-official-v1";
  const CACHE_FRESH_MS = 30 * 60 * 1000;
  const CACHE_MAX_MS = 24 * 60 * 60 * 1000;
  const STORE = window.__COT_MACRO_LIVE__ = window.__COT_MACRO_LIVE__ || {
    core: {},
    official: {},
    updated_at: 0
  };

  const finite = value => {
    const number = Number(value);
    return Number.isFinite(number) ? number : null;
  };

  const toneFromState = state => /support|normal|fresh/i.test(state || "")
    ? "positive"
    : /defens|stress|restrict|stale/i.test(state || "")
      ? "negative"
      : "warning";

  function signed(value, digits = 1, suffix = "") {
    const number = finite(value);
    if (number === null) return "n/a";
    const sign = number > 0 ? "+" : number < 0 ? "−" : "";
    return `${sign}${Math.abs(number).toLocaleString(undefined, {
      minimumFractionDigits: digits,
      maximumFractionDigits: digits
    })}${suffix}`;
  }

  function plain(value, digits = 0, suffix = "") {
    const number = finite(value);
    if (number === null) return "n/a";
    return `${number.toLocaleString(undefined, {
      minimumFractionDigits: digits,
      maximumFractionDigits: digits
    })}${suffix}`;
  }

  function latestMetric(keys) {
    const root = window.__COT_WORLDCLASS_BASE__?.MACRO_MONITOR;
    if (!root || typeof root !== "object") return null;
    const wanted = new Set(keys);
    const seen = new Set();
    let best = null;
    let sequence = 0;

    function visit(node, inheritedDate = "", depth = 0) {
      if (!node || depth > 9 || typeof node !== "object" || seen.has(node)) return;
      seen.add(node);
      if (Array.isArray(node)) {
        for (const item of node) visit(item, inheritedDate, depth + 1);
        return;
      }

      const ownDate = String(
        node.date || node.observation_date || node.report_date || node.as_of_date || inheritedDate || ""
      ).slice(0, 10);

      for (const [key, raw] of Object.entries(node)) {
        if (!wanted.has(key)) continue;
        const value = finite(raw);
        if (value === null) continue;
        sequence += 1;
        const candidate = { key, value, date: ownDate, sequence };
        if (
          !best ||
          (candidate.date && !best.date) ||
          (candidate.date && best.date && candidate.date > best.date) ||
          (candidate.date === best.date && candidate.sequence > best.sequence)
        ) best = candidate;
      }

      for (const value of Object.values(node)) visit(value, ownDate, depth + 1);
    }

    visit(root);
    return best;
  }

  function buildCoreState() {
    const next = {};
    const liquidity = latestMetric(["net_liquidity_4w_change"]);
    if (liquidity) {
      next.system_liquidity = {
        ok: true,
        display: signed(liquidity.value, 1, " bn"),
        state: liquidity.value > 0 ? "Supportive" : liquidity.value < 0 ? "Defensive" : "Neutral",
        detail: `Fed − TGA − RRP · validated macro monitor${liquidity.date ? ` · ${liquidity.date}` : ""}`,
        source: "macro-monitor"
      };
    }

    const reserveImpulse = latestMetric(["bank_reserves_4w_change"]);
    const reserveLevel = latestMetric(["bank_reserves", "reserves"]);
    if (reserveImpulse) {
      next.reserves = {
        ok: true,
        display: signed(reserveImpulse.value, 1, " bn"),
        state: reserveImpulse.value > 0 ? "Supportive" : reserveImpulse.value < 0 ? "Defensive" : "Neutral",
        detail: `4W reserve impulse · validated macro monitor${reserveImpulse.date ? ` · ${reserveImpulse.date}` : ""}`,
        source: "macro-monitor"
      };
    } else if (reserveLevel) {
      next.reserves = {
        ok: true,
        display: plain(reserveLevel.value, 0),
        state: "Context",
        detail: `Bank reserve level · no directional inference${reserveLevel.date ? ` · ${reserveLevel.date}` : ""}`,
        source: "macro-monitor"
      };
    }

    const spread = latestMetric(["sofr_iorb_spread", "effr_iorb_spread"]);
    if (spread) {
      const abs = Math.abs(spread.value);
      const state = abs <= 0.02 ? "Normal" : abs <= 0.05 ? "Watch" : "Stress";
      next.funding_fallback = {
        ok: true,
        display: signed(spread.value, 3, " pp"),
        state,
        detail: `${spread.key === "sofr_iorb_spread" ? "SOFR" : "EFFR"} − IORB · validated macro monitor${spread.date ? ` · ${spread.date}` : ""}`,
        source: "macro-monitor"
      };
    }

    STORE.core = next;
    STORE.updated_at = Date.now();
  }

  function readOfficialCache() {
    try {
      const payload = JSON.parse(localStorage.getItem(CACHE_KEY) || "null");
      if (!payload || typeof payload !== "object") return;
      const fetchedAt = Number(payload.fetched_at || 0);
      const cacheAge = Date.now() - fetchedAt;
      if (!fetchedAt || cacheAge > CACHE_MAX_MS) return;
      const official = {};
      for (const [key, metric] of Object.entries({
        funding: payload.funding,
        dealers: payload.dealers,
        fiscal: payload.fiscal,
        auctions: payload.auctions
      })) {
        if (!metric?.ok) continue;
        official[key] = {
          ...metric,
          stale: Boolean(metric.stale) || cacheAge > CACHE_FRESH_MS,
          detail: `${metric.detail || "official public source"}${cacheAge > CACHE_FRESH_MS ? " · cached browser recovery" : ""}`,
          source: "official-live"
        };
      }
      STORE.official = official;
      STORE.updated_at = Date.now();
    } catch {
      // Keep the last successfully parsed in-memory state.
    }
  }

  function cardByLabel(root, label) {
    return [...root.querySelectorAll(".wc-macro-pillar")].find(card =>
      card.querySelector(":scope > span")?.textContent?.trim().toUpperCase() === label
    ) || null;
  }

  function unavailable(card) {
    if (!card) return true;
    const value = card.querySelector(":scope > strong")?.textContent?.trim().toLowerCase();
    const state = card.querySelector(":scope > em")?.textContent?.trim().toLowerCase();
    return value === "n/a" || !value || state === "unavailable" || !state;
  }

  function replaceable(card, priority) {
    if (!card) return false;
    if (unavailable(card)) return true;
    if (card.dataset.macroPersistent) return true;
    if (card.dataset.macroFallback === "1") return true;
    if (card.dataset.liveOfficial === "1") return priority === "official";
    return false;
  }

  function setText(node, value) {
    if (node && node.textContent !== value) node.textContent = value;
  }

  function setTone(card, desired) {
    for (const tone of ["positive", "negative", "warning"]) {
      if (tone === desired) {
        if (!card.classList.contains(tone)) card.classList.add(tone);
      } else if (card.classList.contains(tone)) card.classList.remove(tone);
    }
  }

  function applyMetric(root, label, metric, priority) {
    if (!metric?.ok) return false;
    const card = cardByLabel(root, label);
    if (!replaceable(card, priority)) return false;
    const state = metric.stale ? `Stale · ${metric.state}` : metric.state;
    setText(card.querySelector(":scope > strong"), String(metric.display || "n/a"));
    setText(card.querySelector(":scope > em"), String(state || "Context"));
    setText(card.querySelector(":scope > small"), String(metric.detail || metric.source || ""));
    setTone(card, metric.stale ? "warning" : toneFromState(metric.state));
    const marker = `${priority}:${metric.source || "runtime"}`;
    if (card.dataset.macroPersistent !== marker) card.dataset.macroPersistent = marker;
    delete card.dataset.macroFallback;
    if (priority === "official") card.dataset.liveOfficial = "1";
    return true;
  }

  let scheduled = false;
  function render() {
    scheduled = false;
    buildCoreState();
    readOfficialCache();
    const root = document.querySelector("#wcMacroControl");
    if (!root) return;

    applyMetric(root, "SYSTEM LIQUIDITY", STORE.core.system_liquidity, "core");
    applyMetric(root, "RESERVES", STORE.core.reserves, "core");
    applyMetric(root, "FUNDING", STORE.official.funding || STORE.core.funding_fallback, STORE.official.funding ? "official" : "core");
    applyMetric(root, "DEALERS", STORE.official.dealers, "official");
    applyMetric(root, "FISCAL CASH", STORE.official.fiscal, "official");
    applyMetric(root, "AUCTION QUALITY", STORE.official.auctions, "official");
  }

  function scheduleRender() {
    if (scheduled) return;
    scheduled = true;
    queueMicrotask(render);
  }

  const observer = new MutationObserver(mutations => {
    if (mutations.some(mutation => mutation.target?.closest?.("#wcMacroControl") || mutation.target?.id === "wcMacroControl")) {
      scheduleRender();
    }
  });
  observer.observe(document.body, { subtree: true, childList: true, characterData: true });

  window.addEventListener("cot:macro-live-updated", scheduleRender);
  document.addEventListener("click", event => {
    if (event.target.closest("[data-market],[data-control]")) setTimeout(scheduleRender, 0);
  });

  // The official recovery script writes its cache asynchronously. Poll briefly so
  // successful network results become persistent even if another renderer races it.
  let polls = 0;
  const poll = setInterval(() => {
    scheduleRender();
    polls += 1;
    if (polls >= 45) clearInterval(poll);
  }, 500);

  scheduleRender();
})();
