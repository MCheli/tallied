<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useSnapshotStore } from '../stores/snapshot'
import { useFormatters } from '../composables/useFormatters'
import MetricCard from '../components/common/MetricCard.vue'
import ChartContainer from '../components/common/ChartContainer.vue'
import InfoTooltip from '../components/common/InfoTooltip.vue'
import NetWorthChart from '../components/assets/NetWorthChart.vue'
import LiquidityWaterfall from '../components/dashboard/LiquidityWaterfall.vue'
import CompDonut from '../components/dashboard/CompDonut.vue'
import LayerCard from '../components/dashboard/LayerCard.vue'

const store = useSnapshotStore()
const { compact } = useFormatters()

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000'
const rsuSummary = ref<any>(null)
const plaidLinks = ref<any[]>([])
const recentSpending = ref<any>(null)
const propertySummary = ref<any>(null)
const assetsSummary = ref<any>(null)
const netWorthTrend = ref<any>(null)

onMounted(async () => {
  store.fetchSnapshot()
  store.fetchIncome()

  // Fetch RSU summary, Plaid links, and recent spending in parallel
  try {
    const [rsuRes, plaidRes, spendRes, propRes, assetsRes, nwTrendRes] = await Promise.all([
      fetch(`${API}/api/rsu/summary`).then(r => r.json()),
      fetch(`${API}/api/plaid/links`).then(r => r.json()),
      fetch(`${API}/api/spending/by-category?start_date=${thirtyDaysAgo()}&end_date=${today()}`).then(r => r.json()),
      fetch(`${API}/api/property/summary`).then(r => r.json()),
      fetch(`${API}/api/assets/summary`).then(r => r.json()),
      fetch(`${API}/api/trends/net-worth`).then(r => r.json()),
    ])
    rsuSummary.value = rsuRes
    plaidLinks.value = plaidRes
    propertySummary.value = propRes
    assetsSummary.value = assetsRes
    netWorthTrend.value = nwTrendRes
    // API returns a list of categories; wrap it
    const cats = Array.isArray(spendRes) ? spendRes : []
    recentSpending.value = {
      categories: cats,
      total: cats.reduce((sum: number, c: any) => sum + c.total, 0),
    }
  } catch { /* non-critical */ }
})

function today() {
  return new Date().toISOString().slice(0, 10)
}
function thirtyDaysAgo() {
  const d = new Date()
  d.setDate(d.getDate() - 30)
  return d.toISOString().slice(0, 10)
}

const nwChange = computed(() => {
  if (!store.data?.net_worth || !store.data?.net_worth_12mo_change) return undefined
  const prev = store.data.net_worth - store.data.net_worth_12mo_change
  if (prev === 0) return 0
  return (store.data.net_worth_12mo_change / prev) * 100
})
</script>

<template>
  <div>
    <h2 class="text-lg font-bold text-gray-900 dark:text-white mb-6">Dashboard</h2>

    <!-- Loading state -->
    <div v-if="store.loading" class="flex items-center justify-center h-64">
      <div class="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-500"></div>
    </div>

    <div v-else-if="store.data">
      <!-- Top Metrics -->
      <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4 mb-6">
        <MetricCard
          label="Net Worth"
          :value="compact(store.data.net_worth)"
          info="Sum of all account balances where include_in_nw is true. Includes cash, investments, home equity (property value minus mortgage), and retirement accounts minus liabilities.&lt;br&gt;&lt;br&gt;&lt;strong&gt;Source:&lt;/strong&gt; Most recent balance snapshot per account."
        />
        <MetricCard
          label="Liquid Net Worth"
          :value="compact(store.data.liquid_net_worth)"
          info="Net worth excluding home equity and retirement — money you can access relatively quickly. Calculated as: cash + investments + credit cards + other loans.&lt;br&gt;&lt;br&gt;&lt;strong&gt;Source:&lt;/strong&gt; Most recent balance snapshot per account, filtered by display group."
        />
        <MetricCard
          label="RSU Holdings"
          :value="rsuSummary ? compact(rsuSummary.held_value) : '\u2014'"
          :subtitle="rsuSummary ? `${rsuSummary.sellable_shares} sellable + ${rsuSummary.unvested_shares} unvested` : ''"
          info="Total value of PTC RSU shares you still own (sellable + unvested). Valued at the current market price fetched daily from Yahoo Finance.&lt;br&gt;&lt;br&gt;&lt;strong&gt;Source:&lt;/strong&gt; RSU grants table (share counts) × live PTC stock price."
        />
        <MetricCard
          label="Total Comp"
          :value="store.data.total_comp_annual ? compact(store.data.total_comp_annual) : '\u2014'"
          subtitle="annual (W2)"
          info="Annual total compensation from your most recent W2 record. Includes base salary + RSU vesting income + any other compensation.&lt;br&gt;&lt;br&gt;&lt;strong&gt;Source:&lt;/strong&gt; W2 records table, most recent tax year."
        />
        <MetricCard
          label="12mo Change"
          :value="store.data.net_worth_12mo_change != null ? compact(store.data.net_worth_12mo_change) : '\u2014'"
          :changeValue="nwChange"
          subtitle="vs. prior year"
          info="Net worth change over the past 12 months. Calculated by comparing current net worth to the net worth 12 months ago based on historical balance snapshots.&lt;br&gt;&lt;br&gt;&lt;strong&gt;Source:&lt;/strong&gt; Balance snapshot history, comparing latest vs 12 months prior."
        />
      </div>

      <!-- Property & Vehicles -->
      <div class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-4 mb-6" v-if="propertySummary || assetsSummary">
        <MetricCard
          v-if="propertySummary"
          label="Property Equity"
          :value="compact(propertySummary.equity)"
          subtitle="home equity"
          info="Estimated home equity based on current property value minus outstanding mortgage balance.&lt;br&gt;&lt;br&gt;&lt;strong&gt;Source:&lt;/strong&gt; /api/property/summary"
        />
        <MetricCard
          v-if="assetsSummary"
          label="Vehicles"
          :value="compact(assetsSummary.total_value)"
          subtitle="estimated value"
          info="Total estimated value of tracked vehicles.&lt;br&gt;&lt;br&gt;&lt;strong&gt;Source:&lt;/strong&gt; /api/assets/summary"
        />
      </div>

      <!-- Charts Row -->
      <div class="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-6">
        <div class="lg:col-span-2">
          <ChartContainer title="Liquidity Layers" subtitle="Asset breakdown by liquidity" info="Asset breakdown ordered by how quickly you can access the money. Each bar shows the total balance for that liquidity tier. The final bar is the sum (net worth).&lt;br&gt;&lt;br&gt;&lt;strong&gt;Layers:&lt;/strong&gt; Cash → Investments → Home Equity → Retirement → Credit Cards → Other Loans&lt;br&gt;&lt;strong&gt;Source:&lt;/strong&gt; Accounts grouped by display_group, latest balance per account.">
            <LiquidityWaterfall :layers="store.data.layers" />
          </ChartContainer>
        </div>
        <div>
          <ChartContainer
            title="Compensation Split"
            subtitle="Salary vs. RSU"
            :loading="!store.income"
            info="Donut chart showing the proportion of your annual compensation that comes from base salary vs RSU vesting income. The center number is total comp.&lt;br&gt;&lt;br&gt;&lt;strong&gt;Source:&lt;/strong&gt; Most recent W2 record (base_salary and rsu_income fields)."
          >
            <CompDonut
              v-if="store.income"
              :salary="store.income.salary"
              :rsu="store.income.rsu_income"
            />
            <p v-else class="text-sm text-gray-500 dark:text-gray-400 text-center py-12">
              Income data not available
            </p>
          </ChartContainer>
        </div>
      </div>

      <!-- Net Worth Trend -->
      <div v-if="netWorthTrend" class="mb-6">
        <div class="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-5">
          <div class="flex items-center gap-1 mb-1">
            <h3 class="text-sm font-semibold text-gray-900 dark:text-white">Net Worth Over Time</h3>
            <InfoTooltip text="Historical net worth broken down by asset group (Cash, Investments, Home Equity, Retirement). Each area is stacked to show total net worth and its composition over time.&lt;br&gt;&lt;br&gt;&lt;strong&gt;Source:&lt;/strong&gt; Monthly balance snapshots grouped by display_group." />
          </div>
          <p class="text-xs text-gray-400 dark:text-gray-500 mb-3">Stacked by asset group</p>
          <NetWorthChart :data="netWorthTrend" />
        </div>
      </div>

      <!-- Quick Info Row -->
      <div class="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-6" v-if="rsuSummary?.upcoming_vests?.length || recentSpending?.categories?.length">
        <!-- Upcoming Vests -->
        <div v-if="rsuSummary?.upcoming_vests?.length" class="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-5">
          <h3 class="text-sm font-semibold text-gray-900 dark:text-white mb-3">Next Vests <InfoTooltip text="Your next 4 upcoming RSU vest events. Estimated value uses the current PTC stock price. Actual value at vest will depend on the stock price on the vest date.&lt;br&gt;&lt;br&gt;&lt;strong&gt;Source:&lt;/strong&gt; Vest events table (future events), current PTC price from Yahoo Finance." /></h3>
          <div class="space-y-2">
            <div v-for="v in rsuSummary.upcoming_vests.slice(0, 4)" :key="`${v.grant_id}-${v.vest_date}`"
              class="flex items-center justify-between text-sm py-1.5 px-3 bg-gray-50 dark:bg-gray-800 rounded-lg">
              <div>
                <span class="text-gray-700 dark:text-gray-300 font-medium">{{ new Date(v.vest_date + 'T00:00:00').toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) }}</span>
                <span class="text-gray-400 text-xs ml-2">{{ v.shares }} shares</span>
              </div>
              <span class="text-xs text-gray-500 dark:text-gray-400">~{{ compact(v.est_value) }}</span>
            </div>
          </div>
        </div>

        <!-- Top Spending (30 days) -->
        <div v-if="recentSpending?.categories?.length" class="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-5">
          <h3 class="text-sm font-semibold text-gray-900 dark:text-white mb-3">Last 30 Days Spending <InfoTooltip text="Top 5 spending categories by total amount in the last 30 days. Only includes expenses (negative transactions), not income or transfers.&lt;br&gt;&lt;br&gt;&lt;strong&gt;Source:&lt;/strong&gt; Transactions table filtered to last 30 days, grouped by category. Includes both Plaid and Monarch transaction sources." /></h3>
          <div class="space-y-2">
            <div v-for="cat in recentSpending.categories.slice(0, 5)" :key="cat.category"
              class="flex items-center justify-between text-sm">
              <span class="text-gray-700 dark:text-gray-300">{{ cat.category }}</span>
              <span class="font-medium text-gray-900 dark:text-white">{{ compact(Math.abs(cat.total)) }}</span>
            </div>
            <div class="flex items-center justify-between text-sm pt-2 border-t border-gray-100 dark:border-gray-800">
              <span class="font-medium text-gray-500 dark:text-gray-400">Total</span>
              <span class="font-bold text-gray-900 dark:text-white">{{ compact(Math.abs(recentSpending.total || 0)) }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- Plaid Status -->
      <div v-if="plaidLinks.length > 0" class="mb-6 text-xs text-gray-400 dark:text-gray-500">
        {{ plaidLinks.length }} Plaid account{{ plaidLinks.length > 1 ? 's' : '' }} connected
        ({{ plaidLinks.map((l: any) => l.institution_name).join(', ') }})
      </div>

      <!-- Layer Cards -->
      <div class="space-y-3">
        <h3 class="text-sm font-semibold text-gray-900 dark:text-white">Account Details</h3>
        <LayerCard v-for="layer in store.data.layers" :key="layer.name" :layer="layer" />
      </div>
    </div>

    <!-- Error state -->
    <div v-else-if="store.error" class="text-red-600 dark:text-red-400 text-sm">
      {{ store.error }}
    </div>
  </div>
</template>
