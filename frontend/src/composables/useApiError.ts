/**
 * The API client throws `Error("<status>: <body>")`. This turns that into the
 * server's `detail` string (or the body text) so pages can show it inline.
 */
export function apiErrorMessage(e: unknown, fallback = 'Request failed'): string {
  if (!(e instanceof Error)) return fallback
  const m = /^(\d{3}):\s*([\s\S]*)$/.exec(e.message)
  const body = m ? m[2] : e.message
  try {
    const parsed = JSON.parse(body)
    if (parsed && typeof parsed.detail === 'string') return parsed.detail
    if (parsed && parsed.detail && typeof parsed.detail.message === 'string') return parsed.detail.message
  } catch {
    /* not JSON */
  }
  return body.trim() || fallback
}

export function apiErrorStatus(e: unknown): number | null {
  if (!(e instanceof Error)) return null
  const m = /^(\d{3}):/.exec(e.message)
  return m ? Number(m[1]) : null
}
