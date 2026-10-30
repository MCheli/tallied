<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import type { ECElementEvent } from 'echarts/core'
import { LineChart, PieChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent, MarkPointComponent, MarkLineComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { ChevronDown, ChevronRight } from 'lucide-vue-next'
import { api } from '../api/client'
import { useDataExplorer } from '../composables/useDataExplorer'
import { useChartDefaults } from '../composables/useChartDefaults'
import { useFormatters } from '../composables/useFormatters'
import { localISO } from '../composables/useDatePresets'
import {
  CASH_RANGES, averageMonthlySpend, changeOver, filterSeries, nearestIndex, rangeDays, rangeFromDate, runwayMonths,
  type CashRange,
} from '../composables/useCashRange'
import PageHeader from '../components/common/PageHeader.vue'
import SyncWarnings from '../components/common/SyncWarnings.vue'
import DataExplorer from '../components/common/DataExplorer.vue'
import DataTable from '../components/common/DataTable.vue'
import InfoTooltip from '../components/common/InfoTooltip.vue'
import MetricCard from '../components/common/MetricCard.vue'
import ChartContainer from '../components/common/ChartContainer.vue'
import SqlViewerModal from '../components/common/SqlViewerModal.vue'
import type { LargeTransaction, LayerAccount, MonthlySpending, NetWorthSeries, SnapshotResponse, Transaction } from '../types'

use([LineChart, PieChart, GridComponent, TooltipComponent, LegendComponent, MarkPointComponent, MarkLineComponent, CanvasRenderer])

const { baseOption, isDark, isMobile, axisLineColor, splitLineColor, mutedTextColor, mobileAxis } = useChartDefaults()
const { openData } = useDataExplorer()
const { money, compact, date, dash } = useFormatters()

const ACCOUNT_COLORS = ['#3b82f6', '#22c55e', '#f59e0b', '#8b5cf6', '#ef4444', '#06b6d4', '#ec4899', '#14b8a6']
const THRESHOLDS = [250, 500, 1000]

const loading = ref(true)
const error = ref('')
const snapshot = ref<SnapshotResponse | null>(null)
const largeTransactions = ref<LargeTransaction[]>([])
const balanceHistory = ref<NetWorthSeries | null>(null)
const monthlySpend = ref<MonthlySpending[]>([])
const syncResult = ref<{ synced: number; detail?: string } | null>(null)
const syncError = ref('')
const syncing = ref(false)

const timeRange = ref<CashRange>('90')
const threshold = ref(500)

// Expandable account detail
const expandedAccountId = ref<string | null>(null)
const accountTransactions = ref<Transaction[]>([])
const accountTxnLoading = ref(false)
const accountTxnPage = ref(0)
const accountTxnTotal = ref(0)
const highlightedTxnIdx = ref<number | null>(null)

const fromDate = computed(() => rangeFromDate(timeRange.value))
const rangeDesc = computed(() => CASH_RANGES.find(o => o.key === timeRange.value)?.desc ?? '')

onMounted(async () => { await loadData() })

async function loadData() {
  loading.value = true
  error.value = ''
  const [snapRes, histRes] = await Promise.allSettled([api.getSnapshot(), api.getNetWorth()])
  if (snapRes.status === 'fulfilled') snapshot.value = snapRes.value
  else error.value = snapRes.reason instanceof Error ? snapRes.reason.message : 'Failed to load balances'
  balanceHistory.value = histRes.status === 'fulfilled' ? histRes.value : null
  await loadRangeData()
  loading.value = false
}

/** Everything the range control scopes: notable transactions and the monthly spend behind runway. */
async function loadRangeData() {
  const days = rangeDays(timeRange.value) ?? 9999
  const [txnRes, spendRes] = await Promise.allSettled([
    api.getLargeTransactions({ threshold: threshold.value, days, limit: 100, excludeIncome: true }),
    api.getMonthlyTrend(fromDate.value ?? undefined, localISO(new Date())),
  ])
  largeTransactions.value = txnRes.status === 'fulfilled' ? txnRes.value : []
  monthlySpend.value = spendRes.status === 'fulfilled' ? spendRes.value : []
  highlightedTxnIdx.value = null
}

watch([timeRange, threshold], () => { void loadRangeData() })

const cashLayer = computed(() => snapshot.value?.layers.find(l => l.name === 'Cash') ?? null)
const totalCash = computed(() => cashLayer.value?.total ?? 0)
const sortedAccounts = computed<LayerAccount[]>(() =>
  cashLayer.value ? [...cashLayer.value.accounts].sort((a, b) => (b.balance || 0) - (a.balance || 0)) : []
)
const asOf = computed(() => cashLayer.value?.as_of ?? snapshot.value?.as_of ?? null)

function accountColor(index: number): string { return ACCOUNT_COLORS[index % ACCOUNT_COLORS.length] }

const filteredHistory = computed(() => {
  const cash = balanceHistory.value?.groups?.['Cash']
  if (!balanceHistory.value || !cash) return { dates: [] as string[], values: [] as number[] }
  return filterSeries(balanceHistory.value.dates, cash, fromDate.value)
})
const cashChange = computed(() => changeOver(filteredHistory.value.values))
const avgMonthlySpend = computed(() => averageMonthlySpend(monthlySpend.value))
const runway = computed(() => runwayMonths(totalCash.value, avgMonthlySpend.value))

async function syncBalances() {
  syncing.value = true
  syncResult.value = null
  syncError.value = ''
  try {
    const started = await api.simplefin.sync()
    if (started.status === 'skipped') {
      syncResult.value = { synced: 0, detail: 'No bank connection. Connect SimpleFIN in Settings.' }
      return
    }
    let totalSynced = 0
    for (let i = 0; i < 150; i++) {
      await new Promise(r => setTimeout(r, 2000))
      const st = await api.simplefin.syncStatus()
      if (st.status === 'succeeded') { totalSynced = st.balances_synced ?? 0; break }
      if (st.status === 'failed') throw new Error(st.error || 'Sync failed')
    }
    syncResult.value = { synced: totalSynced }
    await loadData()
  } catch (e) {
    syncError.value = e instanceof Error ? e.message : 'Sync failed'
  } finally {
    syncing.value = false
  }
}

async function toggleAccount(accountId: string) {
  if (expandedAccountId.value === accountId) {
    expandedAccountId.value = null
    accountTransactions.value = []
    return
  }
  expandedAccountId.value = accountId
  accountTxnPage.value = 0
  await loadAccountTxns(accountId, 0)
}

async function loadAccountTxns(accountId: string, page: number) {
  accountTxnLoading.value = true
  try {
    const d = await api.getTransactions({ account_id: accountId, limit: 25, offset: page * 25 })
    accountTransactions.value = d.items
    accountTxnTotal.value = d.total
    accountTxnPage.value = page
  } catch {
    accountTransactions.value = []
  }
  accountTxnLoading.value = false
}

// Donut with colours matching the bars
const accountPieOption = computed(() => {
  const accts = sortedAccounts.value.filter(a => (a.balance || 0) > 0)
  if (!accts.length) return null
  return {
    ...baseOption.value,
    tooltip: { ...baseOption.value.tooltip, trigger: 'item' as const, formatter: (p: { name: string; value: number; percent: number }) => `${p.name}<br/>${money(p.value)} (${p.percent}%)` },
    series: [{
      type: 'pie', radius: ['50%', '75%'], center: ['50%', '50%'],
      data: accts.map((a, i) => ({ name: a.name, value: Math.round(a.balance || 0), itemStyle: { color: accountColor(i) } })),
      label: { show: false },
      emphasis: { label: { show: true, fontSize: 11, fontWeight: 'bold' as const } },
      itemStyle: { borderColor: isDark.value ? '#111827' : '#fff', borderWidth: 2 },
    }],
  }
})

// Balance chart with notable transactions marked; markers remember their row in largeTransactions
const cashHistoryOption = computed(() => {
  const { dates, values } = filteredHistory.value
  if (!dates.length) return null
  const markPoints = largeTransactions.value
    .map((t, origIdx) => ({ t, origIdx }))
    .filter(({ t }) => t.date >= dates[0] && t.date <= dates[dates.length - 1])
    .map(({ t, origIdx }) => {
      const idx = nearestIndex(dates, t.date)
      return {
        coord: [idx, values[idx]],
        value: `${t.merchant || 'Txn'}\n${t.amount >= 0 ? '+' : '-'}${money(Math.abs(t.amount))}`,
        symbol: t.amount >= 0 ? 'triangle' : 'pin',
        symbolSize: Math.min(28, Math.max(14, Math.abs(t.amount) / 400)),
        itemStyle: { color: t.amount >= 0 ? '#22c55e' : '#ef4444', borderColor: '#fff', borderWidth: 1 },
        label: { show: false },
        txnIdx: origIdx,
      }
    })
  const avg = values.reduce((s, v) => s + v, 0) / values.length
  return {
    ...baseOption.value,
    tooltip: { ...baseOption.value.tooltip, trigger: 'axis' as const, formatter: (params: unknown) => {
      const list = (Array.isArray(params) ? params : [params]) as { name: string; value: number }[]
      if (!list.length) return ''
      const p = list[0]
      let html = `<strong>${date(p.name)}</strong><br/>Cash: ${money(p.value)}`
      for (const t of largeTransactions.value.filter(t => t.date === p.name)) {
        const c = t.amount >= 0 ? '#22c55e' : '#ef4444'
        html += `<br/><span style="color:${c}">&#9679;</span> ${t.merchant || 'Txn'}: <strong style="color:${c}">${money(t.amount)}</strong> <span style="color:#9ca3af">${t.category || ''}</span>`
      }
      return html
    }},
    xAxis: {
      type: 'category' as const, data: dates,
      axisLabel: { ...mobileAxis(), formatter: (v: string) => date(v).replace(/, \d{4}$/, ''), interval: Math.max(0, Math.floor(dates.length / (isMobile.value ? 4 : 8))) },
      axisTick: { show: false }, axisLine: { lineStyle: { color: axisLineColor.value } },
    },
    yAxis: { type: 'value' as const, axisLabel: { ...mobileAxis(), formatter: (v: number) => compact(v) }, splitLine: { lineStyle: { color: splitLineColor.value, type: 'dashed' as const } } },
    series: [{
      type: 'line', data: values, smooth: true, symbol: 'none', lineStyle: { width: 2, color: '#3b82f6' },
      areaStyle: { color: { type: 'linear' as const, x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: 'rgba(59,130,246,0.12)' }, { offset: 1, color: 'rgba(59,130,246,0.02)' }] } },
      markPoint: markPoints.length ? { data: markPoints, emphasis: { label: { show: true, formatter: (p: { value: string }) => p.value, fontSize: 9, backgroundColor: 'rgba(0,0,0,0.85)', padding: [4, 8], borderRadius: 4, color: '#fff', lineHeight: 13 }, itemStyle: { shadowBlur: 10, shadowColor: 'rgba(0,0,0,0.3)' } } } : undefined,
      markLine: { silent: true, symbol: 'none', data: [{ yAxis: Math.round(avg), lineStyle: { color: axisLineColor.value, type: 'dashed' as const, width: 1 }, label: { show: true, formatter: `Avg ${compact(avg)}`, position: 'insideEndTop' as const, fontSize: 10, color: mutedTextColor.value } }] },
    }],
  }
})

function onChartClick(params: ECElementEvent) {
  const idx = (params.data as { txnIdx?: number } | undefined)?.txnIdx
  if (params.componentType === 'markPoint' && idx !== undefined) {
    highlightedTxnIdx.value = idx
    setTimeout(() => { document.getElementById(`txn-row-${idx}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' }) }, 100)
  }
}

// ── SQL transparency (Postgres) ──────────────────────────────────────────────
const showAccountsSql = ref(false)

const SQL = {
  totalCash: `-- Cash layer: active accounts whose display group is Cash, newest balance each
SELECT a.name, bs.balance, bs.snapshot_date
FROM balance_snapshots bs
JOIN accounts a ON bs.account_id = a.id
WHERE a.is_active AND a.include_in_nw
  AND lower(a.display_group) = 'cash'
  AND bs.snapshot_date = (SELECT MAX(snapshot_date) FROM balance_snapshots WHERE account_id = bs.account_id)
ORDER BY bs.balance DESC`,

  avgMonthlySpend: `-- Spending per month inside the selected range; the card averages these months
SELECT to_char(date, 'YYYY-MM') AS month, SUM(amount) AS total
FROM transactions
WHERE amount < 0
  AND (category IS NULL OR category NOT IN ('Transfer', 'Credit Card Payment', 'Loan Payment', 'Mortgage Payment'))
  AND date BETWEEN :from_date AND current_date
GROUP BY month
ORDER BY month
-- Runway = Total Cash / average month`,

  balanceHistory: `SELECT bs.snapshot_date, SUM(bs.balance) AS cash_total
FROM balance_snapshots bs
JOIN accounts a ON bs.account_id = a.id
WHERE a.is_active AND a.include_in_nw AND lower(a.display_group) = 'cash'
  AND bs.snapshot_date >= :from_date
GROUP BY bs.snapshot_date
ORDER BY bs.snapshot_date`,

  largeTransactions: `SELECT t.date, t.amount, t.merchant, t.category, a.name AS account_name
FROM transactions t
LEFT JOIN accounts a ON t.account_id = a.id
WHERE t.date >= current_date - make_interval(days => :days)
  AND t.amount <= -:threshold
ORDER BY t.date DESC
LIMIT 100`,

  accountTransactions: `SELECT t.date, t.merchant, t.category, t.amount
FROM transactions t
WHERE t.account_id = :account_id
ORDER BY t.date DESC
LIMIT 25 OFFSET :offset`,
}
</script>

<template>
  <div class="max-w-6xl mx-auto space-y-6">
    <PageHeader
      title="Cash"
      :subtitle="asOf ? `Checking & savings, balances as of ${date(asOf)}` : 'Checking & savings'"
      tooltip="How much cash the household has, how it is trending, how many months it would last, and the notable transactions behind the movements. The range control scopes every section."
    >
      <div class="flex flex-wrap gap-1 bg-gray-100 dark:bg-gray-800 rounded-lg p-0.5" role="group" aria-label="Range">
        <button v-for="opt in CASH_RANGES" :key="opt.key" @click="timeRange = opt.key" :aria-pressed="timeRange === opt.key"
          class="px-3 py-1.5 min-h-[36px] text-xs font-medium rounded-md transition-colors"
          :class="timeRange === opt.key ? 'bg-white dark:bg-gray-700 text-gray-900 dark:text-white shadow-sm' : 'text-gray-500 dark:text-gray-400'">
          {{ opt.label }}
        </button>
      </div>
      <button @click="openData('cash')"
        class="px-3 py-2 min-h-[40px] text-xs font-medium bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 text-gray-600 dark:text-gray-300">
        Data
      </button>
      <button @click="syncBalances" :disabled="syncing"
        class="px-3 py-2 min-h-[40px] text-xs font-medium bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 text-gray-600 dark:text-gray-300 disabled:opacity-50">
        {{ syncing ? 'Syncing...' : 'Sync' }}
      </button>
    </PageHeader>
    <SyncWarnings />

    <div v-if="syncResult" class="bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-lg p-3 text-xs text-green-700 dark:text-green-400">
      {{ syncResult.detail || `Synced ${syncResult.synced} account balance${syncResult.synced === 1 ? '' : 's'} from SimpleFIN.` }}
    </div>
    <div v-if="syncError" class="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-3 text-xs text-red-700 dark:text-red-400">Sync failed: {{ syncError }}</div>

    <div v-if="loading" class="flex items-center justify-center h-64"><div class="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-500"></div></div>
    <div v-else-if="error" class="text-sm text-red-600 dark:text-red-400">{{ error }}</div>
    <div v-else-if="!cashLayer" class="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-8 text-center"><p class="text-gray-500">No cash accounts yet. Add checking or savings accounts in Settings, or connect SimpleFIN.</p></div>

    <template v-else>
      <!-- Summary Cards -->
      <div class="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4">
        <MetricCard
          label="Total Cash"
          :value="money(totalCash)"
          :changeValue="cashChange ? cashChange.pct : undefined"
          :subtitle="cashChange ? `${money(cashChange.change)}, ${CASH_RANGES.find(o => o.key === timeRange)?.label ?? ''}` : (asOf ? `as of ${date(asOf)}` : '')"
          info="Sum of the newest balance of every checking and savings account (the Cash layer). The change is first-to-last point of the balance history inside the selected range.&lt;br&gt;&lt;br&gt;&lt;strong&gt;Source:&lt;/strong&gt; latest balance_snapshots per Cash account."
          :sql="SQL.totalCash"
          :sqlTables="['balance_snapshots', 'accounts']"
        />
        <MetricCard
          label="Avg Monthly Spend"
          :value="avgMonthlySpend != null ? compact(avgMonthlySpend) : dash"
          :subtitle="monthlySpend.length ? `avg of ${monthlySpend.length} mo, ${CASH_RANGES.find(o => o.key === timeRange)?.label ?? ''}` : 'no spending in range'"
          info="Average of the monthly spending totals inside the selected range. Spending is money out only; income, transfers and loan or card payments are excluded.&lt;br&gt;&lt;br&gt;&lt;strong&gt;Source:&lt;/strong&gt; transactions summed by month."
          :sql="SQL.avgMonthlySpend"
          :sqlTables="['transactions']"
        />
        <MetricCard
          label="Runway"
          :value="runway != null ? `${runway} mo` : dash"
          :subtitle="runway == null ? 'needs spending data' : (runway >= 6 ? 'comfortable (6+)' : runway >= 3 ? 'ok (3 to 6)' : 'tight (under 3)')"
          info="Months the cash would last at the average monthly spend of the selected range: Total Cash divided by Avg Monthly Spend, rounded to whole months."
          :sql="SQL.avgMonthlySpend"
          :sqlTables="['transactions', 'balance_snapshots']"
        />
        <MetricCard
          label="Accounts"
          :value="String(sortedAccounts.length)"
          subtitle="checking & savings"
          info="Number of active accounts in the Cash layer."
        />
      </div>

      <!-- Account Breakdown -->
      <ChartContainer
        title="Account Breakdown"
        subtitle="Share of cash per account"
        :empty="sortedAccounts.length === 0"
        info="How the cash is split across accounts. Colours match between the donut and the bars; accounts with a negative balance are listed but not drawn in the donut."
        :sql="SQL.totalCash"
        :sqlTables="['balance_snapshots', 'accounts']"
      >
        <div class="grid grid-cols-1 lg:grid-cols-3 gap-4 items-center">
          <div class="lg:col-span-1">
            <v-chart v-if="accountPieOption" :option="accountPieOption" style="height: 180px" autoresize />
          </div>
          <div class="lg:col-span-2 space-y-2.5 min-w-0">
            <div v-for="(account, idx) in sortedAccounts" :key="account.id" class="flex items-center gap-3 min-w-0">
              <div class="w-28 sm:w-40 text-xs text-gray-700 dark:text-gray-300 truncate flex-shrink-0" :title="account.name">{{ account.name }}</div>
              <div class="flex-1 min-w-0 h-5 bg-gray-100 dark:bg-gray-800 rounded-full overflow-hidden relative">
                <div class="h-full rounded-full transition-all" :style="{ width: `${totalCash > 0 ? Math.max(2, (account.balance || 0) / totalCash * 100) : 0}%`, backgroundColor: accountColor(idx) }"></div>
                <span v-if="totalCash > 0 && (account.balance || 0) / totalCash > 0.08" class="absolute inset-y-0 left-2 flex items-center text-[10px] font-medium text-white">
                  {{ ((account.balance || 0) / totalCash * 100).toFixed(0) }}%
                </span>
              </div>
              <div class="w-20 text-right text-xs font-medium text-gray-900 dark:text-white whitespace-nowrap flex-shrink-0">{{ money(account.balance) }}</div>
            </div>
          </div>
        </div>
      </ChartContainer>

      <!-- Cash Balance & Activity -->
      <ChartContainer
        title="Cash Balance & Activity"
        :subtitle="rangeDesc"
        :empty="filteredHistory.dates.length === 0"
        :empty-text="`No balance history in the ${rangeDesc.toLowerCase()}. Pick a wider range or sync.`"
        info="Cash balance over the selected range with notable withdrawals marked (pins). The dashed line is the period average. Tap a marker to highlight its row below."
        :sql="`${SQL.balanceHistory}\n\n---\n\n${SQL.largeTransactions}`"
        :sqlTables="['balance_snapshots', 'accounts', 'transactions']"
      >
        <v-chart v-if="cashHistoryOption" :option="cashHistoryOption" :style="{ height: isMobile ? '240px' : '280px' }" autoresize @click="onChartClick" />

        <div class="mt-4 pt-4 border-t border-gray-100 dark:border-gray-800">
          <div class="flex flex-wrap items-center justify-between gap-2 mb-2">
            <p class="text-xs font-medium text-gray-500 flex items-center gap-1">
              Notable transactions
              <InfoTooltip text="Money out above the threshold inside the selected range (income is never listed). Choose the threshold on the right." />
            </p>
            <div class="flex items-center gap-1 text-xs">
              <span class="text-gray-400">over</span>
              <button v-for="t in THRESHOLDS" :key="t" @click="threshold = t" :aria-pressed="threshold === t"
                class="px-2 py-1 min-h-[32px] rounded-md border transition-colors"
                :class="threshold === t ? 'bg-indigo-600 text-white border-indigo-600' : 'bg-white dark:bg-gray-800 border-gray-200 dark:border-gray-700 text-gray-600 dark:text-gray-400'">
                {{ money(t) }}
              </button>
            </div>
          </div>
          <div class="max-h-60 overflow-y-auto">
            <DataTable :empty="largeTransactions.length === 0" :empty-text="`No withdrawals over ${money(threshold)} in the ${rangeDesc.toLowerCase()}`" :columns="5" dense sticky>
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Account</th>
                  <th>Merchant</th>
                  <th class="text-right">Amount</th>
                  <th>Category</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(txn, i) in largeTransactions" :key="txn.id" :id="`txn-row-${i}`"
                  class="transition-colors"
                  :class="highlightedTxnIdx === i ? 'bg-indigo-50 dark:bg-indigo-950/30' : ''">
                  <td class="text-gray-500 whitespace-nowrap">{{ date(txn.date) }}</td>
                  <td class="text-gray-400 max-w-[8rem] truncate text-xs">{{ txn.account_name || dash }}</td>
                  <td class="text-gray-900 dark:text-white max-w-[10rem] truncate" :title="txn.merchant || ''">{{ txn.merchant || dash }}</td>
                  <td class="text-right font-medium whitespace-nowrap" :class="txn.amount >= 0 ? 'text-green-600' : 'text-red-500'">{{ money(txn.amount) }}</td>
                  <td class="text-gray-400 whitespace-nowrap">{{ txn.category || dash }}</td>
                </tr>
              </tbody>
            </DataTable>
          </div>
        </div>
      </ChartContainer>

      <!-- All Accounts Detail (expandable) -->
      <div class="group/accounts relative">
        <button @click="showAccountsSql = true" class="sql-btn absolute -top-1 right-0 w-10 h-10 flex items-center justify-center rounded-md text-gray-300 dark:text-gray-600 opacity-0 group-hover/accounts:opacity-100 focus-visible:opacity-100 hover:!text-indigo-500 hover:bg-indigo-50 dark:hover:bg-indigo-950/40 transition-all" title="View SQL" aria-label="View SQL">
          <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>
        </button>
        <SqlViewerModal :open="showAccountsSql" :sql="`${SQL.totalCash}\n\n---\n\n${SQL.accountTransactions}`" title="All Accounts" :tables="['balance_snapshots', 'accounts', 'transactions']" @close="showAccountsSql = false" />
        <div class="flex items-center gap-1 mb-3 pr-10">
          <h2 class="text-sm font-semibold text-gray-900 dark:text-white">All Accounts</h2>
          <InfoTooltip text="Every account in the Cash layer with its newest balance and date. Open one to page through its transactions (all of them, regardless of the range above)." />
        </div>
        <div class="space-y-2">
          <div v-for="(account, idx) in sortedAccounts" :key="account.id"
            class="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl overflow-hidden">
            <button @click="toggleAccount(account.id)" :aria-expanded="expandedAccountId === account.id"
              class="w-full text-left px-4 sm:px-5 py-3.5 min-h-[44px] flex items-center gap-3 hover:bg-gray-50 dark:hover:bg-gray-800/50 transition-colors">
              <div class="w-3 h-3 rounded-full flex-shrink-0" :style="{ backgroundColor: accountColor(idx) }"></div>
              <div class="flex-1 min-w-0">
                <span class="font-medium text-gray-900 dark:text-white text-sm truncate block" :title="account.name">{{ account.name }}</span>
                <span v-if="account.balance_date" class="text-[11px] text-gray-400">as of {{ date(account.balance_date) }}</span>
              </div>
              <div class="text-right flex-shrink-0">
                <div class="text-sm font-semibold text-gray-900 dark:text-white whitespace-nowrap">{{ money(account.balance) }}</div>
                <div class="text-[10px] text-gray-400">{{ totalCash > 0 ? ((account.balance || 0) / totalCash * 100).toFixed(1) + '% of cash' : '' }}</div>
              </div>
              <component :is="expandedAccountId === account.id ? ChevronDown : ChevronRight" class="w-4 h-4 text-gray-400 flex-shrink-0" />
            </button>

            <div v-if="expandedAccountId === account.id" class="border-t border-gray-100 dark:border-gray-800 px-4 sm:px-5 pb-2">
              <div v-if="accountTxnLoading" class="py-6 text-xs text-gray-400 text-center">Loading transactions...</div>
              <DataTable v-else :empty="accountTransactions.length === 0" empty-text="No transactions for this account" :columns="4" dense>
                <thead>
                  <tr><th>Date</th><th>Merchant</th><th>Category</th><th class="text-right">Amount</th></tr>
                </thead>
                <tbody>
                  <tr v-for="txn in accountTransactions" :key="txn.id">
                    <td class="text-gray-500 whitespace-nowrap">{{ date(txn.date) }}</td>
                    <td class="text-gray-900 dark:text-white max-w-[12rem] truncate" :title="txn.merchant || ''">{{ txn.merchant || dash }}</td>
                    <td class="text-gray-400 whitespace-nowrap">{{ txn.category || dash }}</td>
                    <td class="text-right font-medium whitespace-nowrap" :class="(txn.amount ?? 0) >= 0 ? 'text-green-600' : 'text-red-500'">{{ money(txn.amount) }}</td>
                  </tr>
                </tbody>
              </DataTable>
              <div v-if="accountTxnTotal > 25" class="flex flex-wrap items-center justify-between gap-2 py-3 border-t border-gray-100 dark:border-gray-800">
                <span class="text-xs text-gray-400">Page {{ accountTxnPage + 1 }} of {{ Math.ceil(accountTxnTotal / 25) }} ({{ accountTxnTotal }} transactions)</span>
                <div class="flex gap-2">
                  <button v-if="accountTxnPage > 0" @click="loadAccountTxns(account.id, accountTxnPage - 1)"
                    class="px-3 py-1.5 min-h-[36px] text-xs bg-gray-100 dark:bg-gray-800 rounded hover:bg-gray-200">Previous</button>
                  <button v-if="(accountTxnPage + 1) * 25 < accountTxnTotal" @click="loadAccountTxns(account.id, accountTxnPage + 1)"
                    class="px-3 py-1.5 min-h-[36px] text-xs bg-gray-100 dark:bg-gray-800 rounded hover:bg-gray-200">Next</button>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </template>

    <DataExplorer />
  </div>
</template>

<style scoped>
@media (hover: none) {
  .sql-btn { opacity: 0.4; }
}
</style>
