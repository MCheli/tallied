#!/usr/bin/env node
/**
 * Screenshot tour: logs in as the Claudius Banks persona and captures every
 * route at phone (390px) and desktop (1440px) width into artifacts/screens/<route>/.
 *
 * Usage (backend on :8000 and frontend on :5173, database seeded with `make seed-test`):
 *   node scripts/screenshot_tour.mjs                # all routes, both widths
 *   node scripts/screenshot_tour.mjs spending cash  # only these routes
 *   TOUR_BASE=http://localhost:5173 TOUR_THEME=dark node scripts/screenshot_tour.mjs
 *
 * Output:
 *   artifacts/screens/<route>/mobile.png, desktop.png     (ledger evidence)
 *   artifacts/screens/tour-log.json                       (console errors, failed and 4xx/5xx
 *                                                          requests, horizontal overflow per route)
 * Exit code is 1 if login fails or any route fails to load, so CI notices. Console errors and
 * overflow are reported in the log, not fatal, so the tour stays usable while they are fixed.
 *
 * Uses the installed Google Chrome (channel "chrome") when the bundled Chromium is missing;
 * run `npx playwright install chromium` in frontend/ to use the bundled one instead.
 */
import { createRequire } from 'node:module';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(here, '..');
const require = createRequire(path.join(repoRoot, 'frontend', 'package.json'));
const { chromium, devices } = require('playwright');

const BASE = process.env.TOUR_BASE || 'http://localhost:5173';
const THEME = process.env.TOUR_THEME === 'dark' ? 'dark' : 'light';
const OUT = path.join(repoRoot, 'artifacts', 'screens');
const EMAIL = process.env.TOUR_EMAIL || 'claudius@tallied.dev';
const PASSWORD = process.env.TOUR_PASSWORD || 'demo123';

/** Route name -> path. The name is the folder under artifacts/screens/. */
const ROUTES = {
  login: '/login',
  dashboard: '/',
  guide: '/guide',
  spending: '/spending',
  income: '/income',
  cash: '/cash',
  rsu: '/rsu',
  retirement: '/retirement',
  property: '/property',
  assets: '/assets',
  planning: '/planning',
  database: '/database',
  developer: '/developer',
  settings: '/settings',
};

const VIEWPORTS = {
  mobile: {
    viewport: { width: 390, height: 844 },
    deviceScaleFactor: 1,
    isMobile: true,
    hasTouch: true,
    userAgent: devices['iPhone 13'].userAgent,
  },
  desktop: { viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 },
};

// The app shell is a fixed-height flex column with a scrolling <main>; relax it so
// a full-page screenshot captures the whole page instead of one viewport.
const FULLPAGE_CSS = `
  .h-screen { height: auto !important; min-height: 100vh !important; }
  main.overflow-y-auto { overflow: visible !important; }
`;

const selected = process.argv.slice(2);
const routes = Object.entries(ROUTES).filter(([name]) => selected.length === 0 || selected.includes(name));
if (routes.length === 0) {
  console.error(`no such route(s): ${selected.join(', ')}. Known: ${Object.keys(ROUTES).join(', ')}`);
  process.exit(2);
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const log = {};
let failures = 0;

function track(page, key) {
  log[key] = { consoleErrors: [], failedRequests: [], badResponses: [], overflow: [] };
  page.on('console', (m) => { if (m.type() === 'error') log[key].consoleErrors.push(m.text().slice(0, 300)); });
  page.on('pageerror', (e) => log[key].consoleErrors.push('pageerror: ' + String(e).slice(0, 300)));
  page.on('requestfailed', (r) => log[key].failedRequests.push(`${r.method()} ${r.url()} :: ${r.failure()?.errorText}`));
  page.on('response', (r) => { if (r.status() >= 400) log[key].badResponses.push(`${r.status()} ${r.request().method()} ${r.url()}`); });
}

async function settle(page) {
  try { await page.waitForLoadState('networkidle', { timeout: 15000 }); } catch { /* charts keep polling; move on */ }
  await sleep(1200);
}

async function capture(page, file) {
  await page.addStyleTag({ content: FULLPAGE_CSS }).catch(() => {});
  await sleep(400);
  fs.mkdirSync(path.dirname(file), { recursive: true });
  await page.screenshot({ path: file, fullPage: true });
}

async function launch() {
  try { return await chromium.launch(); } catch { return chromium.launch({ channel: 'chrome' }); }
}

const browser = await launch();
for (const [vpName, vp] of Object.entries(VIEWPORTS)) {
  const ctx = await browser.newContext({ ...vp, colorScheme: THEME });
  const page = await ctx.newPage();
  const loginKey = `login/${vpName}`;
  track(page, loginKey);

  await page.goto(`${BASE}/login`, { waitUntil: 'domcontentloaded' });
  await settle(page);
  if (routes.some(([name]) => name === 'login')) await capture(page, path.join(OUT, 'login', `${vpName}.png`));

  await page.fill('input[type="email"]', EMAIL);
  await page.fill('input[type="password"]', PASSWORD);
  await page.click('button[type="submit"]');
  try {
    await page.waitForURL((u) => !u.pathname.startsWith('/login'), { timeout: 15000 });
  } catch {
    log[loginKey].error = `login did not navigate away from /login (still at ${page.url()})`;
    console.error(`[${vpName}] ${log[loginKey].error}`);
    failures++;
    await page.close();
    await ctx.close();
    continue;
  }
  await page.close();

  for (const [name, route] of routes) {
    if (name === 'login') continue;
    const key = `${name}/${vpName}`;
    const pg = await ctx.newPage();
    track(pg, key);
    try {
      await pg.goto(`${BASE}${route}`, { waitUntil: 'domcontentloaded', timeout: 20000 });
      await settle(pg);
      log[key].finalUrl = pg.url();
      if (new URL(pg.url()).pathname !== route) {
        log[key].error = `redirected to ${pg.url()}`;
        failures++;
      }
      log[key].overflow = await pg.evaluate(() => {
        const vw = document.documentElement.clientWidth;
        const out = [];
        for (const el of document.querySelectorAll('main *')) {
          const r = el.getBoundingClientRect();
          if (r.right > vw + 2 && r.width > 0) {
            out.push(`${el.tagName.toLowerCase()}.${String(el.className).split(' ').slice(0, 3).join('.')} right=${Math.round(r.right)}`);
            if (out.length >= 5) break;
          }
        }
        return out;
      });
      await capture(pg, path.join(OUT, name, `${vpName}.png`));
      console.log(`${key}: ok${log[key].overflow.length ? ` (overflow: ${log[key].overflow.length})` : ''}${log[key].consoleErrors.length ? ` (console errors: ${log[key].consoleErrors.length})` : ''}`);
    } catch (e) {
      log[key].error = String(e).slice(0, 300);
      failures++;
      console.error(`${key}: FAILED ${log[key].error}`);
    } finally {
      await pg.close();
    }
  }
  await ctx.close();
}
await browser.close();

fs.mkdirSync(OUT, { recursive: true });
fs.writeFileSync(path.join(OUT, 'tour-log.json'), JSON.stringify({ capturedAt: new Date().toISOString(), base: BASE, theme: THEME, routes: log }, null, 2));
console.log(`tour: ${Object.keys(log).length} captures, ${failures} failure(s); log at artifacts/screens/tour-log.json`);
process.exit(failures ? 1 : 0);
