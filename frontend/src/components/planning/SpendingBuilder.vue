<script setup lang="ts">
/**
 * SpendingBuilder — "What will retirement cost?": living spending built up from the last 12 months
 * of actual spending, with its uncertainty, what stops or continues at retirement, health cover, and
 * population reference points. "Use" sets the retirement-spending lever (a what-if until saved).
 */
import InfoTooltip from '../common/InfoTooltip.vue'
import { useFormatters } from '../../composables/useFormatters'
import type { SpendingBuilder } from '../../types'

const props = defineProps<{ builder: SpendingBuilder; current: number }>()
const emit = defineEmits<{ (e: 'use', value: number): void }>()
const { money, percent, date } = useFormatters()

const info = `<strong>Built from your transactions.</strong> The last 12 months of spending as every page counts it (no transfers, card or loan payments). One-off spikes are single purchases of at least $2,500 and 10× your median purchase in a category you do not buy from most months; they come out of the suggestion. Work costs (fuel, parking, tolls, transit) are cut by the share set in the assumptions. Health cover, the mortgage and property tax/insurance are not in living spending: the plan adds them year by year.`
</script>

<template>
  <section class="rounded-xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 p-5 min-w-0">
    <h3 class="text-sm font-semibold text-gray-900 dark:text-white">What will retirement cost? <InfoTooltip :text="info" /></h3>
    <p class="text-xs text-gray-500 dark:text-gray-400 mb-3">From {{ date(builder.window.from) }} to {{ date(builder.window.to) }} ({{ builder.window.months }} months with spending).</p>

    <p v-if="builder.trailing_total <= 0" class="py-6 text-center text-sm text-gray-400 dark:text-gray-500">
      No spending in the last 12 months yet. Connect accounts or import transactions; until then set retirement spending by hand.
    </p>

    <div v-else class="grid grid-cols-1 lg:grid-cols-3 gap-5 text-sm">
      <div class="min-w-0">
        <h4 class="text-xs font-semibold uppercase tracking-wide text-gray-400 mb-2">Living spending</h4>
        <dl class="space-y-1.5">
          <div class="flex justify-between gap-2"><dt class="text-gray-600 dark:text-gray-300">{{ (builder.covered_months ?? 12) < 12 ? `Last ${builder.covered_months} months (${money(builder.observed_total ?? 0)}), as a year` : 'Last 12 months' }}</dt><dd class="tabular-nums font-medium text-gray-900 dark:text-white">{{ money(builder.trailing_total) }}</dd></div>
          <div class="flex justify-between gap-2"><dt class="text-gray-600 dark:text-gray-300">One-off spikes</dt><dd class="tabular-nums text-gray-900 dark:text-white">−{{ money(builder.spike_total) }}</dd></div>
          <div class="flex justify-between gap-2"><dt class="text-gray-600 dark:text-gray-300">Work costs that stop ({{ percent(builder.work_reduction, 0) }} of {{ money(builder.work_costs) }})</dt><dd class="tabular-nums text-gray-900 dark:text-white">−{{ money(builder.work_costs * builder.work_reduction) }}</dd></div>
          <div class="flex justify-between gap-2 border-t border-gray-100 dark:border-gray-800 pt-1.5"><dt class="font-semibold text-gray-900 dark:text-white">Suggested a year</dt><dd class="tabular-nums font-semibold text-gray-900 dark:text-white">{{ money(builder.suggested) }}</dd></div>
        </dl>
        <p class="mt-2 text-xs text-gray-500 dark:text-gray-400">
          Range {{ money(builder.range.low) }}–{{ money(builder.range.high) }}: {{ money(builder.uncategorised) }} is uncategorised and median month is {{ money(builder.median_month) }}.
          <span v-if="(builder.covered_months ?? 12) < 12">Only {{ builder.covered_months }} months of history, scaled to a year; seasonal costs may be missed. Property tax and insurance paid from escrow are left out because the plan adds escrow as housing.</span>
        </p>
        <ul v-if="builder.spikes.length" class="mt-2 space-y-0.5 text-xs text-gray-500 dark:text-gray-400">
          <li v-for="s in builder.spikes.slice(0, 4)" :key="s.date + s.amount">{{ date(s.date) }} · {{ s.merchant || s.category || 'Purchase' }} · {{ money(s.amount) }}</li>
        </ul>
        <button type="button" :disabled="Math.abs(builder.suggested - current) < 1"
          class="mt-3 rounded-md bg-indigo-600 px-3 py-1 text-xs font-medium text-white disabled:opacity-50"
          @click="emit('use', builder.suggested)">
          {{ Math.abs(builder.suggested - current) < 1 ? 'In use as retirement spending' : `Use ${money(builder.suggested)} as retirement spending` }}
        </button>
      </div>

      <div class="min-w-0">
        <h4 class="text-xs font-semibold uppercase tracking-wide text-gray-400 mb-2">Added by the plan</h4>
        <ul class="space-y-1.5 text-gray-600 dark:text-gray-300">
          <li v-if="builder.excluded.mortgage_pi_monthly > 0">Mortgage principal and interest {{ money(builder.excluded.mortgage_pi_monthly) }}/mo, until it is paid off.</li>
          <li v-if="builder.excluded.escrow_monthly > 0">Property tax and insurance {{ money(builder.excluded.escrow_monthly) }}/mo, for good.</li>
          <li>Before 65, marketplace cover for {{ builder.health.people }}: {{ money(builder.health.pre65_at_cliff) }} a year at most while income stays under {{ money(builder.health.subsidy_cliff_magi) }} (capped at {{ percent(builder.health.pre65_capped_at, 2) }} of income); {{ money(builder.health.pre65_full) }} above it. The plan uses each year's withdrawals as income.</li>
          <li>From 65, Medicare premiums, Medigap and out-of-pocket: {{ money(builder.health.post65) }} a year.</li>
          <li class="text-xs text-gray-500 dark:text-gray-400">Long-term care is not included; add it as a life event (assisted living {{ money(builder.health.ltc_reference.assisted_living) }} a year, a private nursing-home room {{ money(builder.health.ltc_reference.nursing_home_private) }}, {{ builder.health.ltc_reference.year }} national medians).</li>
        </ul>
        <h4 class="text-xs font-semibold uppercase tracking-wide text-gray-400 mt-3 mb-1">Stops at retirement</h4>
        <p class="text-gray-600 dark:text-gray-300">Payroll taxes ({{ money(builder.excluded.payroll_tax) }} last year) and 401(k) saving ({{ money(builder.excluded.saving_401k) }}) are not spending, so they are already out.</p>
      </div>

      <div class="min-w-0">
        <h4 class="text-xs font-semibold uppercase tracking-wide text-gray-400 mb-2">Reference points <InfoTooltip text="Population figures for context, not targets for this household. Replacement ratio: the 70–80% of pre-retirement income rule of thumb. Spending: BLS Consumer Expenditure Survey average annual expenditures by age of the household reference person." /></h4>
        <dl class="space-y-1.5 text-gray-600 dark:text-gray-300">
          <div class="flex justify-between gap-2"><dt>70–80% of today's pay</dt><dd class="tabular-nums">{{ money(builder.references.replacement_low) }}–{{ money(builder.references.replacement_high) }}</dd></div>
          <div class="flex justify-between gap-2"><dt>US households 65–74 ({{ builder.references.bls.year }})</dt><dd class="tabular-nums">{{ money(builder.references.bls.age_65_74) }}</dd></div>
          <div class="flex justify-between gap-2"><dt>US households 65+ ({{ builder.references.bls.year }})</dt><dd class="tabular-nums">{{ money(builder.references.bls.age_65_plus) }}</dd></div>
          <div class="flex justify-between gap-2"><dt>US households 75+ (2023)</dt><dd class="tabular-nums">{{ money(builder.references.bls.age_75_plus_2023) }}</dd></div>
        </dl>
        <p class="mt-2 text-xs text-gray-500 dark:text-gray-400">The plan's retirement living spending is {{ money(props.current) }} a year.</p>
      </div>
    </div>
  </section>
</template>
