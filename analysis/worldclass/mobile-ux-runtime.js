(() => {
  "use strict";

  const SELECTOR = 'link[data-cot-intelligence-asset="mobile-ux-css"]';
  let scheduled = false;

  function promoteMobileStylesheet() {
    scheduled = false;
    const link = document.querySelector(SELECTOR);
    if (!link || !document.head) return;
    if (document.head.lastElementChild !== link) document.head.appendChild(link);
    document.documentElement.dataset.mobileUxReady = "true";
  }

  function schedulePromotion() {
    if (scheduled) return;
    scheduled = true;
    queueMicrotask(promoteMobileStylesheet);
  }

  const observer = new MutationObserver(mutations => {
    if (mutations.some(mutation => [...mutation.addedNodes].some(node => node.nodeType === 1 && (node.tagName === "LINK" || node.tagName === "STYLE")))) {
      schedulePromotion();
    }
  });

  if (document.head) observer.observe(document.head, { childList: true });
  schedulePromotion();
  window.addEventListener("load", promoteMobileStylesheet, { once: true });
  window.setTimeout(promoteMobileStylesheet, 250);
  window.setTimeout(promoteMobileStylesheet, 1200);
  window.setTimeout(promoteMobileStylesheet, 2600);
})();
