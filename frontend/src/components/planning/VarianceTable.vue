<script setup lang="ts">
import { computed } from 'vue'
import { useFormatters } from '../../composables/useFormatters'
import type { VarianceResponse } from '../../types'

const props = defineProps<{ data: VarianceResponse[] }>()
const { currency, pct } = useFormatters()

const latestVariance = computed(() => {
  if (props.data.length === 0) return null
  return props.data[props.data.length - 1]
})

const rows = computed(() => {
  if (!latestVariance.value) return []
  return Object.entries(latestVariance.value.metrics).map(([metric, m]) => ({
    metric,
    plan: m.plan,
    actual: m.actual,
    variance: m.actual - m.plan,
    variancePct: m.plan_var_pct,
  }))
})
</script>

<template>
  <div class="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 overflow-hidden">
    <div class="px-5 py-4 border-b border-gray-200 dark:border-gray-800">
      <h3 class="text-sm font-semibold text-gray-900 dark:text-white">
        Plan vs. Actual{{ latestVariance ? ` (${latestVariance.year})` : '' }}
      </h3>
    </div>
    <div class="overflow-x-auto">
      <table class="w-full text-sm">
        <thead>
          <tr class="border-b border-gray-100 dark:border-gray-800">
            <th class="text-left px-5 py-3 font-medium text-gray-500 dark:text-gray-400">Metric</th>
            <th class="text-right px-5 py-3 font-medium text-gray-500 dark:text-gray-400">Plan</th>
            <th class="text-right px-5 py-3 font-medium text-gray-500 dark:text-gray-400">Actual</th>
            <th class="text-right px-5 py-3 font-medium text-gray-500 dark:text-gray-400">Variance</th>
            <th class="text-right px-5 py-3 font-medium text-gray-500 dark:text-gray-400">Variance %</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="row in rows"
            :key="row.metric"
            class="border-b border-gray-50 dark:border-gray-800"
          >
            <td class="px-5 py-3 text-gray-900 dark:text-white font-medium capitalize">
              {{ row.metric.replace(/_/g, ' ') }}
            </td>
            <td class="px-5 py-3 text-right text-gray-600 dark:text-gray-400">{{ currency(row.plan) }}</td>
            <td class="px-5 py-3 text-right text-gray-900 dark:text-white">{{ currency(row.actual) }}</td>
            <td
              class="px-5 py-3 text-right font-medium"
              :class="row.variance >= 0 ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'"
            >
              {{ currency(row.variance) }}
            </td>
            <td
              class="px-5 py-3 text-right font-medium"
              :class="(row.variancePct ?? 0) >= 0 ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'"
            >
              {{ row.variancePct != null ? pct(row.variancePct / 100, 1) : '—' }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
