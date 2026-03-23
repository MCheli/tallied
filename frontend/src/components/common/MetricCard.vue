<script setup lang="ts">
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
  <div class="group/card relative bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 p-5">
    <p class="text-sm font-medium text-gray-500 dark:text-gray-400 mb-1">{{ label }} <InfoTooltip v-if="info" :text="info" /></p>
    <p class="text-2xl font-bold text-gray-900 dark:text-white">{{ value }}</p>
    <div v-if="subtitle || changeValue != null" class="mt-1 flex items-center gap-2 text-sm">
      <span
        v-if="changeValue != null"
        :class="changeValue >= 0 ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'"
      >
        {{ changeValue >= 0 ? '▲' : '▼' }}
        {{ Math.abs(changeValue).toFixed(1) }}%
      </span>
      <span v-if="subtitle" class="text-gray-500 dark:text-gray-400">{{ subtitle }}</span>
    </div>
    <!-- View SQL button -->
    <button
      v-if="sql"
      @click="showSql = true"
      class="absolute top-2.5 right-2.5 p-1 rounded-md text-gray-300 dark:text-gray-600 opacity-0 group-hover/card:opacity-100 hover:!text-indigo-500 hover:bg-indigo-50 dark:hover:bg-indigo-950/40 transition-all"
      title="View SQL"
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
