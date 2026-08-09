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

  function modelWeights() {
    return window.__COT_WORLDCLASS_BASE__?.MODEL_SPEC?.score_models?.disaggregated?.category_weights || {};
  }

  function patchRole(role) {
    const strong = role.querySelector("strong");
    const label = strong?.textContent?.trim();
    const meta = ROLE_META[label];
    if (!strong || !meta) return;

    const weight = Number(modelWeights()[meta.key] ?? 0);
    const governed = Number.isFinite(weight) ? weight : 0;
    const weightKey = governed.toFixed(2);
    if (role.dataset.governanceKey === meta.key && role.dataset.governanceWeight === weightKey) return;

    const status = governed === 0 ? "CONTEXT ONLY" : "DIRECTIONAL INPUT";
    const sign = governed > 0 ? "+" : "";
    role.innerHTML = `<strong>${label}</strong><span class="wc-role-copy">${meta.description}</span><small class="wc-role-governance">${status} · score weight ${sign}${weightKey}</small>`;
    role.dataset.governanceKey = meta.key;
    role.dataset.governanceWeight = weightKey;
  }

  function patchBanner() {
    const banner = document.getElementById("wcTaxonomyBanner");
    if (!banner) return;
    banner.querySelectorAll(".wc-role").forEach(patchRole);
  }

  const observer = new MutationObserver(mutations => {
    if (mutations.some(mutation => mutation.target?.id === "wcTaxonomyBanner" || mutation.target?.closest?.("#wcTaxonomyBanner"))) {
      patchBanner();
    }
  });

  function start() {
    observer.observe(document.body, { childList: true, subtree: true });
    patchBanner();
    document.addEventListener("click", event => {
      if (event.target?.closest?.("#instrumentTabs, .controls-surface")) setTimeout(patchBanner, 0);
    });
    document.addEventListener("change", event => {
      if (event.target?.closest?.(".controls-surface")) setTimeout(patchBanner, 0);
    });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start, { once: true });
  else start();
})();
