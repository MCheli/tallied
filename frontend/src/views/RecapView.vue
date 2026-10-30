<script setup lang="ts">
import { computed, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ChevronLeft, ChevronRight } from 'lucide-vue-next'
import { api } from '../api/client'
import { useFormatters } from '../composables/useFormatters'
import { useTile } from '../composables/useDashboardTiles'
import { addDays, recapHeadline, weekLabel } from '../composables/useRecap'
import PageHeader from '../components/common/PageHeader.vue'
import MetricCard from '../components/common/MetricCard.vue'
import ChartContainer from '../components/common/ChartContainer.vue'
import type { WeeklyRecap } from '../types'

const route = useRoute()
const router = useRouter()
const { compact, currency } = useFormatters()
const recap = useTile<WeeklyRecap>()

const week = computed(() => (typeof route.query.week === 'string' ? route.query.week : undefined))
watch(week, w => void recap.load(() => api.getWeeklyRecap(w)), { immediate: true })

const r = computed(() => recap.data.value)
const go = (w: string | null) => { if (w) void router.push({ name: 'recap', query: { week: w } }) }

const spendDelta = computed(() => {
  if (!r.value || r.value.prior_weekly_avg <= 0) return undefined
  return ((r.value.spending - r.value.prior_weekly_avg) / r.value.prior_weekly_avg) * 100
})
const nwDelta = computed(() => {
  const v = r.value
  if (!v || v.net_worth_change == null || !v.net_worth_start) return undefined
  return (v.net_worth_change / Math.abs(v.net_worth_start)) * 100
})
const maxCat = computed(() => Math.max(1, ...(r.value?.categories ?? []).flatMap(c => [c.total, c.prior_avg])))
const shortDay = (d: string) => new Date(`${d}T00:00:00`).toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' })

const SQL = `-- Spending in the week (same definition as everywhere: money out net of refunds,
-- transfers and loan/card payments excluded)
SELECT category, -SUM(amount) AS spent
FROM transactions
WHERE date BETWEEN :week_start AND :week_end
  AND ((amount < 0 AND (category IS NULL OR category NOT IN ('Transfer', 'Credit Card Payment', 'Loan Payment', 'Mortgage Payment')))
    OR (amount > 0 AND category IS NOT NULL AND lower(category) NOT IN ('paycheck', 'interest', 'tax refund', 'rewards')))
GROUP BY category
ORDER BY spent DESC`
</script>

<template>
  <div>
    <PageHeader
      title="Weekly Recap"
      :subtitle="r ? weekLabel(r.week_start, r.week_end) + (r.complete ? '' : ' (so far)') : undefined"
      tooltip="A summary of one Sunday–Saturday week, worked out from your data whenever you open it, so every past week has one. It opens on the last completed week.&lt;br&gt;&lt;br&gt;Spending uses the same definition as the Spending page; the comparison is the average of the four weeks before."
    />

    <div class="flex items-center gap-2 mb-6">
      <button type="button" class="inline-flex items-center gap-1 px-3 py-1.5 text-sm rounded-lg border border-gray-200 dark:border-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-800 disabled:opacity-40"
        :disabled="!r" @click="go(r?.previous_week ?? null)">
        <ChevronLeft class="w-4 h-4" /> Previous week
      </button>
      <button type="button" class="inline-flex items-center gap-1 px-3 py-1.5 text-sm rounded-lg border border-gray-200 dark:border-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-800 disabled:opacity-40"
        :disabled="!r?.next_week" @click="go(r?.next_week ?? null)">
        Next week <ChevronRight class="w-4 h-4" />
      </button>
    </div>

    <div v-if="recap.loading.value && !r" class="flex items-center justify-center h-64">
      <div class="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-500"></div>
    </div>
    <div v-else-if="recap.error.value" class="text-red-600 dark:text-red-400 text-sm">Could not load the recap: {{ recap.error.value }}</div>

    <div v-else-if="r" class="space-y-6">
      <p class="text-base text-gray-800 dark:text-gray-200 max-w-3xl leading-relaxed" data-testid="recap-headline">{{ recapHeadline(r) }}</p>

      <div class="grid grid-cols-2 xl:grid-cols-4 gap-3 sm:gap-4">
        <MetricCard
          label="Net Worth Change"
          :value="r.net_worth_change != null ? compact(r.net_worth_change) : '—'"
          :changeValue="nwDelta"
          :subtitle="r.net_worth_end != null ? `now ${compact(r.net_worth_end)}` : 'no balances yet'"
          info="Net worth at the end of Saturday minus net worth at the end of the Saturday before, each from every account's newest balance on or before that day (accounts included in net worth only). Market moves, paydowns and new vests all show here."
        />
        <MetricCard
          label="Spent"
          :value="compact(r.spending)"
          :subtitle="spendDelta == null ? 'no earlier weeks' : `${spendDelta >= 0 ? '+' : '−'}${Math.abs(Math.round(spendDelta))}% vs avg ${compact(r.prior_weekly_avg)}`"
          info="Net spending in the week: money out minus refunds, with transfers and loan or card payments left out. The average is the four weeks before this one."
          :sql="SQL"
          :sqlTables="['transactions']"
        />
        <MetricCard
          label="Income"
          :value="compact(r.income)"
          subtitle="paychecks, interest"
          info="Money in that counts as income: transactions categorised Paycheck, Interest, Dividends, Tax Refund, Rewards and similar. RSU vests arrive as shares and are not here."
        />
        <MetricCard
          label="Purchases"
          :value="String(r.transaction_count)"
          :subtitle="r.uncategorized ? `${r.uncategorized} uncategorised` : 'all categorised'"
          info="Number of spending transactions in the week. Uncategorised ones count as spending but cannot be grouped; set their category on the Spending page."
        />
      </div>

      <div class="grid grid-cols-1 lg:grid-cols-2 gap-4 items-start">
        <ChartContainer
          title="Where It Went"
          subtitle="This week against the 4-week average"
          :empty="r.categories.length === 0"
          empty-text="No spending this week"
          info="The six biggest categories this week. The bar is this week; the tick is the category's average week over the four weeks before."
        >
          <div class="space-y-3">
            <div v-for="c in r.categories" :key="c.category" class="text-sm">
              <div class="flex items-center justify-between gap-3 mb-1">
                <span class="text-gray-700 dark:text-gray-300 truncate">{{ c.category }}</span>
                <span class="whitespace-nowrap"><span class="font-medium text-gray-900 dark:text-white">{{ currency(c.total) }}</span>
                  <span class="text-xs text-gray-400 ml-1">avg {{ compact(c.prior_avg) }}</span></span>
              </div>
              <div class="relative h-2 rounded-full bg-gray-100 dark:bg-gray-800">
                <div class="absolute inset-y-0 left-0 rounded-full bg-indigo-500" :style="{ width: `${(c.total / maxCat) * 100}%` }" />
                <div v-if="c.prior_avg > 0" class="absolute -top-0.5 -bottom-0.5 w-0.5 bg-gray-500 dark:bg-gray-300" :style="{ left: `${(c.prior_avg / maxCat) * 100}%` }" />
              </div>
            </div>
          </div>
        </ChartContainer>

        <ChartContainer
          title="Largest Purchases"
          :empty="r.largest.length === 0"
          empty-text="No purchases this week"
          info="The five largest spending transactions in the week (transfers and card or loan payments are never here)."
        >
          <div class="divide-y divide-gray-100 dark:divide-gray-800">
            <div v-for="t in r.largest" :key="`${t.date}-${t.merchant}-${t.amount}`" class="flex items-center justify-between gap-3 py-2 text-sm">
              <div class="min-w-0">
                <div class="text-gray-900 dark:text-white truncate">{{ t.merchant }}</div>
                <div class="text-xs text-gray-400">{{ shortDay(t.date) }} · {{ t.category }}</div>
              </div>
              <span class="font-medium text-gray-900 dark:text-white whitespace-nowrap">{{ currency(t.amount) }}</span>
            </div>
          </div>
        </ChartContainer>
      </div>

      <ChartContainer
        title="Coming Up"
        :subtitle="`Week of ${shortDay(addDays(r.week_end, 1))}`"
        :empty="r.upcoming_bills.length === 0 && r.upcoming_vests.length === 0"
        empty-text="No bills or vests expected the following week"
        info="Bills expected in the following Sunday–Saturday week: merchants charged about monthly at a steady amount (the Recurring Expenses rule), due on the same day of the month as their last charge. RSU vests scheduled that week, at the latest share price."
      >
        <div class="space-y-2">
          <div v-for="b in r.upcoming_bills" :key="`bill-${b.merchant}`" class="flex items-center justify-between gap-3 text-sm py-2 px-3 bg-gray-50 dark:bg-gray-800 rounded-lg">
            <div class="min-w-0"><span class="text-gray-900 dark:text-white">{{ b.merchant }}</span>
              <span class="text-xs text-gray-400 ml-2 whitespace-nowrap">{{ shortDay(b.date) }} · {{ b.category }}</span></div>
            <span class="whitespace-nowrap text-gray-700 dark:text-gray-300">~{{ currency(b.amount) }}</span>
          </div>
          <div v-for="v in r.upcoming_vests" :key="`vest-${v.date}`" class="flex items-center justify-between gap-3 text-sm py-2 px-3 bg-emerald-50 dark:bg-emerald-900/20 rounded-lg">
            <div class="min-w-0"><span class="text-gray-900 dark:text-white">RSU vest, {{ v.shares }} shares</span>
              <span class="text-xs text-gray-400 ml-2 whitespace-nowrap">{{ shortDay(v.date) }}</span></div>
            <span class="whitespace-nowrap text-emerald-700 dark:text-emerald-400">~{{ compact(v.est_value) }}</span>
          </div>
        </div>
      </ChartContainer>
    </div>
  </div>
</template>
