<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { api } from '../../api/client'
import { useFormatters } from '../../composables/useFormatters'
import type { ImportLogEntry } from '../../types'

const { dateShort } = useFormatters()

const logs = ref<ImportLogEntry[]>([])
const loading = ref(false)
const error = ref<string | null>(null)

async function load() {
  loading.value = true
  error.value = null
  try {
    logs.value = await api.getImportLog()
  } catch (e) {
    error.value = 'Failed to load import history: ' + (e instanceof Error ? e.message : String(e))
  }
  loading.value = false
}

function statusClass(status: string): string {
  if (status === 'confirmed' || status === 'completed') return 'bg-green-100 dark:bg-green-900 text-green-700 dark:text-green-300'
  if (status === 'error' || status === 'failed') return 'bg-red-100 dark:bg-red-900 text-red-700 dark:text-red-300'
  return 'bg-yellow-100 dark:bg-yellow-900 text-yellow-700 dark:text-yellow-300'
}

onMounted(load)
</script>

<template>
  <div class="min-w-0 bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 overflow-hidden">
    <div class="px-5 py-4 border-b border-gray-200 dark:border-gray-800">
      <h3 class="text-sm font-semibold text-gray-900 dark:text-white">Import history</h3>
      <p class="text-xs text-gray-400 dark:text-gray-500 mt-0.5">One row per confirmed document import.</p>
    </div>

    <div v-if="error" class="px-5 py-3 text-sm text-red-600 dark:text-red-400">{{ error }}</div>

    <div v-if="loading" class="flex items-center justify-center h-32">
      <div class="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-500"></div>
    </div>

    <div v-else-if="logs.length === 0" class="px-5 py-8 text-center text-sm text-gray-500 dark:text-gray-400">
      No imports yet. Use the Import button on the Income, RSU, 401(k) or Property page.
    </div>

    <div v-else class="overflow-x-auto min-w-0">
      <table class="w-full min-w-[40rem] text-sm">
        <thead>
          <tr class="border-b border-gray-100 dark:border-gray-800">
            <th class="text-left px-5 py-3 font-medium text-gray-500 dark:text-gray-400">Date</th>
            <th class="text-left px-5 py-3 font-medium text-gray-500 dark:text-gray-400">Source</th>
            <th class="text-left px-5 py-3 font-medium text-gray-500 dark:text-gray-400">Mode</th>
            <th class="text-left px-5 py-3 font-medium text-gray-500 dark:text-gray-400">Status</th>
            <th class="text-right px-5 py-3 font-medium text-gray-500 dark:text-gray-400">Records</th>
            <th class="text-left px-5 py-3 font-medium text-gray-500 dark:text-gray-400">Error</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="log in logs" :key="log.id" class="border-b border-gray-50 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-gray-800">
            <td class="px-5 py-3 text-gray-600 dark:text-gray-400 whitespace-nowrap">{{ dateShort(log.created_at) }}</td>
            <td class="px-5 py-3 text-gray-900 dark:text-white whitespace-nowrap">{{ log.source }}</td>
            <td class="px-5 py-3 text-gray-600 dark:text-gray-400 whitespace-nowrap">{{ log.capture_mode || '—' }}</td>
            <td class="px-5 py-3">
              <span :class="['inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium', statusClass(log.status)]">{{ log.status }}</span>
            </td>
            <td class="px-5 py-3 text-right text-gray-900 dark:text-white">{{ log.records_created }}</td>
            <td class="px-5 py-3 text-red-600 dark:text-red-400 text-xs max-w-xs"><div class="truncate" :title="log.error_message || undefined">{{ log.error_message || '—' }}</div></td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
