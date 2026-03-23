<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { PieChart, LineChart, BarChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import InfoTooltip from '../components/common/InfoTooltip.vue'
import SqlViewerModal from '../components/common/SqlViewerModal.vue'
import { useChartDefaults } from '../composables/useChartDefaults'
import { useImportModal } from '../composables/useImportModal'

use([PieChart, LineChart, BarChart, GridComponent, TooltipComponent, LegendComponent, CanvasRenderer])

const { baseOption, isDark } = useChartDefaults()
const { openImport } = useImportModal()
const API = import.meta.env.VITE_API_URL || 'http://localhost:8000'

const loading = ref(true)
const error = ref('')
const data = ref<any>(null)

// ── SQL viewer state ──
const showTotalBalanceSql = ref(false)
const showAccountReturnSql = ref(false)
const showRothBalanceSql = ref(false)
const showPretaxBalanceSql = ref(false)
const showEstMonthlyIncomeSql = ref(false)
const showBreakdownSql = ref(false)
const showContributionRatesSql = ref(false)
const showHoldingsSql = ref(false)
const showHoldingsDetailSql = ref(false)
const showBalanceHistorySql = ref(false)
const showContributionsSql = ref(false)

// ── SQL queries ──
const SQL = {
  totalBalance: `SELECT
  ra.total_balance,
  ra.vested_balance
FROM retirement_accounts ra
WHERE ra.id = (
  SELECT id FROM retirement_accounts
  ORDER BY updated_at DESC LIMIT 1
)`,

  accountReturn: `SELECT
  ra.account_return,
  ra.return_period_start
FROM retirement_accounts ra
WHERE ra.id = (
  SELECT id FROM retirement_accounts
  ORDER BY updated_at DESC LIMIT 1
)`,

  rothBalance: `SELECT
  ra.roth_balance AS roth,
  ROUND(ra.roth_balance * 100.0 / ra.total_balance, 1) AS roth_pct
FROM retirement_accounts ra
WHERE ra.id = (
  SELECT id FROM retirement_accounts
  ORDER BY updated_at DESC LIMIT 1
)`,

  pretaxBalance: `SELECT
  ra.pretax_balance AS pretax,
  ROUND(ra.pretax_balance * 100.0 / ra.total_balance, 1) AS pretax_pct
FROM retirement_accounts ra
WHERE ra.id = (
  SELECT id FROM retirement_accounts
  ORDER BY updated_at DESC LIMIT 1
)`,

  estMonthlyIncome: `SELECT
  ra.estimated_monthly_income
FROM retirement_accounts ra
WHERE ra.id = (
  SELECT id FROM retirement_accounts
  ORDER BY updated_at DESC LIMIT 1
)`,

  breakdown: `SELECT
  ra.roth_balance AS roth,
  ra.pretax_balance AS pretax,
  ra.employer_balance AS employer,
  ra.other_balance AS other,
  ra.total_balance
FROM retirement_accounts ra
WHERE ra.id = (
  SELECT id FROM retirement_accounts
  ORDER BY updated_at DESC LIMIT 1
)`,

  contributionRates: `SELECT
  ra.pretax_deferral_rate,
  ra.roth_deferral_rate
FROM retirement_accounts ra
WHERE ra.id = (
  SELECT id FROM retirement_accounts
  ORDER BY updated_at DESC LIMIT 1
)`,

  holdings: `SELECT
  rh.fund_name,
  rh.ticker,
  rh.balance,
  rh.allocation_pct,
  rh.gain_loss
FROM retirement_holdings rh
JOIN retirement_accounts ra ON rh.account_id = ra.id
WHERE ra.id = (
  SELECT id FROM retirement_accounts
  ORDER BY updated_at DESC LIMIT 1
)
ORDER BY rh.balance DESC`,

  balanceHistory: `SELECT
  rs.date,
  rs.balance
FROM retirement_snapshots rs
JOIN retirement_accounts ra ON rs.account_id = ra.id
WHERE ra.id = (
  SELECT id FROM retirement_accounts
  ORDER BY updated_at DESC LIMIT 1
)
ORDER BY rs.date ASC`,

  contributions: `SELECT
  ra.total_employee_contributions,
  ra.total_employer_contributions,
  ra.roth_basis,
  ra.roth_balance
FROM retirement_accounts ra
WHERE ra.id = (
  SELECT id FROM retirement_accounts
  ORDER BY updated_at DESC LIMIT 1
)`,
}

onMounted(async () => {
  await fetchData()
})

async function fetchData() {
  loading.value = true
  error.value = ''
  try {
    const res = await fetch(`${API}/api/v1/retirement/summary`, { credentials: 'include' })
    if (res.ok) {
      data.value = await res.json()
    } else if (res.status === 404) {
      data.value = null
    } else {
      throw new Error(`Failed to load retirement data (${res.status})`)
    }
  } catch (e: any) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

// ── Rate editing ──
const editingRates = ref(false)
const editPretax = ref(0)
const editRoth = ref(0)

function startEditRates() {
  editPretax.value = Math.round((account.value?.pretax_deferral_rate || 0) * 100)
  editRoth.value = Math.round((account.value?.roth_deferral_rate || 0) * 100)
  editingRates.value = true
}

async function saveRates() {
  try {
    const res = await fetch(`${API}/api/v1/retirement/rates`, {
      method: 'PUT',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        pretax_deferral_rate: editPretax.value / 100,
        roth_deferral_rate: editRoth.value / 100,
      }),
    })
    if (!res.ok) throw new Error('Failed to save')
    editingRates.value = false
    await fetchData()
  } catch (e: any) {
    error.value = e.message
  }
}

// ── Format helpers ──


function fmtFull(n: number | null | undefined): string {
  if (n === null || n === undefined) return '--'
  return `$${Math.round(n).toLocaleString()}`
}

function fmtPct(n: number | null | undefined, alreadyDecimal = true): string {
  if (n === null || n === undefined) return '--'
  const val = alreadyDecimal ? n * 100 : n
  return `${val.toFixed(1)}%`
}

function fmtPctWhole(n: number | null | undefined, alreadyDecimal = true): string {
  if (n === null || n === undefined) return '--'
  const val = alreadyDecimal ? n * 100 : n
  return `${Math.round(val)}%`
}

function fmtDate(d: string | null | undefined): string {
  if (!d) return '--'
  return new Date(d + 'T00:00:00').toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

// ── Computed values ──

const account = computed(() => data.value?.account)
const breakdown = computed(() => data.value?.balance_breakdown)
const holdings = computed(() => data.value?.holdings || [])
const snapshots = computed(() => data.value?.snapshots || [])

// ── Balance Breakdown Stacked Bar ──

const breakdownBarOption = computed(() => {
  if (!breakdown.value) return null

  const bd = breakdown.value
  const total = (bd.roth || 0) + (bd.pretax || 0) + (bd.employer || 0) + (bd.other || 0)
  if (total <= 0) return null

  return {
    ...baseOption.value,
    grid: { left: 10, right: 10, top: 10, bottom: 30 },
    tooltip: {
      ...baseOption.value.tooltip,
      trigger: 'item' as const,
      formatter: (params: any) => {
        return `<strong>${params.seriesName}</strong><br/>${fmtFull(params.value)} (${((params.value / total) * 100).toFixed(1)}%)`
      },
    },
    xAxis: {
      type: 'value' as const,
      show: false,
      max: total,
    },
    yAxis: {
      type: 'category' as const,
      data: ['Balance'],
      show: false,
    },
    series: [
      {
        name: 'Roth',
        type: 'bar',
        stack: 'total',
        data: [bd.roth || 0],
        itemStyle: { color: '#22c55e' },
        barWidth: 36,
        label: {
          show: (bd.roth || 0) > total * 0.08,
          position: 'inside' as const,
          formatter: () => fmtFull(bd.roth),
          fontSize: 11,
          color: '#fff',
          fontWeight: 'bold' as const,
        },
      },
      {
        name: 'Pretax',
        type: 'bar',
        stack: 'total',
        data: [bd.pretax || 0],
        itemStyle: { color: '#6366f1' },
        barWidth: 36,
        label: {
          show: (bd.pretax || 0) > total * 0.08,
          position: 'inside' as const,
          formatter: () => fmtFull(bd.pretax),
          fontSize: 11,
          color: '#fff',
          fontWeight: 'bold' as const,
        },
      },
      {
        name: 'Employer Match',
        type: 'bar',
        stack: 'total',
        data: [bd.employer || 0],
        itemStyle: { color: '#f59e0b' },
        barWidth: 36,
        label: {
          show: (bd.employer || 0) > total * 0.08,
          position: 'inside' as const,
          formatter: () => fmtFull(bd.employer),
          fontSize: 11,
          color: '#fff',
          fontWeight: 'bold' as const,
        },
      },
      {
        name: 'Other',
        type: 'bar',
        stack: 'total',
        data: [bd.other || 0],
        itemStyle: { color: '#9ca3af' },
        barWidth: 36,
        label: {
          show: (bd.other || 0) > total * 0.08,
          position: 'inside' as const,
          formatter: () => fmtFull(bd.other),
          fontSize: 11,
          color: '#fff',
          fontWeight: 'bold' as const,
        },
      },
    ],
  }
})

// ── Balance History Line Chart ──

const historyChartOption = computed(() => {
  if (snapshots.value.length === 0) return null

  const dates = snapshots.value.map((s: any) => s.date)
  const balances = snapshots.value.map((s: any) => s.balance)

  return {
    ...baseOption.value,
    grid: { left: 65, right: 20, top: 20, bottom: 30 },
    tooltip: {
      ...baseOption.value.tooltip,
      trigger: 'axis' as const,
      formatter: (params: any) => {
        const p = Array.isArray(params) ? params[0] : params
        const d = new Date(p.name + 'T00:00:00')
        const dateStr = d.toLocaleDateString('en-US', { month: 'short', year: 'numeric' })
        return `<strong>${dateStr}</strong><br/>Balance: ${fmtFull(p.value)}`
      },
    },
    xAxis: {
      type: 'category' as const,
      data: dates,
      axisLabel: {
        formatter: (v: string) => {
          const d = new Date(v + 'T00:00:00')
          return d.toLocaleDateString('en-US', { month: 'short', year: '2-digit' })
        },
      },
      axisTick: { show: false },
      axisLine: { lineStyle: { color: isDark.value ? '#374151' : '#e5e7eb' } },
    },
    yAxis: {
      type: 'value' as const,
      axisLabel: {
        formatter: (v: number) => v >= 1_000 ? `$${(v / 1_000).toFixed(0)}K` : `$${v}`,
      },
      splitLine: { lineStyle: { color: isDark.value ? '#1f2937' : '#f3f4f6', type: 'dashed' as const } },
    },
    series: [{
      type: 'line',
      data: balances,
      smooth: true,
      symbol: snapshots.value.length === 1 ? 'circle' : 'none',
      symbolSize: snapshots.value.length === 1 ? 8 : 4,
      lineStyle: { width: 2.5, color: '#6366f1' },
      areaStyle: {
        color: {
          type: 'linear' as const,
          x: 0, y: 0, x2: 0, y2: 1,
          colorStops: [
            { offset: 0, color: 'rgba(99,102,241,0.15)' },
            { offset: 1, color: 'rgba(99,102,241,0.02)' },
          ],
        },
      },
    }],
  }
})

// ── Holdings Allocation Pie (if multiple holdings) ──

const allocationPieOption = computed(() => {
  if (holdings.value.length <= 1) return null

  const pieData = holdings.value.map((h: any) => ({
    value: h.balance,
    name: h.ticker || h.fund_name,
  }))

  return {
    ...baseOption.value,
    tooltip: {
      ...baseOption.value.tooltip,
      trigger: 'item' as const,
      formatter: (params: any) => {
        return `<strong>${params.name}</strong><br/>${fmtFull(params.value)} (${params.percent.toFixed(1)}%)`
      },
    },
    series: [
      {
        type: 'pie',
        radius: ['40%', '70%'],
        center: ['50%', '50%'],
        avoidLabelOverlap: true,
        label: {
          show: true,
          formatter: '{b}\n{d}%',
          fontSize: 11,
          color: isDark.value ? '#9ca3af' : '#6b7280',
        },
        labelLine: { show: true },
        data: pieData,
      },
    ],
  }
})
</script>

<template>
  <div class="max-w-6xl mx-auto space-y-6">
    <!-- Header -->
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-bold text-gray-900 dark:text-white">401(k) Retirement</h1>
        <p v-if="account" class="text-sm text-gray-500 dark:text-gray-400 mt-1">
          {{ account.plan_name }} &middot; {{ account.provider }}
        </p>
      </div>
      <div class="flex items-center gap-3">
        <button @click="openImport({ context: 'retirement', onComplete: fetchData })"
          class="px-4 py-2 text-xs font-medium bg-purple-600 text-white rounded-lg hover:bg-purple-700">
          Import
        </button>
        <InfoTooltip text="Import a 401(k) quarterly statement. The system will extract balances, contributions, holdings, and account returns." />
      </div>
    </div>

    <div v-if="loading" class="text-sm text-gray-400">Loading retirement data...</div>
    <div v-else-if="error" class="text-sm text-red-500">{{ error }}</div>

    <!-- Empty State -->
    <div v-else-if="!account" class="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-12 text-center">
      <div class="text-gray-400 dark:text-gray-500 text-sm">
        <p class="text-lg font-medium text-gray-600 dark:text-gray-300 mb-2">No retirement data yet</p>
        <p>Upload a 401(k) statement PDF to get started.</p>
      </div>
    </div>

    <template v-else>
      <!-- Summary Cards -->
      <div class="grid grid-cols-2 sm:grid-cols-5 gap-3">
        <!-- Total Balance -->
        <div class="group/totalBal relative bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-4">
          <button @click="showTotalBalanceSql = true" class="absolute top-3.5 right-3.5 p-1 rounded-md text-gray-300 dark:text-gray-600 opacity-0 group-hover/totalBal:opacity-100 hover:!text-indigo-500 hover:bg-indigo-50 dark:hover:bg-indigo-950/40 transition-all" title="View SQL">
            <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>
          </button>
          <SqlViewerModal :open="showTotalBalanceSql" :sql="SQL.totalBalance" title="Total Balance" :tables="['retirement_accounts']" @close="showTotalBalanceSql = false" />
          <div class="text-xs text-gray-500 dark:text-gray-400 font-medium">
            Total Balance
            <InfoTooltip text="<strong>Total 401(k) Balance</strong><br>Sum of all sub-accounts: Roth, Pretax, Employer Match, and Other.<br><br><strong>Source:</strong> T. Rowe Price quarterly statement." />
          </div>
          <div class="text-xl font-bold text-green-600 dark:text-green-400 mt-1">{{ fmtFull(account.total_balance) }}</div>
          <div class="text-xs text-gray-400 mt-1">Vested: {{ fmtFull(account.vested_balance) }}</div>
        </div>

        <!-- Account Return -->
        <div class="group/acctReturn relative bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-4">
          <button @click="showAccountReturnSql = true" class="absolute top-3.5 right-3.5 p-1 rounded-md text-gray-300 dark:text-gray-600 opacity-0 group-hover/acctReturn:opacity-100 hover:!text-indigo-500 hover:bg-indigo-50 dark:hover:bg-indigo-950/40 transition-all" title="View SQL">
            <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>
          </button>
          <SqlViewerModal :open="showAccountReturnSql" :sql="SQL.accountReturn" title="Account Return" :tables="['retirement_accounts']" @close="showAccountReturnSql = false" />
          <div class="text-xs text-gray-500 dark:text-gray-400 font-medium">
            Account Return
            <InfoTooltip text="<strong>Account Return</strong><br>Total return on the account since the return period start date. Includes market gains, dividends, and fund appreciation.<br><br><strong>Period:</strong> Since the return period start shown below." />
          </div>
          <div class="text-xl font-bold mt-1" :class="(account.account_return || 0) >= 0 ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'">
            {{ fmtPct(account.account_return) }}
          </div>
          <div class="text-xs text-gray-400 mt-1">Since {{ fmtDate(account.return_period_start) }}</div>
        </div>

        <!-- Roth Balance -->
        <div class="group/rothBal relative bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-4">
          <button @click="showRothBalanceSql = true" class="absolute top-3.5 right-3.5 p-1 rounded-md text-gray-300 dark:text-gray-600 opacity-0 group-hover/rothBal:opacity-100 hover:!text-indigo-500 hover:bg-indigo-50 dark:hover:bg-indigo-950/40 transition-all" title="View SQL">
            <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>
          </button>
          <SqlViewerModal :open="showRothBalanceSql" :sql="SQL.rothBalance" title="Roth Balance" :tables="['retirement_accounts']" @close="showRothBalanceSql = false" />
          <div class="text-xs text-gray-500 dark:text-gray-400 font-medium">
            Roth Balance
            <InfoTooltip text="<strong>Roth 401(k) Balance</strong><br>After-tax contributions that grow tax-free. Withdrawals in retirement are tax-free (contributions and earnings).<br><br><strong>Roth Basis:</strong> The amount you contributed (not including growth). This is what you can withdraw penalty-free before 59.5." />
          </div>
          <div class="text-xl font-bold text-gray-900 dark:text-white mt-1">{{ fmtFull(breakdown?.roth) }}</div>
          <div class="text-xs text-gray-400 mt-1">{{ fmtPctWhole(breakdown?.roth_pct, false) }} of total</div>
        </div>

        <!-- Pretax Balance -->
        <div class="group/pretaxBal relative bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-4">
          <button @click="showPretaxBalanceSql = true" class="absolute top-3.5 right-3.5 p-1 rounded-md text-gray-300 dark:text-gray-600 opacity-0 group-hover/pretaxBal:opacity-100 hover:!text-indigo-500 hover:bg-indigo-50 dark:hover:bg-indigo-950/40 transition-all" title="View SQL">
            <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>
          </button>
          <SqlViewerModal :open="showPretaxBalanceSql" :sql="SQL.pretaxBalance" title="Pretax Balance" :tables="['retirement_accounts']" @close="showPretaxBalanceSql = false" />
          <div class="text-xs text-gray-500 dark:text-gray-400 font-medium">
            Pretax Balance
            <InfoTooltip text="<strong>Pretax 401(k) Balance</strong><br>Pre-tax contributions that reduce your current taxable income. Withdrawals in retirement are taxed as ordinary income." />
          </div>
          <div class="text-xl font-bold text-gray-900 dark:text-white mt-1">{{ fmtFull(breakdown?.pretax) }}</div>
          <div class="text-xs text-gray-400 mt-1">{{ fmtPctWhole(breakdown?.pretax_pct, false) }} of total</div>
        </div>

        <!-- Est. Monthly Income -->
        <div class="group/estIncome relative bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-4">
          <button @click="showEstMonthlyIncomeSql = true" class="absolute top-3.5 right-3.5 p-1 rounded-md text-gray-300 dark:text-gray-600 opacity-0 group-hover/estIncome:opacity-100 hover:!text-indigo-500 hover:bg-indigo-50 dark:hover:bg-indigo-950/40 transition-all" title="View SQL">
            <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>
          </button>
          <SqlViewerModal :open="showEstMonthlyIncomeSql" :sql="SQL.estMonthlyIncome" title="Est. Monthly Income" :tables="['retirement_accounts']" @close="showEstMonthlyIncomeSql = false" />
          <div class="text-xs text-gray-500 dark:text-gray-400 font-medium">
            Est. Monthly Income
            <InfoTooltip text="<strong>Estimated Monthly Income</strong><br>Projected monthly income at retirement based on current balance and assumed growth rates. This is an estimate and will change as your balance grows.<br><br><strong>Source:</strong> T. Rowe Price statement projection." />
          </div>
          <div class="text-xl font-bold text-gray-900 dark:text-white mt-1">{{ fmtFull(account.estimated_monthly_income) }}</div>
          <div class="text-xs text-gray-400 mt-1">At retirement</div>
        </div>
      </div>

      <!-- Two Column Layout -->
      <div class="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <!-- Left: 2/3 -->
        <div class="lg:col-span-2 space-y-4">
          <!-- Balance Breakdown Bar -->
          <div class="group/breakdown relative bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-5">
            <button @click="showBreakdownSql = true" class="absolute top-3.5 right-3.5 p-1 rounded-md text-gray-300 dark:text-gray-600 opacity-0 group-hover/breakdown:opacity-100 hover:!text-indigo-500 hover:bg-indigo-50 dark:hover:bg-indigo-950/40 transition-all" title="View SQL">
              <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>
            </button>
            <SqlViewerModal :open="showBreakdownSql" :sql="SQL.breakdown" title="Balance Breakdown" :tables="['retirement_accounts']" @close="showBreakdownSql = false" />
            <div class="flex items-center gap-1 mb-3">
              <h2 class="text-sm font-semibold text-gray-900 dark:text-white">Balance Breakdown</h2>
              <InfoTooltip text="<strong>Balance Breakdown</strong><br>Shows how your 401(k) balance is split across account types:<br><br><strong>Roth</strong> (green) — after-tax, tax-free growth<br><strong>Pretax</strong> (indigo) — pre-tax, taxed at withdrawal<br><strong>Employer Match</strong> (amber) — employer contributions, taxed at withdrawal<br><strong>Other</strong> (gray) — rollover or miscellaneous" />
            </div>
            <div v-if="breakdownBarOption" style="height: 80px">
              <VChart :option="breakdownBarOption" autoresize />
            </div>
            <!-- Legend -->
            <div class="flex flex-wrap gap-4 mt-3 text-xs text-gray-500 dark:text-gray-400">
              <span class="flex items-center gap-1.5">
                <span class="w-2.5 h-2.5 rounded-sm bg-green-500"></span>
                Roth {{ fmtPctWhole(breakdown?.roth_pct, false) }}
              </span>
              <span class="flex items-center gap-1.5">
                <span class="w-2.5 h-2.5 rounded-sm bg-indigo-500"></span>
                Pretax {{ fmtPctWhole(breakdown?.pretax_pct, false) }}
              </span>
              <span class="flex items-center gap-1.5">
                <span class="w-2.5 h-2.5 rounded-sm bg-amber-500"></span>
                Employer {{ fmtPctWhole(breakdown?.employer_pct, false) }}
              </span>
              <span v-if="(breakdown?.other || 0) > 0" class="flex items-center gap-1.5">
                <span class="w-2.5 h-2.5 rounded-sm bg-gray-400"></span>
                Other
              </span>
            </div>
          </div>

          <!-- Contribution Rates -->
          <div class="group/contRates relative bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-5">
            <button @click="showContributionRatesSql = true" class="absolute top-3.5 right-3.5 p-1 rounded-md text-gray-300 dark:text-gray-600 opacity-0 group-hover/contRates:opacity-100 hover:!text-indigo-500 hover:bg-indigo-50 dark:hover:bg-indigo-950/40 transition-all" title="View SQL">
              <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>
            </button>
            <SqlViewerModal :open="showContributionRatesSql" :sql="SQL.contributionRates" title="Contribution Rates" :tables="['retirement_accounts']" @close="showContributionRatesSql = false" />
            <div class="flex items-center justify-between mb-3">
              <div class="flex items-center gap-1">
                <h2 class="text-sm font-semibold text-gray-900 dark:text-white">Contribution Rates</h2>
                <InfoTooltip text="<strong>Contribution Rates</strong><br>Your current deferral elections as a percentage of salary. These can be updated directly here when you change your elections.<br><br><strong>Pretax:</strong> Reduces current taxable income<br><strong>Roth:</strong> After-tax, grows tax-free<br><br>The IRS limit for employee 401(k) deferrals is $23,500 for 2025." />
              </div>
              <button v-if="!editingRates" @click="startEditRates"
                class="text-xs text-indigo-600 dark:text-indigo-400 hover:underline">Edit</button>
            </div>

            <!-- View mode -->
            <template v-if="!editingRates">
              <div class="grid grid-cols-2 gap-4">
                <div class="bg-gray-50 dark:bg-gray-800/50 rounded-lg p-4">
                  <div class="text-xs text-gray-500 dark:text-gray-400 font-medium">Pretax Deferral</div>
                  <div class="text-2xl font-bold text-indigo-600 dark:text-indigo-400 mt-1">
                    {{ fmtPctWhole(account.pretax_deferral_rate) }}
                  </div>
                  <div class="text-xs text-gray-400 mt-1">of salary</div>
                </div>
                <div class="bg-gray-50 dark:bg-gray-800/50 rounded-lg p-4">
                  <div class="text-xs text-gray-500 dark:text-gray-400 font-medium">Roth Deferral</div>
                  <div class="text-2xl font-bold text-green-600 dark:text-green-400 mt-1">
                    {{ fmtPctWhole(account.roth_deferral_rate) }}
                  </div>
                  <div class="text-xs text-gray-400 mt-1">of salary</div>
                </div>
              </div>
              <p class="text-xs text-gray-400 mt-3">
                Total deferral: {{ fmtPctWhole((account.pretax_deferral_rate || 0) + (account.roth_deferral_rate || 0)) }} + employer match
              </p>
            </template>

            <!-- Edit mode -->
            <template v-else>
              <div class="grid grid-cols-2 gap-4">
                <div class="bg-gray-50 dark:bg-gray-800/50 rounded-lg p-4">
                  <label class="text-xs text-gray-500 dark:text-gray-400 font-medium block mb-1">Pretax Deferral (%)</label>
                  <input v-model.number="editPretax" type="number" min="0" max="100" step="1"
                    class="w-full px-3 py-2 text-lg font-bold text-indigo-600 dark:text-indigo-400 bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-lg" />
                </div>
                <div class="bg-gray-50 dark:bg-gray-800/50 rounded-lg p-4">
                  <label class="text-xs text-gray-500 dark:text-gray-400 font-medium block mb-1">Roth Deferral (%)</label>
                  <input v-model.number="editRoth" type="number" min="0" max="100" step="1"
                    class="w-full px-3 py-2 text-lg font-bold text-green-600 dark:text-green-400 bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-lg" />
                </div>
              </div>
              <div class="flex items-center justify-between mt-3">
                <p class="text-xs text-gray-400">
                  Total: {{ editPretax + editRoth }}% + employer match
                </p>
                <div class="flex gap-2">
                  <button @click="editingRates = false" class="px-3 py-1.5 text-xs text-gray-500 hover:text-gray-700">Cancel</button>
                  <button @click="saveRates" class="px-3 py-1.5 text-xs font-medium bg-indigo-600 text-white rounded-lg hover:bg-indigo-700">Save</button>
                </div>
              </div>
            </template>
          </div>
        </div>

        <!-- Right: 1/3 -->
        <div class="space-y-4">
          <!-- Asset Allocation / Holdings List -->
          <div class="group/holdings relative bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-5">
            <button @click="showHoldingsSql = true" class="absolute top-3.5 right-3.5 p-1 rounded-md text-gray-300 dark:text-gray-600 opacity-0 group-hover/holdings:opacity-100 hover:!text-indigo-500 hover:bg-indigo-50 dark:hover:bg-indigo-950/40 transition-all" title="View SQL">
              <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>
            </button>
            <SqlViewerModal :open="showHoldingsSql" :sql="SQL.holdings" title="Asset Allocation / Holdings" :tables="['retirement_holdings', 'retirement_accounts']" @close="showHoldingsSql = false" />
            <div class="flex items-center gap-1 mb-3">
              <h2 class="text-sm font-semibold text-gray-900 dark:text-white">
                {{ allocationPieOption ? 'Asset Allocation' : 'Holdings' }}
              </h2>
              <InfoTooltip text="<strong>Holdings</strong><br>The funds your 401(k) is invested in. Allocation percentage shows what portion of your total balance is in each fund.<br><br><strong>Source:</strong> T. Rowe Price statement holdings section." />
            </div>

            <!-- Pie chart if multiple holdings -->
            <div v-if="allocationPieOption" style="height: 200px">
              <VChart :option="allocationPieOption" autoresize />
            </div>

            <!-- Holdings list (always shown) -->
            <div class="space-y-3" :class="{ 'mt-3': allocationPieOption }">
              <div v-for="h in holdings" :key="h.ticker || h.fund_name"
                class="bg-gray-50 dark:bg-gray-800/50 rounded-lg p-3">
                <div class="flex items-start justify-between">
                  <div>
                    <div class="text-xs font-medium text-gray-900 dark:text-white">{{ h.fund_name }}</div>
                    <div class="text-xs text-gray-400 mt-0.5">
                      <span v-if="h.ticker" class="font-mono text-indigo-600 dark:text-indigo-400">{{ h.ticker }}</span>
                      <span v-if="h.allocation_pct != null"> &middot; {{ (h.allocation_pct * 100).toFixed(0) }}%</span>
                    </div>
                  </div>
                  <div class="text-right">
                    <div class="text-xs font-bold text-gray-900 dark:text-white">{{ fmtFull(h.balance) }}</div>
                    <div v-if="h.live_price" class="text-xs text-gray-400 mt-0.5">${{ h.live_price.toFixed(2) }}/share</div>
                  </div>
                </div>
                <div v-if="h.gain_loss != null" class="mt-1.5 text-xs"
                  :class="h.gain_loss >= 0 ? 'text-green-600 dark:text-green-400' : 'text-red-500'">
                  {{ h.gain_loss >= 0 ? '+' : '' }}{{ fmtFull(h.gain_loss) }} gain/loss
                </div>
              </div>
              <div v-if="holdings.length === 0" class="text-xs text-gray-400">No holdings data available.</div>
            </div>
          </div>
        </div>
      </div>

      <!-- Holdings Table -->
      <div v-if="holdings.length > 0" class="group/holdingsDetail relative bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-5">
        <button @click="showHoldingsDetailSql = true" class="absolute top-3.5 right-3.5 p-1 rounded-md text-gray-300 dark:text-gray-600 opacity-0 group-hover/holdingsDetail:opacity-100 hover:!text-indigo-500 hover:bg-indigo-50 dark:hover:bg-indigo-950/40 transition-all" title="View SQL">
          <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>
        </button>
        <SqlViewerModal :open="showHoldingsDetailSql" :sql="SQL.holdings" title="Holdings Detail" :tables="['retirement_holdings', 'retirement_accounts']" @close="showHoldingsDetailSql = false" />
        <div class="flex items-center gap-1 mb-3">
          <h2 class="text-sm font-semibold text-gray-900 dark:text-white">Holdings Detail</h2>
          <InfoTooltip text="<strong>Holdings Detail</strong><br>Full table of all funds in the 401(k) account with balances, allocations, and gain/loss figures.<br><br>Live prices are fetched from Yahoo Finance when available." />
        </div>
        <div class="border border-gray-100 dark:border-gray-800 rounded-lg overflow-hidden">
          <table class="w-full text-xs">
            <thead>
              <tr class="border-b border-gray-100 dark:border-gray-800 text-gray-500 dark:text-gray-400 bg-gray-50 dark:bg-gray-800/50">
                <th class="text-left px-3 py-2 font-medium">Fund</th>
                <th class="text-left px-3 py-2 font-medium">Ticker</th>
                <th class="text-right px-3 py-2 font-medium">Balance</th>
                <th class="text-right px-3 py-2 font-medium">Allocation</th>
                <th class="text-right px-3 py-2 font-medium">Gain/Loss</th>
                <th class="text-right px-3 py-2 font-medium">Live Price</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="h in holdings" :key="'tbl-' + (h.ticker || h.fund_name)"
                class="border-b border-gray-50 dark:border-gray-800/50 hover:bg-gray-50 dark:hover:bg-gray-800/30">
                <td class="px-3 py-2 text-gray-900 dark:text-white font-medium">{{ h.fund_name }}</td>
                <td class="px-3 py-2">
                  <span v-if="h.ticker" class="font-mono text-indigo-600 dark:text-indigo-400">{{ h.ticker }}</span>
                  <span v-else class="text-gray-400">--</span>
                </td>
                <td class="px-3 py-2 text-right text-gray-900 dark:text-white font-medium">{{ fmtFull(h.balance) }}</td>
                <td class="px-3 py-2 text-right text-gray-500 dark:text-gray-400">
                  {{ h.allocation_pct != null ? (h.allocation_pct * 100).toFixed(0) + '%' : '--' }}
                </td>
                <td class="px-3 py-2 text-right"
                  :class="(h.gain_loss || 0) >= 0 ? 'text-green-600 dark:text-green-400' : 'text-red-500'">
                  {{ h.gain_loss != null ? ((h.gain_loss >= 0 ? '+' : '') + fmtFull(h.gain_loss)) : '--' }}
                </td>
                <td class="px-3 py-2 text-right text-gray-500 dark:text-gray-400">
                  {{ h.live_price != null ? '$' + h.live_price.toFixed(2) : '--' }}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- Balance History -->
      <div class="group/balHistory relative bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-5">
        <button @click="showBalanceHistorySql = true" class="absolute top-3.5 right-3.5 p-1 rounded-md text-gray-300 dark:text-gray-600 opacity-0 group-hover/balHistory:opacity-100 hover:!text-indigo-500 hover:bg-indigo-50 dark:hover:bg-indigo-950/40 transition-all" title="View SQL">
          <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>
        </button>
        <SqlViewerModal :open="showBalanceHistorySql" :sql="SQL.balanceHistory" title="Balance History" :tables="['retirement_snapshots', 'retirement_accounts']" @close="showBalanceHistorySql = false" />
        <div class="flex items-center gap-1 mb-3">
          <h2 class="text-sm font-semibold text-gray-900 dark:text-white">Balance History</h2>
          <InfoTooltip text="<strong>Balance History</strong><br>Shows your 401(k) balance over time from uploaded statement snapshots. Upload more quarterly statements to build a more complete picture." />
        </div>
        <div v-if="historyChartOption && snapshots.length > 1" style="height: 240px">
          <VChart :option="historyChartOption" autoresize />
        </div>
        <div v-else-if="snapshots.length === 1" class="flex flex-col items-center justify-center py-8">
          <div class="text-2xl font-bold text-gray-900 dark:text-white mb-1">{{ fmtFull(snapshots[0].balance) }}</div>
          <div class="text-xs text-gray-400">{{ fmtDate(snapshots[0].date) }}</div>
          <p class="text-xs text-gray-400 mt-3">Upload more statements to see trends over time.</p>
        </div>
        <div v-else class="text-xs text-gray-400 py-6 text-center">
          No balance history available. Upload statements to track your balance over time.
        </div>
      </div>

      <!-- Lifetime Contributions -->
      <div class="group/contributions relative bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-5">
        <button @click="showContributionsSql = true" class="absolute top-3.5 right-3.5 p-1 rounded-md text-gray-300 dark:text-gray-600 opacity-0 group-hover/contributions:opacity-100 hover:!text-indigo-500 hover:bg-indigo-50 dark:hover:bg-indigo-950/40 transition-all" title="View SQL">
          <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>
        </button>
        <SqlViewerModal :open="showContributionsSql" :sql="SQL.contributions" title="Contributions" :tables="['retirement_accounts']" @close="showContributionsSql = false" />
        <div class="flex items-center gap-1 mb-3">
          <h2 class="text-sm font-semibold text-gray-900 dark:text-white">Contributions</h2>
          <InfoTooltip text="<strong>Contribution Totals</strong><br>Employee and employer contribution totals as reported by T. Rowe Price. These track contributions <em>since T. Rowe Price became the plan provider</em>, not total lifetime contributions across all providers.<br><br>The Roth Basis is the exception — it tracks your total lifetime Roth contributions across all providers for tax purposes." />
        </div>
        <div class="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <div class="bg-gray-50 dark:bg-gray-800/50 rounded-lg p-4">
            <div class="text-xs text-gray-500 dark:text-gray-400 font-medium">Employee (since T. Rowe Price)</div>
            <div class="text-lg font-bold text-gray-900 dark:text-white mt-1">{{ fmtFull(account.total_employee_contributions) }}</div>
            <div class="text-xs text-gray-400 mt-1">Your contributions with current provider</div>
          </div>
          <div class="bg-gray-50 dark:bg-gray-800/50 rounded-lg p-4">
            <div class="text-xs text-gray-500 dark:text-gray-400 font-medium">Employer (since T. Rowe Price)</div>
            <div class="text-lg font-bold text-gray-900 dark:text-white mt-1">{{ fmtFull(account.total_employer_contributions) }}</div>
            <div class="text-xs text-gray-400 mt-1">Company match with current provider</div>
          </div>
          <div class="bg-gray-50 dark:bg-gray-800/50 rounded-lg p-4">
            <div class="text-xs text-gray-500 dark:text-gray-400 font-medium">
              Roth Basis (lifetime)
              <InfoTooltip text="<strong>Roth Basis</strong><br>Your total lifetime after-tax (Roth) contributions across all providers since Jan 2015. This is <em>not</em> the same as your Roth balance — basis excludes investment growth.<br><br><strong>Why it matters:</strong> You can withdraw your Roth basis penalty-free at any time, even before 59½. The difference between Roth balance (\$253K) and basis (\$137K) = \$116K of tax-free investment growth." />
            </div>
            <div class="text-lg font-bold text-green-600 dark:text-green-400 mt-1">{{ fmtFull(account.roth_basis) }}</div>
            <div class="text-xs text-gray-400 mt-1">
              Growth on Roth: {{ fmtFull((breakdown?.roth || 0) - (account.roth_basis || 0)) }}
            </div>
          </div>
        </div>
      </div>

      <!-- Statement Period Footer -->
      <div v-if="account.statement_start || account.updated_at" class="text-xs text-gray-400 text-center pb-4">
        <span v-if="account.statement_start && account.statement_end">
          Statement period: {{ fmtDate(account.statement_start) }} &ndash; {{ fmtDate(account.statement_end) }}
        </span>
        <span v-if="account.updated_at"> &middot; Last updated: {{ fmtDate(account.updated_at?.substring(0, 10)) }}</span>
      </div>
    </template>
  </div>
</template>
