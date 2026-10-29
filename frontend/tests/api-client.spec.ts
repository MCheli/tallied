import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { buildQuery, fetchJson } from '../src/api/client'

/** The typed client is the only place views talk to the backend; its two contracts are the query string and the 401 retry. */

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}

describe('buildQuery', () => {
  it('returns an empty string for no params or only empty values', () => {
    expect(buildQuery()).toBe('')
    expect(buildQuery({})).toBe('')
    expect(buildQuery({ a: null, b: undefined, c: '' })).toBe('')
  })

  it('encodes the non-empty values and keeps zero and false', () => {
    expect(buildQuery({ months: 12, group: 'cash & more', zero: 0, flag: false })).toBe(
      '?months=12&group=cash+%26+more&zero=0&flag=false',
    )
  })
})

describe('fetchJson', () => {
  const fetchMock = vi.fn<typeof fetch>()

  beforeEach(() => {
    vi.stubGlobal('fetch', fetchMock)
    fetchMock.mockReset()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('sends credentials and the JSON content type and returns the parsed body', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ ok: 1 }))
    const data = await fetchJson<{ ok: number }>('/snapshot')
    expect(data).toEqual({ ok: 1 })
    expect(fetchMock).toHaveBeenCalledTimes(1)
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/v1/snapshot')
    expect(init?.credentials).toBe('include')
    expect((init?.headers as Record<string, string>)['Content-Type']).toBe('application/json')
  })

  it('retries once after a 401 when the refresh succeeds', async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse({ detail: 'expired' }, 401)) // first call
      .mockResolvedValueOnce(jsonResponse({ authenticated: true }))   // refresh
      .mockResolvedValueOnce(jsonResponse({ net_worth: 5 }))          // retry
    const data = await fetchJson<{ net_worth: number }>('/snapshot')
    expect(data).toEqual({ net_worth: 5 })
    expect(fetchMock).toHaveBeenCalledTimes(3)
    expect(String(fetchMock.mock.calls[1][0])).toMatch(/\/api\/v1\/auth\/refresh$/)
    expect(fetchMock.mock.calls[1][1]?.method).toBe('POST')
    expect(fetchMock.mock.calls[2][0]).toBe('/api/v1/snapshot')
  })

  it('throws the original 401 without a second retry when the refresh fails', async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse({ detail: 'expired' }, 401))
      .mockResolvedValueOnce(jsonResponse({ authenticated: false }, 401))
    await expect(fetchJson('/snapshot')).rejects.toThrow(/^401: /)
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })

  it('throws "<status>: <body>" for other failures without retrying', async () => {
    fetchMock.mockResolvedValueOnce(new Response('boom', { status: 500 }))
    await expect(fetchJson('/snapshot')).rejects.toThrow('500: boom')
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('does not set a JSON content type on a FormData body', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ session_id: 'x' }))
    const fd = new FormData()
    fd.append('context', 'income')
    await fetchJson('/import/upload', { method: 'POST', body: fd })
    const init = fetchMock.mock.calls[0][1]
    expect(init?.headers).toBeUndefined()
    expect(init?.body).toBe(fd)
  })
})
