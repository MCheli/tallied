<script setup lang="ts">
import { computed } from 'vue'
import { useFormatters } from '../../composables/useFormatters'
import type { ProjectionRow } from '../../types'

const props = defineProps<{ projections: ProjectionRow[] }>()
const { compact } = useFormatters()

const retirementTransitionIdx = computed(() => {
  return props.projections.findIndex(
    (r, i) => r.phase === 'retired' && (i === 0 || props.projections[i - 1].phase !== 'retired')
  )
})

function phaseClass(phase: string) {
  if (phase === 'retired') return 'bg-orange-100 text-orange-700 dark:bg-orange-900/40 dark:text-orange-400'
  return 'bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-400'
}
</script>

<template>
  <div class="overflow-x-auto rounded-xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900">
    <table class="w-full text-sm whitespace-nowrap">
      <thead class="sticky top-0 z-10 bg-gray-50 dark:bg-gray-800">
        <!-- Group header row -->
        <tr class="border-b border-gray-200 dark:border-gray-700">
          <th colspan="3" class="px-3 py-2 text-left text-xs font-semibold text-gray-400 dark:text-gray-500 uppercase tracking-wider"></th>
          <th colspan="3" class="px-3 py-2 text-center text-xs font-semibold text-indigo-500 dark:text-indigo-400 uppercase tracking-wider border-l border-gray-200 dark:border-gray-700">
            Income
          </th>
          <th colspan="5" class="px-3 py-2 text-center text-xs font-semibold text-indigo-500 dark:text-indigo-400 uppercase tracking-wider border-l border-gray-200 dark:border-gray-700">
            Balances
          </th>
          <th colspan="2" class="px-3 py-2 text-center text-xs font-semibold text-indigo-500 dark:text-indigo-400 uppercase tracking-wider border-l border-gray-200 dark:border-gray-700">
            Total
          </th>
        </tr>
        <!-- Column header row -->
        <tr class="border-b border-gray-200 dark:border-gray-700">
          <th class="px-3 py-2.5 text-left font-medium text-gray-500 dark:text-gray-400">Year</th>
          <th class="px-3 py-2.5 text-left font-medium text-gray-500 dark:text-gray-400">Age</th>
          <th class="px-3 py-2.5 text-left font-medium text-gray-500 dark:text-gray-400">Phase</th>
          <th class="px-3 py-2.5 text-right font-medium text-gray-500 dark:text-gray-400 border-l border-gray-200 dark:border-gray-700">Salary</th>
          <th class="px-3 py-2.5 text-right font-medium text-gray-500 dark:text-gray-400">RSU Income</th>
          <th class="px-3 py-2.5 text-right font-medium text-gray-500 dark:text-gray-400">Total Comp</th>
          <th class="px-3 py-2.5 text-right font-medium text-gray-500 dark:text-gray-400 border-l border-gray-200 dark:border-gray-700">Cash</th>
          <th class="px-3 py-2.5 text-right font-medium text-gray-500 dark:text-gray-400">Investments</th>
          <th class="px-3 py-2.5 text-right font-medium text-gray-500 dark:text-gray-400">Company Stock</th>
          <th class="px-3 py-2.5 text-right font-medium text-gray-500 dark:text-gray-400">Home Equity</th>
          <th class="px-3 py-2.5 text-right font-medium text-gray-500 dark:text-gray-400">Retirement</th>
          <th class="px-3 py-2.5 text-right font-medium text-gray-500 dark:text-gray-400 border-l border-gray-200 dark:border-gray-700">Net Worth</th>
          <th class="px-3 py-2.5 text-right font-medium text-gray-500 dark:text-gray-400">Withdrawal</th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="(row, idx) in projections"
          :key="row.year"
          :class="[
            'border-b border-gray-50 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-gray-800/50 transition-colors',
            idx === retirementTransitionIdx ? 'bg-orange-50/60 dark:bg-orange-950/20 ring-1 ring-inset ring-orange-200 dark:ring-orange-800' : ''
          ]"
        >
          <td class="px-3 py-2 text-gray-900 dark:text-white font-medium">{{ row.year }}</td>
          <td class="px-3 py-2 text-gray-900 dark:text-white">{{ row.age }}</td>
          <td class="px-3 py-2">
            <span :class="['px-2 py-0.5 text-xs font-medium rounded-full', phaseClass(row.phase)]">
              {{ row.phase }}
            </span>
          </td>
          <td class="px-3 py-2 text-right text-gray-700 dark:text-gray-300 border-l border-gray-100 dark:border-gray-800">{{ compact(row.salary) }}</td>
          <td class="px-3 py-2 text-right text-gray-700 dark:text-gray-300">{{ compact(row.rsu_income) }}</td>
          <td class="px-3 py-2 text-right text-gray-900 dark:text-white font-medium">{{ compact(row.total_comp) }}</td>
          <td class="px-3 py-2 text-right text-gray-700 dark:text-gray-300 border-l border-gray-100 dark:border-gray-800">{{ compact(row.cash) }}</td>
          <td class="px-3 py-2 text-right text-gray-700 dark:text-gray-300">{{ compact(row.investments) }}</td>
          <td class="px-3 py-2 text-right text-gray-700 dark:text-gray-300">{{ compact(row.company_stock) }}</td>
          <td class="px-3 py-2 text-right text-gray-700 dark:text-gray-300">{{ compact(row.home_equity) }}</td>
          <td class="px-3 py-2 text-right text-gray-700 dark:text-gray-300">{{ compact(row.retirement_bal) }}</td>
          <td class="px-3 py-2 text-right text-gray-900 dark:text-white font-semibold border-l border-gray-100 dark:border-gray-800">{{ compact(row.net_worth) }}</td>
          <td class="px-3 py-2 text-right text-gray-700 dark:text-gray-300">{{ row.withdrawal > 0 ? compact(row.withdrawal) : '\u2014' }}</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
