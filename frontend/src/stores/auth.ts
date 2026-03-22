import { ref } from 'vue'
import { defineStore } from 'pinia'

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000'

interface User {
  id: number
  email: string
  display_name: string
  is_admin: boolean
}

export const useAuthStore = defineStore('auth', () => {
  const user = ref<User | null>(null)
  const loading = ref(true)
  const authenticated = ref(false)

  async function checkAuth() {
    loading.value = true
    try {
      const res = await fetch(`${API}/api/auth/me`, { credentials: 'include' })
      const data = await res.json()
      if (data.authenticated) {
        user.value = data.user
        authenticated.value = true
      } else {
        user.value = null
        authenticated.value = false
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
      const res = await fetch(`${API}/api/auth/login`, {
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
      return null
    } catch (e: any) {
      return e.message
    }
  }

  async function logout() {
    await fetch(`${API}/api/auth/logout`, { method: 'POST', credentials: 'include' })
    user.value = null
    authenticated.value = false
  }

  return { user, loading, authenticated, checkAuth, login, logout }
})
