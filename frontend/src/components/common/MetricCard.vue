<script setup lang="ts">
/**
 * MetricCard — one number with its explanation.
 *
 * Props: label, value (already formatted), subtitle, changeValue (percent; green up / red down),
 *        info (HTML for the InfoTooltip), sql + sqlTables (shows the "View SQL" button).
 * The "View SQL" button is visible at low opacity on touch devices (no hover) and on hover elsewhere;
 * its tap target is 40px.
 */
import { ref } from 'vue'
import InfoTooltip from './InfoTooltip.vue'
import SqlViewerModal from './SqlViewerModal.vue'

defineProps<{
  label: string
  value: string
  subtitle?: string
  changeValue?: number
  info?: string
  sql?: string
  sqlTables?: string[]
}>()

const showSql = ref(false)
</script>

<template>
  <div class="group/card relative bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 p-5 min-w-0">
    <p class="text-sm font-medium text-gray-500 dark:text-gray-400 mb-1 pr-8">{{ label }} <InfoTooltip v-if="info" :text="info" /></p>
    <p class="text-2xl font-bold text-gray-900 dark:text-white truncate" :title="value">{{ value }}</p>
    <div v-if="subtitle || changeValue != null" class="mt-1 flex items-center gap-2 text-sm min-w-0">
      <span
        v-if="changeValue != null"
        :class="changeValue >= 0 ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'"
      >
        {{ changeValue >= 0 ? '▲' : '▼' }}
        {{ Math.abs(changeValue).toFixed(1) }}%
      </span>
      <span v-if="subtitle" class="text-gray-500 dark:text-gray-400 truncate">{{ subtitle }}</span>
    </div>
    <!-- View SQL button -->
    <button
      v-if="sql"
      @click="showSql = true"
      class="sql-btn absolute top-1 right-1 w-10 h-10 flex items-center justify-center rounded-md text-gray-300 dark:text-gray-600 opacity-0 group-hover/card:opacity-100 focus-visible:opacity-100 hover:!text-indigo-500 hover:bg-indigo-50 dark:hover:bg-indigo-950/40 transition-all"
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
      :title="label"
      :tables="sqlTables"
      @close="showSql = false"
    />
  </div>
</template>

<style scoped>
/* Touch devices have no hover: keep the button discoverable at low opacity. */
@media (hover: none) {
  .sql-btn { opacity: 0.4; }
}
</style>
