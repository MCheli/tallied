<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import SqlViewerModal from '../components/common/SqlViewerModal.vue'
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
      fetch(`${API}/api/v1/rsu/summary`, { credentials: 'include' }).then(r => r.json()),
      fetch(`${API}/api/v1/plaid/links`, { credentials: 'include' }).then(r => r.json()),
      fetch(`${API}/api/v1/spending/by-category?start_date=${thirtyDaysAgo()}&end_date=${today()}`, { credentials: 'include' }).then(r => r.json()),
      fetch(`${API}/api/v1/property/summary`, { credentials: 'include' }).then(r => r.json()),
      fetch(`${API}/api/v1/assets/summary`, { credentials: 'include' }).then(r => r.json()),
      fetch(`${API}/api/v1/trends/net-worth`, { credentials: 'include' }).then(r => r.json()),
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

const showNwTrendSql = ref(false)
const showVestsSql = ref(false)
const showSpendingSql = ref(false)

// ── SQL Transparency ─────────────────────────────────────────────────────────
const SQL = {
  netWorth: `SELECT SUM(bs.balance) AS net_worth
FROM balance_snapshots bs
JOIN accounts a ON bs.account_id = a.id
WHERE a.is_active = 1
  AND a.include_in_nw = 1
  AND bs.snapshot_date = (
    SELECT MAX(snapshot_date)
    FROM balance_snapshots
    WHERE account_id = bs.account_id
  )`,

  liquidNetWorth: `SELECT SUM(bs.balance) AS liquid_net_worth
FROM balance_snapshots bs
JOIN accounts a ON bs.account_id = a.id
WHERE a.is_active = 1
  AND a.include_in_nw = 1
  AND a.display_group IN ('Cash', 'Investments', 'Credit Cards', 'Other Loans')
  AND bs.snapshot_date = (
    SELECT MAX(snapshot_date)
    FROM balance_snapshots
    WHERE account_id = bs.account_id
  )`,

  rsuHoldings: `SELECT
  SUM(rg.sellable_shares + rg.unvested_shares) AS total_shares,
  sp.close_price AS current_price,
  SUM(rg.sellable_shares + rg.unvested_shares) * sp.close_price AS held_value
FROM rsu_grants rg
JOIN stock_prices sp ON sp.symbol = rg.symbol
  AND sp.price_date = (
    SELECT MAX(price_date) FROM stock_prices WHERE symbol = rg.symbol
  )
GROUP BY sp.close_price`,

  totalComp: `SELECT
  tax_year,
  gross_pay AS total_comp,
  base_salary,
  rsu_income
FROM w2_records
ORDER BY tax_year DESC
LIMIT 1`,

  nwChange: `-- Current net worth vs 12 months ago
WITH current_nw AS (
  SELECT SUM(bs.balance) AS nw
  FROM balance_snapshots bs
  JOIN accounts a ON bs.account_id = a.id
  WHERE a.is_active = 1 AND a.include_in_nw = 1
    AND bs.snapshot_date = (
      SELECT MAX(snapshot_date) FROM balance_snapshots WHERE account_id = bs.account_id
    )
),
prior_nw AS (
  SELECT SUM(bs.balance) AS nw
  FROM balance_snapshots bs
  JOIN accounts a ON bs.account_id = a.id
  WHERE a.is_active = 1 AND a.include_in_nw = 1
    AND bs.snapshot_date BETWEEN date('now', '-372 days') AND date('now', '-358 days')
)
SELECT current_nw.nw - prior_nw.nw AS change_12mo
FROM current_nw, prior_nw`,

  propertyEquity: `SELECT
  pv.value AS property_value,
  m.current_balance AS mortgage_balance,
  pv.value - m.current_balance AS equity
FROM property_valuations pv
JOIN accounts a ON pv.account_id = a.id AND a.account_type = 'real_estate'
LEFT JOIN mortgages m ON m.account_id IS NOT NULL
WHERE pv.valuation_date = (
  SELECT MAX(valuation_date) FROM property_valuations WHERE account_id = pv.account_id
)
ORDER BY pv.valuation_date DESC
LIMIT 1`,

  vehicles: `SELECT
  year, make, model,
  estimated_value,
  purchase_price,
  purchase_price - estimated_value AS depreciation
FROM vehicles`,

  liquidityLayers: `SELECT
  a.display_group,
  SUM(bs.balance) AS total
FROM balance_snapshots bs
JOIN accounts a ON bs.account_id = a.id
WHERE a.is_active = 1
  AND bs.snapshot_date = (
    SELECT MAX(snapshot_date) FROM balance_snapshots WHERE account_id = bs.account_id
  )
GROUP BY a.display_group
ORDER BY
  CASE a.display_group
    WHEN 'Cash' THEN 1
    WHEN 'Investments' THEN 2
    WHEN 'Home Equity' THEN 3
    WHEN 'Retirement' THEN 4
    WHEN 'Credit Cards' THEN 5
    WHEN 'Other Loans' THEN 6
  END`,

  compSplit: `SELECT
  base_salary,
  rsu_income,
  base_salary + rsu_income AS total_comp
FROM w2_records
ORDER BY tax_year DESC
LIMIT 1`,

  netWorthTrend: `SELECT
  bs.snapshot_date,
  a.display_group,
  SUM(bs.balance) AS total
FROM balance_snapshots bs
JOIN accounts a ON bs.account_id = a.id
WHERE a.include_in_nw = 1 AND a.is_active = 1
GROUP BY bs.snapshot_date, a.display_group
ORDER BY bs.snapshot_date`,

  upcomingVests: `SELECT
  ve.vest_date,
  ve.shares,
  rg.symbol,
  ve.shares * sp.close_price AS est_value
FROM vest_events ve
JOIN rsu_grants rg ON ve.grant_id = rg.id
JOIN stock_prices sp ON sp.symbol = rg.symbol
  AND sp.price_date = (SELECT MAX(price_date) FROM stock_prices WHERE symbol = rg.symbol)
WHERE ve.is_actual = 0
ORDER BY ve.vest_date
LIMIT 4`,

  spending30d: `SELECT
  category,
  SUM(amount) AS total,
  COUNT(*) AS count
FROM transactions
WHERE amount < 0
  AND date >= date('now', '-30 days')
GROUP BY category
ORDER BY SUM(amount)`,
}
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
          :sql="SQL.netWorth"
          :sqlTables="['accounts', 'balance_snapshots']"
        />
        <MetricCard
          label="Liquid Net Worth"
          :value="compact(store.data.liquid_net_worth)"
          info="Net worth excluding home equity and retirement — money you can access relatively quickly. Calculated as: cash + investments + credit cards + other loans.&lt;br&gt;&lt;br&gt;&lt;strong&gt;Source:&lt;/strong&gt; Most recent balance snapshot per account, filtered by display group."
          :sql="SQL.liquidNetWorth"
          :sqlTables="['accounts', 'balance_snapshots']"
        />
        <MetricCard
          label="RSU Holdings"
          :value="rsuSummary ? compact(rsuSummary.held_value) : '\u2014'"
          :subtitle="rsuSummary ? `${rsuSummary.sellable_shares} sellable + ${rsuSummary.unvested_shares} unvested` : ''"
          info="Total value of PTC RSU shares you still own (sellable + unvested). Valued at the current market price fetched daily from Yahoo Finance.&lt;br&gt;&lt;br&gt;&lt;strong&gt;Source:&lt;/strong&gt; RSU grants table (share counts) × live PTC stock price."
          :sql="SQL.rsuHoldings"
          :sqlTables="['rsu_grants', 'stock_prices']"
        />
        <MetricCard
          label="Total Comp"
          :value="store.data.total_comp_annual ? compact(store.data.total_comp_annual) : '\u2014'"
          subtitle="annual (W2)"
          info="Annual total compensation from your most recent W2 record. Includes base salary + RSU vesting income + any other compensation.&lt;br&gt;&lt;br&gt;&lt;strong&gt;Source:&lt;/strong&gt; W2 records table, most recent tax year."
          :sql="SQL.totalComp"
          :sqlTables="['w2_records']"
        />
        <MetricCard
          label="12mo Change"
          :value="store.data.net_worth_12mo_change != null ? compact(store.data.net_worth_12mo_change) : '\u2014'"
          :changeValue="nwChange"
          subtitle="vs. prior year"
          info="Net worth change over the past 12 months. Calculated by comparing current net worth to the net worth 12 months ago based on historical balance snapshots.&lt;br&gt;&lt;br&gt;&lt;strong&gt;Source:&lt;/strong&gt; Balance snapshot history, comparing latest vs 12 months prior."
          :sql="SQL.nwChange"
          :sqlTables="['accounts', 'balance_snapshots']"
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
          :sql="SQL.propertyEquity"
          :sqlTables="['property_valuations', 'mortgages', 'accounts']"
        />
        <MetricCard
          v-if="assetsSummary"
          label="Vehicles"
          :value="compact(assetsSummary.total_value)"
          subtitle="estimated value"
          info="Total estimated value of tracked vehicles.&lt;br&gt;&lt;br&gt;&lt;strong&gt;Source:&lt;/strong&gt; /api/assets/summary"
          :sql="SQL.vehicles"
          :sqlTables="['vehicles']"
        />
      </div>

      <!-- Charts Row -->
      <div class="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-6">
        <div class="lg:col-span-2">
          <ChartContainer title="Liquidity Layers" subtitle="Asset breakdown by liquidity" info="Asset breakdown ordered by how quickly you can access the money. Each bar shows the total balance for that liquidity tier. The final bar is the sum (net worth).&lt;br&gt;&lt;br&gt;&lt;strong&gt;Layers:&lt;/strong&gt; Cash → Investments → Home Equity → Retirement → Credit Cards → Other Loans&lt;br&gt;&lt;strong&gt;Source:&lt;/strong&gt; Accounts grouped by display_group, latest balance per account." :sql="SQL.liquidityLayers" :sqlTables="['accounts', 'balance_snapshots']">
            <LiquidityWaterfall :layers="store.data.layers" />
          </ChartContainer>
        </div>
        <div>
          <ChartContainer
            title="Compensation Split"
            subtitle="Salary vs. RSU"
            :loading="!store.income"
            info="Donut chart showing the proportion of your annual compensation that comes from base salary vs RSU vesting income. The center number is total comp.&lt;br&gt;&lt;br&gt;&lt;strong&gt;Source:&lt;/strong&gt; Most recent W2 record (base_salary and rsu_income fields)."
            :sql="SQL.compSplit"
            :sqlTables="['w2_records']"
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
        <div class="group/nw relative bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-5">
          <div class="flex items-center gap-1 mb-1">
            <h3 class="text-sm font-semibold text-gray-900 dark:text-white">Net Worth Over Time</h3>
            <InfoTooltip text="Historical net worth broken down by asset group (Cash, Investments, Home Equity, Retirement). Each area is stacked to show total net worth and its composition over time.&lt;br&gt;&lt;br&gt;&lt;strong&gt;Source:&lt;/strong&gt; Monthly balance snapshots grouped by display_group." />
          </div>
          <button
            @click="showNwTrendSql = true"
            class="absolute top-3.5 right-3.5 p-1 rounded-md text-gray-300 dark:text-gray-600 opacity-0 group-hover/nw:opacity-100 hover:!text-indigo-500 hover:bg-indigo-50 dark:hover:bg-indigo-950/40 transition-all"
            title="View SQL"
          >
            <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/>
            </svg>
          </button>
          <SqlViewerModal :open="showNwTrendSql" :sql="SQL.netWorthTrend" title="Net Worth Over Time" :tables="['balance_snapshots', 'accounts']" @close="showNwTrendSql = false" />
          <p class="text-xs text-gray-400 dark:text-gray-500 mb-3">Stacked by asset group</p>
          <NetWorthChart :data="netWorthTrend" />
        </div>
      </div>

      <!-- Quick Info Row -->
      <div class="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-6" v-if="rsuSummary?.upcoming_vests?.length || recentSpending?.categories?.length">
        <!-- Upcoming Vests -->
        <div v-if="rsuSummary?.upcoming_vests?.length" class="group/vests relative bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-5">
          <h3 class="text-sm font-semibold text-gray-900 dark:text-white mb-3">Next Vests <InfoTooltip text="Your next 4 upcoming RSU vest events. Estimated value uses the current PTC stock price. Actual value at vest will depend on the stock price on the vest date.&lt;br&gt;&lt;br&gt;&lt;strong&gt;Source:&lt;/strong&gt; Vest events table (future events), current PTC price from Yahoo Finance." /></h3>
          <button
            @click="showVestsSql = true"
            class="absolute top-3.5 right-3.5 p-1 rounded-md text-gray-300 dark:text-gray-600 opacity-0 group-hover/vests:opacity-100 hover:!text-indigo-500 hover:bg-indigo-50 dark:hover:bg-indigo-950/40 transition-all"
            title="View SQL"
          >
            <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/>
            </svg>
          </button>
          <SqlViewerModal :open="showVestsSql" :sql="SQL.upcomingVests" title="Upcoming Vests" :tables="['vest_events', 'rsu_grants', 'stock_prices']" @close="showVestsSql = false" />
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
        <div v-if="recentSpending?.categories?.length" class="group/spend relative bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-5">
          <h3 class="text-sm font-semibold text-gray-900 dark:text-white mb-3">Last 30 Days Spending <InfoTooltip text="Top 5 spending categories by total amount in the last 30 days. Only includes expenses (negative transactions), not income or transfers.&lt;br&gt;&lt;br&gt;&lt;strong&gt;Source:&lt;/strong&gt; Transactions table filtered to last 30 days, grouped by category. Includes both Plaid and Monarch transaction sources." /></h3>
          <button
            @click="showSpendingSql = true"
            class="absolute top-3.5 right-3.5 p-1 rounded-md text-gray-300 dark:text-gray-600 opacity-0 group-hover/spend:opacity-100 hover:!text-indigo-500 hover:bg-indigo-50 dark:hover:bg-indigo-950/40 transition-all"
            title="View SQL"
          >
            <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/>
            </svg>
          </button>
          <SqlViewerModal :open="showSpendingSql" :sql="SQL.spending30d" title="Last 30 Days Spending" :tables="['transactions']" @close="showSpendingSql = false" />
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
