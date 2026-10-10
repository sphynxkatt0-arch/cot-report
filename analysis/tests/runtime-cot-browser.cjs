// Run against the API-serving local server or a verified deployment:
// BASE_URL=http://127.0.0.1:8769 node analysis/tests/runtime-cot-browser.cjs
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

(async () => {
  const browser = await chromium.launch({ headless: true, ...(process.platform === 'win32' ? { channel: 'msedge' } : {}) });
  try {
    const root = process.env.BASE_URL || 'http://127.0.0.1:8769';
    const api = await fetch(`${root}/api/cot`).then(r => { assert.equal(r.status, 200); return r.json(); });
    const latest = api.markets.nq.history.legacy.at(-1);
    for (const width of [390, 768, 1440]) for (const report of ['legacy', 'tff']) {
      const context = await browser.newContext({ viewport: { width, height: 1000 } });
      const page = await context.newPage(); const errors = [];
      page.on('pageerror', e => errors.push(e.message));
      await page.goto(`${root}/?market=nq&horizon=1w&view=today&model=cot&report=${report}`);
      await page.locator('#positionChanges .decision-cot-change-row').first().waitFor();
      await page.waitForFunction(() => !!window.__COT_CURRENT_EDGE_MODEL__?.state?.current);
      await page.waitForFunction(date => document.querySelector('#weeklyOverview')?.textContent.includes(date) && document.querySelector('#cotScorePanel')?.textContent.includes(date), latest.date);
      const rows = await page.locator('#positionChanges .decision-cot-change-row').allTextContents();
      assert.equal(rows.length, report === 'legacy' ? 4 : 5);
      const changes = await page.locator('#positionChanges').innerText();
      assert(changes.includes(latest.date)); assert(changes.includes(latest.release_date));
      if (report === 'legacy') {
        assert(!changes.includes('Leveraged Funds')); assert(!changes.includes('Asset Manager'));
        const noncommercial = await page.getByRole('row', { name: 'Noncommercial latest COT position changes', exact: true }).innerText();
        assert(noncommercial.replace(/\s/g, '').includes('+8715'), noncommercial);
        assert(noncommercial.replace(/\s/g, '').includes('+5381'), noncommercial);
        const weekly = await page.locator('#weeklyOverview').innerText();
        assert(weekly.includes('2026-09-29')); assert(weekly.includes('+13,704')); assert(weekly.includes('n/a'));
        const score = await page.locator('#cotScorePanel').innerText();
        assert(score.includes(latest.date)); assert(score.includes('79')); assert(!score.includes('report 2026-09-01'));
        assert(!(await page.locator('#modelEstimates').innerText()).includes('+2,34%'));
        if (width === 1440 && process.env.SCREENSHOT_DIR) {
          fs.mkdirSync(process.env.SCREENSHOT_DIR, { recursive: true });
          await page.screenshot({ path: path.join(process.env.SCREENSHOT_DIR, 'cot-nq-legacy-fixed.png') });
        }
      }
      await page.getByRole('button', { name: 'Research', exact: true }).click();
      await page.locator('#cotIntelligence').waitFor({ state: 'visible' });
      await page.getByRole('button', { name: 'Market', exact: true }).click();
      assert(new URL(page.url()).searchParams.get('report') === report);
      assert.equal(errors.length, 0, errors.join('\n'));
      await context.close();
      console.log(`PASS NQ ${report} ${width}px: current report, actors, weekly figures, navigation`);
    }
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
