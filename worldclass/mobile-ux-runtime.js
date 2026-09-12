(() => {
  "use strict";

  const SELECTOR = 'link[data-cot-intelligence-asset="mobile-ux-css"]';
  const media = window.matchMedia("(max-width: 720px)");
  let scheduled = false;

  function promoteMobileStylesheet() {
    scheduled = false;
    const link = document.querySelector(SELECTOR);
    if (link && document.head && document.head.lastElementChild !== link) document.head.appendChild(link);
    document.documentElement.dataset.mobileUxReady = "true";
  }

  // Responsive geometry lives in mobile-ux.css so resizing back to desktop
  // cannot leave viewport-wide inline styles attached to the dashboard.

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
