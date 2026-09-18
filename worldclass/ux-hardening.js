(() => {
  "use strict";

  let frame = 0;
  let observer = null;
  const DAY_MS = 86400000;
  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
  const pad = value => String(value).padStart(2, "0");
  const utcDate = (year, month, day) => new Date(Date.UTC(year, month, day, 12));
  const utcDay = date => Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), date.getUTCDate());
  const ymd = date => date ? `${date.getUTCFullYear()}-${pad(date.getUTCMonth() + 1)}-${pad(date.getUTCDate())}` : "";

  function addMonths(year, month, offset) {
    const date = utcDate(year, month + offset, 1);
    return [date.getUTCFullYear(), date.getUTCMonth()];
  }

  function thirdFriday(year, month) {
    const first = utcDate(year, month, 1);
    const offset = (5 - first.getUTCDay() + 7) % 7;
    return utcDate(year, month, 1 + offset + 14);
  }

  function nextIndexOpex(today, quarterlyOnly = false) {
    for (let offset = 0; offset < 30; offset += 1) {
      const [year, month] = addMonths(today.getUTCFullYear(), today.getUTCMonth(), offset);
      if (quarterlyOnly && ![2, 5, 8, 11].includes(month)) continue;
      const candidate = thirdFriday(year, month);
      if (utcDay(candidate) >= utcDay(today)) return candidate;
    }
    return null;
  }

  function nextVixSettlement(today) {
    for (let offset = 0; offset < 30; offset += 1) {
      const [year, month] = addMonths(today.getUTCFullYear(), today.getUTCMonth(), offset);
      const [nextYear, nextMonth] = addMonths(year, month, 1);
      const followingMonthOpex = thirdFriday(nextYear, nextMonth);
      const candidate = new Date(followingMonthOpex.getTime() - (30 * DAY_MS));
      if (utcDay(candidate) >= utcDay(today)) return candidate;
    }
    return null;
  }

  function dateLabel(date) {
    if (!date) return "n/a";
    return new Intl.DateTimeFormat(undefined, {
      month: "short",
      day: "numeric",
      year: "numeric",
      timeZone: "UTC"
    }).format(date);
  }

  function countdown(date, today) {
    if (!date) return "Date unavailable";
    const days = Math.round((utcDay(date) - utcDay(today)) / DAY_MS);
    if (days === 0) return "today";
    if (days === 1) return "in 1 day";
    return `in ${days} days`;
  }

  function expiryItem(label, date, today) {
    return `<div class="ux-expiry-item"><span>${label}</span><b>${dateLabel(date)}</b><small>${countdown(date, today)}</small></div>`;
  }

  function enhanceExpiryCalendar(root) {
    const node = $(".decision-expiries", root);
    if (!node) return;
    const now = new Date();
    const today = utcDate(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate());
    const monthly = nextIndexOpex(today);
    const quarterly = nextIndexOpex(today, true);
    const vix = nextVixSettlement(today);
    const key = [monthly, quarterly, vix].map(ymd).join("|");
    if (node.dataset.uxExpiryKey === key) return;

    node.dataset.uxExpiryKey = key;
    node.classList.add("ux-expiry-calendar");
    node.setAttribute("aria-label", "Important options expiry dates");
    node.innerHTML = `<strong>Important expiries</strong><div class="ux-expiry-items">${expiryItem("Next index OPEX", monthly, today)}${expiryItem("Next quarterly OPEX", quarterly, today)}${expiryItem("Next VIX settlement", vix, today)}<small class="ux-expiry-note">Calendar-standard dates; exchange holiday rules can shift settlement.</small></div>`;
  }

  function enhanceTableSemantics(root) {
    const table = $(".decision-cot-change-table", root);
    if (!table) return;
    const head = $(".decision-cot-change-head", table);
    const columnCount = head?.children?.length || 0;
    if (head) {
      [...head.children].forEach(cell => cell.setAttribute("role", "columnheader"));
    }
    const rows = $$(".decision-cot-change-row", table);
    table.setAttribute("aria-rowcount", String(rows.length + (head ? 1 : 0)));
    if (columnCount) table.setAttribute("aria-colcount", String(columnCount));
    rows.forEach(row => {
      [...row.children].forEach((cell, index) => cell.setAttribute("role", index === 0 ? "rowheader" : "cell"));
      const actor = $(":scope > div strong", row)?.textContent?.trim();
      if (actor) row.setAttribute("aria-label", `${actor} latest COT position changes`);
    });
  }

  function enhance() {
    const root = $("#currentEdgeCommand");
    if (!root) return;
    enhanceTableSemantics(root);
    enhanceExpiryCalendar(root);
    document.documentElement.classList.add("cot-ux-hardening-ready");
  }

  function schedule() {
    if (frame) return;
    frame = requestAnimationFrame(() => {
      frame = 0;
      enhance();
    });
  }

  function boot() {
    schedule();
    observer = new MutationObserver(schedule);
    observer.observe($("main") || document.body, { childList: true, subtree: true });
    window.addEventListener("popstate", schedule);
    window.addEventListener("cot:market-change", schedule);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot, { once: true });
  else boot();
})();
