import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { api } from '../api/client'
import type { AuthConfig } from '../types'

/** What the server says about this deployment (sign-in methods, demo mode). Loaded once per page load. */
export const useAppConfig = defineStore('appConfig', () => {
  const config = ref<AuthConfig | null>(null)
  let pending: Promise<AuthConfig | null> | null = null

  function load(): Promise<AuthConfig | null> {
    if (!pending) {
      pending = api.auth.config()
        .then(c => (config.value = c))
        .catch(() => { pending = null; return null })
    }
    return pending
  }

  const demo = computed(() => config.value?.demo_mode ?? false)
  return { config, load, demo }
})
