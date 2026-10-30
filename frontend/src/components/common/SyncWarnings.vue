<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api } from '../../api/client'

// The bank connection's own warnings from the latest sync (e.g. "Connection to <bank> may need attention").
// Without them a bank that stopped updating shows yesterday's balance as if it were current.
const warnings = ref<string[]>([])

onMounted(async () => {
  try {
    const st = await api.simplefin.syncStatus()
    warnings.value = st.warnings ?? []
  } catch (e) {
    console.warn('Could not read sync status', e)
  }
})
</script>

<template>
  <div v-if="warnings.length" role="status"
    class="mb-4 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900 dark:border-amber-900/60 dark:bg-amber-950/40 dark:text-amber-200">
    <p class="font-medium">The bank connection reported a problem on the last sync</p>
    <ul class="mt-1 list-disc pl-5 space-y-0.5">
      <li v-for="w in warnings" :key="w">{{ w }}</li>
    </ul>
    <p class="mt-1 text-xs text-amber-800/80 dark:text-amber-300/80">Balances from an affected bank may be out of date. Fix it in SimpleFIN Bridge; the next sync picks it up.</p>
  </div>
</template>
