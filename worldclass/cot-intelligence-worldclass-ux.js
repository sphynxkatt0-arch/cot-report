(() => {
  "use strict";

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

  function coordinateResearchSurface() {
    const legacy = $("#cotIntelligence");
    if (!legacy) return;
    legacy.classList.add("cot-intel-worldclass", "decision-legacy-research");
    const researchVisible = document.documentElement.dataset.cotDecisionView === "research";
    legacy.setAttribute("aria-hidden", researchVisible ? "false" : "true");
    legacy.querySelector(".cot-ux-market-switcher")?.remove();
  }

  function coordinate() {
    coordinateResearchSurface();
    document.documentElement.classList.toggle("cot-worldclass-ux-ready", Boolean($("#currentEdgeCommand")));
  }

  function boot() {
    coordinate();
    $("#instrumentTabs")?.addEventListener("click", schedule);
    observer = new MutationObserver(schedule);
    observer.observe($("main") || document.body, {
      subtree: true,
      childList: true,
      attributes: true,
      attributeFilter: ["class", "aria-pressed", "data-cot-decision-view"]
    });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot, { once: true });
  else boot();
})();
