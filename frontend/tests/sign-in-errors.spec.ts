import { describe, expect, it } from 'vitest'
import { signInErrorMessage } from '../src/config/signInErrors'

/** /login?error=<code> is where a failed Google callback lands; the page explains it and offers a retry. */

describe('signInErrorMessage', () => {
  it('explains each code the Google callback sends', () => {
    expect(signInErrorMessage('google')).toMatch(/didn't finish/)
    expect(signInErrorMessage('unverified')).toMatch(/verified/)
    expect(signInErrorMessage('disabled')).toMatch(/disabled/)
  })

  it('ignores anything else, including repeated query params and prototype keys', () => {
    expect(signInErrorMessage(undefined)).toBeNull()
    expect(signInErrorMessage(['google', 'google'])).toBeNull()
    expect(signInErrorMessage('constructor')).toBeNull()
    expect(signInErrorMessage('<script>')).toBeNull()
  })
})
