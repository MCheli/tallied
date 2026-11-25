import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

vi.mock('../src/api/client', () => ({
  api: { auth: { me: vi.fn(), refresh: vi.fn() } },
}))

import { api } from '../src/api/client'
import { useAuthStore } from '../src/stores/auth'

const me = vi.mocked(api.auth.me)
const refresh = vi.mocked(api.auth.refresh)
const user = { id: 1, email: 'claudius@tallied.dev', display_name: 'Claudius Banks', is_admin: false, status: 'active' }

describe('auth store session', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    // Recent Node ships its own (unset) localStorage global, which hides jsdom's; use a plain one.
    const store = new Map<string, string>()
    vi.stubGlobal('localStorage', {
      getItem: (k: string) => store.get(k) ?? null,
      setItem: (k: string, v: string) => { store.set(k, String(v)) },
      removeItem: (k: string) => { store.delete(k) },
      clear: () => store.clear(),
    })
    me.mockReset()
    refresh.mockReset()
  })

  it('remembers a session that arrived by cookie (Google sign-in), so a lapsed access token is refreshed later', async () => {
    me.mockResolvedValueOnce({ authenticated: true, user } as never)
    await useAuthStore().checkAuth()
    expect(localStorage.getItem('tallied:had-session')).toBe('1')

    setActivePinia(createPinia())
    me.mockResolvedValueOnce({ authenticated: false, user: null } as never)
    refresh.mockResolvedValueOnce({ authenticated: true, user } as never)
    const auth = useAuthStore()
    await auth.checkAuth()
    expect(refresh).toHaveBeenCalledOnce()
    expect(auth.authenticated).toBe(true)
  })

  it('does not try a refresh for a visitor who never signed in', async () => {
    me.mockResolvedValueOnce({ authenticated: false, user: null } as never)
    const auth = useAuthStore()
    await auth.checkAuth()
    expect(refresh).not.toHaveBeenCalled()
    expect(auth.authenticated).toBe(false)
  })
})
