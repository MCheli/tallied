<script setup lang="ts">
import InfoTooltip from './InfoTooltip.vue'

defineProps<{
  label: string
  value: string
  subtitle?: string
  changeValue?: number
  info?: string
}>()
</script>

<template>
  <div class="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 p-5">
    <p class="text-sm font-medium text-gray-500 dark:text-gray-400 mb-1">{{ label }} <InfoTooltip v-if="info" :text="info" /></p>
    <p class="text-2xl font-bold text-gray-900 dark:text-white">{{ value }}</p>
    <div v-if="subtitle || changeValue != null" class="mt-1 flex items-center gap-2 text-sm">
      <span
        v-if="changeValue != null"
        :class="changeValue >= 0 ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'"
      >
        {{ changeValue >= 0 ? '\u25B2' : '\u25BC' }}
        {{ Math.abs(changeValue).toFixed(1) }}%
      </span>
      <span v-if="subtitle" class="text-gray-500 dark:text-gray-400">{{ subtitle }}</span>
    </div>
  </div>
</template>
