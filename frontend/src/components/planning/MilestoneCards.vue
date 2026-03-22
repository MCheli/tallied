<script setup lang="ts">
import { computed } from 'vue'
import { useFormatters } from '../../composables/useFormatters'
import type { ProjectionRow } from '../../types'

const props = defineProps<{ projections: ProjectionRow[] }>()
const { compact } = useFormatters()

const milestoneAges = [40, 45, 50, 55, 60, 65]

const milestones = computed(() => {
  const results: ProjectionRow[] = []
  // Find retirement age
  const retRow = props.projections.find(r => r.phase === 'retired')
  const retAge = retRow?.age ?? null

  const targetAges = new Set(milestoneAges)
  if (retAge) {
    targetAges.add(retAge)
    targetAges.add(retAge + 10)
    targetAges.add(retAge + 20)
  }

  for (const age of Array.from(targetAges).sort((a, b) => a - b)) {
    const row = props.projections.find(r => r.age === age)
    if (row) results.push(row)
  }
  return results
})
</script>

<template>
  <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
    <div
      v-for="m in milestones"
      :key="m.age"
      class="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 p-4"
    >
      <div class="flex items-center justify-between mb-3">
        <div>
          <span class="text-lg font-bold text-gray-900 dark:text-white">Age {{ m.age }}</span>
          <span class="ml-2 text-xs px-2 py-0.5 rounded-full"
            :class="m.phase === 'retired' ? 'bg-green-100 dark:bg-green-900 text-green-700 dark:text-green-300' : 'bg-blue-100 dark:bg-blue-900 text-blue-700 dark:text-blue-300'"
          >
            {{ m.phase }}
          </span>
        </div>
        <span class="text-sm text-gray-500 dark:text-gray-400">{{ m.year }}</span>
      </div>
      <p class="text-2xl font-bold text-gray-900 dark:text-white mb-3">{{ compact(m.net_worth) }}</p>
      <div class="space-y-1 text-xs">
        <div class="flex justify-between text-gray-600 dark:text-gray-400">
          <span>Cash</span><span class="font-medium">{{ compact(m.cash) }}</span>
        </div>
        <div class="flex justify-between text-gray-600 dark:text-gray-400">
          <span>Investments</span><span class="font-medium">{{ compact(m.investments) }}</span>
        </div>
        <div class="flex justify-between text-gray-600 dark:text-gray-400">
          <span>Company Stock</span><span class="font-medium">{{ compact(m.company_stock) }}</span>
        </div>
        <div class="flex justify-between text-gray-600 dark:text-gray-400">
          <span>Home Equity</span><span class="font-medium">{{ compact(m.home_equity) }}</span>
        </div>
        <div class="flex justify-between text-gray-600 dark:text-gray-400">
          <span>Retirement</span><span class="font-medium">{{ compact(m.retirement_bal) }}</span>
        </div>
      </div>
    </div>
  </div>
</template>
