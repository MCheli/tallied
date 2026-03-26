<script setup lang="ts">
import { onMounted } from 'vue'
import { useRouter } from 'vue-router'

const router = useRouter()

onMounted(async () => {
  // Plaid OAuth redirects back here with oauth_state_id in the URL.
  // Re-initialize Plaid Link with the same link_token stored before redirect.
  const linkToken = sessionStorage.getItem('plaid_link_token')
  if (!linkToken) {
    router.push({ name: 'settings' })
    return
  }

  const API = import.meta.env.VITE_API_URL || ''

  const handler = (window as any).Plaid.create({
    token: linkToken,
    receivedRedirectUri: window.location.href,
    onSuccess: async (public_token: string, metadata: any) => {
      await fetch(`${API}/api/v1/plaid/exchange`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          public_token,
          institution_name: metadata.institution?.name || 'Unknown',
        }),
      })
      sessionStorage.removeItem('plaid_link_token')
      router.push({ name: 'settings' })
    },
    onExit: () => {
      sessionStorage.removeItem('plaid_link_token')
      router.push({ name: 'settings' })
    },
  })
  handler.open()
})
</script>

<template>
  <div class="flex items-center justify-center h-full">
    <p class="text-gray-500 dark:text-gray-400">Completing bank connection...</p>
  </div>
</template>
