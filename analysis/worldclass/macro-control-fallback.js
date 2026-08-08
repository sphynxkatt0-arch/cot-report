(() => {
  "use strict";

  const finite = value => {
    const number = Number(value);
    return Number.isFinite(number) ? number : null;
  };

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
        ) {
          best = candidate;
        }
      }

      for (const value of Object.values(node)) visit(value, ownDate, depth + 1);
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
    let used = false;

    const liquidity = latestMetric(["net_liquidity_4w_change"]);
    if (liquidity) {
      used = setCard(
        cardByLabel(root, "SYSTEM LIQUIDITY"),
        signed(liquidity.value, 1, " bn"),
        liquidity.value > 0 ? "Supportive" : liquidity.value < 0 ? "Defensive" : "Neutral",
        `Fed − TGA − RRP · validated macro monitor${liquidity.date ? ` · ${liquidity.date}` : ""}`,
        liquidity.value > 0 ? "positive" : liquidity.value < 0 ? "negative" : "warning"
      ) || used;
    }

    const reserveImpulse = latestMetric(["bank_reserves_4w_change"]);
    const reserveLevel = latestMetric(["bank_reserves", "reserves"]);
    if (reserveImpulse) {
      used = setCard(
        cardByLabel(root, "RESERVES"),
        signed(reserveImpulse.value, 1, " bn"),
        reserveImpulse.value > 0 ? "Supportive" : reserveImpulse.value < 0 ? "Defensive" : "Neutral",
        `4W reserve impulse · validated macro monitor${reserveImpulse.date ? ` · ${reserveImpulse.date}` : ""}`,
        reserveImpulse.value > 0 ? "positive" : reserveImpulse.value < 0 ? "negative" : "warning"
      ) || used;
    } else if (reserveLevel) {
      used = setCard(
        cardByLabel(root, "RESERVES"),
        plain(reserveLevel.value, 0),
        "Context",
        `Bank reserve level · no directional inference${reserveLevel.date ? ` · ${reserveLevel.date}` : ""}`,
        "warning"
      ) || used;
    }

    const spread = latestMetric(["sofr_iorb_spread", "effr_iorb_spread"]);
    if (spread) {
      const abs = Math.abs(spread.value);
      const state = abs <= 0.02 ? "Normal" : abs <= 0.05 ? "Watch" : "Stress";
      used = setCard(
        cardByLabel(root, "FUNDING"),
        signed(spread.value, 3, " pp"),
        state,
        `${spread.key === "sofr_iorb_spread" ? "SOFR" : "EFFR"} − IORB · validated macro monitor${spread.date ? ` · ${spread.date}` : ""}`,
        state === "Normal" ? "positive" : state === "Stress" ? "negative" : "warning"
      ) || used;
    }

    if (used) {
      const note = root.querySelector(".wc-control-note");
      if (note && !note.dataset.fallbackNote) {
        note.dataset.fallbackNote = "1";
        note.textContent += " Core liquidity/funding fields are resolved independently from the validated macro monitor when the extended plumbing payload is unavailable; reserve levels are never treated as directional impulses.";
      }
    }
    return used;
  }

  let attempts = 0;
  const timer = window.setInterval(() => {
    applyFallback();
    attempts += 1;
    if (attempts >= 48 || document.querySelectorAll("[data-macro-fallback='1']").length >= 3) {
      window.clearInterval(timer);
    }
  }, 250);

  document.addEventListener("click", event => {
    if (event.target.closest("[data-market],[data-control]")) window.setTimeout(applyFallback, 150);
  });
})();
