import { test, expect } from '@playwright/test';

async function open(page) {
  await page.goto('/worldclass_dashboard.html');
  await page.waitForFunction(() => document.documentElement.classList.contains('cot-worldclass-ux-ready'));
  await expect(page.locator('#cotIntelligence')).toBeVisible();
  await expect(page.locator('.cot-ux-market-switcher')).toBeVisible();
}

test('market selection and decision surfaces stay above deep statistical evidence', async ({ page }) => {
  await page.setViewportSize({ width: 1600, height: 1000 });
  await open(page);
  await page.waitForFunction(() => Boolean(document.querySelector('#currentEdgeCommand')) && Boolean(document.querySelector('#wcCommandCenter')));
  await page.waitForTimeout(100);

  const order = await page.evaluate(() => {
    const top = selector => document.querySelector(selector)?.getBoundingClientRect().top ?? null;
    return {
      instrument: top('.instrument-bar'),
      current: top('#currentEdgeCommand'),
      command: top('#wcCommandCenter'),
      evidence: top('#cotIntelligence')
    };
  });

  expect(order.instrument).not.toBeNull();
  expect(order.current).not.toBeNull();
  expect(order.command).not.toBeNull();
  expect(order.evidence).not.toBeNull();
  expect(order.instrument).toBeLessThan(order.evidence);
  expect(order.current).toBeLessThan(order.evidence);
  expect(order.command).toBeLessThan(order.evidence);
});

test('evidence panel exposes a synchronized market selector at the top', async ({ page }) => {
  await open(page);
  const panel = page.locator('#cotIntelligence');
  const switcher = panel.locator('.cot-ux-market-switcher');
  await expect(switcher.locator('[data-cot-ux-market]')).toHaveCount(7);

  await switcher.locator('[data-cot-ux-market="nq"]').click();
  await expect(page.locator('#instrumentTabs [data-market="nq"]')).toHaveClass(/active/);
  await expect(switcher.locator('[data-cot-ux-market="nq"]')).toHaveAttribute('aria-pressed', 'true');
  await expect(panel.locator('#cotIntelMarket')).toContainText('Nasdaq-100');
});

test('active edge view prioritizes directional actors and uses a compact evidence summary', async ({ page }) => {
  await open(page);
  const panel = page.locator('#cotIntelligence');
  await panel.getByRole('button', { name: 'EDGES' }).click();
  await expect(panel.locator('.cot-edge-overview article')).toHaveCount(3);

  const priorities = await panel.locator('.cot-edge-grid-active .cot-edge-card.threshold').evaluateAll(cards => cards.map(card => {
    if (card.querySelector('.cot-role.primary_directional')) return 0;
    if (card.querySelector('.cot-role.secondary_directional')) return 1;
    return 2;
  }));
  expect(priorities).toEqual([...priorities].sort((a, b) => a - b));
});
