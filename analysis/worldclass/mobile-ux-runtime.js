(() => {
  "use strict";

  const SELECTOR = 'link[data-cot-intelligence-asset="mobile-ux-css"]';
  const media = window.matchMedia("(max-width: 720px)");
  let scheduled = false;

  function important(el, property, value) {
    if (el) el.style.setProperty(property, value, "important");
  }

  function promoteMobileStylesheet() {
    scheduled = false;
    const link = document.querySelector(SELECTOR);
    if (link && document.head && document.head.lastElementChild !== link) document.head.appendChild(link);
    enforceMobileGeometry();
    document.documentElement.dataset.mobileUxReady = "true";
  }

  function enforceMobileGeometry() {
    if (!media.matches) return;
    important(document.body, "overflow-x", "hidden");
    const frame = document.querySelector(".app-frame");
    const main = document.querySelector("main");
    important(frame, "width", "100%");
    important(frame, "max-width", "100%");
    important(frame, "min-width", "0");
    important(main, "width", "100%");
    important(main, "max-width", "100%");
    important(main, "min-width", "0");

    const commandWidth = "calc(100vw - 24px)";
    for (const selector of ["#currentEdgeCommand", "#wcCommandCenter", "#cotIntelligence"]) {
      const el = document.querySelector(selector);
      important(el, "width", commandWidth);
      important(el, "max-width", commandWidth);
      important(el, "min-width", "0");
      important(el, "justify-self", "stretch");
    }

    const bar = document.querySelector(".instrument-bar");
    important(bar, "width", "100vw");
    important(bar, "max-width", "100vw");
    const tabs = document.querySelector(".instrument-tabs");
    important(tabs, "display", "flex");
    important(tabs, "grid-template-columns", "none");
    important(tabs, "width", "100%");
    important(tabs, "max-width", "100%");
    important(tabs, "overflow-x", "auto");
    important(tabs, "overflow-y", "hidden");
    document.querySelectorAll(".instrument-tab").forEach(tab => important(tab, "min-width", "94px"));
  }

  function schedulePromotion() {
    if (scheduled) return;
    scheduled = true;
    queueMicrotask(promoteMobileStylesheet);
  }

  const headObserver = new MutationObserver(mutations => {
    if (mutations.some(mutation => [...mutation.addedNodes].some(node => node.nodeType === 1 && (node.tagName === "LINK" || node.tagName === "STYLE")))) schedulePromotion();
  });
  const bodyObserver = new MutationObserver(() => schedulePromotion());

  if (document.head) headObserver.observe(document.head, { childList: true });
  if (document.body) bodyObserver.observe(document.body, { childList: true, subtree: true });
  media.addEventListener?.("change", schedulePromotion);
  window.addEventListener("resize", schedulePromotion, { passive: true });
  window.addEventListener("orientationchange", schedulePromotion, { passive: true });
  window.addEventListener("load", promoteMobileStylesheet, { once: true });

  schedulePromotion();
  window.setTimeout(promoteMobileStylesheet, 100);
  window.setTimeout(promoteMobileStylesheet, 500);
  window.setTimeout(promoteMobileStylesheet, 1500);
  window.setTimeout(promoteMobileStylesheet, 3000);
})();
