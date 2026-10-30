<script setup lang="ts">
/**
 * SprintPanel — "Sprint to retirement": save as hard as possible now (401(k) at the IRS limit, every
 * equity payout invested), retire at the earliest safe age, live lean after. Shows, for the target
 * chance of success: the most living spending per retirement age and return, the earliest age per
 * spending level, and which levers move the answer most. The view runs it on request (it is slower).
 */
import ChartContainer from '../common/ChartContainer.vue'
import DataTable from '../common/DataTable.vue'
import InfoTooltip from '../common/InfoTooltip.vue'
import LeverTornado from './LeverTornado.vue'
import { useFormatters } from '../../composables/useFormatters'
import { tornadoFromSprint } from '../../composables/usePlanningOutlook'
import type { SprintResult } from '../../types'

defineProps<{ result: SprintResult | null; loading: boolean; error: string | null }>()
const emit = defineEmits<{ (e: 'run'): void }>()
const { money, percent } = useFormatters()
</script>

<template>
  <section class="rounded-xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 p-5 min-w-0 space-y-4">
    <div class="flex flex-wrap items-start justify-between gap-3">
      <div class="min-w-0">
        <h3 class="text-sm font-semibold text-gray-900 dark:text-white">Sprint to retirement
          <InfoTooltip text="Everything as shown, except: the 401(k) at the IRS limit and every equity payout sold and invested. For each retirement age and return assumption, the most living spending (today's dollars) that still reaches your target chance of success; read it the other way for the earliest age at a given spending. Uses the levers you have moved, unsaved ones included, and the selected market scenario." />
        </h3>
        <p class="text-xs text-gray-500 dark:text-gray-400">Max the 401(k), invest every vest, retire at the earliest safe age, live lean.</p>
      </div>
      <button type="button" :disabled="loading" class="rounded-md bg-indigo-600 px-3 py-1 text-sm font-medium text-white disabled:opacity-50" @click="emit('run')">
        {{ loading ? 'Running… (a few seconds)' : result ? 'Run again' : 'Run the sprint' }}
      </button>
    </div>
    <p v-if="error" role="alert" class="text-sm text-red-700 dark:text-red-300">{{ error }}</p>
    <p v-if="!result && !loading && !error" class="py-4 text-center text-sm text-gray-400 dark:text-gray-500">Not run yet. It solves about a hundred goal-seeks, so it runs on request.</p>

    <template v-if="result">
      <p class="text-sm text-gray-700 dark:text-gray-200">
        At {{ money(result.plan_spending) }} a year you could retire at
        <strong>{{ result.earliest_at_plan_spending ?? 'no age up to 70' }}</strong> with your return assumptions
        ({{ percent(result.target, 0) }} chance of success).
      </p>
      <div>
        <h4 class="text-xs font-semibold uppercase tracking-wide text-gray-400 mb-1">To retire at this age, spend at most</h4>
        <DataTable dense :columns="result.shifts.length + 1">
          <thead><tr><th>Retire at</th><th v-for="(l, i) in result.return_labels" :key="i" class="text-right">{{ l }}<span v-if="result.shifts[i] === 0"> (plan)</span></th></tr></thead>
          <tbody>
            <tr v-for="row in result.grid" :key="row.age">
              <td>{{ row.age }}</td>
              <td v-for="(v, i) in row.max_spending" :key="i" class="text-right tabular-nums"
                :class="v != null && v >= result.plan_spending ? 'text-green-700 dark:text-green-400 font-medium' : ''">{{ v == null ? 'not reachable' : money(v) }}</td>
            </tr>
          </tbody>
        </DataTable>
        <p class="mt-1 text-[11px] text-gray-400">Columns: return while working / in retirement. Green: at or above the plan's spending.</p>
      </div>
      <div>
        <h4 class="text-xs font-semibold uppercase tracking-wide text-gray-400 mb-1">At this spending, retire at</h4>
        <DataTable dense :columns="result.shifts.length + 1">
          <thead><tr><th>Spending a year</th><th v-for="(l, i) in result.return_labels" :key="i" class="text-right">{{ l }}</th></tr></thead>
          <tbody>
            <tr v-for="row in result.by_spending" :key="row.spending">
              <td class="tabular-nums">{{ money(row.spending) }}</td>
              <td v-for="(a, i) in row.earliest_age" :key="i" class="text-right tabular-nums">{{ a ?? `after ${result.grid[result.grid.length - 1]?.age}` }}</td>
            </tr>
          </tbody>
        </DataTable>
      </div>
      <ChartContainer title="What moves the sprint most" :empty="!result.levers.length"
        :info="`Chance of success under the sprint (${percent(result.base_success, 0)}) when one thing changes. Job levers apply to ${result.job_change.synthetic ? `a job change at ${result.job_change.age} (6 months out, same pay, equity) that the plan does not otherwise have` : `the plan's layoff at ${result.job_change.age}`}.`">
        <LeverTornado :rows="tornadoFromSprint(result.levers)" :base="result.base_success" />
      </ChartContainer>
    </template>
  </section>
</template>
