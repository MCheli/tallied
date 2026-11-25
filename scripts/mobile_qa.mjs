#!/usr/bin/env node
/**
 * iPhone QA: signs in as Claudius Banks in WebKit with the iPhone 15 Pro and iPhone SE device
 * profiles (touch, mobile) and checks what makes the Home Screen app feel like a web page.
 *
 * Usage (a running app, dev server or production build, database seeded):
 *   node scripts/mobile_qa.mjs [base url] [label] [playwright package dir]   # default http://localhost:5173 after
 *   QA_DEMO=1 node scripts/mobile_qa.mjs https://money-demo.markcheli.com live
 *
 * Needs `npx playwright install webkit` in frontend/. Writes .mobile-qa/<label>/<device>/<route>.png
 * and .mobile-qa/<label>/report.json (git-ignored). Exit code 1 if any check fails.
 *
 * Checks per route: every field renders at >= 16px (iOS zooms smaller ones on focus), the
 * viewport meta and manifest are there, the page does not scroll sideways, no keyboard-shortcut
 * hint is visible, and (reported, not fatal) buttons and links smaller than 44px.
 */
import { createRequire } from 'node:module';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(here, '..');
const require = createRequire(path.join(repoRoot, 'frontend', 'package.json'));
// Optional third argument after the url and label: a playwright or playwright-core package directory whose WebKit build is installed.
const { webkit, devices } = require(process.argv[4] || 'playwright');

const BASE = process.argv[2] || 'http://localhost:5173';
const LABEL = process.argv[3] || 'after';
const DEMO = process.env.QA_DEMO === '1';
const OUT = path.join(repoRoot, '.mobile-qa', LABEL);
const DEVICES = { 'iphone-15-pro': devices['iPhone 15 Pro'], 'iphone-se': devices['iPhone SE'] };
const ROUTES = {
  dashboard: '/', recap: '/recap', spending: '/spending', income: '/income', cash: '/cash',
  rsu: '/rsu', retirement: '/retirement', property: '/property', assets: '/assets',
  planning: '/planning', database: '/database', developer: '/developer', settings: '/settings',
};

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
async function settle(page) {
  try { await page.waitForLoadState('networkidle', { timeout: 15000 }); } catch { /* charts keep polling; move on */ }
  await sleep(1000);
}

function inspect() {
  const visible = (el) => {
    const r = el.getBoundingClientRect();
    const cs = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && cs.visibility !== 'hidden' && cs.display !== 'none';
  };
  const describe = (el) => `${el.tagName.toLowerCase()}${el.getAttribute('type') ? `[${el.getAttribute('type')}]` : ''}${el.getAttribute('aria-label') ? ` "${el.getAttribute('aria-label')}"` : el.getAttribute('placeholder') ? ` "${el.getAttribute('placeholder')}"` : ''}`;
  const skip = new Set(['hidden', 'range', 'checkbox', 'radio', 'file', 'button', 'submit', 'color']);
  const smallFields = [];
  for (const el of document.querySelectorAll('input, textarea, select, [contenteditable="true"]')) {
    if (el.tagName === 'INPUT' && skip.has(el.type)) continue;
    const fs = parseFloat(getComputedStyle(el).fontSize);
    if (fs < 16) smallFields.push(`${describe(el)} ${fs}px`);
  }
  const hints = [...document.querySelectorAll('kbd, [data-shortcut-hint]')].filter(visible).map((el) => el.textContent.trim());
  const smallTargets = [];
  for (const el of document.querySelectorAll('button, a[href], [role="button"], input[type="checkbox"], input[type="radio"], select')) {
    if (!visible(el)) continue;
    const r = el.getBoundingClientRect();
    if (r.width < 44 || r.height < 44) smallTargets.push(`${describe(el)} ${Math.round(r.width)}x${Math.round(r.height)}`);
  }
  const main = document.querySelector('main');
  return {
    viewport: document.querySelector('meta[name="viewport"]')?.content ?? null,
    manifest: !!document.querySelector('link[rel="manifest"]'),
    appleCapable: document.querySelector('meta[name="apple-mobile-web-app-capable"]')?.content ?? null,
    statusBar: document.querySelector('meta[name="apple-mobile-web-app-status-bar-style"]')?.content ?? null,
    docScrollWidth: document.documentElement.scrollWidth,
    innerWidth: window.innerWidth,
    mainScrollWidth: main ? main.scrollWidth : null,
    mainClientWidth: main ? main.clientWidth : null,
    fieldCount: document.querySelectorAll('input, textarea, select').length,
    smallFields, hints, smallTargetCount: smallTargets.length, smallTargets: smallTargets.slice(0, 15),
  };
}

const report = { base: BASE, label: LABEL, capturedAt: new Date().toISOString(), devices: {} };
let failures = 0;
const browser = await webkit.launch();
for (const [devName, profile] of Object.entries(DEVICES)) {
  const ctx = await browser.newContext({ ...profile });
  const page = await ctx.newPage();
  const res = { login: null, routes: {} };
  report.devices[devName] = res;
  fs.mkdirSync(path.join(OUT, devName), { recursive: true });

  await page.goto(`${BASE}/login`, { waitUntil: 'domcontentloaded' });
  await settle(page);
  res.login = await page.evaluate(inspect);
  await page.screenshot({ path: path.join(OUT, devName, 'login.png') });
  if (DEMO) await page.click('[data-testid="enter-demo"]');
  else {
    await page.fill('input[type="email"]', process.env.QA_EMAIL || 'claudius@tallied.dev');
    await page.fill('input[type="password"]', process.env.QA_PASSWORD || 'demo123');
    await page.click('button[type="submit"]');
  }
  try {
    await page.waitForURL((u) => !u.pathname.startsWith('/login'), { timeout: 15000 });
  } catch {
    res.loginError = `still at ${page.url()}`;
    await page.screenshot({ path: path.join(OUT, devName, 'login-failed.png'), fullPage: true });
    failures++;
    await ctx.close();
    continue;
  }

  for (const [name, route] of Object.entries(ROUTES)) {
    try {
      await page.goto(`${BASE}${route}`, { waitUntil: 'domcontentloaded', timeout: 20000 });
      await settle(page);
      const r = await page.evaluate(inspect);
      const problems = [];
      if (r.smallFields.length) problems.push(`fields under 16px: ${r.smallFields.join(', ')}`);
      if (r.docScrollWidth > r.innerWidth) problems.push(`page scrolls sideways (${r.docScrollWidth} > ${r.innerWidth})`);
      if (r.mainScrollWidth !== null && r.mainScrollWidth > r.mainClientWidth + 1) problems.push(`main wider than screen (${r.mainScrollWidth} > ${r.mainClientWidth})`);
      if (r.hints.length) problems.push(`shortcut hints visible: ${r.hints.join(', ')}`);
      if (!r.viewport?.includes('viewport-fit=cover') || !r.viewport?.includes('maximum-scale=1')) problems.push(`viewport meta: ${r.viewport}`);
      if (!r.manifest) problems.push('no manifest link');
      r.problems = problems;
      failures += problems.length ? 1 : 0;
      res.routes[name] = r;
      await page.screenshot({ path: path.join(OUT, devName, `${name}.png`) });
      console.log(`${devName} ${name}: ${problems.length ? 'FAIL ' + problems.join(' | ') : 'ok'} (small targets: ${r.smallTargetCount})`);
    } catch (e) {
      res.routes[name] = { error: String(e).slice(0, 300) };
      failures++;
      console.error(`${devName} ${name}: ERROR ${String(e).slice(0, 200)}`);
    }
  }
  await ctx.close();
}
await browser.close();
fs.writeFileSync(path.join(OUT, 'report.json'), JSON.stringify(report, null, 2));
console.log(`mobile qa: ${failures} route(s) with problems; report at .mobile-qa/${LABEL}/report.json`);
process.exit(failures ? 1 : 0);
