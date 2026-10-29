<script setup lang="ts">
/**
 * ChartContainer — the card around every chart.
 *
 * Props: title, subtitle, info (HTML for the InfoTooltip), sql + sqlTables ("View SQL" button),
 *        loading (skeleton instead of the chart), empty + emptyText (centered message instead of the chart;
 *        default "No data for this period"). Slot (default): the chart.
 * Rule: pass `empty` whenever the series has no points, so a bare axis never renders.
 */
import { ref } from 'vue'
import InfoTooltip from './InfoTooltip.vue'
import SqlViewerModal from './SqlViewerModal.vue'

withDefaults(defineProps<{
  title: string
  subtitle?: string
  loading?: boolean
  empty?: boolean
  emptyText?: string
  info?: string
  sql?: string
  sqlTables?: string[]
}>(), {
  loading: false,
  empty: false,
  emptyText: 'No data for this period',
})

const showSql = ref(false)
</script>

<template>
  <div class="group/chart relative bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 p-5 min-w-0">
    <div class="mb-4 pr-8 min-w-0">
      <h3 class="text-sm font-semibold text-gray-900 dark:text-white">{{ title }} <InfoTooltip v-if="info" :text="info" /></h3>
      <p v-if="subtitle" class="text-xs text-gray-500 dark:text-gray-400 mt-0.5">{{ subtitle }}</p>
    </div>
    <div v-if="loading" class="h-48 rounded-lg bg-gray-100 dark:bg-gray-800 animate-pulse" aria-busy="true" />
    <div v-else-if="empty" class="h-48 flex items-center justify-center text-sm text-gray-400 dark:text-gray-500 text-center px-4">
      {{ emptyText }}
    </div>
    <div v-else class="min-w-0 overflow-hidden">
      <slot />
    </div>
    <!-- View SQL button -->
    <button
      v-if="sql"
      @click="showSql = true"
      class="sql-btn absolute top-1 right-1 w-10 h-10 flex items-center justify-center rounded-md text-gray-300 dark:text-gray-600 opacity-0 group-hover/chart:opacity-100 focus-visible:opacity-100 hover:!text-indigo-500 hover:bg-indigo-50 dark:hover:bg-indigo-950/40 transition-all"
      title="View SQL"
      aria-label="View SQL"
    >
      <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/>
      </svg>
    </button>
    <SqlViewerModal
      v-if="sql"
      :open="showSql"
      :sql="sql"
      :title="title"
      :tables="sqlTables"
      @close="showSql = false"
    />
  </div>
</template>

<style scoped>
@media (hover: none) {
  .sql-btn { opacity: 0.4; }
}
</style>
