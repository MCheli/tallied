#!/usr/bin/env node
// Production-bundle smoke test: serve frontend/dist exactly as production does and
// fail if the app throws while loading. The dev server and the tour run unbundled
// modules, so chunk-ordering bugs (circular chunks, "x is not a function" at load)
// only show up here. Run: make build-smoke   (builds first) or node scripts/build_smoke.mjs
import { spawn } from 'node:child_process'
import { existsSync } from 'node:fs'
import net from 'node:net'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { chromium } from '../frontend/node_modules/playwright/index.mjs'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', 'frontend')
const dist = path.join(root, 'dist')
if (!existsSync(path.join(dist, 'index.html'))) {
  console.error(`build-smoke: ${dist}/index.html missing; run "npm run build" in frontend first`)
  process.exit(2)
}
// A free port each run, so two checkouts (e.g. an agent worktree) can run the gate at once
// without one silently testing the other's bundle.
const PORT = await new Promise((resolve, reject) => {
  const srv = net.createServer()
  srv.unref()
  srv.on('error', reject)
  srv.listen(0, '127.0.0.1', () => { const { port } = srv.address(); srv.close(() => resolve(port)) })
})
const ROUTES = ['/', '/login']

// Hard stop: a hung browser or server must fail the gate, never hang CI.
const watchdog = setTimeout(() => { console.error('build-smoke: timed out after 120s'); stopPreview(); process.exit(1) }, 120000)
watchdog.unref()

// Run vite directly (no npx wrapper) in its own process group so the whole tree can be killed.
const viteBin = path.join(root, 'node_modules', 'vite', 'bin', 'vite.js')
const preview = spawn(process.execPath, [viteBin, 'preview', '--outDir', dist, '--port', String(PORT), '--strictPort'], { cwd: root, stdio: ['ignore', 'pipe', 'pipe'], detached: process.platform !== 'win32' })
let previewLog = ''
preview.stdout.on('data', d => { previewLog += d })
preview.stderr.on('data', d => { previewLog += d })
function stopPreview() {
  try { if (process.platform !== 'win32') process.kill(-preview.pid, 'SIGTERM'); else preview.kill() } catch {}
}
const deadline = Date.now() + 20000
let up = false
while (Date.now() < deadline) {
  try { const r = await fetch(`http://localhost:${PORT}/`); if (r.ok) { up = true; break } } catch {}
  await new Promise(r => setTimeout(r, 250))
}
if (!up) { console.error('build-smoke: preview server did not start on port ' + PORT + '\n' + previewLog.slice(-2000)); stopPreview(); process.exit(1) }

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
  stopPreview()
}
if (failures.length) {
  console.error('build-smoke FAILED (production bundle throws on load):')
  for (const f of failures) console.error('  ' + f)
  if (previewLog.trim()) console.error('preview server output:\n' + previewLog.slice(-2000))
  process.exit(1)
}
console.log('build-smoke: production bundle loads cleanly')
process.exit(0)
