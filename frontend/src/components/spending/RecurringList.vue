<script setup lang="ts">
import { computed } from 'vue'
import { useFormatters } from '../../composables/useFormatters'
import InfoTooltip from '../common/InfoTooltip.vue'
import type { RecurringExpense } from '../../types'

const props = defineProps<{ expenses: RecurringExpense[]; loading?: boolean; periodLabel?: string }>()
const { currency, date } = useFormatters()

const sorted = computed(() =>
  [...props.expenses].sort((a, b) => Math.abs(b.avg_monthly) - Math.abs(a.avg_monthly))
)
</script>

<template>
  <div class="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 min-w-0">
    <div class="px-5 py-4 border-b border-gray-200 dark:border-gray-800 pr-12">
      <h3 class="text-sm font-semibold text-gray-900 dark:text-white">Recurring Expenses <InfoTooltip text="Bills and subscriptions: merchants charged in two or more months of the period (three or more when it is longer than four months), at most twice a month, at a steady amount (most charges within 25% of the typical one), and charged in the last 45 days. Dining, delivery, groceries, gas, shopping, parking and trips are habits and never listed. The amount is the merchant's total over the months from its first to its last charge: what the bill costs a month.&lt;br&gt;&lt;br&gt;&lt;strong&gt;Source:&lt;/strong&gt; spending transactions grouped by merchant; transfers and loan payments excluded." /></h3>
      <p v-if="periodLabel" class="text-xs text-gray-500 dark:text-gray-400 mt-0.5">{{ periodLabel }}</p>
    </div>
    <div v-if="loading" class="px-5 py-8"><div class="h-24 rounded-lg bg-gray-100 dark:bg-gray-800 animate-pulse" /></div>
    <div v-else class="divide-y divide-gray-50 dark:divide-gray-800 max-h-80 overflow-y-auto">
      <div
        v-for="exp in sorted"
        :key="`${exp.merchant}-${exp.category}`"
        class="flex items-center justify-between gap-3 px-5 py-3"
      >
        <div class="min-w-0">
          <p class="text-sm font-medium text-gray-900 dark:text-white truncate" :title="exp.merchant">{{ exp.merchant }}</p>
          <p class="text-xs text-gray-500 dark:text-gray-400 truncate">{{ exp.category || 'Uncategorized' }} &middot; {{ exp.months_seen }} mo &middot; last {{ date(exp.last_date) }}</p>
        </div>
        <span class="text-sm font-medium text-red-600 dark:text-red-400 whitespace-nowrap">
          {{ currency(exp.avg_monthly) }}/mo
        </span>
      </div>
      <div v-if="sorted.length === 0" class="px-5 py-8 text-center text-sm text-gray-400 dark:text-gray-500">
        No recurring merchants in this period
      </div>
    </div>
  </div>
</template>
