<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'

const API = import.meta.env.VITE_API_URL || ''
const router = useRouter()

const userName = ref('')
const userEmail = ref('')
const checking = ref(false)
const statusMessage = ref('')

onMounted(async () => {
  await fetchUserInfo()
})

async function fetchUserInfo() {
  try {
    const res = await fetch(`${API}/api/v1/auth/me`, { credentials: 'include' })
    const data = await res.json()
    if (data.authenticated && data.user) {
      userName.value = data.user.display_name || ''
      userEmail.value = data.user.email || ''
      // If user now has a tenant, they've been approved
      if (data.user.current_tenant) {
        router.push('/')
        return
      }
    } else {
      // Not authenticated at all — go to login
      router.push('/login')
    }
  } catch {
    // Silently handle fetch errors
  }
}

async function checkStatus() {
  checking.value = true
  statusMessage.value = ''
  try {
    const res = await fetch(`${API}/api/v1/auth/me`, { credentials: 'include' })
    const data = await res.json()
    if (data.authenticated && data.user?.current_tenant) {
      statusMessage.value = 'Your account has been approved! Redirecting...'
      setTimeout(() => router.push('/'), 1000)
    } else {
      statusMessage.value = 'Your account is still being reviewed.'
    }
  } catch {
    statusMessage.value = 'Unable to check status. Please try again.'
  } finally {
    checking.value = false
  }
}

async function handleLogout() {
  await fetch(`${API}/api/v1/auth/logout`, { method: 'POST', credentials: 'include' })
  router.push('/login')
}
</script>

<template>
  <div class="min-h-screen flex items-center justify-center bg-gray-50 dark:bg-gray-950">
    <div class="w-full max-w-md">
      <div class="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-2xl p-8 shadow-lg text-center">
        <div class="mb-6">
          <div class="w-16 h-16 mx-auto mb-4 rounded-full bg-amber-100 dark:bg-amber-900/30 flex items-center justify-center">
            <svg class="w-8 h-8 text-amber-600 dark:text-amber-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          </div>
          <h1 class="text-xl font-bold text-gray-900 dark:text-white">Your account is being reviewed</h1>
          <p class="text-sm text-gray-500 dark:text-gray-400 mt-2">
            We'll notify you when your account is ready. You can close this page.
          </p>
        </div>

        <div v-if="userEmail" class="mb-6 py-3 px-4 bg-gray-50 dark:bg-gray-800 rounded-lg">
          <p class="text-sm font-medium text-gray-900 dark:text-white">{{ userName }}</p>
          <p class="text-xs text-gray-500 dark:text-gray-400">{{ userEmail }}</p>
        </div>

        <button
          @click="checkStatus"
          :disabled="checking"
          class="w-full py-2.5 bg-indigo-600 text-white text-sm font-medium rounded-lg hover:bg-indigo-700 disabled:opacity-50 transition-colors"
        >
          {{ checking ? 'Checking...' : 'Check status' }}
        </button>

        <p v-if="statusMessage" class="mt-3 text-sm" :class="statusMessage.includes('approved') ? 'text-green-600 dark:text-green-400' : 'text-gray-500 dark:text-gray-400'">
          {{ statusMessage }}
        </p>

        <button
          @click="handleLogout"
          class="mt-4 text-xs text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 transition-colors"
        >
          Sign out
        </button>
      </div>
    </div>
  </div>
</template>
