<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const router = useRouter()

const email = ref('')
const password = ref('')
const error = ref('')
const loading = ref(false)

async function handleLogin() {
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
</script>

<template>
  <div class="min-h-screen flex items-center justify-center bg-gray-50 dark:bg-gray-950">
    <div class="w-full max-w-sm">
      <div class="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-2xl p-8 shadow-lg">
        <div class="text-center mb-8">
          <h1 class="text-2xl font-bold text-gray-900 dark:text-white">Tallied</h1>
          <p class="text-sm text-gray-500 dark:text-gray-400 mt-1">Your finances, tallied.</p>
        </div>

        <form @submit.prevent="handleLogin" class="space-y-4">
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

        <div class="mt-6 pt-4 border-t border-gray-100 dark:border-gray-800">
          <p class="text-[10px] text-gray-400 text-center">
            Demo: claudius@tallied.dev / demo123
          </p>
        </div>
      </div>
    </div>
  </div>
</template>
