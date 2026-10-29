<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { LineChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import PageHeader from '../components/common/PageHeader.vue'
import MetricCard from '../components/common/MetricCard.vue'
import ChartContainer from '../components/common/ChartContainer.vue'
import InfoTooltip from '../components/common/InfoTooltip.vue'
import SqlViewerModal from '../components/common/SqlViewerModal.vue'
import DataExplorer from '../components/common/DataExplorer.vue'
import { useChartDefaults } from '../composables/useChartDefaults'
import { useFormatters } from '../composables/useFormatters'
import { useDataExplorer } from '../composables/useDataExplorer'
import { apiErrorMessage } from '../composables/useApiError'
import { valuationLabel } from '../composables/useValuationLabel'
import { api } from '../api/client'
import type { AggregateVehicleHistory, AssetsSummary, Vehicle, VehicleHistory, VehicleInput } from '../types'

use([LineChart, GridComponent, TooltipComponent, LegendComponent, CanvasRenderer])
const { baseOption, COLORS, axisLineColor, splitLineColor, mobileAxis, mobileLegend, isMobile } = useChartDefaults()
const { money, number, date: fmtDate, dash } = useFormatters()
const { openData } = useDataExplorer()

// ── SQL (Postgres) ──
const totalValueSql = `SELECT SUM(estimated_value) AS total_value, COUNT(*) AS vehicle_count
FROM vehicles;`
const totalPurchaseSql = `SELECT SUM(purchase_price) AS total_purchase_price,
       COUNT(*) AS vehicles_with_purchase_price
FROM vehicles
WHERE purchase_price IS NOT NULL;`
const totalDepreciationSql = `-- Only vehicles with both figures count
SELECT SUM(purchase_price - estimated_value) AS total_depreciation
FROM vehicles
WHERE purchase_price IS NOT NULL AND estimated_value IS NOT NULL;`
const vehiclesSql = `SELECT id, year, make, model, trim, mileage, condition, purchase_price, purchase_date,
       estimated_value, valuation_source, valuation_model, valuation_confidence, value_last_updated,
       purchase_price - estimated_value AS depreciation
FROM vehicles
ORDER BY estimated_value DESC NULLS LAST;`
const historySql = `SELECT vehicle_id, date, value, source, is_projected
FROM asset_value_histories
ORDER BY vehicle_id, date;`

// ── State ──
const loading = ref(true)
const error = ref('')
const summary = ref<AssetsSummary | null>(null)
const vehicles = computed<Vehicle[]>(() => summary.value?.vehicles ?? [])
const vehicleHistories = ref<Record<number, VehicleHistory>>({})
const aggregateHistory = ref<AggregateVehicleHistory | null>(null)
const collapsedNotes = ref<Record<number, boolean>>({})

const showAddForm = ref(false)
const addForm = ref({
  year: new Date().getFullYear(), make: '', model: '', trim: '', vin: '',
  mileage: null as number | null, condition: 'good', purchase_price: null as number | null, purchase_date: '', notes: '',
})
const addLoading = ref(false)
const addError = ref('')
const addNotice = ref('')

const editingId = ref<number | null>(null)
const editForm = ref({ mileage: null as number | null, condition: '', notes: '', purchase_price: null as number | null, purchase_date: '' })
const editLoading = ref(false)

const refreshingId = ref<number | null>(null)
const refreshErrors = ref<Record<number, string>>({})
const confirmDeleteId = ref<number | null>(null)
const showVehiclesSql = ref(false)

// ── Loading ──
onMounted(async () => {
  await fetchData()
  loading.value = false
})

async function fetchData() {
  try {
    summary.value = await api.assets.summary()
    error.value = ''
    await fetchAllHistory()
  } catch (e) {
    error.value = apiErrorMessage(e, 'Failed to load assets')
  }
}

async function fetchAllHistory() {
  try {
    const [agg, ...perVehicle] = await Promise.all([
      api.assets.aggregateHistory(),
      ...vehicles.value.map((v) => api.assets.vehicleHistory(v.id).catch(() => null)),
    ])
    aggregateHistory.value = agg
    const map: Record<number, VehicleHistory> = {}
    perVehicle.forEach((h, i) => { if (h) map[vehicles.value[i].id] = h })
    vehicleHistories.value = map
  } catch {
    aggregateHistory.value = null
  }
}

// ── Add / edit / delete ──
function resetAddForm() {
  addForm.value = { year: new Date().getFullYear(), make: '', model: '', trim: '', vin: '', mileage: null, condition: 'good', purchase_price: null, purchase_date: '', notes: '' }
  addError.value = ''
  addNotice.value = ''
}

async function addVehicle() {
  if (!addForm.value.make || !addForm.value.model || !addForm.value.year) {
    addError.value = 'Year, make and model are required.'
    return
  }
  addLoading.value = true
  addError.value = ''
  try {
    const body: VehicleInput = { year: addForm.value.year, make: addForm.value.make, model: addForm.value.model }
    if (addForm.value.trim) body.trim = addForm.value.trim
    if (addForm.value.vin) body.vin = addForm.value.vin
    if (addForm.value.mileage) body.mileage = addForm.value.mileage
    if (addForm.value.condition) body.condition = addForm.value.condition
    if (addForm.value.purchase_price) body.purchase_price = addForm.value.purchase_price
    if (addForm.value.purchase_date) body.purchase_date = addForm.value.purchase_date
    if (addForm.value.notes) body.notes = addForm.value.notes
    const created = await api.assets.createVehicle(body)
    showAddForm.value = false
    resetAddForm()
    await fetchData()
    // Value it right away; a failure shows on the card, never silently.
    await refreshValue(created.id)
  } catch (e) {
    addError.value = apiErrorMessage(e, 'Could not add the vehicle')
  } finally {
    addLoading.value = false
  }
}

function startEdit(v: Vehicle) {
  editingId.value = v.id
  editForm.value = { mileage: v.mileage, condition: v.condition || 'good', notes: v.notes || '', purchase_price: v.purchase_price, purchase_date: v.purchase_date || '' }
}

async function saveEdit(id: number) {
  editLoading.value = true
  try {
    await api.assets.updateVehicle(id, {
      mileage: editForm.value.mileage || null,
      condition: editForm.value.condition || null,
      notes: editForm.value.notes || null,
      purchase_price: editForm.value.purchase_price ? Number(editForm.value.purchase_price) : null,
      purchase_date: editForm.value.purchase_date || undefined,
    })
    editingId.value = null
    await fetchData()
  } catch (e) {
    error.value = apiErrorMessage(e, 'Could not update the vehicle')
  } finally {
    editLoading.value = false
  }
}

async function refreshValue(id: number) {
  refreshingId.value = id
  delete refreshErrors.value[id]
  try {
    await api.assets.refreshValue(id)
    await fetchData()
  } catch (e) {
    refreshErrors.value[id] = apiErrorMessage(e, 'Valuation failed')
  } finally {
    refreshingId.value = null
  }
}

async function deleteVehicle(id: number) {
  try {
    await api.assets.deleteVehicle(id)
    confirmDeleteId.value = null
    await fetchData()
  } catch (e) {
    error.value = apiErrorMessage(e, 'Could not delete the vehicle')
  }
}

// ── Formatting ──
const conditionLabels: Record<string, string> = { excellent: 'Excellent', very_good: 'Very Good', good: 'Good', fair: 'Fair', poor: 'Poor' }
function conditionColor(c: string): string {
  if (c === 'excellent' || c === 'very_good') return 'bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-400'
  if (c === 'good') return 'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-400'
  return 'bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-400'
}
const yAxisMoney = (v: number) => (v >= 1000 ? `$${(v / 1000).toFixed(0)}K` : `$${v}`)

const hasVehicles = computed(() => vehicles.value.length > 0)
const depreciationSubtitle = computed(() => {
  const s = summary.value
  if (!s) return ''
  const n = s.vehicles_with_purchase_price ?? 0
  const scope = `${n} of ${s.vehicle_count} priced`
  if (s.total_depreciation == null) return `Add purchase prices · ${scope}`
  return `${s.total_depreciation > 0 ? 'Lost' : 'Gained'} since purchase · ${scope}`
})

// ── Charts ──
const aggregateChartOption = computed(() => {
  const agg = aggregateHistory.value
  if (!agg || agg.dates.length === 0) return null
  const names = Object.keys(agg.vehicles)
  const projStart = agg.is_projected.indexOf(true)
  const series = names.flatMap((name, i) => {
    const values = agg.vehicles[name]
    const color = COLORS[i % COLORS.length]
    // null = the vehicle has no point on that date (a gap); the backend already returns it that way
    const historical = values.map((v, idx) => (projStart >= 0 && idx >= projStart ? null : v))
    const projected = values.map((v, idx) => (projStart >= 0 && idx >= projStart - 1 ? v : null))
    const out: any[] = [{ name, type: 'line', stack: 'total', areaStyle: { opacity: 0.3 }, emphasis: { focus: 'series' }, data: historical, color, symbol: 'circle', symbolSize: 4, connectNulls: false }]
    if (projStart >= 0) out.push({ name: `${name} (projected)`, type: 'line', stack: 'total-proj', areaStyle: { opacity: 0.12 }, lineStyle: { type: 'dashed' }, emphasis: { focus: 'series' }, data: projected, color, symbol: 'circle', symbolSize: 4, connectNulls: false })
    return out
  })
  return {
    ...baseOption.value,
    legend: { ...mobileLegend(), data: names },
    grid: { ...baseOption.value.grid, bottom: isMobile.value ? 44 : 36 },
    xAxis: { type: 'category', data: agg.dates.map((d) => d.substring(0, 4)), axisLabel: mobileAxis(), axisLine: { lineStyle: { color: axisLineColor.value } } },
    yAxis: { type: 'value', axisLabel: { ...mobileAxis(), formatter: yAxisMoney }, axisLine: { show: false }, splitLine: { lineStyle: { color: splitLineColor.value, type: 'dashed' } } },
    tooltip: {
      ...baseOption.value.tooltip,
      formatter: (params: any) => {
        const list = Array.isArray(params) ? params : [params]
        let html = `<div style="font-weight:600;margin-bottom:4px">${list[0]?.axisValue || ''}</div>`
        let total = 0
        for (const p of list) {
          if (p.value != null) { html += `<div>${p.marker} ${p.seriesName}: <strong>${money(Number(p.value))}</strong></div>`; total += Number(p.value) }
        }
        if (list.length > 1) html += `<div style="margin-top:4px;font-weight:600">Total: ${money(total)}</div>`
        return html
      },
    },
    series,
  }
})

function vehicleChartOption(vehicleId: number) {
  const hist = vehicleHistories.value[vehicleId]
  if (!hist || hist.history.length === 0) return null
  const entries = hist.history
  const dates = entries.map((e) => e.date.substring(0, 4))
  const lastHistIdx = entries.reduce((last, e, i) => (!e.is_projected ? i : last), -1)
  const historical = entries.map((e) => (e.is_projected ? null : e.value))
  const projected = entries.map((e, i) => (e.is_projected || i === lastHistIdx ? e.value : null))
  const series: any[] = [{ name: 'Value', type: 'line', data: historical, color: COLORS[0], symbol: 'circle', symbolSize: 3, lineStyle: { width: 2 }, areaStyle: { opacity: 0.1 } }]
  if (entries.some((e) => e.is_projected)) series.push({ name: 'Projected', type: 'line', data: projected, color: COLORS[0], symbol: 'circle', symbolSize: 3, lineStyle: { width: 2, type: 'dashed' }, areaStyle: { opacity: 0.05 } })
  return {
    ...baseOption.value,
    grid: { left: 4, right: 8, top: 8, bottom: 4, containLabel: true },
    xAxis: { type: 'category', data: dates, axisLabel: mobileAxis(), axisLine: { lineStyle: { color: axisLineColor.value } } },
    yAxis: { type: 'value', axisLabel: { ...mobileAxis(), formatter: yAxisMoney }, axisLine: { show: false }, splitLine: { lineStyle: { color: splitLineColor.value, type: 'dashed' } } },
    tooltip: { ...baseOption.value.tooltip, formatter: (params: any) => { const p = (Array.isArray(params) ? params : [params])[0]; return p && p.value != null ? `<div>${p.axisValue}: <strong>${money(Number(p.value))}</strong></div>` : '' } },
    legend: { show: false },
    series,
  }
}

function vehicleHasHistory(vehicleId: number): boolean {
  const hist = vehicleHistories.value[vehicleId]
  return !!(hist && hist.history.length > 0)
}

const inputClass = 'w-full px-3 py-2 min-h-10 text-sm border border-gray-200 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:ring-2 focus:ring-indigo-500 focus:border-transparent'
</script>

<template>
  <div class="max-w-6xl mx-auto space-y-6">
    <PageHeader
      title="Assets"
      subtitle="Vehicles and what they are worth"
      tooltip="<strong>Assets</strong><br>Vehicles with an estimated value, depreciation since purchase, and a value history. Values are Claude's estimate from year, make, model, mileage and condition; each one is labelled with its confidence, model and date."
    >
      <button @click="openData('assets')" class="px-3 py-2 min-h-10 text-xs font-medium bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 text-gray-600 dark:text-gray-300">Data</button>
      <button v-if="!showAddForm" @click="showAddForm = true; resetAddForm()" class="px-4 py-2 min-h-10 text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-700 rounded-lg transition-colors">Add Vehicle</button>
    </PageHeader>

    <div v-if="loading" class="text-sm text-gray-400">Loading assets...</div>
    <div v-else-if="error && !summary" class="text-sm text-red-500">{{ error }}</div>

    <template v-else>
      <div v-if="error" class="text-xs text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-800 rounded-lg px-3 py-2">{{ error }}</div>

      <!-- Add Vehicle -->
      <div v-if="showAddForm" class="bg-white dark:bg-gray-900 border border-indigo-200 dark:border-indigo-800 rounded-xl p-5">
        <h2 class="text-sm font-semibold text-gray-900 dark:text-white mb-4">Add Vehicle</h2>
        <div v-if="addError" class="text-sm text-red-500 mb-3">{{ addError }}</div>
        <div class="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-4">
          <label class="block text-xs font-medium text-gray-500 dark:text-gray-400">Year *<input v-model.number="addForm.year" type="number" min="1900" max="2100" :class="inputClass" class="mt-1" /></label>
          <label class="block text-xs font-medium text-gray-500 dark:text-gray-400">Make *<input v-model="addForm.make" type="text" placeholder="e.g. Toyota" :class="inputClass" class="mt-1" /></label>
          <label class="block text-xs font-medium text-gray-500 dark:text-gray-400">Model *<input v-model="addForm.model" type="text" placeholder="e.g. RAV4" :class="inputClass" class="mt-1" /></label>
          <label class="block text-xs font-medium text-gray-500 dark:text-gray-400">Trim<input v-model="addForm.trim" type="text" placeholder="e.g. XLE" :class="inputClass" class="mt-1" /></label>
        </div>
        <div class="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-4">
          <label class="block text-xs font-medium text-gray-500 dark:text-gray-400">Mileage<input v-model.number="addForm.mileage" type="number" min="0" placeholder="e.g. 85000" :class="inputClass" class="mt-1" /></label>
          <label class="block text-xs font-medium text-gray-500 dark:text-gray-400">Condition
            <select v-model="addForm.condition" :class="inputClass" class="mt-1">
              <option v-for="(label, key) in conditionLabels" :key="key" :value="key">{{ label }}</option>
            </select>
          </label>
          <label class="block text-xs font-medium text-gray-500 dark:text-gray-400">Purchase price<input v-model.number="addForm.purchase_price" type="number" min="0" placeholder="e.g. 25000" :class="inputClass" class="mt-1" /></label>
          <label class="block text-xs font-medium text-gray-500 dark:text-gray-400">Purchase date<input v-model="addForm.purchase_date" type="date" :class="inputClass" class="mt-1" /></label>
        </div>
        <div class="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-4">
          <label class="block text-xs font-medium text-gray-500 dark:text-gray-400">VIN<input v-model="addForm.vin" type="text" placeholder="optional" :class="inputClass" class="mt-1" /></label>
          <label class="block text-xs font-medium text-gray-500 dark:text-gray-400">Notes<textarea v-model="addForm.notes" rows="1" placeholder="Any details" :class="inputClass" class="mt-1"></textarea></label>
        </div>
        <p class="text-[11px] text-gray-400 mb-3">After saving, a value is estimated right away. The purchase date lets the chart start at what you paid.</p>
        <div class="flex flex-wrap items-center gap-3">
          <button @click="addVehicle" :disabled="addLoading" class="px-4 py-2 min-h-10 text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-700 rounded-lg disabled:opacity-50">{{ addLoading ? 'Saving…' : 'Save' }}</button>
          <button @click="showAddForm = false" :disabled="addLoading" class="px-4 py-2 min-h-10 text-sm font-medium text-gray-600 dark:text-gray-400 bg-gray-100 dark:bg-gray-800 hover:bg-gray-200 dark:hover:bg-gray-700 rounded-lg">Cancel</button>
        </div>
      </div>

      <!-- Value over time -->
      <ChartContainer
        v-if="hasVehicles"
        title="Vehicle Value Over Time"
        :empty="!aggregateChartOption"
        empty-text="No value history yet. Refresh a vehicle's value to build it."
        info="<strong>Vehicle Value History</strong><br>Stacked area of each vehicle's value: the purchase price (when you entered a purchase date), interpolated history to today's estimate, and five dashed projected years computed from the depreciation rate Claude expects. All of it is an estimate, not market data."
        :sql="historySql" :sql-tables="['asset_value_histories']"
      >
        <div class="h-72"><VChart v-if="aggregateChartOption" :option="aggregateChartOption" autoresize class="w-full h-full" /></div>
      </ChartContainer>

      <!-- Summary -->
      <div v-if="hasVehicles && summary" class="grid grid-cols-1 sm:grid-cols-3 gap-3 items-start">
        <MetricCard label="Total Asset Value" :value="money(summary.total_value)" :subtitle="`${summary.vehicle_count} vehicle${summary.vehicle_count !== 1 ? 's' : ''}`"
          info="<strong>Total Asset Value</strong><br>Sum of the vehicles' estimated values. Vehicles without an estimate count as zero."
          :sql="totalValueSql" :sql-tables="['vehicles']" />
        <MetricCard label="Total Purchase Price" :value="summary.total_purchase_price != null ? money(summary.total_purchase_price) : dash" subtitle="Original cost basis"
          info="<strong>Total Purchase Price</strong><br>Sum of purchase prices for the vehicles that have one."
          :sql="totalPurchaseSql" :sql-tables="['vehicles']" />
        <MetricCard label="Total Depreciation"
          :value="summary.total_depreciation != null ? (summary.total_depreciation > 0 ? '-' : '+') + money(Math.abs(summary.total_depreciation)) : dash"
          :subtitle="depreciationSubtitle"
          info="<strong>Total Depreciation</strong><br>purchase price − estimated value, summed only over vehicles that have both figures, so a vehicle without a purchase price cannot shrink the total."
          :sql="totalDepreciationSql" :sql-tables="['vehicles']" />
      </div>

      <!-- Vehicle cards -->
      <div v-if="hasVehicles" class="group/vehicles relative">
        <div class="flex items-center gap-2 mb-3">
          <h2 class="text-sm font-semibold text-gray-900 dark:text-white">Vehicles <InfoTooltip text="Each card shows a vehicle and its labelled estimate. Refresh Value asks Claude for today's value; the label tells you the confidence, the model and the date." /></h2>
          <button @click="showVehiclesSql = true" class="w-10 h-10 flex items-center justify-center rounded-md text-gray-300 dark:text-gray-600 hover:!text-indigo-500 hover:bg-indigo-50 dark:hover:bg-indigo-950/40 transition-all" title="View SQL" aria-label="View SQL">
            <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>
          </button>
        </div>
        <SqlViewerModal :open="showVehiclesSql" :sql="vehiclesSql" title="Vehicles" :tables="['vehicles']" @close="showVehiclesSql = false" />
        <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <div v-for="v in vehicles" :key="v.id" class="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-5 min-w-0">
            <template v-if="editingId !== v.id">
              <div class="flex flex-wrap items-start justify-between gap-2 mb-3">
                <div class="min-w-0">
                  <h3 class="text-base font-bold text-gray-900 dark:text-white">{{ v.year }} {{ v.make }} {{ v.model }}</h3>
                  <p v-if="v.trim" class="text-sm text-gray-500 dark:text-gray-400">{{ v.trim }}</p>
                </div>
                <div class="text-left sm:text-right min-w-0">
                  <div v-if="v.estimated_value != null" class="text-lg font-bold text-green-600 dark:text-green-400">{{ money(v.estimated_value) }}</div>
                  <div v-else class="text-sm font-semibold text-gray-400">No estimate yet</div>
                  <div class="text-[11px] text-gray-400 dark:text-gray-500 break-words">{{ v.estimated_value != null ? valuationLabel(v) : 'Press Refresh Value to estimate it' }}</div>
                </div>
              </div>

              <div v-if="refreshErrors[v.id]" class="mb-3 text-xs text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-800 rounded-lg px-3 py-2">{{ refreshErrors[v.id] }}</div>

              <div v-if="vehicleHasHistory(v.id)" class="mb-3 h-36"><VChart :option="vehicleChartOption(v.id)!" autoresize class="w-full h-full" /></div>

              <div v-if="v.valuation_notes" class="mb-3">
                <button @click="collapsedNotes[v.id] = !collapsedNotes[v.id]" class="flex items-center gap-1 min-h-8 text-xs text-indigo-600 dark:text-indigo-400 font-medium">
                  <svg class="w-3 h-3 transition-transform" :class="{ 'rotate-90': !collapsedNotes[v.id] }" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9 18 15 12 9 6"/></svg>
                  Why this value
                </button>
                <div v-if="!collapsedNotes[v.id]" class="mt-1.5 p-2.5 bg-indigo-50 dark:bg-indigo-950/30 border border-indigo-100 dark:border-indigo-900 rounded-lg">
                  <p class="text-xs text-gray-600 dark:text-gray-400 leading-relaxed">{{ v.valuation_notes }}</p>
                </div>
              </div>

              <div class="grid grid-cols-2 sm:grid-cols-3 gap-3 mb-3 text-sm">
                <div><div class="text-xs text-gray-400">Mileage</div><div class="font-medium text-gray-900 dark:text-white">{{ v.mileage ? number(v.mileage) + ' mi' : dash }}</div></div>
                <div><div class="text-xs text-gray-400">Condition</div>
                  <span v-if="v.condition" class="inline-block mt-0.5 px-2 py-0.5 text-xs font-medium rounded-full" :class="conditionColor(v.condition)">{{ conditionLabels[v.condition] || v.condition }}</span>
                  <span v-else class="text-gray-500">{{ dash }}</span>
                </div>
                <div><div class="text-xs text-gray-400">Purchased</div>
                  <div class="font-medium text-gray-900 dark:text-white">{{ v.purchase_price ? money(v.purchase_price) : dash }}<span v-if="v.purchase_date" class="text-xs text-gray-400 font-normal"> · {{ fmtDate(v.purchase_date) }}</span></div>
                  <div v-if="v.depreciation != null" class="text-xs mt-0.5" :class="v.depreciation > 0 ? 'text-red-500' : 'text-green-600 dark:text-green-400'">{{ v.depreciation > 0 ? '-' : '+' }}{{ money(Math.abs(v.depreciation)) }} since purchase</div>
                </div>
              </div>

              <div v-if="v.notes" class="text-xs text-gray-500 dark:text-gray-400 mb-3 italic">{{ v.notes }}</div>

              <div class="flex flex-wrap items-center justify-end gap-2 pt-3 border-t border-gray-100 dark:border-gray-800">
                <button @click="refreshValue(v.id)" :disabled="refreshingId === v.id" class="px-3 py-2 min-h-10 text-xs font-medium text-indigo-600 dark:text-indigo-400 bg-indigo-50 dark:bg-indigo-950/40 hover:bg-indigo-100 dark:hover:bg-indigo-900/40 rounded-lg disabled:opacity-50">
                  {{ refreshingId === v.id ? 'Estimating…' : 'Refresh Value' }}
                </button>
                <button @click="startEdit(v)" class="px-3 py-2 min-h-10 text-xs font-medium text-gray-600 dark:text-gray-400 bg-gray-100 dark:bg-gray-800 hover:bg-gray-200 dark:hover:bg-gray-700 rounded-lg">Edit</button>
                <button v-if="confirmDeleteId !== v.id" @click="confirmDeleteId = v.id" class="px-3 py-2 min-h-10 text-xs font-medium text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-950/40 hover:bg-red-100 dark:hover:bg-red-900/40 rounded-lg">Delete</button>
                <template v-else>
                  <button @click="deleteVehicle(v.id)" class="px-3 py-2 min-h-10 text-xs font-medium text-white bg-red-600 hover:bg-red-700 rounded-lg">Confirm delete</button>
                  <button @click="confirmDeleteId = null" class="px-3 py-2 min-h-10 text-xs font-medium text-gray-500 hover:text-gray-700 dark:hover:text-gray-300">Cancel</button>
                </template>
              </div>
            </template>

            <template v-else>
              <h3 class="text-base font-bold text-gray-900 dark:text-white mb-4">{{ v.year }} {{ v.make }} {{ v.model }} <span v-if="v.trim" class="text-sm font-normal text-gray-500 dark:text-gray-400">{{ v.trim }}</span></h3>
              <div class="grid grid-cols-2 gap-4 mb-4">
                <label class="block text-xs font-medium text-gray-500 dark:text-gray-400">Mileage<input v-model.number="editForm.mileage" type="number" min="0" :class="inputClass" class="mt-1" /></label>
                <label class="block text-xs font-medium text-gray-500 dark:text-gray-400">Condition
                  <select v-model="editForm.condition" :class="inputClass" class="mt-1"><option v-for="(label, key) in conditionLabels" :key="key" :value="key">{{ label }}</option></select>
                </label>
                <label class="block text-xs font-medium text-gray-500 dark:text-gray-400">Purchase price<input v-model.number="editForm.purchase_price" type="number" min="0" :class="inputClass" class="mt-1" /></label>
                <label class="block text-xs font-medium text-gray-500 dark:text-gray-400">Purchase date<input v-model="editForm.purchase_date" type="date" :class="inputClass" class="mt-1" /></label>
              </div>
              <label class="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-4">Notes<textarea v-model="editForm.notes" rows="2" :class="inputClass" class="mt-1"></textarea></label>
              <div class="flex flex-wrap items-center gap-3">
                <button @click="saveEdit(v.id)" :disabled="editLoading" class="px-4 py-2 min-h-10 text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-700 rounded-lg disabled:opacity-50">{{ editLoading ? 'Saving…' : 'Save' }}</button>
                <button @click="editingId = null" :disabled="editLoading" class="px-4 py-2 min-h-10 text-sm font-medium text-gray-600 dark:text-gray-400 bg-gray-100 dark:bg-gray-800 hover:bg-gray-200 dark:hover:bg-gray-700 rounded-lg">Cancel</button>
              </div>
            </template>
          </div>
        </div>
      </div>

      <div v-if="!hasVehicles && !showAddForm" class="text-center py-16">
        <div class="text-gray-400 dark:text-gray-500 text-sm mb-4">No vehicles tracked yet.</div>
        <button @click="showAddForm = true; resetAddForm()" class="px-4 py-2 min-h-10 text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-700 rounded-lg">Add Vehicle</button>
      </div>
    </template>

    <DataExplorer />
  </div>
</template>
