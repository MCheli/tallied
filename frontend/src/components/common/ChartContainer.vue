<script setup lang="ts">
import { ref } from 'vue'
import InfoTooltip from './InfoTooltip.vue'
import SqlViewerModal from './SqlViewerModal.vue'

defineProps<{
  title: string
  subtitle?: string
  loading?: boolean
  info?: string
  sql?: string
  sqlTables?: string[]
}>()

const showSql = ref(false)
</script>

<template>
  <div class="group/chart relative bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 p-5">
    <div class="mb-4">
      <h3 class="text-sm font-semibold text-gray-900 dark:text-white">{{ title }} <InfoTooltip v-if="info" :text="info" /></h3>
      <p v-if="subtitle" class="text-xs text-gray-500 dark:text-gray-400 mt-0.5">{{ subtitle }}</p>
    </div>
    <div v-if="loading" class="flex items-center justify-center h-48">
      <div class="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-500"></div>
    </div>
    <slot v-else />
    <!-- View SQL button -->
    <button
      v-if="sql"
      @click="showSql = true"
      class="absolute top-3.5 right-3.5 p-1 rounded-md text-gray-300 dark:text-gray-600 opacity-0 group-hover/chart:opacity-100 hover:!text-indigo-500 hover:bg-indigo-50 dark:hover:bg-indigo-950/40 transition-all"
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
      :title="title"
      :tables="sqlTables"
      @close="showSql = false"
    />
  </div>
</template>
