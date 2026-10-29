#!/usr/bin/env node
// Production-bundle smoke test: serve frontend/dist exactly as production does and
// fail if the app throws while loading. The dev server and the tour run unbundled
// modules, so chunk-ordering bugs (circular chunks, "x is not a function" at load)
// only show up here. Run: make build-smoke   (builds first) or node scripts/build_smoke.mjs
import { spawn } from 'node:child_process'
import { existsSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { chromium } from '../frontend/node_modules/playwright/index.mjs'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', 'frontend')
const dist = path.join(root, 'dist')
if (!existsSync(path.join(dist, 'index.html'))) {
  console.error(`build-smoke: ${dist}/index.html missing; run "npm run build" in frontend first`)
  process.exit(2)
}
const PORT = 4199
const ROUTES = ['/', '/login']

const preview = spawn('npx', ['vite', 'preview', '--outDir', dist, '--port', String(PORT), '--strictPort'], { cwd: root, stdio: ['ignore', 'pipe', 'pipe'] })
let previewLog = ''
preview.stdout.on('data', d => { previewLog += d })
preview.stderr.on('data', d => { previewLog += d })
const deadline = Date.now() + 20000
while (Date.now() < deadline) {
  try { const r = await fetch(`http://localhost:${PORT}/`); if (r.ok) break } catch {}
  await new Promise(r => setTimeout(r, 250))
}

const launch = async () => {
  try { return await chromium.launch({ channel: 'chrome', headless: true }) } catch (e) { return chromium.launch({ headless: true }) }
}
const browser = await launch()
const failures = []
try {
  for (const route of ROUTES) {
    const page = await browser.newPage()
    const errors = []
    page.on('pageerror', e => errors.push(`uncaught: ${e.message}`))
    page.on('console', m => { if (m.type() === 'error' && !/Failed to load resource|net::ERR|fetch/i.test(m.text())) errors.push(`console.error: ${m.text().slice(0, 200)}`) })
    await page.goto(`http://localhost:${PORT}${route}`, { waitUntil: 'load', timeout: 20000 }).catch(e => errors.push(`navigation: ${e.message}`))
    await page.waitForTimeout(1500)
    const rendered = await page.evaluate(() => (document.querySelector('#app')?.innerHTML || '').trim().length > 0)
    if (!rendered) errors.push('#app rendered nothing')
    if (errors.length) failures.push(`${route}: ${errors.join(' | ')}`)
    else console.log(`build-smoke: ${route} ok`)
    await page.close()
  }
} finally {
  await browser.close()
  preview.kill()
}
if (failures.length) {
  console.error('build-smoke FAILED (production bundle throws on load):')
  for (const f of failures) console.error('  ' + f)
  process.exit(1)
}
console.log('build-smoke: production bundle loads cleanly')
