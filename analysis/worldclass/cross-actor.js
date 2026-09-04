(() => {
  "use strict";

  const MULTIPLIERS = { sp500: 50, nq: 20, vix: 1000 };
  const ACTORS = [
    { key: "asset_mgr", label: "Asset Manager / Institutional" },
    { key: "lev_money", label: "Leveraged Funds" },
    { key: "other_reportable", label: "Other Reportables" },
    { key: "non_reportable", label: "Non-reportable" }
  ];
  const MARKETS = ["sp500", "nq", "vix"];
  const $ = selector => document.querySelector(selector);

  function finite(value) {
    if (value === null || value === undefined || value === "") return null;
    const number = Number(value);
    return Number.isFinite(number) ? number : null;
  }

  function esc(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function signed(value, digits = 1, suffix = "") {
    const n = finite(value);
    if (n === null) return "n/a";
    const body = Math.abs(n).toLocaleString("en-US", {
      minimumFractionDigits: digits,
      maximumFractionDigits: digits
    });
    return `${n > 0 ? "+" : n < 0 ? "−" : ""}${body}${suffix}`;
  }

  function tone(value, neutral = 0.01) {
    const n = finite(value);
    if (n === null || Math.abs(n) <= neutral) return "neutral";
    return n > 0 ? "positive" : "negative";
  }

  function tffRecords(base, market) {
    return (base?.COT_DATA?.tff?.[market]?.records || [])
      .filter(row => row?.date)
      .slice()
      .sort((a, b) => String(a.date).localeCompare(String(b.date)));
  }

  function rowMap(base, market) {
    return new Map(tffRecords(base, market).map(row => [String(row.date).slice(0, 10), row]));
  }

  function riskNotionalBn(row, actor, market) {
    const net = finite(row?.[`${actor}_net`]);
    const price = finite(row?.price);
    const multiplier = MULTIPLIERS[market];
    if (net === null || price === null || !multiplier) return null;
    return net * price * multiplier / 1e9;
  }

  function actorSeries(base, actor) {
    const maps = Object.fromEntries(MARKETS.map(market => [market, rowMap(base, market)]));
    const dates = [...maps.sp500.keys()]
      .filter(date => maps.nq.has(date) && maps.vix.has(date))
      .sort();
    const series = [];
    for (const date of dates) {
      const sp500 = riskNotionalBn(maps.sp500.get(date), actor, "sp500");
      const nq = riskNotionalBn(maps.nq.get(date), actor, "nq");
      const vixRaw = riskNotionalBn(maps.vix.get(date), actor, "vix");
      if ([sp500, nq, vixRaw].some(value => value === null)) continue;
      const vixInverse = -vixRaw;
      series.push({
        date,
        sp500,
        nq,
        vixInverse,
        combined: sp500 + nq + vixInverse
      });
    }
    return series;
  }

  function change(series, weeks) {
    if (series.length <= weeks) return null;
    const latest = finite(series.at(-1)?.combined);
    const prior = finite(series.at(-1 - weeks)?.combined);
    return latest === null || prior === null ? null : latest - prior;
  }

  function trendSeries(series, weeks) {
    const output = [];
    for (let index = weeks; index < series.length; index += 1) {
      const current = finite(series[index]?.combined);
      const prior = finite(series[index - weeks]?.combined);
      if (current !== null && prior !== null) output.push(current - prior);
    }
    return output;
  }

  function percentile(values, current) {
    const target = finite(current);
    const clean = values.map(finite).filter(value => value !== null).sort((a, b) => a - b);
    if (target === null || !clean.length) return null;
    let below = 0;
    let equal = 0;
    for (const value of clean) {
      if (value < target) below += 1;
      else if (value === target) equal += 1;
    }
    return ((below + Math.max(equal, 1) / 2) / clean.length) * 100;
  }

  function actorSnapshot(base, actor) {
    const series = actorSeries(base, actor.key);
    const latest = series.at(-1) || {};
    const trend13 = change(series, 13);
    const trend26 = change(series, 26);
    return {
      ...actor,
      date: latest.date || null,
      sp500: finite(latest.sp500),
      nq: finite(latest.nq),
      vixInverse: finite(latest.vixInverse),
      combined: finite(latest.combined),
      flow1: change(series, 1),
      flow4: change(series, 4),
      trend13,
      trend26,
      trend13Rank: percentile(trendSeries(series, 13), trend13),
      historyWeeks: series.length
    };
  }

  function rankClass(rank) {
    const n = finite(rank);
    if (n === null) return "";
    if (n >= 80) return "high";
    if (n <= 20) return "low";
    return "";
  }

  function extremeRows(base, market) {
    const extremes = base?.RESEARCH?.[market]?.extremes || {};
    return [...(extremes.best || []), ...(extremes.worst || [])];
  }

  function findExtreme(base, market, category, side = "bottom") {
    return extremeRows(base, market).find(row => row?.category === category && row?.side === side) || null;
  }

  function currentRank(base, market, category) {
    return finite(base?.RESEARCH?.[market]?.current?.[category]?.percentile);
  }

  function researchMeta(base, market) {
    return base?.RESEARCH?.[market]?._meta || {};
  }

  function horizonLine(row) {
    if (!row) return "Historical decile result unavailable";
    return `13W ${signed(row["13w"], 2, "%")} · 26W ${signed(row["26w"], 2, "%")} · 52W ${signed(row["52w"], 2, "%")}`;
  }

  function decileState(rank) {
    const n = finite(rank);
    if (n === null) return "Current percentile unavailable";
    if (n <= 10) return `ACTIVE · ${n.toFixed(1)}th percentile`;
    return `Not active · current percentile ${n.toFixed(1)}`;
  }

  function researchCards(base) {
    const spNon = findExtreme(base, "sp500", "non_reportable", "bottom");
    const nqNon = findExtreme(base, "nq", "non_reportable", "bottom");
    const nqOther = findExtreme(base, "nq", "other_reportable", "bottom");
    const spRank = currentRank(base, "sp500", "non_reportable");
    const nqRank = currentRank(base, "nq", "non_reportable");
    const otherRank = currentRank(base, "nq", "other_reportable");
    if (!spNon && !nqNon && !nqOther) return "";
    return `<div class="wc-cross-research" aria-label="Instrument-specific historical decile evidence">
      <article class="wc-cross-research-card strong">
        <span>S&P · Non-reportable bottom 10%</span>
        <strong>${esc(horizonLine(spNon))}</strong>
        <p><b>${esc(decileState(spRank))}</b>. This was the strongest bullish reset bucket in the S&P research sample.</p>
      </article>
      <article class="wc-cross-research-card caution">
        <span>NQ · Non-reportable bottom 10%</span>
        <strong>${esc(horizonLine(nqNon))}</strong>
        <p><b>${esc(decileState(nqRank))}</b>. Positive historical returns, but not the strongest NQ decile signal.</p>
      </article>
      <article class="wc-cross-research-card strong">
        <span>NQ · Other Reportable bottom 10%</span>
        <strong>${esc(horizonLine(nqOther))}</strong>
        <p><b>${esc(decileState(otherRank))}</b>. This was the strongest bullish NQ reset bucket in the stored research.</p>
      </article>
    </div>`;
  }

  function actorRow(snapshot) {
    return `<tr data-cross-actor="${esc(snapshot.key)}">
      <td class="wc-cross-actor-name"><strong>${esc(snapshot.label)}</strong><small>${esc(snapshot.date || "date unavailable")}</small></td>
      <td class="${tone(snapshot.sp500)}">${signed(snapshot.sp500, 1)}</td>
      <td class="${tone(snapshot.nq)}">${signed(snapshot.nq, 1)}</td>
      <td class="${tone(snapshot.vixInverse)}">${signed(snapshot.vixInverse, 1)}</td>
      <td class="wc-cross-actor-total ${tone(snapshot.combined)}">${signed(snapshot.combined, 1)}</td>
      <td class="${tone(snapshot.flow1)}">${signed(snapshot.flow1, 1)}</td>
      <td class="${tone(snapshot.flow4)}">${signed(snapshot.flow4, 1)}</td>
      <td class="${tone(snapshot.trend13)}">${signed(snapshot.trend13, 1)}</td>
      <td class="${tone(snapshot.trend26)}">${signed(snapshot.trend26, 1)}</td>
      <td><span class="wc-cross-actor-rank ${rankClass(snapshot.trend13Rank)}">${snapshot.trend13Rank === null ? "n/a" : `${snapshot.trend13Rank.toFixed(0)}th`}</span></td>
    </tr>`;
  }

  function render(base) {
    const root = $("#wcCrossActorPanel");
    if (!root || !base) return;
    const snapshots = ACTORS.map(actor => actorSnapshot(base, actor));
    const usable = snapshots.filter(row => row.combined !== null);
    if (!usable.length) {
      root.innerHTML = `<div class="wc-cross-actor-head"><div><span class="wc-v3-kicker">CROSS-INSTRUMENT ACTOR TREND</span><h2>Actor aggregation unavailable</h2><p>The compact runtime does not contain the common S&P, NQ and VIX observations needed to reconstruct the old comparison.</p></div></div>`;
      return;
    }
    const latestDate = usable.map(row => row.date).filter(Boolean).sort().at(-1) || "n/a";
    const historyFloor = Math.min(...usable.map(row => row.historyWeeks));
    const spMeta = researchMeta(base, "sp500");
    const nqMeta = researchMeta(base, "nq");
    root.innerHTML = `
      <div class="wc-cross-actor-head">
        <div>
          <span class="wc-v3-kicker">CROSS-INSTRUMENT ACTOR TREND</span>
          <h2>Same participant, combined across equity-risk futures</h2>
          <p>Restored from the old dashboard logic. Every row follows one participant across S&P 500, Nasdaq-100 and VIX, converts positions to USD notional, inverts VIX, then measures the participant's total 1W/4W flow and 13W/26W trend change.</p>
        </div>
        <div class="wc-cross-actor-formula" aria-label="Cross-market aggregation formula">
          <span><strong>S&P</strong> net</span><span>+</span><span><strong>NQ</strong> net</span><span>−</span><span><strong>VIX</strong> net</span><span>= risk notional</span>
        </div>
      </div>
      <div class="wc-cross-actor-table-wrap">
        <table class="wc-cross-actor-table">
          <thead><tr>
            <th>Actor</th><th>S&P $bn</th><th>NQ $bn</th><th>VIX inverse $bn</th><th>Combined $bn</th><th>1W Δ</th><th>4W Δ</th><th>13W trend</th><th>26W trend</th><th>13W rank</th>
          </tr></thead>
          <tbody>${usable.map(actorRow).join("")}</tbody>
        </table>
      </div>
      ${researchCards(base)}
      <div class="wc-cross-actor-foot">
        <span><strong>Current cross-market window:</strong> ${historyFloor} common weekly observations through ${esc(latestDate)}. Positive VIX-inverse means hedge selling / short volatility; negative means long volatility / hedge demand.</span>
        <span><strong>Decile research:</strong> ${esc(spMeta.sample_start || "n/a")}–${esc(spMeta.sample_end || "n/a")} S&P (${esc(spMeta.rows || "n/a")} rows); ${esc(nqMeta.sample_start || "n/a")}–${esc(nqMeta.sample_end || "n/a")} NQ (${esc(nqMeta.rows || "n/a")} rows). Bucket averages are descriptive conditional outcomes, not guaranteed excess returns.</span>
      </div>`;
  }

  function mount() {
    const base = window.__COT_WORLDCLASS_BASE__;
    if (!base) return;
    let section = $("#wcCrossActorPanel");
    if (!section) {
      section = document.createElement("section");
      section.id = "wcCrossActorPanel";
      section.className = "wc-cross-actor";
      section.setAttribute("aria-label", "Cross-instrument actor positioning comparison");
      const decision = $("#currentEdgeCommand");
      const command = $("#wcCommandCenter");
      const anchor = decision || command || $(".instrument-bar");
      if (!anchor) return;
      anchor.insertAdjacentElement("afterend", section);
    }
    render(base);
  }

  async function boot() {
    try {
      if (window.__COT_APP_DATA_READY__) await window.__COT_APP_DATA_READY__;
      mount();
    } catch (error) {
      console.error("Cross-instrument actor comparison failed to initialize.", error);
    }
  }

  boot();
})();
