<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { LineChart, BarChart, PieChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent, MarkPointComponent, MarkLineComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { useDataExplorer } from '../composables/useDataExplorer'
import DataExplorer from '../components/common/DataExplorer.vue'
import InfoTooltip from '../components/common/InfoTooltip.vue'
import SqlViewerModal from '../components/common/SqlViewerModal.vue'
import { useChartDefaults } from '../composables/useChartDefaults'
import { ChevronDown, ChevronRight } from 'lucide-vue-next'

use([LineChart, BarChart, PieChart, GridComponent, TooltipComponent, LegendComponent, MarkPointComponent, MarkLineComponent, CanvasRenderer])

const { baseOption, isDark } = useChartDefaults()
const { openData } = useDataExplorer()
const API = import.meta.env.VITE_API_URL || ''

// Consistent account colors
const ACCOUNT_COLORS = ['#3b82f6', '#22c55e', '#f59e0b', '#8b5cf6', '#ef4444', '#06b6d4', '#ec4899', '#14b8a6']

const loading = ref(true)
const error = ref('')
const snapshot = ref<any>(null)
const largeTransactions = ref<any[]>([])
const balanceHistory = ref<any>(null)
const cashFlow = ref<any[]>([])
const syncResult = ref<any>(null)
const syncing = ref(false)

type TimeRange = '30' | '90' | '180' | '365' | 'all'
const timeRange = ref<TimeRange>('90')
const TIME_OPTIONS: { key: TimeRange; label: string; desc: string }[] = [
  { key: '30', label: '1M', desc: 'Last month' },
  { key: '90', label: '3M', desc: 'Last 3 months' },
  { key: '180', label: '6M', desc: 'Last 6 months' },
  { key: '365', label: '1Y', desc: 'Last year' },
  { key: 'all', label: 'All', desc: 'All time' },
]

// Expandable account detail
const expandedAccountId = ref<string | null>(null)
const accountTransactions = ref<any[]>([])
const accountTxnLoading = ref(false)
const accountTxnPage = ref(0)
const accountTxnTotal = ref(0)
const highlightedTxnIdx = ref<number | null>(null)

onMounted(async () => { await loadData() })

async function loadData() {
  loading.value = true
  try {
    const days = timeRange.value === 'all' ? 9999 : parseInt(timeRange.value)
    const [snapRes, txnRes, histRes, flowRes] = await Promise.all([
      fetch(`${API}/api/v1/snapshot`, { credentials: 'include' }).then(r => r.json()),
      fetch(`${API}/api/v1/transactions/large?threshold=500&days=${days}&limit=100`, { credentials: 'include' }).then(r => r.json()),
      fetch(`${API}/api/v1/trends/net-worth`, { credentials: 'include' }).then(r => r.json()).catch(() => null),
      fetch(`${API}/api/v1/spending/monthly-trend`, { credentials: 'include' }).then(r => r.json()).catch(() => []),
    ])
    snapshot.value = snapRes
    largeTransactions.value = Array.isArray(txnRes) ? txnRes : []
    balanceHistory.value = histRes
    cashFlow.value = Array.isArray(flowRes) ? flowRes : []
  } catch (e: any) { error.value = e.message }
  finally { loading.value = false }
}

watch(timeRange, () => {
  const days = timeRange.value === 'all' ? 9999 : parseInt(timeRange.value)
  fetch(`${API}/api/v1/transactions/large?threshold=500&days=${days}&limit=100`, { credentials: 'include' })
    .then(r => r.json()).then(d => { largeTransactions.value = Array.isArray(d) ? d : [] })
})

const cashLayer = computed(() => snapshot.value?.layers?.find((l: any) => l.name === 'Cash') || null)
const totalCash = computed(() => cashLayer.value?.total ?? 0)
const sortedAccounts = computed(() => {
  if (!cashLayer.value?.accounts) return []
  return [...cashLayer.value.accounts].sort((a: any, b: any) => (b.balance || 0) - (a.balance || 0))
})

function accountColor(index: number): string {
  return ACCOUNT_COLORS[index % ACCOUNT_COLORS.length]
}

const cashChange = computed(() => {
  if (!filteredHistory.value?.data || filteredHistory.value.data.length < 2) return null
  const first = filteredHistory.value.data[0]
  const last = filteredHistory.value.data[filteredHistory.value.data.length - 1]
  const change = last - first
  return { change, pct: first > 0 ? (change / first) * 100 : 0 }
})

const avgMonthlySpend = computed(() => {
  if (!cashFlow.value.length) return null
  const n = Math.min(cashFlow.value.length, Math.max(1, Math.round(parseInt(timeRange.value || '90') / 30)))
  const recent = cashFlow.value.slice(-n)
  if (!recent.length) return null
  return recent.reduce((s: number, m: any) => s + Math.abs(m.total || 0), 0) / recent.length
})

const runwayMonths = computed(() => {
  if (!avgMonthlySpend.value || avgMonthlySpend.value <= 0) return null
  return Math.round(totalCash.value / avgMonthlySpend.value)
})

const filteredHistory = computed(() => {
  if (!balanceHistory.value?.dates?.length) return null
  const cashData = balanceHistory.value.groups?.['Cash']
  if (!cashData) return null
  const dates: string[] = balanceHistory.value.dates
  if (timeRange.value === 'all') return { dates, data: cashData }
  const cutoff = new Date(); cutoff.setDate(cutoff.getDate() - parseInt(timeRange.value))
  const cutoffStr = cutoff.toISOString().slice(0, 10)
  const startIdx = dates.findIndex(d => d >= cutoffStr)
  if (startIdx < 0) return { dates, data: cashData }
  return { dates: dates.slice(startIdx), data: cashData.slice(startIdx) }
})

async function syncBalances() {
  syncing.value = true; syncResult.value = null
  try {
    const res = await fetch(`${API}/api/v1/plaid/sync-balances`, { method: 'POST', credentials: 'include' })
    if (!res.ok) throw new Error('Sync failed')
    syncResult.value = await res.json()
    snapshot.value = await fetch(`${API}/api/v1/snapshot`, { credentials: 'include' }).then(r => r.json())
  } catch (e: any) { error.value = e.message }
  finally { syncing.value = false }
}

async function toggleAccount(accountId: string) {
  if (expandedAccountId.value === accountId) {
    expandedAccountId.value = null; accountTransactions.value = []; return
  }
  expandedAccountId.value = accountId
  accountTxnPage.value = 0
  await loadAccountTxns(accountId, 0)
}

async function loadAccountTxns(accountId: string, page: number) {
  accountTxnLoading.value = true
  const offset = page * 25
  try {
    const res = await fetch(`${API}/api/v1/transactions/?account_id=${accountId}&limit=25&offset=${offset}`, { credentials: 'include' })
    if (res.ok) {
      const d = await res.json()
      accountTransactions.value = d.items || d || []
      accountTxnTotal.value = d.total || accountTransactions.value.length
      accountTxnPage.value = page
    }
  } catch {}
  accountTxnLoading.value = false
}

// Pie chart with correlated colors
const accountPieOption = computed(() => {
  const accts = sortedAccounts.value.filter(a => (a.balance || 0) > 0)
  if (!accts.length) return null
  return {
    ...baseOption.value,
    tooltip: { ...baseOption.value.tooltip, trigger: 'item' as const, formatter: (p: any) => `${p.name}<br/>${fmtFull(p.value)} (${p.percent}%)` },
    series: [{
      type: 'pie', radius: ['50%', '75%'], center: ['50%', '50%'],
      data: accts.map((a: any, i: number) => ({ name: a.name, value: Math.round(a.balance || 0), itemStyle: { color: accountColor(i) } })),
      label: { show: false },
      emphasis: { label: { show: true, fontSize: 11, fontWeight: 'bold' as const } },
      itemStyle: { borderColor: isDark.value ? '#111827' : '#fff', borderWidth: 2 },
    }],
  }
})

// Balance chart
const cashHistoryOption = computed(() => {
  if (!filteredHistory.value) return null
  const { dates, data: cashData } = filteredHistory.value
  const markPoints = largeTransactions.value
    .filter(t => t.date && t.date >= dates[0] && t.date <= dates[dates.length - 1])
    .map((t, origIdx) => {
      let idx = dates.findIndex((d: string) => d >= t.date)
      if (idx < 0) idx = dates.length - 1
      if (idx > 0 && t.date < dates[idx]) {
        if (Math.abs(new Date(t.date).getTime() - new Date(dates[idx - 1]).getTime()) < Math.abs(new Date(t.date).getTime() - new Date(dates[idx]).getTime())) idx--
      }
      return {
        coord: [idx, cashData[idx]], value: `${t.merchant || 'Txn'}\n${t.amount >= 0 ? '+' : '-'}$${Math.round(Math.abs(t.amount)).toLocaleString()}`,
        symbol: t.amount >= 0 ? 'triangle' : 'pin', symbolSize: Math.min(28, Math.max(14, Math.abs(t.amount) / 400)),
        itemStyle: { color: t.amount >= 0 ? '#22c55e' : '#ef4444', borderColor: '#fff', borderWidth: 1 }, label: { show: false }, _txnIdx: origIdx,
      }
    }).filter(Boolean)
  const avg = cashData.length ? cashData.reduce((s: number, v: number) => s + v, 0) / cashData.length : 0
  return {
    ...baseOption.value, grid: { left: 55, right: 20, top: 20, bottom: 30 },
    tooltip: { ...baseOption.value.tooltip, trigger: 'axis' as const, formatter: (params: any) => {
      if (!Array.isArray(params) || !params.length) return ''
      const p = params[0]; const d = new Date(p.name + 'T00:00:00')
      let html = `<strong>${d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}</strong><br/>Cash: ${fmtFull(p.value)}`
      for (const t of largeTransactions.value.filter(t => t.date === p.name)) {
        const c = t.amount >= 0 ? '#22c55e' : '#ef4444'
        html += `<br/><span style="color:${c}">&#9679;</span> ${t.merchant || 'Txn'}: <strong style="color:${c}">${t.amount >= 0 ? '+' : ''}${fmtFull(t.amount)}</strong> <span style="color:#9ca3af">${t.category || ''}</span>`
      }
      return html
    }},
    xAxis: { type: 'category' as const, data: dates, axisLabel: { formatter: (v: string) => new Date(v + 'T00:00:00').toLocaleDateString('en-US', { month: 'short', day: 'numeric' }), interval: Math.max(1, Math.floor(dates.length / 8)) }, axisTick: { show: false }, axisLine: { lineStyle: { color: isDark.value ? '#374151' : '#e5e7eb' } } },
    yAxis: { type: 'value' as const, axisLabel: { formatter: (v: number) => v >= 1000 ? `$${(v / 1000).toFixed(0)}K` : `$${v}` }, splitLine: { lineStyle: { color: isDark.value ? '#1f2937' : '#f3f4f6', type: 'dashed' as const } } },
    series: [{ type: 'line', data: cashData, smooth: true, symbol: 'none', lineStyle: { width: 2, color: '#3b82f6' },
      areaStyle: { color: { type: 'linear' as const, x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: 'rgba(59,130,246,0.12)' }, { offset: 1, color: 'rgba(59,130,246,0.02)' }] } },
      markPoint: markPoints.length ? { data: markPoints, emphasis: { label: { show: true, formatter: (p: any) => p.value, fontSize: 9, backgroundColor: 'rgba(0,0,0,0.85)', padding: [4, 8], borderRadius: 4, color: '#fff', lineHeight: 13 }, itemStyle: { shadowBlur: 10, shadowColor: 'rgba(0,0,0,0.3)' } } } : undefined,
      markLine: { silent: true, symbol: 'none', data: [{ yAxis: Math.round(avg), lineStyle: { color: isDark.value ? '#4b5563' : '#d1d5db', type: 'dashed' as const, width: 1 }, label: { show: true, formatter: `Avg ${fmtShort(avg)}`, position: 'insideEndTop' as const, fontSize: 10, color: isDark.value ? '#6b7280' : '#9ca3af' } }] },
    }],
  }
})

function onChartClick(params: any) {
  if (params.componentType === 'markPoint' && params.data?._txnIdx !== undefined) {
    highlightedTxnIdx.value = params.data._txnIdx
    setTimeout(() => { document.getElementById(`txn-row-${params.data._txnIdx}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' }) }, 100)
  }
}

// SQL transparency
const showSummarySql = ref(false)
const showBreakdownSql = ref(false)
const showBalanceSql = ref(false)
const showAccountsSql = ref(false)

const SQL = {
  totalCash: `SELECT a.name, bs.balance
FROM balance_snapshots bs
JOIN accounts a ON bs.account_id = a.id
WHERE a.is_active = 1
  AND a.display_group = 'Cash'
  AND bs.snapshot_date = (
    SELECT MAX(snapshot_date)
    FROM balance_snapshots
    WHERE account_id = bs.account_id
  )
ORDER BY bs.balance DESC

-- Total Cash = SUM(balance)
-- Accounts count = COUNT(*)`,

  avgMonthlySpend: `SELECT
  strftime('%Y-%m', date) AS month,
  SUM(amount) AS total,
  COUNT(*) AS count
FROM transactions
WHERE amount < 0
  AND source != 'plaid'
GROUP BY month
ORDER BY month

-- Avg Monthly Spend = AVG(ABS(total)) over recent N months
-- Runway = Total Cash / Avg Monthly Spend`,

  accountBreakdown: `SELECT a.name, bs.balance,
  ROUND(bs.balance * 100.0 / SUM(bs.balance) OVER (), 1) AS pct
FROM balance_snapshots bs
JOIN accounts a ON bs.account_id = a.id
WHERE a.is_active = 1
  AND a.display_group = 'Cash'
  AND bs.snapshot_date = (
    SELECT MAX(snapshot_date)
    FROM balance_snapshots
    WHERE account_id = bs.account_id
  )
ORDER BY bs.balance DESC`,

  balanceHistory: `SELECT bs.snapshot_date, SUM(bs.balance) AS cash_total
FROM balance_snapshots bs
JOIN accounts a ON bs.account_id = a.id
WHERE a.is_active = 1
  AND a.include_in_nw = 1
  AND a.display_group = 'Cash'
GROUP BY bs.snapshot_date
ORDER BY bs.snapshot_date`,

  largeTransactions: `SELECT t.date, t.amount, t.merchant,
  t.category, a.name AS account_name
FROM transactions t
LEFT JOIN accounts a ON t.account_id = a.id
WHERE t.date >= date('now', '-N days')
  AND ABS(t.amount) >= 500
  AND t.source != 'plaid'
ORDER BY t.date DESC
LIMIT 100`,

  accountTransactions: `SELECT t.date, t.merchant, t.category, t.amount
FROM transactions t
WHERE t.account_id = :account_id
  AND t.source != 'plaid'
ORDER BY t.date DESC
LIMIT 25 OFFSET :offset`,
}

function fmt(n: number | null | undefined): string { if (n == null) return '--'; return `$${Math.round(n).toLocaleString()}` }
function fmtFull(n: number | null | undefined): string { if (n == null) return '--'; return `$${Math.round(n).toLocaleString()}` }
function fmtShort(n: number): string { return n >= 1000 ? `$${(n / 1000).toFixed(1)}K` : `$${Math.round(n)}` }
function fmtDate(d: string | null | undefined): string { if (!d) return '--'; return new Date(d.includes('T') ? d : d + 'T00:00:00').toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) }
</script>

<template>
  <div class="max-w-6xl mx-auto space-y-6">
    <!-- Header -->
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-bold text-gray-900 dark:text-white">Cash</h1>
        <p class="text-sm text-gray-500 dark:text-gray-400 mt-1">Checking & savings accounts</p>
      </div>
      <div class="flex items-center gap-3">
        <div class="flex bg-gray-100 dark:bg-gray-800 rounded-lg p-0.5">
          <button v-for="opt in TIME_OPTIONS" :key="opt.key" @click="timeRange = opt.key"
            class="px-3 py-1.5 text-xs font-medium rounded-md transition-colors"
            :class="timeRange === opt.key ? 'bg-white dark:bg-gray-700 text-gray-900 dark:text-white shadow-sm' : 'text-gray-500 dark:text-gray-400'">
            {{ opt.label }}
          </button>
        </div>
        <button @click="openData('cash')"
          class="px-3 py-1.5 text-xs font-medium bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 text-gray-600 dark:text-gray-300">
          Data
        </button>
        <button @click="syncBalances" :disabled="syncing"
          class="px-3 py-1.5 text-xs font-medium bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg hover:bg-gray-50 disabled:opacity-50">
          {{ syncing ? 'Syncing...' : 'Sync' }}
        </button>
      </div>
    </div>

    <div v-if="syncResult" class="bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-lg p-3 text-xs text-green-700 dark:text-green-400">Synced {{ syncResult.synced }} accounts.</div>

    <div v-if="loading" class="flex items-center justify-center h-64"><div class="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-500"></div></div>
    <div v-else-if="error" class="text-sm text-red-600">{{ error }}</div>
    <div v-else-if="!cashLayer" class="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-8 text-center"><p class="text-gray-500">No cash accounts found.</p></div>

    <template v-else>
      <!-- Summary Cards -->
      <div class="group/summary relative grid grid-cols-2 sm:grid-cols-4 gap-3">
        <button @click="showSummarySql = true" class="absolute top-3.5 right-3.5 z-10 p-1 rounded-md text-gray-300 dark:text-gray-600 opacity-0 group-hover/summary:opacity-100 hover:!text-indigo-500 hover:bg-indigo-50 dark:hover:bg-indigo-950/40 transition-all" title="View SQL">
          <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>
        </button>
        <SqlViewerModal :open="showSummarySql" :sql="`${SQL.totalCash}\n\n---\n\n${SQL.avgMonthlySpend}`" title="Cash Summary Cards" :tables="['balance_snapshots', 'accounts', 'transactions']" @close="showSummarySql = false" />
        <div class="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-4">
          <div class="text-xs text-gray-500 dark:text-gray-400 font-medium">Total Cash <InfoTooltip text="Sum of all checking and savings account balances." /></div>
          <div class="text-2xl font-bold text-gray-900 dark:text-white mt-1">{{ fmt(totalCash) }}</div>
          <div v-if="cashChange" class="text-xs mt-1" :class="cashChange.change >= 0 ? 'text-green-600' : 'text-red-500'">
            {{ cashChange.change >= 0 ? '+' : '' }}{{ fmt(cashChange.change) }} ({{ cashChange.pct >= 0 ? '+' : '' }}{{ cashChange.pct.toFixed(1) }}%)
          </div>
        </div>
        <div class="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-4">
          <div class="text-xs text-gray-500 dark:text-gray-400 font-medium">Avg Monthly Spend <InfoTooltip text="Average monthly expenses over the selected period." /></div>
          <div class="text-2xl font-bold text-red-500 mt-1">{{ avgMonthlySpend ? fmtShort(avgMonthlySpend) : '--' }}</div>
          <div class="text-xs text-gray-400 mt-1">expenses/month</div>
        </div>
        <div class="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-4">
          <div class="text-xs text-gray-500 dark:text-gray-400 font-medium">Runway <InfoTooltip text="Months your cash would last at current spend rate. Target: 3-6 months." /></div>
          <div class="text-2xl font-bold mt-1" :class="runwayMonths && runwayMonths >= 6 ? 'text-green-600' : runwayMonths && runwayMonths >= 3 ? 'text-amber-600' : 'text-red-500'">
            {{ runwayMonths ? `${runwayMonths} mo` : '--' }}
          </div>
          <div class="text-xs text-gray-400 mt-1">at current spend</div>
        </div>
        <div class="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-4">
          <div class="text-xs text-gray-500 dark:text-gray-400 font-medium">Accounts</div>
          <div class="text-2xl font-bold text-gray-900 dark:text-white mt-1">{{ sortedAccounts.length }}</div>
          <div class="text-xs text-gray-400 mt-1">checking & savings</div>
        </div>
      </div>

      <!-- Account Breakdown (donut + bars with correlated colors) -->
      <div class="group/breakdown relative bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-5">
        <button @click="showBreakdownSql = true" class="absolute top-3.5 right-3.5 p-1 rounded-md text-gray-300 dark:text-gray-600 opacity-0 group-hover/breakdown:opacity-100 hover:!text-indigo-500 hover:bg-indigo-50 dark:hover:bg-indigo-950/40 transition-all" title="View SQL">
          <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>
        </button>
        <SqlViewerModal :open="showBreakdownSql" :sql="SQL.accountBreakdown" title="Account Breakdown" :tables="['balance_snapshots', 'accounts']" @close="showBreakdownSql = false" />
        <div class="flex items-center gap-1 mb-3">
          <h2 class="text-sm font-semibold text-gray-900 dark:text-white">Account Breakdown</h2>
          <InfoTooltip text="Distribution of cash across accounts. Colors match between the chart and the bars." />
        </div>
        <div class="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <div class="lg:col-span-1">
            <v-chart v-if="accountPieOption" :option="accountPieOption" style="height: 180px" autoresize />
          </div>
          <div class="lg:col-span-2 space-y-2.5">
            <div v-for="(account, idx) in sortedAccounts" :key="account.id" class="flex items-center gap-3">
              <div class="w-40 text-xs text-gray-700 dark:text-gray-300 truncate">{{ account.name }}</div>
              <div class="flex-1 h-5 bg-gray-100 dark:bg-gray-800 rounded-full overflow-hidden relative">
                <div class="h-full rounded-full transition-all" :style="{ width: `${totalCash > 0 ? Math.max(2, (account.balance || 0) / totalCash * 100) : 0}%`, backgroundColor: accountColor(idx) }"></div>
                <span v-if="totalCash > 0 && (account.balance || 0) / totalCash > 0.08"
                  class="absolute inset-y-0 flex items-center text-[10px] font-medium text-white"
                  :style="{ left: '8px' }">
                  {{ ((account.balance || 0) / totalCash * 100).toFixed(0) }}%
                </span>
              </div>
              <div class="w-20 text-right text-xs font-medium text-gray-900 dark:text-white">{{ fmt(account.balance) }}</div>
              <div class="w-10 text-right text-[10px] text-gray-400">{{ totalCash > 0 ? ((account.balance || 0) / totalCash * 100).toFixed(0) + '%' : '' }}</div>
            </div>
          </div>
        </div>
      </div>

      <!-- Cash Balance & Activity (chart + notable transactions) -->
      <div class="group/balance relative bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-5">
        <button @click="showBalanceSql = true" class="absolute top-3.5 right-3.5 p-1 rounded-md text-gray-300 dark:text-gray-600 opacity-0 group-hover/balance:opacity-100 hover:!text-indigo-500 hover:bg-indigo-50 dark:hover:bg-indigo-950/40 transition-all" title="View SQL">
          <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>
        </button>
        <SqlViewerModal :open="showBalanceSql" :sql="`${SQL.balanceHistory}\n\n---\n\n${SQL.largeTransactions}`" title="Cash Balance & Activity" :tables="['balance_snapshots', 'accounts', 'transactions']" @close="showBalanceSql = false" />
        <div class="flex items-center gap-1 mb-1">
          <h2 class="text-sm font-semibold text-gray-900 dark:text-white">Cash Balance & Activity</h2>
          <InfoTooltip text="Balance trend with notable transactions marked. Green = deposits, red = withdrawals. Dashed line = period average. Hover markers for details." />
        </div>
        <v-chart v-if="cashHistoryOption" :option="cashHistoryOption" style="height: 280px" autoresize @click="onChartClick" />

        <div v-if="largeTransactions.length" class="mt-4 pt-4 border-t border-gray-100 dark:border-gray-800">
          <div class="flex items-center justify-between mb-2">
            <p class="text-xs font-medium text-gray-500">Notable Transactions (>$500)</p>
            <p class="text-xs text-gray-400">{{ TIME_OPTIONS.find(o => o.key === timeRange)?.desc }}</p>
          </div>
          <div class="overflow-x-auto max-h-52 overflow-y-auto">
            <table class="w-full text-xs">
              <thead class="sticky top-0 bg-white dark:bg-gray-900">
                <tr class="border-b border-gray-100 dark:border-gray-800 text-gray-500">
                  <th class="text-left py-1.5 pr-3 font-medium">Date</th>
                  <th class="text-left py-1.5 pr-3 font-medium">Account</th>
                  <th class="text-left py-1.5 pr-3 font-medium">Merchant</th>
                  <th class="text-right py-1.5 pr-3 font-medium">Amount</th>
                  <th class="text-left py-1.5 font-medium">Category</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(txn, i) in largeTransactions" :key="i" :id="`txn-row-${i}`"
                  class="border-b border-gray-50 dark:border-gray-800 last:border-0 transition-colors"
                  :class="highlightedTxnIdx === i ? 'bg-indigo-50 dark:bg-indigo-950/30 ring-1 ring-indigo-300' : ''">
                  <td class="py-1.5 pr-3 text-gray-500 whitespace-nowrap">{{ fmtDate(txn.date) }}</td>
                  <td class="py-1.5 pr-3 text-gray-400 truncate max-w-[120px]">{{ txn.account_name || '--' }}</td>
                  <td class="py-1.5 pr-3 text-gray-900 dark:text-white">{{ txn.merchant || '--' }}</td>
                  <td class="py-1.5 pr-3 text-right font-medium whitespace-nowrap" :class="txn.amount >= 0 ? 'text-green-600' : 'text-red-500'">{{ txn.amount >= 0 ? '+' : '' }}{{ fmt(txn.amount) }}</td>
                  <td class="py-1.5 text-gray-400">{{ txn.category || '--' }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <!-- All Accounts Detail (expandable) -->
      <div class="group/accounts relative">
        <button @click="showAccountsSql = true" class="absolute top-0.5 right-0 p-1 rounded-md text-gray-300 dark:text-gray-600 opacity-0 group-hover/accounts:opacity-100 hover:!text-indigo-500 hover:bg-indigo-50 dark:hover:bg-indigo-950/40 transition-all" title="View SQL">
          <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>
        </button>
        <SqlViewerModal :open="showAccountsSql" :sql="`${SQL.totalCash}\n\n---\n\n${SQL.accountTransactions}`" title="All Accounts" :tables="['balance_snapshots', 'accounts', 'transactions']" @close="showAccountsSql = false" />
        <div class="flex items-center gap-1 mb-3">
          <h2 class="text-sm font-semibold text-gray-900 dark:text-white">All Accounts</h2>
          <InfoTooltip text="Click any account to expand and see its full transaction history." />
        </div>
        <div class="space-y-2">
          <div v-for="(account, idx) in sortedAccounts" :key="account.id"
            class="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl overflow-hidden">
            <!-- Account header row -->
            <button @click="toggleAccount(account.id)"
              class="w-full text-left px-5 py-4 flex items-center gap-4 hover:bg-gray-50 dark:hover:bg-gray-800/50 transition-colors">
              <div class="w-3 h-3 rounded-full flex-shrink-0" :style="{ backgroundColor: accountColor(idx) }"></div>
              <div class="flex-1 min-w-0">
                <div class="flex items-center gap-2">
                  <span class="font-medium text-gray-900 dark:text-white text-sm">{{ account.name }}</span>
                  <span v-if="account.institution" class="text-xs text-gray-400">{{ account.institution }}</span>
                </div>
              </div>
              <div class="text-right">
                <div class="text-sm font-semibold text-gray-900 dark:text-white">{{ fmt(account.balance) }}</div>
                <div class="text-[10px] text-gray-400">{{ totalCash > 0 ? ((account.balance || 0) / totalCash * 100).toFixed(1) + '% of total' : '' }}</div>
              </div>
              <component :is="expandedAccountId === account.id ? ChevronDown : ChevronRight" class="w-4 h-4 text-gray-400 flex-shrink-0" />
            </button>

            <!-- Expanded transaction list -->
            <div v-if="expandedAccountId === account.id" class="border-t border-gray-100 dark:border-gray-800">
              <div v-if="accountTxnLoading" class="px-5 py-6 text-xs text-gray-400 text-center">Loading transactions...</div>
              <div v-else-if="!accountTransactions.length" class="px-5 py-6 text-xs text-gray-400 text-center">No transactions found.</div>
              <div v-else>
                <table class="w-full text-xs">
                  <thead>
                    <tr class="bg-gray-50 dark:bg-gray-800/50 text-gray-500">
                      <th class="text-left px-5 py-2 font-medium">Date</th>
                      <th class="text-left px-3 py-2 font-medium">Merchant</th>
                      <th class="text-left px-3 py-2 font-medium">Category</th>
                      <th class="text-right px-5 py-2 font-medium">Amount</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="txn in accountTransactions" :key="txn.id"
                      class="border-b border-gray-50 dark:border-gray-800 last:border-0">
                      <td class="px-5 py-2 text-gray-500 whitespace-nowrap">{{ fmtDate(txn.date) }}</td>
                      <td class="px-3 py-2 text-gray-900 dark:text-white">{{ txn.merchant || '--' }}</td>
                      <td class="px-3 py-2 text-gray-400">{{ txn.category || '--' }}</td>
                      <td class="px-5 py-2 text-right font-medium whitespace-nowrap" :class="txn.amount >= 0 ? 'text-green-600' : 'text-red-500'">
                        {{ txn.amount >= 0 ? '+' : '' }}{{ fmt(txn.amount) }}
                      </td>
                    </tr>
                  </tbody>
                </table>
                <!-- Pagination -->
                <div v-if="accountTxnTotal > 25" class="flex items-center justify-between px-5 py-3 border-t border-gray-100 dark:border-gray-800">
                  <span class="text-xs text-gray-400">Page {{ accountTxnPage + 1 }} of {{ Math.ceil(accountTxnTotal / 25) }} ({{ accountTxnTotal }} transactions)</span>
                  <div class="flex gap-2">
                    <button v-if="accountTxnPage > 0" @click="loadAccountTxns(expandedAccountId!, accountTxnPage - 1)"
                      class="px-3 py-1 text-xs bg-gray-100 dark:bg-gray-800 rounded hover:bg-gray-200">Previous</button>
                    <button v-if="(accountTxnPage + 1) * 25 < accountTxnTotal" @click="loadAccountTxns(expandedAccountId!, accountTxnPage + 1)"
                      class="px-3 py-1 text-xs bg-gray-100 dark:bg-gray-800 rounded hover:bg-gray-200">Next</button>
                  </div>
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
