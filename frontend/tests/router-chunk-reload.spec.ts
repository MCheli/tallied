import { describe, expect, it } from 'vitest'
import { isChunkLoadError } from '../src/router'

// NAV-STALE-001: after a deploy, an open tab's old page chunks are gone; the tap must reload, not do nothing.
describe('isChunkLoadError', () => {
  it('recognises the stale-chunk errors of Chrome, Safari and Firefox', () => {
    expect(isChunkLoadError(new TypeError('Failed to fetch dynamically imported module: https://x/assets/RetirementView-abc.js'))).toBe(true)
    expect(isChunkLoadError(new TypeError('Importing a module script failed.'))).toBe(true)
    expect(isChunkLoadError(new TypeError('error loading dynamically imported module'))).toBe(true)
  })

  it('leaves other navigation errors alone', () => {
    expect(isChunkLoadError(new Error('Navigation cancelled'))).toBe(false)
  })
})
