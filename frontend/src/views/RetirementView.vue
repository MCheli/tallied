<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { PieChart, LineChart, BarChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import PageHeader from '../components/common/PageHeader.vue'
import MetricCard from '../components/common/MetricCard.vue'
import ChartContainer from '../components/common/ChartContainer.vue'
import DataTable from '../components/common/DataTable.vue'
import InfoTooltip from '../components/common/InfoTooltip.vue'
import SqlViewerModal from '../components/common/SqlViewerModal.vue'
import DataExplorer from '../components/common/DataExplorer.vue'
import { useChartDefaults } from '../composables/useChartDefaults'
import { useFormatters } from '../composables/useFormatters'
import { useImportModal } from '../composables/useImportModal'
import { useDataExplorer } from '../composables/useDataExplorer'
import { api } from '../api/client'
import type { RetirementSummary } from '../types'

use([PieChart, LineChart, BarChart, GridComponent, TooltipComponent, LegendComponent, CanvasRenderer])

const { baseOption, COLORS, isMobile, axisLineColor, splitLineColor, mutedTextColor, mobileAxis } = useChartDefaults()
const { money, compact, percent, date: fmtDate, monthYear, dash } = useFormatters()
const { openImport } = useImportModal()
const { openData } = useDataExplorer()

/** Employee 401(k) deferral limit shown in the Contribution Rates tooltip. Update when the IRS does. */
const IRS_401K_LIMIT = { year: 2025, amount: 23_500 }

const loading = ref(true)
const error = ref('')
const data = ref<RetirementSummary | null>(null)

const showContributionRatesSql = ref(false)
const showContributionsSql = ref(false)

// ── "View SQL" (Postgres, real column names) ──
const LATEST = `(SELECT id FROM retirement_accounts ORDER BY updated_at DESC LIMIT 1)`
const SQL = {
  totalBalance: `SELECT total_balance, vested_balance\nFROM retirement_accounts\nWHERE id = ${LATEST};`,
  accountReturn: `SELECT account_return, return_period_start\nFROM retirement_accounts\nWHERE id = ${LATEST};`,
  rothBalance: `SELECT roth_balance, ROUND(roth_balance * 100.0 / total_balance, 1) AS roth_pct\nFROM retirement_accounts\nWHERE id = ${LATEST};`,
  pretaxBalance: `SELECT pretax_balance, ROUND(pretax_balance * 100.0 / total_balance, 1) AS pretax_pct\nFROM retirement_accounts\nWHERE id = ${LATEST};`,
  estMonthlyIncome: `SELECT estimated_monthly_income\nFROM retirement_accounts\nWHERE id = ${LATEST};`,
  breakdown: `SELECT roth_balance, pretax_balance, employer_match_balance, other_balance, total_balance\nFROM retirement_accounts\nWHERE id = ${LATEST};`,
  contributionRates: `SELECT pretax_deferral_rate, roth_deferral_rate\nFROM retirement_accounts\nWHERE id = ${LATEST};`,
  holdings: `SELECT fund_name, ticker, balance, allocation_pct, gain_loss\nFROM retirement_holdings\nWHERE retirement_account_id = ${LATEST}\nORDER BY balance DESC;`,
  balanceHistory: `SELECT snapshot_date, balance\nFROM retirement_snapshots\nWHERE retirement_account_id = ${LATEST}\nORDER BY snapshot_date;`,
  contributions: `SELECT total_employee_contributions, total_employer_contributions, roth_basis, roth_balance\nFROM retirement_accounts\nWHERE id = ${LATEST};`,
}

async function fetchData() {
  loading.value = true
  error.value = ''
  try {
    data.value = await api.retirement.getSummary()
  } catch (e: any) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

onMounted(fetchData)

const account = computed(() => data.value?.account ?? null)
const breakdown = computed(() => data.value?.balance_breakdown)
const holdings = computed(() => data.value?.holdings || [])
const snapshots = computed(() => data.value?.snapshots || [])
const providerName = computed(() => account.value?.provider || 'your plan provider')

// ── Rate editing ──
const editingRates = ref(false)
const editPretax = ref(0)
const editRoth = ref(0)
const rateError = ref('')

function startEditRates() {
  editPretax.value = Math.round((account.value?.pretax_deferral_rate || 0) * 100)
  editRoth.value = Math.round((account.value?.roth_deferral_rate || 0) * 100)
  rateError.value = ''
  editingRates.value = true
}

async function saveRates() {
  try {
    await api.retirement.updateRates(editPretax.value / 100, editRoth.value / 100)
    editingRates.value = false
    await fetchData()
  } catch (e: any) {
    rateError.value = e.message
  }
}

// ── Charts ──
const BREAKDOWN_COLORS = { roth: COLORS[1], pretax: COLORS[0], employer: COLORS[2], other: mutedTextColor }

const breakdownBarOption = computed(() => {
  const bd = breakdown.value
  if (!bd) return null
  const total = (bd.roth || 0) + (bd.pretax || 0) + (bd.employer || 0) + (bd.other || 0)
  if (total <= 0) return null
  const seg = (name: string, value: number, color: string) => ({
    name, type: 'bar', stack: 'total', data: [value], itemStyle: { color }, barWidth: 36,
    label: { show: value > total * 0.12, position: 'inside' as const, formatter: () => compact(value), fontSize: 11, color: '#fff', fontWeight: 'bold' as const },
  })
  return {
    ...baseOption.value,
    grid: { left: 4, right: 4, top: 4, bottom: 4 },
    tooltip: { ...baseOption.value.tooltip, trigger: 'item' as const, formatter: (p: any) => `<strong>${p.seriesName}</strong><br/>${money(p.value)} (${((p.value / total) * 100).toFixed(1)}%)` },
    xAxis: { type: 'value' as const, show: false, max: total },
    yAxis: { type: 'category' as const, data: ['Balance'], show: false },
    series: [
      seg('Roth', bd.roth || 0, BREAKDOWN_COLORS.roth),
      seg('Pre-tax', bd.pretax || 0, BREAKDOWN_COLORS.pretax),
      seg('Employer match', bd.employer || 0, BREAKDOWN_COLORS.employer),
      seg('Other', bd.other || 0, BREAKDOWN_COLORS.other.value),
    ],
  }
})

const historyChartOption = computed(() => ({
  ...baseOption.value,
  tooltip: {
    ...baseOption.value.tooltip,
    formatter: (params: any) => {
      const p = Array.isArray(params) ? params[0] : params
      return `<strong>${monthYear(p.name)}</strong><br/>Balance: ${money(p.value)}`
    },
  },
  xAxis: {
    type: 'category' as const,
    data: snapshots.value.map(s => s.date),
    axisLabel: { ...mobileAxis(), formatter: (v: string) => monthYear(v) },
    axisTick: { show: false },
    axisLine: { lineStyle: { color: axisLineColor.value } },
  },
  yAxis: { type: 'value' as const, axisLabel: { ...mobileAxis(), formatter: (v: number) => compact(v) }, splitLine: { lineStyle: { color: splitLineColor.value, type: 'dashed' as const } } },
  series: [{
    type: 'line', data: snapshots.value.map(s => s.balance), smooth: true, symbol: 'circle', symbolSize: 6,
    lineStyle: { width: 2.5, color: COLORS[0] },
    areaStyle: { color: { type: 'linear' as const, x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: 'rgba(99,102,241,0.15)' }, { offset: 1, color: 'rgba(99,102,241,0.02)' }] } },
  }],
}))

const allocationPieOption = computed(() => {
  if (holdings.value.length <= 1) return null
  return {
    ...baseOption.value,
    tooltip: { ...baseOption.value.tooltip, trigger: 'item' as const, formatter: (p: any) => `<strong>${p.name}</strong><br/>${money(p.value)} (${p.percent.toFixed(1)}%)` },
    series: [{
      type: 'pie', radius: ['40%', '70%'], center: ['50%', '50%'], avoidLabelOverlap: true,
      label: { show: !isMobile.value, formatter: '{b}\n{d}%', fontSize: 11, color: mutedTextColor.value },
      labelLine: { show: !isMobile.value },
      data: holdings.value.map(h => ({ value: h.balance || 0, name: h.ticker || h.fund_name })),
    }],
  }
})
</script>

<template>
  <div class="max-w-6xl mx-auto space-y-6 min-w-0">
    <PageHeader
      title="401(k)"
      :subtitle="account ? [account.plan_name, account.provider].filter(Boolean).join(' · ') : 'Retirement account from your statements'"
      tooltip="<strong>401(k)</strong><br>Balances, rates and holdings come from the newest statement you imported; an older statement only adds a history point. The balance here is also what net worth and Planning use for the account."
    >
      <button @click="openData('retirement')" class="min-h-10 px-4 py-2 text-xs font-medium bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 text-gray-600 dark:text-gray-300">Data</button>
      <button @click="openImport({ context: 'retirement', onComplete: fetchData })" class="min-h-10 px-4 py-2 text-xs font-medium bg-indigo-600 text-white rounded-lg hover:bg-indigo-700">Import</button>
    </PageHeader>

    <div v-if="loading" class="text-sm text-gray-400">Loading retirement data...</div>
    <div v-else-if="error" class="text-sm text-red-500">{{ error }}</div>

    <div v-else-if="!account" class="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-12 text-center">
      <p class="text-lg font-medium text-gray-600 dark:text-gray-300 mb-2">No retirement data yet</p>
      <p class="text-sm text-gray-400 dark:text-gray-500">Import a 401(k) statement (PDF) to get started.</p>
    </div>

    <template v-else>
      <!-- Tiles -->
      <div class="grid grid-cols-2 lg:grid-cols-5 gap-3">
        <MetricCard label="Total Balance" :value="compact(account.total_balance)" :subtitle="`Vested ${compact(account.vested_balance)}`"
          :info="`<strong>Total balance</strong><br>Roth + pre-tax + employer match + other, as of the newest statement.<br><br><strong>Source:</strong> ${providerName} statement (statement end ${fmtDate(account.statement_end)}).`"
          :sql="SQL.totalBalance" :sql-tables="['retirement_accounts']" />
        <MetricCard label="Account Return" :value="percent(account.account_return)" :subtitle="`Since ${fmtDate(account.return_period_start)}`"
          info="<strong>Account return</strong><br>Total return reported on the statement since the return period start: market gains, dividends and fund appreciation."
          :sql="SQL.accountReturn" :sql-tables="['retirement_accounts']" />
        <MetricCard label="Roth Balance" :value="compact(breakdown?.roth)" :subtitle="`${Math.round(breakdown?.roth_pct || 0)}% of total`"
          info="<strong>Roth 401(k)</strong><br>After-tax contributions that grow tax-free; qualified withdrawals are tax-free. The Roth basis (what you put in) is under Contributions."
          :sql="SQL.rothBalance" :sql-tables="['retirement_accounts']" />
        <MetricCard label="Pre-tax Balance" :value="compact(breakdown?.pretax)" :subtitle="`${Math.round(breakdown?.pretax_pct || 0)}% of total`"
          info="<strong>Pre-tax 401(k)</strong><br>Contributions that reduced taxable income when made; withdrawals are taxed as ordinary income."
          :sql="SQL.pretaxBalance" :sql-tables="['retirement_accounts']" />
        <div class="col-span-2 lg:col-span-1 min-w-0">
          <MetricCard label="Est. Monthly Income" :value="compact(account.estimated_monthly_income)" subtitle="At retirement"
            :info="`<strong>Estimated monthly income</strong><br>The retirement income projection printed on the ${providerName} statement. It is their estimate, not Tallied's; the Planning page has Tallied's projection.`"
            :sql="SQL.estMonthlyIncome" :sql-tables="['retirement_accounts']" />
        </div>
      </div>

      <div class="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div class="lg:col-span-2 space-y-4 min-w-0">
          <!-- Breakdown -->
          <ChartContainer title="Balance Breakdown" subtitle="Roth · pre-tax · employer match · other"
            info="<strong>Balance breakdown</strong><br>How the balance splits by money type: Roth (after-tax, tax-free growth), pre-tax (taxed at withdrawal), employer match (taxed at withdrawal), other (rollovers etc.)."
            :sql="SQL.breakdown" :sql-tables="['retirement_accounts']" :empty="!breakdownBarOption" empty-text="No balance on the newest statement">
            <div style="height: 64px"><VChart v-if="breakdownBarOption" :option="breakdownBarOption" autoresize /></div>
            <div class="flex flex-wrap gap-x-4 gap-y-1 mt-3 text-xs text-gray-500 dark:text-gray-400">
              <span class="flex items-center gap-1.5"><span class="w-2.5 h-2.5 rounded-sm" :style="{ background: BREAKDOWN_COLORS.roth }"></span>Roth {{ Math.round(breakdown?.roth_pct || 0) }}%</span>
              <span class="flex items-center gap-1.5"><span class="w-2.5 h-2.5 rounded-sm" :style="{ background: BREAKDOWN_COLORS.pretax }"></span>Pre-tax {{ Math.round(breakdown?.pretax_pct || 0) }}%</span>
              <span class="flex items-center gap-1.5"><span class="w-2.5 h-2.5 rounded-sm" :style="{ background: BREAKDOWN_COLORS.employer }"></span>Employer {{ Math.round(breakdown?.employer_pct || 0) }}%</span>
              <span v-if="(breakdown?.other || 0) > 0" class="flex items-center gap-1.5"><span class="w-2.5 h-2.5 rounded-sm" :style="{ background: BREAKDOWN_COLORS.other.value }"></span>Other</span>
            </div>
          </ChartContainer>

          <!-- Contribution rates -->
          <div class="group/rates relative bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-5 min-w-0">
            <button @click="showContributionRatesSql = true" class="sql-btn absolute top-1 right-1 w-10 h-10 flex items-center justify-center rounded-md text-gray-300 dark:text-gray-600 opacity-0 group-hover/rates:opacity-100 focus-visible:opacity-100 hover:!text-indigo-500 transition-all" title="View SQL" aria-label="View SQL">
              <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>
            </button>
            <SqlViewerModal :open="showContributionRatesSql" :sql="SQL.contributionRates" title="Contribution Rates" :tables="['retirement_accounts']" @close="showContributionRatesSql = false" />
            <div class="flex items-center justify-between mb-3 pr-8 gap-2">
              <h3 class="text-sm font-semibold text-gray-900 dark:text-white">Contribution Rates <InfoTooltip :text="`<strong>Contribution rates</strong><br>Your deferral elections as a percentage of salary, from the statement; edit them here when you change them with ${providerName}.<br><br>The IRS employee deferral limit is ${money(IRS_401K_LIMIT.amount)} for ${IRS_401K_LIMIT.year}.`" /></h3>
              <button v-if="!editingRates" @click="startEditRates" class="min-h-10 px-2 text-xs text-indigo-600 dark:text-indigo-400 hover:underline">Edit</button>
            </div>
            <template v-if="!editingRates">
              <div class="grid grid-cols-2 gap-4">
                <div class="bg-gray-50 dark:bg-gray-800/50 rounded-lg p-4"><div class="text-xs text-gray-500 dark:text-gray-400 font-medium">Pre-tax deferral</div><div class="text-2xl font-bold text-indigo-600 dark:text-indigo-400 mt-1">{{ Math.round((account.pretax_deferral_rate || 0) * 100) }}%</div><div class="text-xs text-gray-400 mt-1">of salary</div></div>
                <div class="bg-gray-50 dark:bg-gray-800/50 rounded-lg p-4"><div class="text-xs text-gray-500 dark:text-gray-400 font-medium">Roth deferral</div><div class="text-2xl font-bold text-green-600 dark:text-green-400 mt-1">{{ Math.round((account.roth_deferral_rate || 0) * 100) }}%</div><div class="text-xs text-gray-400 mt-1">of salary</div></div>
              </div>
              <p class="text-xs text-gray-400 mt-3">Total deferral: {{ Math.round(((account.pretax_deferral_rate || 0) + (account.roth_deferral_rate || 0)) * 100) }}% + employer match</p>
            </template>
            <template v-else>
              <div class="grid grid-cols-2 gap-4">
                <div class="bg-gray-50 dark:bg-gray-800/50 rounded-lg p-4"><label class="text-xs text-gray-500 dark:text-gray-400 font-medium block mb-1">Pre-tax deferral (%)</label><input v-model.number="editPretax" type="number" min="0" max="100" step="1" class="w-full min-h-10 px-3 py-2 text-lg font-bold text-indigo-600 dark:text-indigo-400 bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-lg" /></div>
                <div class="bg-gray-50 dark:bg-gray-800/50 rounded-lg p-4"><label class="text-xs text-gray-500 dark:text-gray-400 font-medium block mb-1">Roth deferral (%)</label><input v-model.number="editRoth" type="number" min="0" max="100" step="1" class="w-full min-h-10 px-3 py-2 text-lg font-bold text-green-600 dark:text-green-400 bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-lg" /></div>
              </div>
              <p v-if="rateError" class="text-xs text-red-500 mt-2">{{ rateError }}</p>
              <div class="flex items-center justify-between mt-3 gap-2 flex-wrap">
                <p class="text-xs text-gray-400">Total: {{ editPretax + editRoth }}% + employer match</p>
                <div class="flex gap-2">
                  <button @click="editingRates = false" class="min-h-10 px-3 py-1.5 text-xs text-gray-500 hover:text-gray-700">Cancel</button>
                  <button @click="saveRates" class="min-h-10 px-3 py-1.5 text-xs font-medium bg-indigo-600 text-white rounded-lg hover:bg-indigo-700">Save</button>
                </div>
              </div>
            </template>
          </div>
        </div>

        <!-- Holdings -->
        <ChartContainer :title="allocationPieOption ? 'Asset Allocation' : 'Holdings'" :subtitle="`${holdings.length} fund${holdings.length === 1 ? '' : 's'} on the statement`"
          :info="`<strong>Holdings</strong><br>The funds the account is invested in and each one's share of the balance, from the ${providerName} statement. Live prices are from Yahoo Finance when the ticker is known.`"
          :sql="SQL.holdings" :sql-tables="['retirement_holdings', 'retirement_accounts']" :empty="holdings.length === 0" empty-text="No holdings on the statement">
          <div v-if="allocationPieOption" style="height: 200px"><VChart :option="allocationPieOption" autoresize /></div>
          <div class="space-y-3" :class="{ 'mt-3': allocationPieOption }">
            <div v-for="h in holdings" :key="h.id" class="bg-gray-50 dark:bg-gray-800/50 rounded-lg p-3 min-w-0">
              <div class="flex items-start justify-between gap-2 min-w-0">
                <div class="min-w-0">
                  <div class="text-xs font-medium text-gray-900 dark:text-white truncate" :title="h.fund_name">{{ h.fund_name }}</div>
                  <div class="text-xs text-gray-400 mt-0.5 whitespace-nowrap"><span v-if="h.ticker" class="font-mono text-indigo-600 dark:text-indigo-400">{{ h.ticker }}</span><span v-if="h.allocation_pct != null"> · {{ Math.round(h.allocation_pct * 100) }}%</span></div>
                </div>
                <div class="text-right flex-shrink-0 whitespace-nowrap">
                  <div class="text-xs font-bold text-gray-900 dark:text-white">{{ money(h.balance) }}</div>
                  <div v-if="h.live_price" class="text-xs text-gray-400 mt-0.5">{{ money(h.live_price, { cents: true }) }}/share</div>
                </div>
              </div>
              <div v-if="h.gain_loss != null" class="mt-1.5 text-xs" :class="h.gain_loss >= 0 ? 'text-green-600 dark:text-green-400' : 'text-red-500'">{{ h.gain_loss >= 0 ? '+' : '' }}{{ money(h.gain_loss) }} gain/loss</div>
            </div>
          </div>
        </ChartContainer>
      </div>

      <!-- Holdings table -->
      <ChartContainer v-if="holdings.length > 0" title="Holdings Detail" subtitle="Balances, allocation and gain/loss per fund"
        info="<strong>Holdings detail</strong><br>Every fund on the statement with its balance, allocation and reported gain/loss. Live price is Yahoo Finance's latest quote for the ticker."
        :sql="SQL.holdings" :sql-tables="['retirement_holdings', 'retirement_accounts']">
        <DataTable dense :columns="6">
          <thead>
            <tr><th>Fund</th><th>Ticker</th><th class="text-right">Balance</th><th class="text-right">Allocation</th><th class="text-right">Gain/Loss</th><th class="text-right">Live Price</th></tr>
          </thead>
          <tbody>
            <tr v-for="h in holdings" :key="'tbl-' + h.id" class="text-xs">
              <td class="text-gray-900 dark:text-white font-medium">{{ h.fund_name }}</td>
              <td><span v-if="h.ticker" class="font-mono text-indigo-600 dark:text-indigo-400">{{ h.ticker }}</span><span v-else class="text-gray-400">{{ dash }}</span></td>
              <td class="text-right text-gray-900 dark:text-white font-medium whitespace-nowrap">{{ money(h.balance) }}</td>
              <td class="text-right text-gray-500 dark:text-gray-400">{{ h.allocation_pct != null ? Math.round(h.allocation_pct * 100) + '%' : dash }}</td>
              <td class="text-right whitespace-nowrap" :class="(h.gain_loss || 0) >= 0 ? 'text-green-600 dark:text-green-400' : 'text-red-500'">{{ h.gain_loss != null ? (h.gain_loss >= 0 ? '+' : '') + money(h.gain_loss) : dash }}</td>
              <td class="text-right text-gray-500 dark:text-gray-400 whitespace-nowrap">{{ h.live_price != null ? money(h.live_price, { cents: true }) : dash }}</td>
            </tr>
          </tbody>
        </DataTable>
      </ChartContainer>

      <!-- Balance history -->
      <ChartContainer title="Balance History" subtitle="One point per imported statement"
        info="<strong>Balance history</strong><br>The balance at the end of each statement you imported. Import more statements (older ones are fine) to extend the line."
        :sql="SQL.balanceHistory" :sql-tables="['retirement_snapshots', 'retirement_accounts']" :empty="snapshots.length === 0" empty-text="No statements imported yet">
        <div v-if="snapshots.length > 1" style="height: 240px"><VChart :option="historyChartOption" autoresize /></div>
        <div v-else class="flex flex-col items-center justify-center py-8">
          <div class="text-2xl font-bold text-gray-900 dark:text-white mb-1">{{ money(snapshots[0].balance) }}</div>
          <div class="text-xs text-gray-400">{{ fmtDate(snapshots[0].date) }}</div>
          <p class="text-xs text-gray-400 mt-3">Import another statement to see the trend.</p>
        </div>
      </ChartContainer>

      <!-- Contributions -->
      <div class="group/contrib relative bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-5 min-w-0">
        <button @click="showContributionsSql = true" class="sql-btn absolute top-1 right-1 w-10 h-10 flex items-center justify-center rounded-md text-gray-300 dark:text-gray-600 opacity-0 group-hover/contrib:opacity-100 focus-visible:opacity-100 hover:!text-indigo-500 transition-all" title="View SQL" aria-label="View SQL">
          <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>
        </button>
        <SqlViewerModal :open="showContributionsSql" :sql="SQL.contributions" title="Contributions" :tables="['retirement_accounts']" @close="showContributionsSql = false" />
        <h3 class="text-sm font-semibold text-gray-900 dark:text-white mb-3 pr-8">Contributions <InfoTooltip :text="`<strong>Contributions</strong><br>Employee and employer totals as ${providerName} reports them, which usually means since the plan moved to this provider rather than your whole career. Roth basis is the lifetime after-tax amount you contributed, which you may withdraw without penalty.`" /></h3>
        <div class="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <div class="bg-gray-50 dark:bg-gray-800/50 rounded-lg p-4"><div class="text-xs text-gray-500 dark:text-gray-400 font-medium">Employee (with {{ providerName }})</div><div class="text-lg font-bold text-gray-900 dark:text-white mt-1">{{ money(account.total_employee_contributions) }}</div><div class="text-xs text-gray-400 mt-1">Your contributions at the current provider</div></div>
          <div class="bg-gray-50 dark:bg-gray-800/50 rounded-lg p-4"><div class="text-xs text-gray-500 dark:text-gray-400 font-medium">Employer (with {{ providerName }})</div><div class="text-lg font-bold text-gray-900 dark:text-white mt-1">{{ money(account.total_employer_contributions) }}</div><div class="text-xs text-gray-400 mt-1">Company match at the current provider</div></div>
          <div class="bg-gray-50 dark:bg-gray-800/50 rounded-lg p-4">
            <div class="text-xs text-gray-500 dark:text-gray-400 font-medium">Roth basis (lifetime) <InfoTooltip :text="`<strong>Roth basis</strong><br>Lifetime after-tax Roth contributions, excluding growth. Roth balance ${money(breakdown?.roth)} − basis ${money(account.roth_basis)} = ${money((breakdown?.roth || 0) - (account.roth_basis || 0))} of tax-free growth.`" /></div>
            <div class="text-lg font-bold text-green-600 dark:text-green-400 mt-1">{{ money(account.roth_basis) }}</div>
            <div class="text-xs text-gray-400 mt-1">Growth on Roth: {{ money((breakdown?.roth || 0) - (account.roth_basis || 0)) }}</div>
          </div>
        </div>
      </div>

      <div v-if="account.statement_start || account.updated_at" class="text-xs text-gray-400 text-center pb-4">
        <span v-if="account.statement_start && account.statement_end">Statement period: {{ fmtDate(account.statement_start) }} – {{ fmtDate(account.statement_end) }}</span>
        <span v-if="account.updated_at"> · Last updated: {{ fmtDate(account.updated_at.slice(0, 10)) }}</span>
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
