import { ref } from 'vue'
import { defineStore } from 'pinia'
import { api } from '../api/client'
import { apiErrorMessage, apiErrorStatus } from '../composables/useApiError'
import type { AuthUser as User } from '../types'

export const useAuthStore = defineStore('auth', () => {
  const user = ref<User | null>(null)
  const loading = ref(true)
  const authenticated = ref(false)
  let refreshing: Promise<boolean> | null = null

  async function tryRefresh(): Promise<boolean> {
    try {
      const data = await api.auth.refresh()
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
    try {
      if (on) localStorage.setItem(SESSION_FLAG, '1')
      else localStorage.removeItem(SESSION_FLAG)
    } catch { /* ignore */ }
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
      let data
      try {
        data = await api.auth.me()
      } catch (e) {
        if (apiErrorStatus(e) === 401) {
          const ok = await refreshOnce()
          if (!ok) {
            user.value = null
            authenticated.value = false
          }
          return
        }
        throw e
      }
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
      const data = await api.auth.login(email, password)
      user.value = data.user
      authenticated.value = true
      rememberSession(true)
      return null
    } catch (e) {
      return apiErrorMessage(e, 'Login failed')
    }
  }

  async function logout() {
    try { await api.auth.logout() } catch { /* the cookie is cleared server-side even on a stale session */ }
    rememberSession(false)
    user.value = null
    authenticated.value = false
  }

  async function selectTenant(tenantId: number): Promise<string | null> {
    try {
      await api.auth.selectTenant(tenantId)
      // Reload the page to refresh all data stores with new tenant context
      window.location.reload()
      return null
    } catch (e) {
      return apiErrorMessage(e, 'Failed to switch tenant')
    }
  }

  return { user, loading, authenticated, checkAuth, login, logout, selectTenant, refreshOnce }
})
