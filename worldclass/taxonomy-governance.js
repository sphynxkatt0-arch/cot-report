(() => {
  "use strict";

  const ROLE_META = {
    "Producer / Merchant / Processor / User": {
      key: "producer_merchant",
      description: "Commercial physical hedgers: producers, processors and users of the commodity."
    },
    "Swap Dealers": {
      key: "swap_dealer",
      description: "Swap/intermediation books serving clients and carrying OTC-linked risk."
    },
    "Managed Money": {
      key: "managed_money",
      description: "Managed speculative money such as CTAs and CPOs; the production directional metals cohort."
    },
    "Other Reportables": {
      key: "other_reportable",
      description: "Large reportable traders outside the named Disaggregated groups; retained as positioning context."
    },
    "Non-reportable": {
      key: "non_reportable",
      description: "Smaller traders below CFTC reporting thresholds; retained as positioning context."
    }
  };

  const state = { metals: null, scheduled: false };

  const finite = value => {
    const number = Number(value);
    return Number.isFinite(number) ? number : null;
  };

  function modelSpec() {
    return window.__COT_WORLDCLASS_BASE__?.MODEL_SPEC || null;
  }

  function weights(dataset = "disaggregated") {
    return modelSpec()?.score_models?.[dataset]?.category_weights || {};
  }

  function patchRole(role) {
    const strong = role.querySelector("strong");
    const label = strong?.textContent?.trim();
    const meta = ROLE_META[label];
    if (!strong || !meta) return;

    const weight = finite(weights("disaggregated")[meta.key]) ?? 0;
    const weightKey = weight.toFixed(2);
    if (role.dataset.governanceKey === meta.key && role.dataset.governanceWeight === weightKey) return;

    const status = weight === 0 ? "CONTEXT ONLY" : "DIRECTIONAL INPUT";
    const sign = weight > 0 ? "+" : "";
    role.innerHTML = `<strong>${label}</strong><span class="wc-role-copy">${meta.description}</span><div class="wc-role-governance"><small>${status} · score weight ${sign}${weightKey}</small></div>`;
    role.dataset.governanceKey = meta.key;
    role.dataset.governanceWeight = weightKey;
  }

  function patchBanner() {
    const banner = document.getElementById("wcTaxonomyBanner");
    if (!banner) return;
    banner.querySelectorAll(".wc-role").forEach(patchRole);
  }

  function activeMarket() {
    return document.querySelector("#instrumentTabs [data-market].active")?.dataset.market || "sp500";
  }

  function activeDataset() {
    return document.querySelector("#desktopControls [data-control='dataset']")?.value
      || document.querySelector("#mobileControlBody [data-control='dataset']")?.value
      || (["gold", "silver"].includes(activeMarket()) ? "disaggregated" : "tff");
  }

  function payload(dataset, market) {
    if (dataset === "disaggregated") {
      return state.metals?.markets?.[market]
        || window.__COT_WORLDCLASS_BASE__?.COT_DATA?.disaggregated?.[market]
        || null;
    }
    return window.__COT_WORLDCLASS_BASE__?.COT_DATA?.[dataset]?.[market] || null;
  }

  function percentile(values, current) {
    const value = finite(current);
    const clean = values.map(finite).filter(item => item !== null).sort((a, b) => a - b);
    if (value === null || !clean.length) return null;
    let less = 0;
    let equal = 0;
    for (const item of clean) {
      if (item < value) less += 1;
      else if (item === value) equal += 1;
    }
    return (less + Math.max(equal, 1) / 2) / clean.length * 100;
  }

  function governedScore(dataset, market) {
    const block = payload(dataset, market);
    const rows = (block?.records || []).filter(row => row?.date);
    const categories = block?.categories || {};
    const latest = rows.at(-1) || {};
    const modelWeights = weights(dataset);
    if (!rows.length || !Object.keys(modelWeights).length) return null;

    let weighted = 0;
    let totalWeight = 0;
    for (const key of Object.keys(categories)) {
      const weight = finite(modelWeights[key]) ?? 0;
      if (!weight) continue;
      const rank = percentile(rows.map(row => row[`${key}_net_oi_pct`]), latest[`${key}_net_oi_pct`]);
      if (rank === null) continue;
      weighted += weight * ((rank - 50) / 50);
      totalWeight += Math.abs(weight);
    }
    if (!totalWeight) return null;
    return Math.max(0, Math.min(100, 50 + 50 * weighted / totalWeight));
  }

  function scoreState(score) {
    if (score === null) return "Unavailable";
    const thresholds = modelSpec()?.thresholds || {};
    const bullish = finite(thresholds.bullish) ?? 60;
    const bearish = finite(thresholds.bearish) ?? 40;
    return score >= bullish ? "Bullish" : score <= bearish ? "Bearish" : "Neutral";
  }

  function setTone(node, stateName) {
    if (!node) return;
    node.classList.remove("positive", "negative", "warning");
    if (/bull/i.test(stateName)) node.classList.add("positive");
    else if (/bear/i.test(stateName)) node.classList.add("negative");
    else node.classList.add("warning");
  }

  function decisionCard(label) {
    return [...document.querySelectorAll("#wcDecisionLayer .wc-decision-card")].find(card =>
      card.querySelector(":scope > span")?.textContent?.trim().toUpperCase() === label
    ) || null;
  }

  function patchDecisionLayer() {
    const root = document.getElementById("wcDecisionLayer");
    if (!root || !modelSpec()) return;

    const dataset = activeDataset();
    const market = activeMarket();
    const score = governedScore(dataset, market);
    const regime = scoreState(score);
    const card = decisionCard("POSITIONING");
    if (card) {
      const display = score === null ? "n/a" : score.toFixed(0);
      const detail = `Governed ${modelSpec().model_version} · canonical MODEL_SPEC`;
      const strong = card.querySelector(":scope > strong");
      const em = card.querySelector(":scope > em");
      const small = card.querySelector(":scope > small");
      if (strong?.textContent !== display) strong.textContent = display;
      if (em?.textContent !== regime) em.textContent = regime;
      if (small?.textContent !== detail) small.textContent = detail;
      setTone(card, regime);
      card.dataset.governedModel = modelSpec().model_version;
    }

    const liquidity = decisionCard("LIQUIDITY")?.querySelector(":scope > em")?.textContent?.trim() || "Unavailable";
    const regimeLabel = root.querySelector(".wc-regime-label");
    if (regimeLabel) {
      const text = score === null ? "Incomplete regime" : `${regime} COT / ${liquidity} macro`;
      const strong = regimeLabel.querySelector("strong");
      if (strong?.textContent !== text) strong.textContent = text;
      setTone(regimeLabel, regime);
    }
  }

  function patchTffLegacyDivergence() {
    const root = document.getElementById("wcWeeklyIntel");
    if (!root || !modelSpec()) return;
    const market = activeMarket();
    const tff = governedScore("tff", market);
    const legacy = governedScore("legacy", market);
    const card = [...root.querySelectorAll(".wc-divergence")].find(item =>
      item.querySelector("strong")?.textContent?.trim() === "TFF vs Legacy"
    );
    if (tff === null || legacy === null) {
      card?.remove();
      return;
    }
    const difference = Math.abs(tff - legacy);
    if (difference < 20) {
      card?.remove();
      const grid = root.querySelector(".wc-divergence-grid");
      if (grid && !grid.children.length) grid.remove();
      return;
    }
    if (card) {
      const span = card.querySelector("span");
      const text = `TFF ${tff.toFixed(0)} vs Legacy ${legacy.toFixed(0)} · governed ${modelSpec().model_version}`;
      if (span?.textContent !== text) span.textContent = text;
    }
  }

  function patchGovernance() {
    state.scheduled = false;
    patchBanner();
    patchDecisionLayer();
    patchTffLegacyDivergence();
  }

  function schedulePatch() {
    if (state.scheduled) return;
    state.scheduled = true;
    queueMicrotask(patchGovernance);
  }

  async function loadMetals() {
    try {
      const response = await fetch(`worldclass/metals.json?v=${Date.now()}`, { cache: "no-store" });
      if (response.ok) state.metals = await response.json();
    } catch {}
    schedulePatch();
  }

  const observer = new MutationObserver(mutations => {
    if (mutations.some(mutation =>
      mutation.target?.id === "wcTaxonomyBanner"
      || mutation.target?.id === "wcDecisionLayer"
      || mutation.target?.id === "wcWeeklyIntel"
      || mutation.target?.closest?.("#wcTaxonomyBanner, #wcDecisionLayer, #wcWeeklyIntel")
    )) schedulePatch();
  });

  function start() {
    observer.observe(document.body, { childList: true, subtree: true, characterData: true });
    patchGovernance();
    loadMetals();
    document.addEventListener("click", event => {
      if (event.target?.closest?.("#instrumentTabs, .controls-surface")) setTimeout(schedulePatch, 0);
    });
    document.addEventListener("change", event => {
      if (event.target?.closest?.(".controls-surface")) setTimeout(schedulePatch, 0);
    });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start, { once: true });
  else start();
})();