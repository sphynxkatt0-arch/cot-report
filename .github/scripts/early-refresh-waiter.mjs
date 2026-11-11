// Starts "Refresh and Deploy" at 21:35 and 22:35 Stockholm time on weekdays.
//
// GitHub's cron starts runs 2-6+ hours late, so the "COT Early Refresh Waiter"
// workflow is scheduled hours ahead. This script then sleeps until each slot and
// dispatches the refresh. A job may only run 6 hours, so when a slot is further
// away than MAX_RUN_MINUTES the run waits as long as it may and then relays: it
// dispatches a fresh copy of the waiter workflow and exits. workflow_dispatch
// runs start within seconds, unlike cron, so the chain keeps its timing however
// late the cron run that started it was. A slot is skipped when a refresh was already dispatched
// for it (another waiter run, or the Windows backup task), or when it is more
// than GRACE_MINUTES in the past.
//
// Env: GITHUB_TOKEN, GITHUB_REPOSITORY (set by Actions).
// Testing: DRY_RUN=1 prints the plan without sleeping or dispatching;
//          NOW=2026-11-09T18:00:00Z pretends the run started at that time;
//          SLOTS=17:50 overrides the Stockholm slot times.

const TZ = 'Europe/Stockholm';
const SLOTS = (process.env.SLOTS || '21:35,22:35').split(',');
const GRACE_MINUTES = 90;
const DEDUP_MINUTES = 5;
const MAX_RUN_MINUTES = 330; // job timeout is 350 min
const MAX_LEAD_HOURS = 12;   // do not start a chain further ahead of the next slot
const SELF_WORKFLOW = 'cot-early-refresh-waiter.yml';
const WORKFLOW = 'refresh-and-deploy.yml';

const repo = process.env.GITHUB_REPOSITORY || 'sphynxkatt0-arch/cot-report';
const token = process.env.GITHUB_TOKEN;
const dryRun = process.env.DRY_RUN === '1';
let clockOffset = process.env.NOW ? Date.parse(process.env.NOW) - Date.now() : 0;
const now = () => Date.now() + clockOffset;

const iso = (ms) => new Date(ms).toISOString().replace(/\.\d{3}Z$/, 'Z');
const log = (msg) => console.log(`${iso(now())}  ${msg}`);

// Wall-clock parts of an instant in TZ.
function zoned(ms) {
  const parts = new Intl.DateTimeFormat('en-GB', {
    timeZone: TZ, hourCycle: 'h23', weekday: 'short',
    year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit',
  }).formatToParts(new Date(ms));
  const p = Object.fromEntries(parts.map((x) => [x.type, x.value]));
  return { y: +p.year, m: +p.month, d: +p.day, h: +p.hour, min: +p.minute, s: +p.second, weekday: p.weekday };
}

// UTC instant for a wall-clock time in TZ (handles DST by re-checking the offset).
function zonedToUtc(y, m, d, h, min) {
  const target = Date.UTC(y, m - 1, d, h, min);
  let guess = target;
  for (let i = 0; i < 3; i++) {
    const z = zoned(guess);
    const asUtc = Date.UTC(z.y, z.m - 1, z.d, z.h, z.min, z.s);
    guess += target - asUtc;
  }
  return guess;
}

async function api(path, init = {}) {
  const headers = { Accept: 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28', 'User-Agent': 'cot-early-refresh-waiter' };
  if (token) headers.Authorization = `Bearer ${token}`;
  for (let attempt = 1; ; attempt++) {
    const res = await fetch(`https://api.github.com/repos/${repo}${path}`, { ...init, headers: { ...headers, ...init.headers } });
    if (res.ok) return res.status === 204 ? null : res.json();
    if (attempt >= 5 || (res.status < 500 && res.status !== 429)) {
      throw new Error(`${init.method || 'GET'} ${path} -> ${res.status} ${await res.text()}`);
    }
    log(`API ${res.status}, retrying in 30s (attempt ${attempt})`);
    await new Promise((r) => setTimeout(r, 30_000));
  }
}

// A dispatch counts for a slot if it was created between just before the slot
// and just before the next slot.
async function alreadyDispatched(slotMs, nextSlotMs) {
  const since = slotMs - DEDUP_MINUTES * 60_000;
  const until = (nextSlotMs ?? slotMs + GRACE_MINUTES * 60_000) - DEDUP_MINUTES * 60_000;
  const range = `${iso(since)}..${iso(until)}`;
  const data = await api(`/actions/workflows/${WORKFLOW}/runs?event=workflow_dispatch&created=${encodeURIComponent(range)}&per_page=20`);
  return (data.workflow_runs || []).find((r) => {
    const t = Date.parse(r.created_at);
    return t >= since && t < until;
  });
}

async function sleepUntil(ms) {
  const wait = ms - now();
  if (wait <= 0) return;
  log(`Waiting ${Math.round(wait / 60_000)} min until ${iso(ms)}`);
  if (dryRun) { clockOffset += wait; return; }
  while (now() < ms) await new Promise((r) => setTimeout(r, Math.min(ms - now(), 60_000)));
}

const today = zoned(now());
log(`Started; Stockholm time is ${String(today.h).padStart(2, '0')}:${String(today.min).padStart(2, '0')} on ${today.weekday} ${today.y}-${String(today.m).padStart(2, '0')}-${String(today.d).padStart(2, '0')}`);
if (today.weekday === 'Sat' || today.weekday === 'Sun') {
  log('Weekend in Stockholm; nothing to do');
  process.exit(0);
}

const slotTimes = SLOTS.map((slot) => {
  const [h, min] = slot.split(':').map(Number);
  return zonedToUtc(today.y, today.m, today.d, h, min);
});

let runStart = now();
const nextOpen = slotTimes.find((ms) => ms >= now());
if (nextOpen !== undefined && nextOpen - now() > MAX_LEAD_HOURS * 3_600_000) {
  log(`Next slot ${iso(nextOpen)} is more than ${MAX_LEAD_HOURS} h away; leaving it to a later scheduled run`);
  process.exit(0);
}

for (const [i, slot] of SLOTS.entries()) {
  const slotMs = slotTimes[i];
  const nextSlotMs = slotTimes[i + 1];
  const label = `${slot} Stockholm (${iso(slotMs)})`;
  // Too late for this slot: past the grace period, or the next slot is due anyway.
  const deadline = Math.min(slotMs + GRACE_MINUTES * 60_000, nextSlotMs ?? Infinity);
  if (now() > deadline) {
    log(`Slot ${label}: too late (deadline ${iso(deadline)}), skipping`);
    continue;
  }
  const runLimit = runStart + MAX_RUN_MINUTES * 60_000;
  if (slotMs > runLimit) {
    await sleepUntil(runLimit);
    if (dryRun) {
      log(`Slot ${label}: DRY RUN, would relay to a new ${SELF_WORKFLOW} run`);
      runStart = now(); // simulate the relayed run
    } else {
      await api(`/actions/workflows/${SELF_WORKFLOW}/dispatches`, { method: 'POST', body: JSON.stringify({ ref: 'main', inputs: { dry_run: 'false' } }) });
      log(`Slot ${label}: still ${Math.round((slotMs - now()) / 60_000)} min away; relayed to a new ${SELF_WORKFLOW} run`);
      process.exit(0);
    }
  }
  await sleepUntil(slotMs);
  const existing = await alreadyDispatched(slotMs, nextSlotMs);
  if (existing) {
    log(`Slot ${label}: refresh already dispatched at ${existing.created_at} (${existing.html_url}), skipping`);
    continue;
  }
  if (dryRun) {
    log(`Slot ${label}: DRY RUN, would dispatch ${WORKFLOW} on main`);
    continue;
  }
  await api(`/actions/workflows/${WORKFLOW}/dispatches`, { method: 'POST', body: JSON.stringify({ ref: 'main' }) });
  log(`Slot ${label}: dispatched ${WORKFLOW} on main`);
}
log('Done');
