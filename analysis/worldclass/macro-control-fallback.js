(() => {
  "use strict";

  const TARGET_KEYS = [
    "net_liquidity_4w_change",
    "bank_reserves_4w_change",
    "bank_reserves",
    "reserves",
    "sofr_iorb_spread",
    "effr_iorb_spread"
  ];

  const finite = value => {
    const number = Number(value);
    return Number.isFinite(number) ? number : null;
  };

  function latestMacroRow() {
    const root = window.__COT_WORLDCLASS_BASE__?.MACRO_MONITOR;
    if (!root || typeof root !== "object") return null;

    let best = null;
    let bestScore = -1;
    let bestDate = "";
    const seen = new Set();

    function visit(node, depth = 0) {
      if (!node || depth > 8 || typeof node !== "object" || seen.has(node)) return;
      seen.add(node);
      if (Array.isArray(node)) {
        for (const item of node) visit(item, depth + 1);
        return;
      }

      const score = TARGET_KEYS.reduce((sum, key) => sum + (finite(node[key]) !== null ? 1 : 0), 0);
      const date = String(node.date || node.observation_date || node.report_date || "").slice(0, 10);
      if (score > 0 && (score > bestScore || (score === bestScore && date > bestDate))) {
        best = node;
        bestScore = score;
        bestDate = date;
      }
      for (const value of Object.values(node)) visit(value, depth + 1);
    }

    visit(root);
    return best;
  }

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

  function cardByLabel(root, label) {
    return [...root.querySelectorAll(".wc-macro-pillar")].find(card =>
      card.querySelector(":scope > span")?.textContent?.trim().toUpperCase() === label
    );
  }

  function isUnavailable(card) {
    if (!card) return false;
    const value = card.querySelector(":scope > strong")?.textContent?.trim().toLowerCase();
    const state = card.querySelector(":scope > em")?.textContent?.trim().toLowerCase();
    return value === "n/a" || state === "unavailable";
  }

  function setCard(card, value, state, detail, tone) {
    if (!card || !isUnavailable(card)) return false;
    const strong = card.querySelector(":scope > strong");
    const em = card.querySelector(":scope > em");
    const small = card.querySelector(":scope > small");
    if (strong) strong.textContent = value;
    if (em) em.textContent = state;
    if (small) small.textContent = detail;
    card.classList.remove("positive", "negative", "warning");
    if (tone) card.classList.add(tone);
    card.dataset.macroFallback = "1";
    return true;
  }

  function applyFallback() {
    const root = document.querySelector("#wcMacroControl");
    if (!root) return false;
    const row = latestMacroRow();
    if (!row) return false;

    let used = false;
    const liquidity = finite(row.net_liquidity_4w_change);
    if (liquidity !== null) {
      used = setCard(
        cardByLabel(root, "SYSTEM LIQUIDITY"),
        signed(liquidity, 1, " bn"),
        liquidity > 0 ? "Supportive" : liquidity < 0 ? "Defensive" : "Neutral",
        "Fed − TGA − RRP · validated macro-monitor fallback",
        liquidity > 0 ? "positive" : liquidity < 0 ? "negative" : "warning"
      ) || used;
    }

    const reserveImpulse = finite(row.bank_reserves_4w_change);
    const reserveLevel = finite(row.bank_reserves) ?? finite(row.reserves);
    if (reserveImpulse !== null) {
      used = setCard(
        cardByLabel(root, "RESERVES"),
        signed(reserveImpulse, 1, " bn"),
        reserveImpulse > 0 ? "Supportive" : reserveImpulse < 0 ? "Defensive" : "Neutral",
        "4W reserve impulse · validated macro-monitor fallback",
        reserveImpulse > 0 ? "positive" : reserveImpulse < 0 ? "negative" : "warning"
      ) || used;
    } else if (reserveLevel !== null) {
      used = setCard(
        cardByLabel(root, "RESERVES"),
        plain(reserveLevel, 0),
        "Context",
        "Bank reserve level · no directional inference",
        "warning"
      ) || used;
    }

    const spread = finite(row.sofr_iorb_spread) ?? finite(row.effr_iorb_spread);
    if (spread !== null) {
      const abs = Math.abs(spread);
      const state = abs <= 0.02 ? "Normal" : abs <= 0.05 ? "Watch" : "Stress";
      used = setCard(
        cardByLabel(root, "FUNDING"),
        signed(spread, 3, " pp"),
        state,
        `${finite(row.sofr_iorb_spread) !== null ? "SOFR" : "EFFR"} − IORB fallback; full repo microstructure pending`,
        state === "Normal" ? "positive" : state === "Stress" ? "negative" : "warning"
      ) || used;
    }

    if (used) {
      const note = root.querySelector(".wc-control-note");
      if (note && !note.dataset.fallbackNote) {
        note.dataset.fallbackNote = "1";
        note.textContent += " Core liquidity/funding fields use the validated macro monitor when the extended plumbing payload is temporarily unavailable; reserve levels are never treated as directional impulses.";
      }
    }
    return used;
  }

  let attempts = 0;
  const timer = window.setInterval(() => {
    applyFallback();
    attempts += 1;
    if (attempts >= 40 || document.querySelectorAll("[data-macro-fallback='1']").length >= 3) {
      window.clearInterval(timer);
    }
  }, 250);

  document.addEventListener("click", event => {
    if (event.target.closest("[data-market],[data-control]")) window.setTimeout(applyFallback, 150);
  });
})();
