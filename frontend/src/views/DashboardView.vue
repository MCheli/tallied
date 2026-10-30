<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { api } from '../api/client'
import { useSnapshotStore } from '../stores/snapshot'
import { useFormatters } from '../composables/useFormatters'
import { pctChange, thirtyDayWindow, useTile, waterfallNetWorth } from '../composables/useDashboardTiles'
import PageHeader from '../components/common/PageHeader.vue'
import SyncWarnings from '../components/common/SyncWarnings.vue'
import MetricCard from '../components/common/MetricCard.vue'
import ChartContainer from '../components/common/ChartContainer.vue'
import InfoTooltip from '../components/common/InfoTooltip.vue'
import NetWorthChart from '../components/assets/NetWorthChart.vue'
import LiquidityWaterfall from '../components/dashboard/LiquidityWaterfall.vue'
import CompDonut from '../components/dashboard/CompDonut.vue'
import LayerCard from '../components/dashboard/LayerCard.vue'
import type { AssetsSummary, CategorySummary, NetWorthSeries, PropertySummary, RSUSummary } from '../types'

const store = useSnapshotStore()
const { compact, date, dash } = useFormatters()

// Every tile loads on its own: one failing request shows one error, not a blank page (LOOK-005).
const rsu = useTile<RSUSummary>()
const spending = useTile<CategorySummary[]>()
const property = useTile<PropertySummary>()
const assets = useTile<AssetsSummary>()
const trend = useTile<NetWorthSeries>()

const window30 = thirtyDayWindow()

onMounted(() => {
  store.fetchSnapshot()
  store.fetchIncome()
  void Promise.allSettled([
    rsu.load(() => api.getRsuSummary()),
    spending.load(() => api.getSpendingByCategory(window30.from, window30.to)),
    property.load(() => api.getPropertySummary()),
    assets.load(() => api.getAssetsSummary()),
    trend.load(() => api.getNetWorth()),
  ])
})

const nwChange = computed(() => pctChange(store.data?.net_worth, store.data?.net_worth_12mo_change))
const asOf = computed(() => (store.data?.as_of ? `as of ${date(store.data.as_of)}` : ''))
const waterfallTotal = computed(() => (store.data ? waterfallNetWorth(store.data.layers) : 0))

const spendingTotal = computed(() => (spending.data.value ?? []).reduce((s, c) => s + c.total, 0))
const topSpending = computed(() => (spending.data.value ?? []).slice(0, 5))
const upcomingVests = computed(() => rsu.data.value?.upcoming_vests?.slice(0, 4) ?? [])
const symbol = computed(() => rsu.data.value?.symbol ?? 'the grants’ symbol')

// ── SQL transparency (Postgres; describes what the API runs) ─────────────────
const LATEST_SNAPSHOT = `bs.snapshot_date = (
    SELECT MAX(snapshot_date) FROM balance_snapshots WHERE account_id = bs.account_id
  )`

const SQL = {
  netWorth: `SELECT SUM(bs.balance) AS net_worth
FROM balance_snapshots bs
JOIN accounts a ON bs.account_id = a.id
WHERE a.is_active AND a.include_in_nw
  AND ${LATEST_SNAPSHOT}`,

  liquidNetWorth: `SELECT SUM(bs.balance) AS liquid_net_worth
FROM balance_snapshots bs
JOIN accounts a ON bs.account_id = a.id
WHERE a.is_active AND a.include_in_nw
  AND lower(replace(a.display_group, ' ', '_')) IN ('cash', 'investments', 'company_stock')
  AND ${LATEST_SNAPSHOT}`,

  rsuHoldings: `SELECT
  SUM(rg.sellable_shares + rg.unvested_shares) AS held_shares,
  sp.close_price AS current_price,
  SUM(rg.sellable_shares + rg.unvested_shares) * sp.close_price AS held_value
FROM rsu_grants rg
JOIN stock_prices sp ON sp.symbol = rg.symbol
  AND sp.price_date = (SELECT MAX(price_date) FROM stock_prices WHERE symbol = rg.symbol)
GROUP BY sp.close_price`,

  totalComp: `SELECT tax_year, base_salary + rsu_income AS total_comp, base_salary, rsu_income
FROM w2_records
ORDER BY tax_year DESC
LIMIT 1`,

  nwChange: `-- Net worth now minus net worth as of a year ago (each account's newest snapshot on or before that date)
WITH now_nw AS (
  SELECT SUM(bs.balance) AS nw FROM balance_snapshots bs
  JOIN accounts a ON bs.account_id = a.id
  WHERE a.is_active AND a.include_in_nw AND ${LATEST_SNAPSHOT}
),
then_nw AS (
  SELECT SUM(bs.balance) AS nw FROM balance_snapshots bs
  JOIN accounts a ON bs.account_id = a.id
  WHERE a.is_active AND a.include_in_nw
    AND bs.snapshot_date = (
      SELECT MAX(snapshot_date) FROM balance_snapshots
      WHERE account_id = bs.account_id AND snapshot_date <= current_date - interval '365 days'
    )
)
SELECT now_nw.nw - then_nw.nw AS change_12mo FROM now_nw, then_nw`,

  propertyEquity: `SELECT pv.value AS property_value, m.current_balance AS mortgage_balance,
  pv.value - m.current_balance AS equity
FROM property_valuations pv
JOIN accounts a ON pv.account_id = a.id AND a.account_type = 'real_estate'
CROSS JOIN LATERAL (SELECT current_balance FROM mortgages ORDER BY updated_at DESC LIMIT 1) m
ORDER BY pv.valuation_date DESC
LIMIT 1`,

  vehicles: `SELECT year, make, model, estimated_value, purchase_price,
  purchase_price - estimated_value AS depreciation
FROM vehicles`,

  liquidityLayers: `SELECT a.display_group, SUM(bs.balance) AS total
FROM balance_snapshots bs
JOIN accounts a ON bs.account_id = a.id
WHERE a.is_active AND a.include_in_nw AND ${LATEST_SNAPSHOT}
GROUP BY a.display_group
ORDER BY CASE lower(replace(a.display_group, ' ', '_'))
  WHEN 'cash' THEN 0 WHEN 'investments' THEN 1 WHEN 'home_equity' THEN 2 WHEN 'retirement' THEN 3 ELSE 9 END`,

  compSplit: `SELECT base_salary, rsu_income, base_salary + rsu_income AS total_comp
FROM w2_records
ORDER BY tax_year DESC
LIMIT 1`,

  netWorthTrend: `SELECT bs.snapshot_date, a.display_group, SUM(bs.balance) AS total
FROM balance_snapshots bs
JOIN accounts a ON bs.account_id = a.id
WHERE a.include_in_nw AND a.is_active
GROUP BY bs.snapshot_date, a.display_group
ORDER BY bs.snapshot_date`,

  upcomingVests: `SELECT ve.vest_date, ve.shares, rg.symbol, ve.shares * sp.close_price AS est_value
FROM vest_events ve
JOIN rsu_grants rg ON ve.grant_id = rg.id
JOIN stock_prices sp ON sp.symbol = rg.symbol
  AND sp.price_date = (SELECT MAX(price_date) FROM stock_prices WHERE symbol = rg.symbol)
WHERE NOT ve.is_actual
ORDER BY ve.vest_date
LIMIT 4`,

  spending30d: `-- Spending = negative amounts, excluding transfers and loan/card payments
SELECT category, SUM(amount) AS total, COUNT(*) AS count
FROM transactions
WHERE amount < 0
  AND (category IS NULL OR category NOT IN ('Transfer', 'Credit Card Payment', 'Loan Payment', 'Mortgage Payment'))
  AND date BETWEEN current_date - interval '30 days' AND current_date
GROUP BY category
ORDER BY SUM(amount)`,
}
</script>

<template>
  <div>
    <PageHeader
      title="Dashboard"
      :subtitle="asOf ? `Balances ${asOf}` : undefined"
      tooltip="What the household is worth right now, split by how quickly the money can be reached, with the next RSU vests and the last 30 days of spending.&lt;br&gt;&lt;br&gt;Every balance is the newest snapshot per account; the as-of date shows how fresh that is."
    />

    <SyncWarnings />

    <!-- Loading state -->
    <div v-if="store.loading" class="flex items-center justify-center h-64">
      <div class="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-500"></div>
    </div>

    <div v-else-if="store.data">
      <!-- Top metrics: one tile per concept, 2 per row on phones, 3 then 6 wider -->
      <div class="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-3 sm:gap-4 mb-6">
        <MetricCard
          label="Net Worth"
          :value="compact(store.data.net_worth)"
          :subtitle="asOf"
          info="Sum of the newest balance of every active account marked &lsquo;include in net worth&rsquo;. Liabilities (credit cards, loans) are negative balances and subtract.&lt;br&gt;&lt;br&gt;&lt;strong&gt;Source:&lt;/strong&gt; latest balance_snapshots row per account."
          :sql="SQL.netWorth"
          :sqlTables="['accounts', 'balance_snapshots']"
        />
        <MetricCard
          label="Liquid Net Worth"
          :value="compact(store.data.liquid_net_worth)"
          subtitle="cash + investments"
          info="Money that can be spent within days: the Cash, Investments and Company Stock layers only. Home equity, retirement accounts and liabilities are left out.&lt;br&gt;&lt;br&gt;&lt;strong&gt;Source:&lt;/strong&gt; latest balance_snapshots row per account, filtered by display group."
          :sql="SQL.liquidNetWorth"
          :sqlTables="['accounts', 'balance_snapshots']"
        />
        <MetricCard
          label="RSU Holdings"
          :value="rsu.data.value ? compact(rsu.data.value.held_value) : dash"
          :subtitle="rsu.error.value ? 'unavailable' : (rsu.data.value ? `${rsu.data.value.sellable_shares} sellable + ${rsu.data.value.unvested_shares} unvested` : '')"
          :info="`Value of the ${symbol} RSU shares still held (sellable + unvested) at the current market price, fetched once a day from Yahoo Finance. Not part of net worth.&lt;br&gt;&lt;br&gt;&lt;strong&gt;Source:&lt;/strong&gt; rsu_grants share counts &times; stock_prices.`"
          :sql="SQL.rsuHoldings"
          :sqlTables="['rsu_grants', 'stock_prices']"
        />
        <MetricCard
          label="Total Comp"
          :value="store.data.total_comp_annual ? compact(store.data.total_comp_annual) : dash"
          subtitle="base + RSU, latest W-2"
          info="Base salary plus RSU income from the most recent W-2 record. When the W-2 has only gross pay, this is the gross pay, split using that year's vests.&lt;br&gt;&lt;br&gt;&lt;strong&gt;Source:&lt;/strong&gt; w2_records, newest tax year, and vest_events."
          :sql="SQL.totalComp"
          :sqlTables="['w2_records']"
        />
        <MetricCard
          label="12mo Change"
          :value="store.data.net_worth_12mo_change != null ? compact(store.data.net_worth_12mo_change) : dash"
          :changeValue="nwChange"
          subtitle="year over year"
          info="Net worth now minus net worth as of a year ago, using each account's newest snapshot on or before that date. Accounts that did not exist a year ago count as new money.&lt;br&gt;&lt;br&gt;&lt;strong&gt;Source:&lt;/strong&gt; balance_snapshots history."
          :sql="SQL.nwChange"
          :sqlTables="['accounts', 'balance_snapshots']"
        />
        <MetricCard
          label="Property Equity"
          :value="property.data.value?.equity != null ? compact(property.data.value.equity) : dash"
          :subtitle="property.error.value ? 'unavailable' : 'value minus mortgage'"
          info="Latest property valuation minus the mortgage's newest balance (synced daily), so this matches the Home Equity layer.&lt;br&gt;&lt;br&gt;&lt;strong&gt;Source:&lt;/strong&gt; property_valuations and balance_snapshots."
          :sql="SQL.propertyEquity"
          :sqlTables="['property_valuations', 'mortgages', 'accounts']"
        />
      </div>

      <!-- Charts Row -->
      <div class="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-6 items-start">
        <div class="lg:col-span-2 min-w-0">
          <ChartContainer
            title="Liquidity Layers"
            :subtitle="`Cash to retirement, in order of access; the last bar is net worth (${compact(waterfallTotal)})`"
            :empty="store.data.layers.length === 0"
            info="Each bar is one layer's total over the accounts included in net worth: Cash, Investments, Home Equity, Retirement, then liabilities, which hang downward. The final bar equals the Net Worth tile.&lt;br&gt;&lt;br&gt;&lt;strong&gt;Source:&lt;/strong&gt; accounts grouped by display_group, latest balance per account."
            :sql="SQL.liquidityLayers"
            :sqlTables="['accounts', 'balance_snapshots']"
          >
            <LiquidityWaterfall :layers="store.data.layers" />
          </ChartContainer>
        </div>
        <div class="min-w-0">
          <ChartContainer
            title="Compensation Split"
            :subtitle="store.income?.source === 'vests' ? 'Salary vs. RSU, latest W-2; RSU from vest records' : 'Salary vs. RSU, latest W-2'"
            :loading="!store.income && !store.error"
            :empty="!!store.income && store.income.total_comp === 0"
            empty-text="No W-2 record yet"
            info="Share of annual compensation from base salary vs RSU income; the centre is the total. When the W-2 has only gross pay, RSU income is that year's actual vests (shares &times; price at vest) and salary is the rest of gross pay.&lt;br&gt;&lt;br&gt;&lt;strong&gt;Source:&lt;/strong&gt; w2_records, newest tax year, and vest_events."
            :sql="SQL.compSplit"
            :sqlTables="['w2_records']"
          >
            <CompDonut v-if="store.income" :salary="store.income.salary" :rsu="store.income.rsu_income" />
          </ChartContainer>
        </div>
      </div>

      <!-- Net Worth Trend -->
      <div class="mb-6">
        <ChartContainer
          title="Net Worth Over Time"
          subtitle="Assets stacked by layer; liabilities as dashed lines"
          :loading="trend.loading.value"
          :empty="!trend.loading.value && (!trend.data.value || trend.data.value.dates.length === 0)"
          :empty-text="trend.error.value ? `Could not load history: ${trend.error.value}` : 'No balance history yet'"
          info="Daily balances summed by layer; each account keeps its last known balance until a newer one arrives (the house between valuations, the 401(k) between statements). The chart starts on the first day every established account has a balance. Asset layers stack to the total; liability layers (credit cards, loans) are drawn as their own dashed lines below zero so the stacked area is not distorted.&lt;br&gt;&lt;br&gt;&lt;strong&gt;Source:&lt;/strong&gt; balance_snapshots grouped by display_group."
          :sql="SQL.netWorthTrend"
          :sqlTables="['balance_snapshots', 'accounts']"
        >
          <NetWorthChart v-if="trend.data.value" :data="trend.data.value" />
        </ChartContainer>
      </div>

      <!-- Quick Info Row -->
      <div class="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-6 items-start">
        <!-- Upcoming Vests -->
        <ChartContainer
          title="Next Vests"
          :subtitle="rsu.data.value ? `${symbol} at the current price` : undefined"
          :loading="rsu.loading.value"
          :empty="!rsu.loading.value && upcomingVests.length === 0"
          :empty-text="rsu.error.value ? `Could not load RSU data: ${rsu.error.value}` : 'No upcoming vests'"
          :info="`The next four RSU vest events. The estimated value multiplies the shares by today's ${symbol} price; the real value depends on the price on the vest date.&lt;br&gt;&lt;br&gt;&lt;strong&gt;Source:&lt;/strong&gt; vest_events (future events) and stock_prices.`"
          :sql="SQL.upcomingVests"
          :sqlTables="['vest_events', 'rsu_grants', 'stock_prices']"
        >
          <div class="space-y-2">
            <div v-for="v in upcomingVests" :key="`${v.grant_id}-${v.vest_date}`"
              class="flex items-center justify-between gap-3 text-sm py-2 px-3 bg-gray-50 dark:bg-gray-800 rounded-lg">
              <div class="min-w-0">
                <span class="text-gray-700 dark:text-gray-300 font-medium">{{ date(v.vest_date) }}</span>
                <span class="text-gray-400 text-xs ml-2 whitespace-nowrap">{{ v.shares }} shares</span>
              </div>
              <span class="text-xs text-gray-500 dark:text-gray-400 whitespace-nowrap">~{{ compact(v.est_value) }}</span>
            </div>
          </div>
        </ChartContainer>

        <!-- Top Spending (30 days) -->
        <ChartContainer
          title="Last 30 Days Spending"
          :subtitle="`${date(window30.from)} to ${date(window30.to)}`"
          :loading="spending.loading.value"
          :empty="!spending.loading.value && topSpending.length === 0"
          :empty-text="spending.error.value ? `Could not load spending: ${spending.error.value}` : 'No spending recorded in the last 30 days'"
          info="Top five categories by amount spent in the last 30 days. Spending means negative transactions; transfers and loan or card payments are excluded, income is never counted.&lt;br&gt;&lt;br&gt;&lt;strong&gt;Source:&lt;/strong&gt; transactions in the window, grouped by category (SimpleFIN, email receipts, manual)."
          :sql="SQL.spending30d"
          :sqlTables="['transactions']"
        >
          <div class="space-y-2">
            <div v-for="cat in topSpending" :key="cat.category" class="flex items-center justify-between gap-3 text-sm">
              <span class="text-gray-700 dark:text-gray-300 truncate">{{ cat.category }}</span>
              <span class="font-medium text-gray-900 dark:text-white whitespace-nowrap">{{ compact(Math.abs(cat.total)) }}</span>
            </div>
            <div class="flex items-center justify-between text-sm pt-2 border-t border-gray-100 dark:border-gray-800">
              <span class="font-medium text-gray-500 dark:text-gray-400">Total</span>
              <span class="font-bold text-gray-900 dark:text-white">{{ compact(Math.abs(spendingTotal)) }}</span>
            </div>
          </div>
        </ChartContainer>
      </div>

      <!-- Vehicles (small, only when tracked) -->
      <div v-if="assets.data.value && assets.data.value.vehicle_count > 0" class="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-3 sm:gap-4 mb-6">
        <MetricCard
          label="Vehicles"
          :value="compact(assets.data.value.total_value)"
          :subtitle="`${assets.data.value.vehicle_count} tracked, AI estimate`"
          info="Sum of the vehicles' estimated values. Each value is a labelled AI estimate with its date and reasoning on the Assets page; vehicles are not part of net worth.&lt;br&gt;&lt;br&gt;&lt;strong&gt;Source:&lt;/strong&gt; vehicles.estimated_value."
          :sql="SQL.vehicles"
          :sqlTables="['vehicles']"
        />
      </div>

      <!-- Layer Cards -->
      <div class="space-y-3">
        <h3 class="text-sm font-semibold text-gray-900 dark:text-white">Account Details <InfoTooltip text="Every active account by layer, with the date of its newest balance. Accounts excluded from net worth are shown but do not count toward the layer total." /></h3>
        <LayerCard v-for="layer in store.data.layers" :key="layer.name" :layer="layer" />
      </div>
    </div>

    <!-- Error state -->
    <div v-else-if="store.error" class="text-red-600 dark:text-red-400 text-sm">
      {{ store.error }}
    </div>
  </div>
</template>
