<script setup lang="ts">
import InfoTooltip from './InfoTooltip.vue'

defineProps<{
  title: string
  subtitle?: string
  loading?: boolean
  info?: string
}>()
</script>

<template>
  <div class="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 p-5">
    <div class="mb-4">
      <h3 class="text-sm font-semibold text-gray-900 dark:text-white">{{ title }} <InfoTooltip v-if="info" :text="info" /></h3>
      <p v-if="subtitle" class="text-xs text-gray-500 dark:text-gray-400 mt-0.5">{{ subtitle }}</p>
    </div>
    <div v-if="loading" class="flex items-center justify-center h-48">
      <div class="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-500"></div>
    </div>
    <slot v-else />
  </div>
</template>
