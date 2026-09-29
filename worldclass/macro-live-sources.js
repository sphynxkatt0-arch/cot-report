(() => {
  "use strict";

  const OFR = "https://data.financialresearch.gov/v1";
  const FISCAL = "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting";
  const CACHE_KEY = "cot-macro-live-official-v1";
  const CACHE_TTL_MS = 30 * 60 * 1000;
  const DAY_MS = 86400000;

  const finite = value => {
    const number = Number(value);
    return Number.isFinite(number) ? number : null;
  };
  const clamp = (value, low, high) => Math.max(low, Math.min(high, value));
  const iso = value => {
    const text = String(value || "").slice(0, 10);
    return /^\d{4}-\d{2}-\d{2}$/.test(text) ? text : null;
  };
  const ageDays = value => {
    const stamp = iso(value);
    if (!stamp) return null;
    const parsed = new Date(`${stamp}T12:00:00Z`);
    return Math.max(0, Math.floor((Date.now() - parsed.getTime()) / DAY_MS));
  };
  const dateAgo = days => new Date(Date.now() - days * DAY_MS).toISOString().slice(0, 10);
  const stateFromScore = score => score >= 60 ? "Supportive" : score <= 40 ? "Defensive" : "Neutral";
  const toneFromState = state => /support|normal/i.test(state || "") ? "positive" : /defens|stress/i.test(state || "") ? "negative" : "warning";
  const mean = values => values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : null;

  async function fetchJson(url, timeoutMs = 14000) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
      const response = await fetch(url, { cache: "no-store", mode: "cors", signal: controller.signal });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      return await response.json();
    } finally {
      clearTimeout(timer);
    }
  }

  function parseSeries(payload, scaleDivisor = 1) {
    if (!Array.isArray(payload)) return [];
    const points = [];
    for (const item of payload) {
      if (!Array.isArray(item) || item.length < 2) continue;
      const date = iso(item[0]);
      const value = finite(item[1]);
      if (date && value !== null) points.push([date, value / scaleDivisor]);
    }
    return [...new Map(points).entries()].sort((a, b) => a[0].localeCompare(b[0]));
  }

  function change(points, observations) {
    if (points.length <= observations) return null;
    return points.at(-1)[1] - points.at(-1 - observations)[1];
  }

  function zscore(points, window = 156) {
    const values = points.slice(-window).map(item => item[1]).filter(value => finite(value) !== null);
    if (values.length < 26) return null;
    const avg = mean(values);
    const variance = values.reduce((sum, value) => sum + (value - avg) ** 2, 0) / Math.max(1, values.length - 1);
    const std = Math.sqrt(variance);
    return std > 1e-12 ? (values.at(-1) - avg) / std : null;
  }

  async function ofrSeries(mnemonic, startDays, scaleDivisor = 1) {
    const params = new URLSearchParams({ mnemonic, start_date: dateAgo(startDays), remove_nulls: "true" });
    const payload = await fetchJson(`${OFR}/series/timeseries?${params}`);
    const points = parseSeries(payload, scaleDivisor);
    if (!points.length) throw new Error(`${mnemonic}: no observations`);
    return { mnemonic, points, date: points.at(-1)[0], value: points.at(-1)[1] };
  }

  function card(label) {
    const root = document.querySelector("#wcMacroControl");
    if (!root) return null;
    return [...root.querySelectorAll(".wc-macro-pillar")].find(item =>
      item.querySelector(":scope > span")?.textContent?.trim().toUpperCase() === label
    ) || null;
  }

  function canReplace(target) {
    if (!target) return false;
    const value = target.querySelector(":scope > strong")?.textContent?.trim().toLowerCase();
    const state = target.querySelector(":scope > em")?.textContent?.trim().toLowerCase();
    return value === "n/a" || state === "unavailable" || target.dataset.macroFallback === "1" || target.dataset.liveOfficial === "1";
  }

  function setCard(label, metric) {
    const target = card(label);
    if (!target || !metric?.ok || !canReplace(target)) return false;
    const strong = target.querySelector(":scope > strong");
    const em = target.querySelector(":scope > em");
    const small = target.querySelector(":scope > small");
    if (strong) strong.textContent = metric.display;
    if (em) em.textContent = metric.stale ? `Stale · ${metric.state}` : metric.state;
    if (small) small.textContent = metric.detail;
    target.classList.remove("positive", "negative", "warning");
    target.classList.add(metric.stale ? "warning" : toneFromState(metric.state));
    target.dataset.liveOfficial = "1";
    delete target.dataset.macroFallback;
    return true;
  }

  function markFailure(label, source) {
    const target = card(label);
    if (!target || !canReplace(target) || target.dataset.liveOfficial === "1") return;
    const small = target.querySelector(":scope > small");
    if (small) small.textContent = `${source} live feed unavailable · no value substituted`;
  }

  function formatNumber(value, digits = 1, suffix = "") {
    const number = finite(value);
    if (number === null) return "n/a";
    return `${number.toLocaleString(undefined, { minimumFractionDigits: digits, maximumFractionDigits: digits })}${suffix}`;
  }

  async function loadFunding() {
    const mnemonics = ["REPO-DVP_AR_OO-P", "REPO-GCF_AR_OO-P", "REPO-TRI_AR_OO-P"];
    const settled = await Promise.allSettled(mnemonics.map(mnemonic => ofrSeries(mnemonic, 70)));
    const valid = settled.filter(item => item.status === "fulfilled").map(item => item.value);
    const fresh = valid.filter(item => (ageDays(item.date) ?? 999) <= 5);
    if (fresh.length < 2) throw new Error("fewer than two fresh repo-rate series");

    const rates = fresh.map(item => item.value);
    const dispersionBp = (Math.max(...rates) - Math.min(...rates)) * 100;
    const movesBp = fresh.map(item => change(item.points, 5)).filter(value => value !== null).map(value => Math.abs(value) * 100);
    const maxMoveBp = movesBp.length ? Math.max(...movesBp) : null;
    let score = 50;
    score -= Math.min(25, Math.max(0, dispersionBp - 2) * 1.8);
    if (maxMoveBp !== null) score -= Math.min(20, Math.max(0, maxMoveBp - 3) * 1.2);
    score = Math.round(clamp(score, 0, 100) * 10) / 10;
    const latest = fresh.map(item => item.date).sort().at(-1);
    const state = stateFromScore(score);
    return {
      ok: true,
      display: `${score.toFixed(0)}/100`,
      state,
      stale: false,
      date: latest,
      detail: `OFR repo · ${fresh.length}/3 feeds · dispersion ${dispersionBp.toFixed(1)} bp${maxMoveBp === null ? "" : ` · max move ${maxMoveBp.toFixed(1)} bp`} · ${latest}`
    };
  }

  function metadataScore(row) {
    if (String(row?.dataset || "").toLowerCase() !== "nypd") return -1e9;
    const text = [row?.value, row?.field, row?.mnemonic, row?.dataset].join(" ").toLowerCase();
    let score = 0;
    for (const term of ["net positions", "treasury"]) score += text.includes(term) ? 3 : -1;
    for (const term of ["agency", "mortgage", "corporate"]) if (text.includes(term)) score -= 8;
    return score;
  }

  async function resolveDealerPositionMnemonic() {
    const params = new URLSearchParams({ query: "Net Positions*U.S. Treasury*" });
    const rows = await fetchJson(`${OFR}/metadata/search?${params}`);
    if (!Array.isArray(rows)) return null;
    const candidates = rows
      .filter(row => row && row.mnemonic && String(row.mnemonic).toLowerCase() !== "none")
      .map(row => ({ row, score: metadataScore(row) }))
      .sort((a, b) => b.score - a.score);
    return candidates[0]?.score >= 4 ? String(candidates[0].row.mnemonic) : null;
  }

  async function loadDealers() {
    let positionsMnemonic = null;
    try { positionsMnemonic = await resolveDealerPositionMnemonic(); } catch {}
    const specs = [
      positionsMnemonic ? ["inventory", positionsMnemonic] : null,
      ["financing", "NYPD-PD_RP_T_TOT-A"],
      ["fails", "NYPD-PD_AFtD_T-A"]
    ].filter(Boolean);

    const settled = await Promise.allSettled(specs.map(async ([key, mnemonic]) => {
      const series = await ofrSeries(mnemonic, 1800, 1_000_000);
      return { ...series, key, z: zscore(series.points) };
    }));
    const valid = settled.filter(item => item.status === "fulfilled").map(item => item.value);
    const fresh = valid.filter(item => (ageDays(item.date) ?? 999) <= 12);
    if (!fresh.length) throw new Error("no fresh primary-dealer series");

    let score = 50;
    const reasons = [];
    const inventory = fresh.find(item => item.key === "inventory");
    const financing = fresh.find(item => item.key === "financing");
    const fails = fresh.find(item => item.key === "fails");
    if (inventory?.z !== null && inventory?.z !== undefined) {
      score -= Math.max(0, inventory.z) * 10;
      reasons.push(`inventory z ${inventory.z.toFixed(2)}`);
    }
    if (financing?.z !== null && financing?.z !== undefined) {
      score -= Math.max(0, financing.z) * 6;
      reasons.push(`financing z ${financing.z.toFixed(2)}`);
    }
    if (fails?.z !== null && fails?.z !== undefined) {
      score -= Math.max(0, fails.z) * 12;
      reasons.push(`fails z ${fails.z.toFixed(2)}`);
    }
    score = Math.round(clamp(score, 0, 100) * 10) / 10;
    const latest = fresh.map(item => item.date).sort().at(-1);
    return {
      ok: true,
      display: `${score.toFixed(0)}/100`,
      state: stateFromScore(score),
      stale: false,
      date: latest,
      detail: `OFR primary dealers · ${fresh.length}/3 feeds · ${reasons.join(" · ") || "fresh source coverage"} · ${latest}`
    };
  }

  function fiscalRows(payload) {
    return Array.isArray(payload?.data) ? payload.data.filter(row => row && typeof row === "object") : [];
  }

  function fiscalValue(row, keys) {
    for (const key of keys) {
      const value = finite(row?.[key]);
      if (value !== null) return value;
    }
    return null;
  }

  function parseOperatingCash(rows) {
    const byDate = new Map();
    for (const row of rows) {
      const date = iso(row.record_date);
      if (!date) continue;
      const descriptor = [row.account_type, row.account_nm, row.account_name, row.line_desc].filter(Boolean).join(" ").toLowerCase();
      if (!descriptor.includes("treasury general account")) continue;
      const value = fiscalValue(row, ["close_today_bal", "closing_balance", "open_today_bal", "account_bal", "current_day_bal"]);
      if (value === null) continue;
      let priority = descriptor.includes("closing balance") ? 30 : 10;
      if (descriptor.includes("opening balance")) priority = 5;
      const previous = byDate.get(date);
      if (!previous || priority > previous.priority) byDate.set(date, { priority, value: value / 1000 });
    }
    return [...byDate.entries()].map(([date, item]) => [date, item.value]).sort((a, b) => a[0].localeCompare(b[0]));
  }

  function parseTreasuryFlows(rows) {
    const byDate = new Map();
    for (const row of rows) {
      const date = iso(row.record_date);
      const amountMn = fiscalValue(row, ["transaction_today_amt", "current_day_amt", "today_amt", "amount"]);
      if (!date || amountMn === null) continue;
      const type = String(row.transaction_type || row.type || "").toLowerCase();
      const category = String(row.transaction_catg || row.transaction_category || row.account_type || "Other");
      if (!byDate.has(date)) byDate.set(date, { deposits: 0, withdrawals: 0, taxes: 0 });
      const bucket = byDate.get(date);
      const amountBn = amountMn / 1000;
      if (type.includes("withdraw")) bucket.withdrawals += amountBn;
      else if (type.includes("deposit")) {
        bucket.deposits += amountBn;
        if (/tax|internal revenue/i.test(category)) bucket.taxes += amountBn;
      }
    }
    return [...byDate.entries()].sort((a, b) => a[0].localeCompare(b[0]));
  }

  async function fiscalEndpoint(endpoint, start, pageSize) {
    const params = new URLSearchParams({
      filter: `record_date:gte:${start}`,
      sort: "record_date",
      "page[size]": String(pageSize)
    });
    return fetchJson(`${FISCAL}/dts/${endpoint}?${params}`, 18000);
  }

  async function loadFiscal() {
    const start = dateAgo(70);
    const settled = await Promise.allSettled([
      fiscalEndpoint("operating_cash_balance", start, 500),
      fiscalEndpoint("deposits_withdrawals_operating_cash", start, 10000)
    ]);
    const cashRows = settled[0].status === "fulfilled" ? fiscalRows(settled[0].value) : [];
    const flowRows = settled[1].status === "fulfilled" ? fiscalRows(settled[1].value) : [];
    const cash = parseOperatingCash(cashRows);
    const flows = parseTreasuryFlows(flowRows);
    const cashFresh = cash.length && (ageDays(cash.at(-1)[0]) ?? 999) <= 4;
    const flowFresh = flows.length && (ageDays(flows.at(-1)[0]) ?? 999) <= 4;
    if (!cashFresh && !flowFresh) throw new Error("Daily Treasury Statement feeds unavailable/stale");

    const tgaChange = cashFresh ? change(cash, Math.min(5, Math.max(1, cash.length - 1))) : null;
    let flow5 = null;
    let tax5 = null;
    if (flowFresh) {
      const recent = flows.slice(-5);
      flow5 = recent.reduce((sum, [, item]) => sum + item.withdrawals - item.deposits, 0);
      tax5 = recent.reduce((sum, [, item]) => sum + item.taxes, 0);
    }

    let score = 50;
    if (flow5 !== null) score += clamp(flow5 / 4, -25, 25);
    if (tgaChange !== null) score -= clamp(tgaChange / 5, -15, 15);
    score = Math.round(clamp(score, 0, 100) * 10) / 10;
    const dates = [cashFresh ? cash.at(-1)[0] : null, flowFresh ? flows.at(-1)[0] : null].filter(Boolean).sort();
    const latest = dates.at(-1);
    return {
      ok: true,
      display: `${score.toFixed(0)}/100`,
      state: stateFromScore(score),
      stale: false,
      date: latest,
      detail: `Treasury DTS · 5D private cash ${flow5 === null ? "n/a" : `${flow5 >= 0 ? "+" : ""}${flow5.toFixed(1)} bn`} · TGA Δ ${tgaChange === null ? "n/a" : `${tgaChange >= 0 ? "+" : ""}${tgaChange.toFixed(1)} bn`}${tax5 !== null ? ` · tax ${tax5.toFixed(1)} bn` : ""} · ${latest}`
    };
  }

  function auctionRows(payload) {
    if (!Array.isArray(payload?.data)) return [];
    const rows = [];
    for (const raw of payload.data) {
      const auctionDate = iso(raw?.auction_date);
      const btc = finite(raw?.bid_to_cover_ratio);
      const accepted = finite(raw?.total_accepted);
      if (!auctionDate || btc === null || accepted === null || accepted <= 0) continue;
      const dealer = finite(raw.primary_dealer_accepted);
      const indirect = finite(raw.indirect_bidder_accepted);
      const direct = finite(raw.direct_bidder_accepted);
      const securityType = String(raw.security_type || "Unknown");
      const term = String(raw.original_security_term || raw.security_term || "Unknown");
      rows.push({
        auction_date: auctionDate,
        security_type: securityType,
        security_term: term,
        term_key: `${securityType.toLowerCase()}|${term.toLowerCase()}`,
        bid_to_cover_ratio: btc,
        total_accepted: accepted,
        dealer_share: dealer === null ? null : dealer / accepted * 100,
        indirect_share: indirect === null ? null : indirect / accepted * 100,
        direct_share: direct === null ? null : direct / accepted * 100
      });
    }
    return rows.sort((a, b) => a.auction_date.localeCompare(b.auction_date));
  }

  function sameTerm(rows, latest) {
    const prior = rows.filter(row => row.term_key === latest.term_key && row.auction_date < latest.auction_date).slice(-8);
    if (!prior.length) return { ...latest, quality: null };
    const btcPrior = mean(prior.map(row => row.bid_to_cover_ratio).filter(value => value !== null));
    const dealerPrior = mean(prior.map(row => row.dealer_share).filter(value => value !== null));
    const indirectPrior = mean(prior.map(row => row.indirect_share).filter(value => value !== null));
    const btcDelta = btcPrior === null ? null : latest.bid_to_cover_ratio - btcPrior;
    const dealerDelta = dealerPrior === null || latest.dealer_share === null ? null : latest.dealer_share - dealerPrior;
    const indirectDelta = indirectPrior === null || latest.indirect_share === null ? null : latest.indirect_share - indirectPrior;
    let quality = 50;
    if (btcDelta !== null) quality += btcDelta * 30;
    if (dealerDelta !== null) quality -= dealerDelta * 0.6;
    if (indirectDelta !== null) quality += indirectDelta * 0.4;
    return { ...latest, btc_delta: btcDelta, dealer_delta: dealerDelta, indirect_delta: indirectDelta, quality: Math.round(clamp(quality, 0, 100) * 10) / 10 };
  }

  async function loadAuctions() {
    const params = new URLSearchParams({
      filter: `auction_date:gte:${dateAgo(730)}`,
      sort: "auction_date",
      "page[size]": "1000"
    });
    const rows = auctionRows(await fetchJson(`${FISCAL}/od/auctions_query?${params}`, 18000));
    const coupons = rows.filter(row => ["note", "bond", "tips"].includes(row.security_type.toLowerCase()));
    if (!coupons.length) throw new Error("no completed coupon auctions");
    const latestByTerm = new Map();
    for (const row of coupons) latestByTerm.set(row.term_key, row);
    const comparisons = [...latestByTerm.values()].map(row => sameTerm(coupons, row)).sort((a, b) => b.auction_date.localeCompare(a.auction_date));
    const cutoff = dateAgo(45);
    let recent = comparisons.filter(row => row.auction_date >= cutoff && row.quality !== null);
    if (!recent.length) recent = comparisons.filter(row => row.quality !== null).slice(0, 5);
    if (!recent.length) throw new Error("insufficient same-tenor auction history");
    const weight = recent.reduce((sum, row) => sum + Math.max(1, row.total_accepted), 0);
    const score = Math.round((recent.reduce((sum, row) => sum + row.quality * Math.max(1, row.total_accepted), 0) / weight) * 10) / 10;
    const btcDelta = mean(recent.map(row => row.btc_delta).filter(value => value !== null));
    const dealerDelta = mean(recent.map(row => row.dealer_delta).filter(value => value !== null));
    const indirectDelta = mean(recent.map(row => row.indirect_delta).filter(value => value !== null));
    const latest = coupons.map(row => row.auction_date).sort().at(-1);
    const stale = (ageDays(latest) ?? 999) > 14;
    return {
      ok: true,
      display: `${score.toFixed(0)}/100`,
      state: stateFromScore(score),
      stale,
      date: latest,
      detail: `Treasury auctions · BTC Δ ${btcDelta === null ? "n/a" : `${btcDelta >= 0 ? "+" : ""}${btcDelta.toFixed(2)}`} · dealer ${dealerDelta === null ? "n/a" : `${dealerDelta >= 0 ? "+" : ""}${dealerDelta.toFixed(1)} pp`} · indirect ${indirectDelta === null ? "n/a" : `${indirectDelta >= 0 ? "+" : ""}${indirectDelta.toFixed(1)} pp`} · ${latest}`
    };
  }

  function render(payload) {
    if (!payload) return;
    setCard("FUNDING", payload.funding);
    setCard("DEALERS", payload.dealers);
    setCard("FISCAL CASH", payload.fiscal);
    setCard("AUCTION QUALITY", payload.auctions);
    if (!payload.funding?.ok) markFailure("FUNDING", "OFR");
    if (!payload.dealers?.ok) markFailure("DEALERS", "OFR");
    if (!payload.fiscal?.ok) markFailure("FISCAL CASH", "U.S. Treasury Fiscal Data");
    if (!payload.auctions?.ok) markFailure("AUCTION QUALITY", "U.S. Treasury Fiscal Data");

    const root = document.querySelector("#wcMacroControl");
    const note = root?.querySelector(".wc-control-note");
    if (note && Object.values(payload).some(item => item?.ok) && !note.dataset.liveOfficialNote) {
      note.dataset.liveOfficialNote = "1";
      note.textContent += " Missing server-side plumbing is recovered from the official OFR and U.S. Treasury public APIs in-browser; the backend and browser use the same scoring rules.";
    }
  }

  function cached() {
    try {
      const payload = JSON.parse(localStorage.getItem(CACHE_KEY) || "null");
      if (!payload || Date.now() - Number(payload.fetched_at || 0) > CACHE_TTL_MS) return null;
      return payload;
    } catch { return null; }
  }

  function save(payload) {
    try { localStorage.setItem(CACHE_KEY, JSON.stringify(payload)); } catch {}
  }

  async function refresh() {
    const jobs = await Promise.allSettled([loadFunding(), loadDealers(), loadFiscal(), loadAuctions()]);
    const value = index => jobs[index].status === "fulfilled" ? jobs[index].value : { ok: false };
    const payload = {
      fetched_at: Date.now(),
      funding: value(0),
      dealers: value(1),
      fiscal: value(2),
      auctions: value(3)
    };
    save(payload);
    render(payload);
  }

  function needsLiveData() {
    return ["FUNDING", "DEALERS", "FISCAL CASH", "AUCTION QUALITY"].some(label => canReplace(card(label)));
  }

  let attempts = 0;
  const ready = setInterval(() => {
    attempts += 1;
    if (!document.querySelector("#wcMacroControl")) {
      if (attempts > 48) clearInterval(ready);
      return;
    }
    clearInterval(ready);
    const cache = cached();
    if (cache) render(cache);
    if (!cache && needsLiveData()) refresh();
  }, 250);

  document.addEventListener("click", event => {
    if (!event.target.closest("[data-market],[data-control]")) return;
    setTimeout(() => {
      const cache = cached();
      if (cache) render(cache);
      else if (needsLiveData()) refresh();
    }, 180);
  });
})();
