<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const API = import.meta.env.VITE_API_URL || ''
const auth = useAuthStore()
const router = useRouter()

const email = ref('')
const password = ref('')
const error = ref('')
const loading = ref(false)

// Auth config from server
const configLoaded = ref(false)
const devMode = ref(false)
const googleSso = ref(false)

onMounted(async () => {
  // Check if already authenticated
  await auth.checkAuth()
  if (auth.authenticated) {
    router.push('/')
    return
  }

  // Get available auth methods
  try {
    const res = await fetch(`${API}/api/v1/auth/config`)
    const config = await res.json()
    devMode.value = config.dev_mode
    googleSso.value = config.google_sso
  } catch {} finally {
    configLoaded.value = true
  }
})

async function handleDevLogin() {
  error.value = ''
  loading.value = true
  const err = await auth.login(email.value, password.value)
  loading.value = false
  if (err) {
    error.value = err
  } else {
    router.push('/')
  }
}

function handleGoogleLogin() {
  window.location.href = `${API}/api/v1/auth/google/login`
}
</script>

<template>
  <div class="min-h-screen flex items-center justify-center bg-gray-50 dark:bg-gray-950">
    <div class="w-full max-w-sm">
      <div class="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-2xl p-8 shadow-lg">
        <div class="text-center mb-8">
          <h1 class="text-2xl font-bold text-gray-900 dark:text-white">Tallied</h1>
          <p class="text-sm text-gray-500 dark:text-gray-400 mt-1">Your finances, tallied.</p>
        </div>

        <!-- Loading state while fetching auth config -->
        <div v-if="!configLoaded" class="flex justify-center py-8">
          <div class="h-6 w-6 border-2 border-indigo-600 border-t-transparent rounded-full animate-spin"></div>
        </div>

        <template v-else>

        <!-- Google SSO button -->
        <div v-if="googleSso" class="mb-6">
          <button @click="handleGoogleLogin"
            class="w-full flex items-center justify-center gap-3 py-2.5 bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded-lg text-sm font-medium text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors">
            <svg class="w-5 h-5" viewBox="0 0 24 24">
              <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z"/>
              <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
              <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/>
              <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
            </svg>
            Sign in with Google
          </button>
        </div>

        <!-- Divider (when both methods available) -->
        <div v-if="googleSso && devMode" class="flex items-center gap-3 mb-6">
          <div class="flex-1 h-px bg-gray-200 dark:bg-gray-700"></div>
          <span class="text-xs text-gray-400">or</span>
          <div class="flex-1 h-px bg-gray-200 dark:bg-gray-700"></div>
        </div>

        <!-- Dev mode login form -->
        <form v-if="devMode" @submit.prevent="handleDevLogin" class="space-y-4">
          <div>
            <label class="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">Email</label>
            <input v-model="email" type="email" required autofocus
              class="w-full px-3 py-2.5 text-sm border border-gray-200 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
              placeholder="claudius@tallied.dev" />
          </div>

          <div>
            <label class="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">Password</label>
            <input v-model="password" type="password" required
              class="w-full px-3 py-2.5 text-sm border border-gray-200 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
              placeholder="••••••" />
          </div>

          <div v-if="error" class="text-xs text-red-500 bg-red-50 dark:bg-red-950/30 rounded-lg px-3 py-2">
            {{ error }}
          </div>

          <button type="submit" :disabled="loading"
            class="w-full py-2.5 bg-indigo-600 text-white text-sm font-medium rounded-lg hover:bg-indigo-700 disabled:opacity-50 transition-colors">
            {{ loading ? 'Signing in...' : 'Sign in' }}
          </button>
        </form>

        <!-- Only Google available, no dev mode -->
        <div v-if="!devMode && !googleSso" class="text-center text-sm text-gray-500">
          No authentication methods configured.
        </div>

        <!-- Dev mode hint -->
        <div v-if="devMode" class="mt-6 pt-4 border-t border-gray-100 dark:border-gray-800">
          <p class="text-[10px] text-gray-400 text-center">
            Dev mode &middot; claudius@tallied.dev / demo123 &middot; admin account also available
          </p>
        </div>

        </template>
      </div>
    </div>
  </div>
</template>
