import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

/**
 * The screenshot tour (scripts/screenshot_tour.mjs) is ledger evidence. These checks make its
 * log a gate: every route it knows is captured at both widths with no horizontal overflow,
 * console errors or failed requests, and its route list matches the router.
 */
const repo = resolve(__dirname, '..', '..')
const log = JSON.parse(readFileSync(resolve(repo, 'artifacts/screens/tour-log.json'), 'utf8')) as {
  routes: Record<string, { overflow?: string[]; consoleErrors?: string[]; badResponses?: string[]; error?: string }>
}
const tourSource = readFileSync(resolve(repo, 'scripts/screenshot_tour.mjs'), 'utf8')
const routerSource = readFileSync(resolve(repo, 'frontend/src/router/index.ts'), 'utf8')

function tourRoutes(): Record<string, string> {
  const block = tourSource.slice(tourSource.indexOf('const ROUTES = {'), tourSource.indexOf('};', tourSource.indexOf('const ROUTES = {')))
  const out: Record<string, string> = {}
  for (const m of block.matchAll(/(\w+): '([^']*)'/g)) out[m[1]] = m[2]
  return out
}

describe('screenshot tour log (artifacts/screens/tour-log.json)', () => {
  const routes = tourRoutes()

  it('covers every non-admin, non-callback router path', () => {
    const routerPaths = [...routerSource.matchAll(/path: '([^']*)'/g)].map(m => m[1])
      .filter(p => !p.startsWith('/admin-portal') && p !== '/pending-approval')
    const tourPaths = new Set(Object.values(routes))
    for (const p of routerPaths) expect(tourPaths.has(p), `tour is missing route ${p}`).toBe(true)
  })

  it('has a clean capture of every tour route at phone and desktop width', () => {
    for (const name of Object.keys(routes)) {
      for (const vp of ['mobile', 'desktop']) {
        const entry = log.routes[`${name}/${vp}`]
        expect(entry, `${name}/${vp} was not captured`).toBeTruthy()
        expect(entry.error ?? null, `${name}/${vp} failed`).toBeNull()
        expect(entry.overflow ?? [], `${name}/${vp} overflows horizontally`).toEqual([])
        expect(entry.consoleErrors ?? [], `${name}/${vp} logged console errors`).toEqual([])
        expect(entry.badResponses ?? [], `${name}/${vp} had failed requests`).toEqual([])
      }
    }
  })
})
