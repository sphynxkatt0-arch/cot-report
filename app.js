const formatInt = new Intl.NumberFormat('en-US', { maximumFractionDigits: 0 });
const formatDecimal = new Intl.NumberFormat('en-US', { maximumFractionDigits: 1 });

function number(value, signed = false) {
  if (!Number.isFinite(value)) return '—';
  const formatted = formatInt.format(Math.abs(value));
  if (!signed || value === 0) return value < 0 ? `−${formatted}` : formatted;
  return value > 0 ? `+${formatted}` : `−${formatted}`;
}

function decimal(value, suffix = '') {
  return Number.isFinite(value) ? `${formatDecimal.format(value)}${suffix}` : '—';
}

function tone(value) {
  if (!Number.isFinite(value) || value === 0) return 'neutral';
  return value > 0 ? 'positive' : 'negative';
}

function dateLabel(value) {
  if (!value) return '—';
  return new Intl.DateTimeFormat('en-GB', { dateStyle: 'medium', timeZone: 'UTC' }).format(new Date(value));
}

function timeLabel(value) {
  if (!value) return '—';
  return new Intl.DateTimeFormat('en-GB', {
    dateStyle: 'medium',
    timeStyle: 'short',
    timeZone: 'Europe/Stockholm',
  }).format(new Date(value));
}

function signal(label, value, detail, options = {}) {
  const display = options.percent ? decimal(value, '%') : number(value, options.signed);
  return `
    <article class="signal">
      <span>${label}</span>
      <strong class="${options.tone === false ? 'neutral' : tone(value)}">${display}</strong>
      <small>${detail}</small>
    </article>`;
}

function tableRow(label, item) {
  return `
    <tr>
      <td>${label}</td>
      <td>${number(item.long)}</td>
      <td>${number(item.short)}</td>
      <td class="${tone(item.net)}">${number(item.net, true)}</td>
      <td class="${tone(item.weeklyChange)}">${number(item.weeklyChange, true)}</td>
      <td>${decimal(item.netPctOpenInterest, '%')}</td>
      <td><span class="pill">${decimal(item.percentile3y, '%')}</span></td>
    </tr>`;
}

function marketCard(market) {
  const rows = [
    tableRow('Asset Manager', market.tff.assetManager),
    tableRow('Leveraged Funds', market.tff.leveragedFunds),
    tableRow('Dealer / Intermediary', market.tff.dealer),
    tableRow('Other Reportables', market.tff.otherReportables),
    tableRow('Non-reportable', market.tff.nonReportable),
    tableRow('Legacy Non-commercial', market.legacy.nonCommercial),
  ].join('');

  return `
    <section class="market-card">
      <header class="market-head">
        <div class="market-title">
          <div class="symbol">${market.symbol}</div>
          <div>
            <h2>${market.name}</h2>
            <p>CFTC ${market.code} · report ${dateLabel(market.reportDate)}</p>
          </div>
        </div>
        <div class="oi">
          <span>Open interest</span>
          <strong>${number(market.openInterest)}</strong>
          <small class="${tone(market.changeOpenInterest)}">${number(market.changeOpenInterest, true)} weekly</small>
        </div>
      </header>
      <div class="market-body">
        <div class="signal-grid">
          ${signal('Legacy non-commercial net', market.legacy.nonCommercial.net, `${decimal(market.legacy.nonCommercial.percentile3y, '%')} 3-year percentile`, { signed: true })}
          ${signal('Asset Manager net', market.tff.assetManager.net, `${decimal(market.tff.assetManager.percentile3y, '%')} 3-year percentile`, { signed: true })}
          ${signal('Leveraged Funds net', market.tff.leveragedFunds.net, `${number(market.tff.leveragedFunds.weeklyChange, true)} weekly change`, { signed: true })}
          ${signal('AM − leveraged divergence', market.tff.amVsLeveragedDivergencePctOi, `${number(market.tff.amVsLeveragedDivergence, true)} contracts`, { percent: true })}
        </div>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Participant</th>
                <th>Long</th>
                <th>Short</th>
                <th>Net</th>
                <th>Weekly Δ net</th>
                <th>Net / OI</th>
                <th>3Y percentile</th>
              </tr>
            </thead>
            <tbody>${rows}</tbody>
          </table>
        </div>
      </div>
    </section>`;
}

function updateStatus(data) {
  const states = Object.values(data.markets).map((market) => market.release.state);
  const state = states.includes('stale') ? 'stale' : states.includes('delayed') ? 'delayed' : 'current';
  const maxAge = Math.max(...Object.values(data.markets).map((market) => market.release.ageDays ?? 0));
  const label = state === 'current' ? 'Current CFTC release' : state === 'delayed' ? 'Release may be delayed' : 'CFTC data is stale';

  document.querySelector('#status-dot').className = `status-dot ${state}`;
  document.querySelector('#status-label').textContent = label;
  document.querySelector('#status-detail').textContent = `${maxAge} day${maxAge === 1 ? '' : 's'} since position date`;
}

async function load() {
  const marketsNode = document.querySelector('#markets');
  try {
    const response = await fetch('/api/cot');
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || data.error || `HTTP ${response.status}`);

    document.querySelector('#report-date').textContent = dateLabel(data.latestReportDate);
    document.querySelector('#fetched-at').textContent = timeLabel(data.fetchedAt);
    updateStatus(data);
    marketsNode.innerHTML = [data.markets.sp500, data.markets.nq].map(marketCard).join('');
  } catch (error) {
    document.querySelector('#status-dot').className = 'status-dot stale';
    document.querySelector('#status-label').textContent = 'Refresh failed';
    document.querySelector('#status-detail').textContent = 'Official source unavailable';
    marketsNode.innerHTML = `
      <section class="error-card">
        <h2>Could not load the latest COT data</h2>
        <p>${error.message}</p>
        <a href="/api/cot">Open the API response ↗</a>
      </section>`;
  }
}

load();
