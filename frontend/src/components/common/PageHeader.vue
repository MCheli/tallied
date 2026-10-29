<script setup lang="ts">
/**
 * PageHeader — the one page title block.
 *
 * Usage:
 *   <PageHeader title="Spending" subtitle="Where the money went" tooltip="<strong>…</strong>">
 *     <button …>Data</button>
 *     <PresetButtons … />
 *   </PageHeader>
 *
 * Props: title (required), subtitle (optional), tooltip (optional HTML shown in an InfoTooltip next to the title).
 * Slot (default): actions. They sit in a toolbar that wraps onto new lines at phone width, so nothing is ever cut off.
 * Slot "below": optional second row (filter chips, tabs) rendered full-width under the title/actions row.
 */
import InfoTooltip from './InfoTooltip.vue'

defineProps<{
  title: string
  subtitle?: string
  tooltip?: string
}>()
</script>

<template>
  <header class="mb-6 min-w-0">
    <div class="flex flex-wrap items-start justify-between gap-x-4 gap-y-3 min-w-0">
      <div class="min-w-0">
        <h1 class="text-2xl font-bold tracking-tight text-gray-900 dark:text-white flex items-center gap-1 flex-wrap">
          <span class="truncate">{{ title }}</span>
          <InfoTooltip v-if="tooltip" :text="tooltip" />
        </h1>
        <p v-if="subtitle" class="mt-1 text-sm text-gray-500 dark:text-gray-400">{{ subtitle }}</p>
      </div>
      <div v-if="$slots.default" class="flex flex-wrap items-center gap-2 min-w-0 max-w-full">
        <slot />
      </div>
    </div>
    <div v-if="$slots.below" class="mt-3 min-w-0">
      <slot name="below" />
    </div>
  </header>
</template>
