import { ref } from 'vue'
import { defineStore } from 'pinia'

const API = import.meta.env.VITE_API_URL || ''

interface Tenant {
  id: number
  display_name: string
  slug: string
}

interface User {
  id: number
  email: string
  display_name: string
  is_admin: boolean
  status: string
  current_tenant: Tenant | null
  tenants: Tenant[]
}

export const useAuthStore = defineStore('auth', () => {
  const user = ref<User | null>(null)
  const loading = ref(true)
  const authenticated = ref(false)
  let refreshing: Promise<boolean> | null = null

  async function tryRefresh(): Promise<boolean> {
    try {
      const res = await fetch(`${API}/api/v1/auth/refresh`, {
        method: 'POST',
        credentials: 'include',
      })
      if (!res.ok) return false
      const data = await res.json()
      if (data.authenticated) {
        user.value = data.user
        authenticated.value = true
        rememberSession(true)
        return true
      }
      return false
    } catch {
      return false
    }
  }

  // The refresh cookie is httpOnly, so the page cannot see whether one exists. Remember
  // that a session was established in this browser and only try to refresh then; a fresh
  // visitor on the login page no longer fires two 401s (BUG-8).
  const SESSION_FLAG = 'tallied:had-session'
  function hadSession(): boolean {
    try { return localStorage.getItem(SESSION_FLAG) === '1' } catch { return true }
  }
  function rememberSession(on: boolean) {
    try { on ? localStorage.setItem(SESSION_FLAG, '1') : localStorage.removeItem(SESSION_FLAG) } catch { /* ignore */ }
  }

  async function refreshOnce(): Promise<boolean> {
    if (!hadSession()) return false
    if (!refreshing) {
      refreshing = tryRefresh().then(ok => { if (!ok) rememberSession(false); return ok }).finally(() => { refreshing = null })
    }
    return refreshing
  }

  async function checkAuth() {
    loading.value = true
    try {
      const res = await fetch(`${API}/api/v1/auth/me`, { credentials: 'include' })
      if (res.status === 401) {
        const ok = await refreshOnce()
        if (!ok) {
          user.value = null
          authenticated.value = false
        }
        return
      }
      const data = await res.json()
      if (data.authenticated) {
        user.value = data.user
        authenticated.value = true
      } else {
        // Access token may have expired — try refresh
        const ok = await refreshOnce()
        if (!ok) {
          user.value = null
          authenticated.value = false
        }
      }
    } catch {
      user.value = null
      authenticated.value = false
    } finally {
      loading.value = false
    }
  }

  async function login(email: string, password: string): Promise<string | null> {
    try {
      const res = await fetch(`${API}/api/v1/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password }),
        credentials: 'include',
      })
      if (!res.ok) {
        const data = await res.json()
        return data.detail || 'Login failed'
      }
      const data = await res.json()
      user.value = data.user
      authenticated.value = true
      rememberSession(true)
      return null
    } catch (e: any) {
      return e.message
    }
  }

  async function logout() {
    await fetch(`${API}/api/v1/auth/logout`, { method: 'POST', credentials: 'include' })
    rememberSession(false)
    user.value = null
    authenticated.value = false
  }

  async function selectTenant(tenantId: number): Promise<string | null> {
    try {
      const res = await fetch(`${API}/api/v1/auth/select-tenant`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tenant_id: tenantId }),
        credentials: 'include',
      })
      if (!res.ok) {
        const data = await res.json()
        return data.detail || 'Failed to switch tenant'
      }
      // Reload the page to refresh all data stores with new tenant context
      window.location.reload()
      return null
    } catch (e: any) {
      return e.message
    }
  }

  return { user, loading, authenticated, checkAuth, login, logout, selectTenant, refreshOnce }
})
