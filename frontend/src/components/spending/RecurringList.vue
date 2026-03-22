<script setup lang="ts">
import { computed } from 'vue'
import { useFormatters } from '../../composables/useFormatters'
import InfoTooltip from '../common/InfoTooltip.vue'
import type { RecurringExpense } from '../../types'

const props = defineProps<{ expenses: RecurringExpense[] }>()
const { currency } = useFormatters()

const sorted = computed(() =>
  [...props.expenses].sort((a, b) => Math.abs(b.avg_monthly) - Math.abs(a.avg_monthly))
)
</script>

<template>
  <div class="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800">
    <div class="px-5 py-4 border-b border-gray-200 dark:border-gray-800">
      <h3 class="text-sm font-semibold text-gray-900 dark:text-white">Recurring Expenses <InfoTooltip text="Expenses that appear consistently across multiple months. Detected automatically by looking for merchants that appear in 2+ months during the lookback period. Amount shown is the average monthly spend.&lt;br&gt;&lt;br&gt;&lt;strong&gt;Source:&lt;/strong&gt; Transactions table, merchants grouped by month and filtered for &ge;2 month appearances." /></h3>
    </div>
    <div class="divide-y divide-gray-50 dark:divide-gray-800 max-h-80 overflow-y-auto">
      <div
        v-for="exp in sorted"
        :key="exp.merchant"
        class="flex items-center justify-between px-5 py-3"
      >
        <div>
          <p class="text-sm font-medium text-gray-900 dark:text-white">{{ exp.merchant }}</p>
          <p class="text-xs text-gray-500 dark:text-gray-400">{{ exp.category || 'Uncategorized' }}</p>
        </div>
        <span class="text-sm font-medium text-red-600 dark:text-red-400">
          {{ currency(exp.avg_monthly) }}/mo
        </span>
      </div>
      <div v-if="sorted.length === 0" class="px-5 py-8 text-center text-sm text-gray-500 dark:text-gray-400">
        No recurring expenses detected
      </div>
    </div>
  </div>
</template>
