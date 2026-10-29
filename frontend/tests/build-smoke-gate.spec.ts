import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

// NFR-PROC-003: the minified production bundle is loaded in a real browser before
// every commit and before the Docker image is built. The dev server and the tour
// run unbundled modules, so a circular chunk (2026-10-29: "d is not a function",
// blank production) is invisible to them.
const root = resolve(__dirname, '..', '..')
const read = (p: string) => readFileSync(resolve(root, p), 'utf8')

describe('production bundle smoke gate', () => {
  it('pre-commit runs build-smoke', () => {
    const makefile = read('Makefile')
    expect(makefile).toMatch(/^pre-commit:.*\bbuild-smoke\b/m)
    expect(makefile).toMatch(/^build-smoke:/m)
    expect(makefile).toContain('node scripts/build_smoke.mjs')
  })

  it('CI runs the smoke test before the image is built', () => {
    const ci = read('.github/workflows/ci.yml')
    const smoke = ci.indexOf('scripts/build_smoke.mjs')
    const docker = ci.indexOf('docker/build-push-action')
    expect(smoke).toBeGreaterThan(-1)
    expect(docker).toBeGreaterThan(smoke)
  })

  it('the smoke script loads the root and login routes and fails on uncaught errors', () => {
    const script = read('scripts/build_smoke.mjs')
    expect(script).toContain("'/', '/login'")
    expect(script).toContain("page.on('pageerror'")
    expect(script).toContain('process.exit(1)')
  })
})
