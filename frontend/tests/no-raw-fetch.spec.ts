import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

/** Views and components call the typed client in src/api; raw fetch() lives only there and in the auth store. */
const src = resolve(__dirname, '..', 'src')
const ALLOWED = new Set(['api/client.ts', 'api/planning.ts', 'stores/auth.ts'])
// Still to be moved onto the client (NFR-CODE-001). Remove entries as they are converted; never add.
const REMAINING = new Set([
  'components/common/DataExplorer.vue',
  'components/common/SqlViewerModal.vue',
  'components/import/ImportModal.vue',
  'views/AdminPortalView.vue',
  'views/AdminTenantDetailView.vue',
  'views/AdminUserDetailView.vue',
  'views/ApiView.vue',
  'views/DatabaseView.vue',
  'views/LoginView.vue',
  'views/PendingApprovalView.vue',
])

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
      .filter(f => /\bfetch\(/.test(readFileSync(f, 'utf8')))
      .map(f => f.slice(src.length + 1))
      .filter(f => !ALLOWED.has(f) && !REMAINING.has(f))
    expect(offenders).toEqual([])
  })
})
