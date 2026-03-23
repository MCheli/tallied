<script setup lang="ts">
import { ref, computed } from 'vue'
import { highlightSql } from '../../composables/useSqlHighlight'

const props = defineProps<{
  open: boolean
  sql: string
  title: string
  tables?: string[]
}>()

const emit = defineEmits<{
  close: []
}>()

const copied = ref(false)

const API_BASE = import.meta.env.VITE_API_URL || ''

// Table preview state
const previewTable = ref<string | null>(null)
const previewData = ref<{ columns: string[]; rows: Record<string, unknown>[]; total: number } | null>(null)
const previewLoading = ref(false)

const highlightedSql = computed(() => highlightSql(props.sql))

function copyToClipboard() {
  navigator.clipboard.writeText(props.sql)
  copied.value = true
  setTimeout(() => (copied.value = false), 1500)
}

function openInRunner() {
  sessionStorage.setItem('sql-runner-query', props.sql)
  window.location.href = '/database'
}

async function toggleTablePreview(tableName: string) {
  if (previewTable.value === tableName) {
    previewTable.value = null
    previewData.value = null
    return
  }
  previewTable.value = tableName
  previewLoading.value = true
  previewData.value = null
  try {
    const res = await fetch(`${API_BASE}/api/v1/admin/tables/${encodeURIComponent(tableName)}/preview?limit=5&offset=0`, { credentials: 'include' })
    if (!res.ok) throw new Error(`${res.status}`)
    previewData.value = await res.json()
  } catch {
    previewData.value = null
  } finally {
    previewLoading.value = false
  }
}

function formatCell(val: unknown): string {
  if (val === null || val === undefined) return '\u2014'
  if (typeof val === 'object') return JSON.stringify(val)
  return String(val)
}
</script>

<template>
  <Teleport to="body">
    <div v-if="open" class="fixed inset-0 z-[100] flex items-center justify-center">
      <div class="absolute inset-0 bg-black/50 backdrop-blur-sm" @click="emit('close')"></div>
      <div class="relative w-[700px] max-w-[90vw] max-h-[85vh] bg-white dark:bg-gray-900 rounded-xl shadow-2xl border border-gray-200 dark:border-gray-700 flex flex-col overflow-hidden">
        <!-- Header -->
        <div class="flex items-center justify-between px-5 py-3 border-b border-gray-200 dark:border-gray-700 flex-shrink-0">
          <div class="flex items-center gap-2.5">
            <span class="text-xs font-mono px-1.5 py-0.5 rounded bg-indigo-100 dark:bg-indigo-900/50 text-indigo-600 dark:text-indigo-400">&lt;/&gt;</span>
            <h3 class="text-sm font-semibold text-gray-900 dark:text-white">{{ title }}</h3>
          </div>
          <button
            @click="emit('close')"
            class="p-1.5 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 transition-colors"
          >
            <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M18 6L6 18"/><path d="M6 6l12 12"/>
            </svg>
          </button>
        </div>

        <!-- Body -->
        <div class="flex-1 overflow-auto p-5 space-y-4">
          <!-- SQL with syntax highlighting -->
          <pre class="sql-block text-[12px] leading-relaxed font-mono bg-gray-50 dark:bg-gray-950 border border-gray-200 dark:border-gray-800 rounded-lg p-4 overflow-x-auto whitespace-pre-wrap"><code v-html="highlightedSql"></code></pre>

          <!-- Tables referenced -->
          <div v-if="tables?.length">
            <p class="text-[10px] font-semibold uppercase tracking-wider text-gray-400 dark:text-gray-500 mb-2">Tables referenced</p>
            <div class="flex flex-wrap gap-1.5">
              <button
                v-for="t in tables"
                :key="t"
                @click="toggleTablePreview(t)"
                :class="[
                  'px-2 py-0.5 text-[11px] font-mono rounded-md border transition-colors cursor-pointer',
                  previewTable === t
                    ? 'bg-indigo-100 dark:bg-indigo-900/50 text-indigo-600 dark:text-indigo-400 border-indigo-300 dark:border-indigo-700'
                    : 'bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400 border-gray-200 dark:border-gray-700 hover:border-indigo-300 dark:hover:border-indigo-700 hover:text-indigo-600 dark:hover:text-indigo-400'
                ]"
              >
                <span class="flex items-center gap-1">
                  <svg class="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18"/><path d="M3 15h18"/><path d="M9 3v18"/>
                  </svg>
                  {{ t }}
                </span>
              </button>
            </div>

            <!-- Inline table preview -->
            <div v-if="previewTable" class="mt-3">
              <div v-if="previewLoading" class="flex items-center justify-center py-4">
                <div class="animate-spin rounded-full h-4 w-4 border-b-2 border-indigo-500"></div>
              </div>
              <div v-else-if="previewData" class="border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden">
                <div class="px-3 py-1.5 bg-gray-50 dark:bg-gray-800/80 border-b border-gray-200 dark:border-gray-700 flex items-center justify-between">
                  <span class="text-[10px] font-semibold text-gray-500 dark:text-gray-400">{{ previewTable }}</span>
                  <span class="text-[10px] text-gray-400 dark:text-gray-500 tabular-nums">{{ previewData.total.toLocaleString() }} rows (showing 5)</span>
                </div>
                <div class="overflow-x-auto">
                  <table class="w-full text-[11px]">
                    <thead>
                      <tr class="bg-gray-50 dark:bg-gray-800/50">
                        <th
                          v-for="col in previewData.columns"
                          :key="col"
                          class="px-2.5 py-1.5 text-left font-semibold text-gray-500 dark:text-gray-400 whitespace-nowrap border-b border-gray-200 dark:border-gray-700"
                        >{{ col }}</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr
                        v-for="(row, idx) in previewData.rows"
                        :key="idx"
                        class="border-b border-gray-50 dark:border-gray-800/50"
                      >
                        <td
                          v-for="col in previewData.columns"
                          :key="col"
                          class="px-2.5 py-1 whitespace-nowrap max-w-[180px] truncate"
                          :class="row[col] === null || row[col] === undefined ? 'text-gray-300 dark:text-gray-600 italic' : 'text-gray-700 dark:text-gray-300'"
                          :title="formatCell(row[col])"
                        >{{ formatCell(row[col]) }}</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Footer -->
        <div class="flex items-center justify-between px-5 py-3 border-t border-gray-200 dark:border-gray-700 flex-shrink-0">
          <button
            @click="openInRunner"
            class="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg text-indigo-600 dark:text-indigo-400 hover:bg-indigo-50 dark:hover:bg-indigo-950/40 transition-colors"
          >
            <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <polygon points="5 3 19 12 5 21 5 3"/>
            </svg>
            Run in SQL Runner
          </button>
          <button
            @click="copyToClipboard"
            class="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
          >
            <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"/>
            </svg>
            {{ copied ? 'Copied!' : 'Copy SQL' }}
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style>
/* SQL syntax highlighting */
.sql-block .sql-keyword { color: #8b5cf6; font-weight: 600; }
.sql-block .sql-function { color: #0891b2; }
.sql-block .sql-string { color: #16a34a; }
.sql-block .sql-number { color: #d97706; }
.sql-block .sql-comment { color: #9ca3af; font-style: italic; }
.sql-block .sql-operator { color: #6b7280; }

.dark .sql-block .sql-keyword { color: #a78bfa; }
.dark .sql-block .sql-function { color: #22d3ee; }
.dark .sql-block .sql-string { color: #4ade80; }
.dark .sql-block .sql-number { color: #fbbf24; }
.dark .sql-block .sql-comment { color: #6b7280; }
.dark .sql-block .sql-operator { color: #9ca3af; }
</style>
