import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

/** Views and components call the typed client in src/api; raw fetch() lives only there. */
const src = resolve(__dirname, '..', 'src')
const ALLOWED = new Set(['api/client.ts', 'api/planning.ts'])
// Files still to be moved onto the client (NFR-CODE-001). Empty since 2026-10-29; never add to it.
const REMAINING = new Set<string>([])

/** Code samples shown to the user (the API page's quick start) are not calls. */
function withoutCodeSamples(text: string): string {
  return text.replace(/<pre[\s\S]*?<\/pre>/g, '')
}

function walk(dir: string, out: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    const full = join(dir, name)
    if (statSync(full).isDirectory()) walk(full, out)
    else if (/\.(vue|ts)$/.test(name)) out.push(full)
  }
  return out
}

describe('no raw fetch outside the API client', () => {
  it('finds fetch( only in the allowed files', () => {
    const offenders = walk(src)
      .filter(f => /\bfetch\(/.test(withoutCodeSamples(readFileSync(f, 'utf8'))))
      .map(f => f.slice(src.length + 1))
      .filter(f => !ALLOWED.has(f) && !REMAINING.has(f))
    expect(offenders).toEqual([])
  })
})
