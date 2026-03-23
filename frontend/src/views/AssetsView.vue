<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { LineChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent, MarkLineComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { useChartDefaults } from '../composables/useChartDefaults'
import InfoTooltip from '../components/common/InfoTooltip.vue'
import SqlViewerModal from '../components/common/SqlViewerModal.vue'

use([LineChart, GridComponent, TooltipComponent, LegendComponent, MarkLineComponent, CanvasRenderer])
const { baseOption, COLORS } = useChartDefaults()

// SQL transparency state
const showTotalValueSql = ref(false)
const showTotalPurchaseSql = ref(false)
const showTotalDepreciationSql = ref(false)
const showVehiclesSql = ref(false)

// SQL queries
const totalValueSql = `SELECT SUM(estimated_value) AS total_value,
       COUNT(*) AS vehicle_count
FROM vehicles
WHERE estimated_value IS NOT NULL;`

const totalPurchaseSql = `SELECT SUM(purchase_price) AS total_purchase_price
FROM vehicles
WHERE purchase_price IS NOT NULL;`

const totalDepreciationSql = `SELECT SUM(purchase_price - estimated_value) AS total_depreciation
FROM vehicles
WHERE purchase_price IS NOT NULL
  AND estimated_value IS NOT NULL;`

const vehiclesSql = `SELECT id, year, make, model, trim,
       mileage, condition, purchase_price,
       estimated_value,
       (purchase_price - estimated_value) AS depreciation,
       value_last_updated, notes
FROM vehicles
ORDER BY estimated_value DESC;`

const API = import.meta.env.VITE_API_URL || ''

// ── State ──
const loading = ref(true)
const error = ref('')
const summary = ref<any>(null)
const vehicles = ref<any[]>([])

// Value history state
interface ValueHistoryEntry {
  date: string
  value: number
  source: string
  is_projected: boolean
}
interface VehicleValueHistory {
  vehicle_id: number
  history: ValueHistoryEntry[]
}
interface AggregateHistory {
  dates: string[]
  total: number[]
  vehicles: Record<string, (number | null)[]>
  is_projected: boolean[]
}

const vehicleHistories = ref<Record<number, VehicleValueHistory>>({})
const aggregateHistory = ref<AggregateHistory | null>(null)
const collapsedNotes = ref<Record<number, boolean>>({})

// Add form state
const showAddForm = ref(false)
const addForm = ref({
  year: new Date().getFullYear(),
  make: '',
  model: '',
  trim: '',
  mileage: null as number | null,
  condition: 'good',
  purchase_price: null as number | null,
  notes: '',
})
const addLoading = ref(false)
const addError = ref('')

// Edit state
const editingId = ref<number | null>(null)
const editForm = ref({
  mileage: null as number | null,
  condition: '',
  notes: '',
  purchase_price: null as number | null,
})
const editLoading = ref(false)

// Refresh state
const refreshingId = ref<number | null>(null)

// Delete state
const confirmDeleteId = ref<number | null>(null)

// ── Data Loading ──
onMounted(async () => {
  await fetchData()
  await fetchAllHistory()
})

async function fetchData() {
  try {
    const res = await fetch(`${API}/api/v1/assets/summary`, { credentials: 'include' })
    if (!res.ok) throw new Error(`Failed to load assets (${res.status})`)
    const data = await res.json()
    summary.value = data
    vehicles.value = data.vehicles || []
  } catch (e: any) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

async function fetchAllHistory() {
  try {
    // Fetch aggregate
    const aggRes = await fetch(`${API}/api/v1/assets/value-history/aggregate`, { credentials: 'include' })
    if (aggRes.ok) {
      aggregateHistory.value = await aggRes.json()
    }
    // Fetch per-vehicle
    for (const v of vehicles.value) {
      await fetchVehicleHistory(v.id)
    }
  } catch {
    // Non-critical — charts just won't show
  }
}

async function fetchVehicleHistory(vehicleId: number) {
  try {
    const res = await fetch(`${API}/api/v1/assets/vehicles/${vehicleId}/value-history`, { credentials: 'include' })
    if (res.ok) {
      const data = await res.json()
      vehicleHistories.value[vehicleId] = data
    }
  } catch {
    // Non-critical
  }
}

// ── Formatting ──
const conditionLabels: Record<string, string> = {
  excellent: 'Excellent',
  very_good: 'Very Good',
  good: 'Good',
  fair: 'Fair',
  poor: 'Poor',
}

function conditionColor(c: string): string {
  if (c === 'excellent' || c === 'very_good') return 'bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-400'
  if (c === 'good') return 'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-400'
  return 'bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-400'
}

function fmt(n: number | null | undefined, style: 'currency' | 'number' = 'currency'): string {
  if (n === null || n === undefined) return '--'
  if (style === 'currency') {
    const abs = Math.abs(n)
    const sign = n < 0 ? '-' : ''
    if (abs >= 1_000_000) return `${sign}$${(abs / 1_000_000).toFixed(2)}M`
    if (abs >= 10_000) return `${sign}$${(abs / 1_000).toFixed(1)}K`
    return `${sign}$${abs.toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`
  }
  return n.toLocaleString()
}

function fmtCurrency(n: number | null | undefined): string {
  if (n === null || n === undefined) return '--'
  return `$${n.toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`
}

function fmtDate(d: string | null | undefined): string {
  if (!d) return '--'
  // Handle both date strings (YYYY-MM-DD) and datetime strings (YYYY-MM-DDTHH:MM:SS)
  const parsed = new Date(d.includes('T') ? d : d + 'T00:00:00')
  if (isNaN(parsed.getTime())) return '--'
  return parsed.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

// ── Add Vehicle ──
function resetAddForm() {
  addForm.value = {
    year: new Date().getFullYear(),
    make: '',
    model: '',
    trim: '',
    mileage: null,
    condition: 'good',
    purchase_price: null,
    notes: '',
  }
  addError.value = ''
}

async function addVehicle() {
  if (!addForm.value.make || !addForm.value.model || !addForm.value.year) {
    addError.value = 'Year, Make, and Model are required.'
    return
  }
  addLoading.value = true
  addError.value = ''
  try {
    const body: any = {
      year: addForm.value.year,
      make: addForm.value.make,
      model: addForm.value.model,
    }
    if (addForm.value.trim) body.trim = addForm.value.trim
    if (addForm.value.mileage) body.mileage = addForm.value.mileage
    if (addForm.value.condition) body.condition = addForm.value.condition
    if (addForm.value.purchase_price) body.purchase_price = addForm.value.purchase_price
    if (addForm.value.notes) body.notes = addForm.value.notes

    const res = await fetch(`${API}/api/v1/assets/vehicles`, {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    if (!res.ok) {
      const text = await res.text()
      throw new Error(`Failed to add vehicle (${res.status}): ${text}`)
    }
    showAddForm.value = false
    resetAddForm()
    await fetchData()
    await fetchAllHistory()
  } catch (e: any) {
    addError.value = e.message
  } finally {
    addLoading.value = false
  }
}

// ── Edit Vehicle ──
function startEdit(v: any) {
  editingId.value = v.id
  editForm.value = {
    mileage: v.mileage,
    condition: v.condition || 'good',
    notes: v.notes || '',
    purchase_price: v.purchase_price,
  }
}

function cancelEdit() {
  editingId.value = null
}

async function saveEdit(id: number) {
  editLoading.value = true
  try {
    const body: any = {
      mileage: editForm.value.mileage || null,
      condition: editForm.value.condition || null,
      notes: editForm.value.notes || null,
      purchase_price: editForm.value.purchase_price ? Number(editForm.value.purchase_price) : null,
    }

    const res = await fetch(`${API}/api/v1/assets/vehicles/${id}`, {
      method: 'PUT',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    if (!res.ok) {
      const text = await res.text()
      throw new Error(`Failed to update vehicle: ${text}`)
    }
    editingId.value = null
    await fetchData()
  } catch (e: any) {
    error.value = e.message
  } finally {
    editLoading.value = false
  }
}

// ── Refresh Value ──
async function refreshValue(id: number) {
  refreshingId.value = id
  try {
    const res = await fetch(`${API}/api/v1/assets/vehicles/${id}/refresh-value`, { method: 'POST', credentials: 'include' })
    if (!res.ok) {
      const text = await res.text()
      throw new Error(`Failed to refresh value: ${text}`)
    }
    await fetchData()
    await fetchAllHistory()
  } catch (e: any) {
    error.value = e.message
  } finally {
    refreshingId.value = null
  }
}

// ── Delete Vehicle ──
async function deleteVehicle(id: number) {
  try {
    const res = await fetch(`${API}/api/v1/assets/vehicles/${id}`, { method: 'DELETE', credentials: 'include' })
    if (!res.ok) {
      const text = await res.text()
      throw new Error(`Failed to delete vehicle: ${text}`)
    }
    confirmDeleteId.value = null
    await fetchData()
    await fetchAllHistory()
  } catch (e: any) {
    error.value = e.message
  }
}

// ── Computed ──
const hasVehicles = computed(() => vehicles.value.length > 0)
const hasAggregateHistory = computed(() => {
  return aggregateHistory.value && aggregateHistory.value.dates.length > 0
})

// ── Chart Options ──
const aggregateChartOption = computed(() => {
  const agg = aggregateHistory.value
  if (!agg || agg.dates.length === 0) return null

  const vehicleNames = Object.keys(agg.vehicles)

  // Find the index where projections start
  const projStartIdx = agg.is_projected.indexOf(true)

  // Build series for each vehicle (stacked area)
  const series: any[] = vehicleNames.map((name, i) => {
    const values = agg.vehicles[name]
    // Split into historical and projected
    const historicalData = values.map((v, idx) => {
      if (projStartIdx >= 0 && idx >= projStartIdx) return null
      return v
    })
    const projectedData = values.map((v, idx) => {
      // Include the last historical point for continuity
      if (projStartIdx >= 0 && idx >= projStartIdx - 1) return v
      return null
    })

    const result: any[] = [
      {
        name,
        type: 'line',
        stack: 'total',
        areaStyle: { opacity: 0.3 },
        emphasis: { focus: 'series' },
        data: historicalData,
        color: COLORS[i % COLORS.length],
        symbol: 'circle',
        symbolSize: 4,
      },
    ]

    // Add projected series (dashed)
    if (projStartIdx >= 0) {
      result.push({
        name: `${name} (projected)`,
        type: 'line',
        stack: 'total-proj',
        areaStyle: { opacity: 0.15 },
        lineStyle: { type: 'dashed' },
        emphasis: { focus: 'series' },
        data: projectedData,
        color: COLORS[i % COLORS.length],
        symbol: 'circle',
        symbolSize: 4,
        showInLegend: false,
      })
    }

    return result
  }).flat()

  return {
    ...baseOption.value,
    legend: {
      data: vehicleNames,
      textStyle: { color: baseOption.value.textStyle.color },
      bottom: 0,
    },
    grid: { ...baseOption.value.grid, bottom: 60 },
    xAxis: {
      type: 'category',
      data: agg.dates.map((d: string) => d.substring(0, 4)),
      axisLine: { lineStyle: { color: baseOption.value.textStyle.color } },
    },
    yAxis: {
      type: 'value',
      axisLabel: {
        formatter: (v: number) => {
          if (v >= 1000) return `$${(v / 1000).toFixed(0)}K`
          return `$${v}`
        },
      },
      axisLine: { lineStyle: { color: baseOption.value.textStyle.color } },
      splitLine: { lineStyle: { color: baseOption.value.textStyle.color, opacity: 0.1 } },
    },
    tooltip: {
      ...baseOption.value.tooltip,
      formatter: (params: any) => {
        if (!Array.isArray(params)) params = [params]
        const date = params[0]?.axisValue || ''
        let html = `<div style="font-weight:600;margin-bottom:4px">${date}</div>`
        let total = 0
        for (const p of params) {
          if (p.value != null) {
            html += `<div>${p.marker} ${p.seriesName}: <strong>$${Number(p.value).toLocaleString()}</strong></div>`
            total += Number(p.value)
          }
        }
        if (params.length > 1) {
          html += `<div style="margin-top:4px;border-top:1px solid #555;padding-top:4px;font-weight:600">Total: $${total.toLocaleString()}</div>`
        }
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
  const dates = entries.map(e => e.date.substring(0, 4))
  const historicalValues = entries.map(e => e.is_projected ? null : e.value)

  // Find where projections start for continuity
  const lastHistIdx = entries.reduce((last, e, i) => !e.is_projected ? i : last, -1)
  const projectedValues = entries.map((e, i) => {
    if (e.is_projected) return e.value
    if (i === lastHistIdx) return e.value // bridge point
    return null
  })

  const hasProjections = entries.some(e => e.is_projected)

  const series: any[] = [
    {
      name: 'Value',
      type: 'line',
      data: historicalValues,
      color: COLORS[0],
      symbol: 'circle',
      symbolSize: 3,
      lineStyle: { width: 2 },
      areaStyle: { opacity: 0.1 },
    },
  ]

  if (hasProjections) {
    series.push({
      name: 'Projected',
      type: 'line',
      data: projectedValues,
      color: COLORS[0],
      symbol: 'circle',
      symbolSize: 3,
      lineStyle: { width: 2, type: 'dashed' },
      areaStyle: { opacity: 0.05 },
    })
  }

  return {
    ...baseOption.value,
    grid: { left: 50, right: 10, top: 10, bottom: 20 },
    xAxis: {
      type: 'category',
      data: dates,
      axisLabel: { fontSize: 10 },
      axisLine: { lineStyle: { color: baseOption.value.textStyle.color } },
    },
    yAxis: {
      type: 'value',
      axisLabel: {
        fontSize: 10,
        formatter: (v: number) => {
          if (v >= 1000) return `$${(v / 1000).toFixed(0)}K`
          return `$${v}`
        },
      },
      axisLine: { show: false },
      splitLine: { lineStyle: { color: baseOption.value.textStyle.color, opacity: 0.1 } },
    },
    tooltip: {
      ...baseOption.value.tooltip,
      formatter: (params: any) => {
        if (!Array.isArray(params)) params = [params]
        const p = params[0]
        if (!p || p.value == null) return ''
        return `<div>${p.axisValue}: <strong>$${Number(p.value).toLocaleString()}</strong></div>`
      },
    },
    legend: { show: false },
    series,
  }
}

function vehicleHasHistory(vehicleId: number): boolean {
  const hist = vehicleHistories.value[vehicleId]
  return !!(hist && hist.history.length > 0)
}
</script>

<template>
  <div class="max-w-6xl mx-auto space-y-6">
    <!-- Header -->
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-bold text-gray-900 dark:text-white">Assets</h1>
        <p class="text-sm text-gray-500 dark:text-gray-400 mt-1">
          Fixed capital assets — vehicles, equipment, and valuables
        </p>
      </div>
      <button
        v-if="!showAddForm"
        @click="showAddForm = true; resetAddForm()"
        class="px-4 py-2 text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-700 rounded-lg transition-colors"
      >
        Add Vehicle
      </button>
    </div>

    <!-- Loading / Error -->
    <div v-if="loading" class="text-sm text-gray-400">Loading assets...</div>
    <div v-else-if="error" class="text-sm text-red-500">{{ error }}</div>

    <template v-else>
      <!-- Add Vehicle Form (inline, shown at top) -->
      <div v-if="showAddForm" class="bg-white dark:bg-gray-900 border border-indigo-200 dark:border-indigo-800 rounded-xl p-5">
        <h2 class="text-sm font-semibold text-gray-900 dark:text-white mb-4">Add Vehicle</h2>
        <div v-if="addError" class="text-sm text-red-500 mb-3">{{ addError }}</div>
        <div class="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-4">
          <div>
            <label class="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">Year *</label>
            <input v-model.number="addForm.year" type="number" min="1900" max="2030"
              class="w-full px-3 py-2 text-sm border border-gray-200 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:ring-2 focus:ring-indigo-500 focus:border-transparent" />
          </div>
          <div>
            <label class="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">Make *</label>
            <input v-model="addForm.make" type="text" placeholder="e.g. Toyota"
              class="w-full px-3 py-2 text-sm border border-gray-200 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:ring-2 focus:ring-indigo-500 focus:border-transparent" />
          </div>
          <div>
            <label class="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">Model *</label>
            <input v-model="addForm.model" type="text" placeholder="e.g. Tacoma"
              class="w-full px-3 py-2 text-sm border border-gray-200 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:ring-2 focus:ring-indigo-500 focus:border-transparent" />
          </div>
          <div>
            <label class="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">Trim</label>
            <input v-model="addForm.trim" type="text" placeholder="e.g. SR5"
              class="w-full px-3 py-2 text-sm border border-gray-200 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:ring-2 focus:ring-indigo-500 focus:border-transparent" />
          </div>
        </div>
        <div class="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-4">
          <div>
            <label class="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">Mileage</label>
            <input v-model.number="addForm.mileage" type="number" min="0" placeholder="e.g. 85000"
              class="w-full px-3 py-2 text-sm border border-gray-200 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:ring-2 focus:ring-indigo-500 focus:border-transparent" />
          </div>
          <div>
            <label class="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">Condition</label>
            <select v-model="addForm.condition"
              class="w-full px-3 py-2 text-sm border border-gray-200 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:ring-2 focus:ring-indigo-500 focus:border-transparent">
              <option value="excellent">Excellent</option>
              <option value="very_good">Very Good</option>
              <option value="good">Good</option>
              <option value="fair">Fair</option>
              <option value="poor">Poor</option>
            </select>
          </div>
          <div>
            <label class="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">Purchase Price</label>
            <input v-model.number="addForm.purchase_price" type="number" min="0" placeholder="e.g. 25000"
              class="w-full px-3 py-2 text-sm border border-gray-200 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:ring-2 focus:ring-indigo-500 focus:border-transparent" />
          </div>
        </div>
        <div class="mb-4">
          <label class="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">Notes</label>
          <textarea v-model="addForm.notes" rows="2" placeholder="Any additional details..."
            class="w-full px-3 py-2 text-sm border border-gray-200 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:ring-2 focus:ring-indigo-500 focus:border-transparent"></textarea>
        </div>
        <div class="flex items-center gap-3">
          <button @click="addVehicle" :disabled="addLoading"
            class="px-4 py-2 text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-700 rounded-lg transition-colors disabled:opacity-50">
            {{ addLoading ? 'Saving...' : 'Save' }}
          </button>
          <button @click="showAddForm = false" :disabled="addLoading"
            class="px-4 py-2 text-sm font-medium text-gray-600 dark:text-gray-400 bg-gray-100 dark:bg-gray-800 hover:bg-gray-200 dark:hover:bg-gray-700 rounded-lg transition-colors">
            Cancel
          </button>
        </div>
      </div>

      <!-- Cumulative Value Chart -->
      <div v-if="hasAggregateHistory" class="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-5">
        <h2 class="text-sm font-semibold text-gray-900 dark:text-white mb-3">
          Vehicle Value Over Time
          <InfoTooltip text="<strong>Vehicle Value History</strong><br>Stacked area chart showing estimated value of each vehicle over time. Solid lines represent historical estimates; dashed lines show projected future values based on typical depreciation curves.<br><br><strong>Source:</strong> AI-generated estimates using KBB, Edmunds, and NADA reference data." />
        </h2>
        <VChart v-if="aggregateChartOption" :option="aggregateChartOption" style="height: 300px; width: 100%;" autoresize />
      </div>

      <!-- Summary Cards -->
      <div v-if="hasVehicles" class="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <div class="group/totalValue relative bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-4">
          <button @click="showTotalValueSql = true" class="absolute top-3.5 right-3.5 p-1 rounded-md text-gray-300 dark:text-gray-600 opacity-0 group-hover/totalValue:opacity-100 hover:!text-indigo-500 hover:bg-indigo-50 dark:hover:bg-indigo-950/40 transition-all" title="View SQL">
            <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>
          </button>
          <SqlViewerModal :open="showTotalValueSql" :sql="totalValueSql" title="Total Asset Value" :tables="['vehicles']" @close="showTotalValueSql = false" />
          <div class="text-xs text-gray-500 dark:text-gray-400 font-medium">
            Total Asset Value
            <InfoTooltip text="<strong>Total Asset Value</strong><br>Sum of all estimated current market values for tracked vehicles. Values are estimated using AI based on year, make, model, mileage, and condition.<br><br><strong>Source:</strong> AI-generated estimates, refreshed on demand." />
          </div>
          <div class="text-xl font-bold text-gray-900 dark:text-white mt-1">{{ fmtCurrency(summary.total_value) }}</div>
          <div class="text-xs text-gray-400 mt-1">{{ summary.vehicle_count }} vehicle{{ summary.vehicle_count !== 1 ? 's' : '' }}</div>
        </div>
        <div class="group/totalPurchase relative bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-4">
          <button @click="showTotalPurchaseSql = true" class="absolute top-3.5 right-3.5 p-1 rounded-md text-gray-300 dark:text-gray-600 opacity-0 group-hover/totalPurchase:opacity-100 hover:!text-indigo-500 hover:bg-indigo-50 dark:hover:bg-indigo-950/40 transition-all" title="View SQL">
            <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>
          </button>
          <SqlViewerModal :open="showTotalPurchaseSql" :sql="totalPurchaseSql" title="Total Purchase Price" :tables="['vehicles']" @close="showTotalPurchaseSql = false" />
          <div class="text-xs text-gray-500 dark:text-gray-400 font-medium">
            Total Purchase Price
            <InfoTooltip text="<strong>Total Purchase Price</strong><br>Sum of original purchase prices for vehicles where the purchase price is known. Useful for calculating total depreciation." />
          </div>
          <div class="text-xl font-bold text-gray-900 dark:text-white mt-1">{{ summary.total_purchase_price ? fmtCurrency(summary.total_purchase_price) : '--' }}</div>
          <div class="text-xs text-gray-400 mt-1">Original cost basis</div>
        </div>
        <div class="group/totalDepr relative bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-4">
          <button @click="showTotalDepreciationSql = true" class="absolute top-3.5 right-3.5 p-1 rounded-md text-gray-300 dark:text-gray-600 opacity-0 group-hover/totalDepr:opacity-100 hover:!text-indigo-500 hover:bg-indigo-50 dark:hover:bg-indigo-950/40 transition-all" title="View SQL">
            <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>
          </button>
          <SqlViewerModal :open="showTotalDepreciationSql" :sql="totalDepreciationSql" title="Total Depreciation" :tables="['vehicles']" @close="showTotalDepreciationSql = false" />
          <div class="text-xs text-gray-500 dark:text-gray-400 font-medium">
            Total Depreciation
            <InfoTooltip text="<strong>Total Depreciation</strong><br>How much value has been lost since purchase. Positive = lost value (typical for vehicles). Negative = gained value (appreciation).<br><br><strong>Formula:</strong> <code>purchase price - current value</code>" />
          </div>
          <div class="text-xl font-bold mt-1"
            :class="summary.total_depreciation != null ? (summary.total_depreciation > 0 ? 'text-red-600 dark:text-red-400' : 'text-green-600 dark:text-green-400') : 'text-gray-900 dark:text-white'">
            {{ summary.total_depreciation != null ? (summary.total_depreciation > 0 ? '-' : '+') + fmtCurrency(Math.abs(summary.total_depreciation)) : '--' }}
          </div>
          <div class="text-xs text-gray-400 mt-1">
            {{ summary.total_depreciation != null && summary.total_depreciation > 0 ? 'Lost since purchase' : summary.total_depreciation != null && summary.total_depreciation < 0 ? 'Gained since purchase' : 'Add purchase prices to track' }}
          </div>
        </div>
      </div>

      <!-- Vehicle Cards -->
      <div v-if="hasVehicles" class="group/vehicles relative">
        <div class="flex items-center gap-2 mb-3">
          <h2 class="text-sm font-semibold text-gray-900 dark:text-white">
            Vehicles
            <InfoTooltip text="Each card shows a tracked vehicle with its AI-estimated market value. Click 'Refresh Value' to get an updated estimate based on current market data." />
          </h2>
          <button @click="showVehiclesSql = true" class="p-1 rounded-md text-gray-300 dark:text-gray-600 opacity-0 group-hover/vehicles:opacity-100 hover:!text-indigo-500 hover:bg-indigo-50 dark:hover:bg-indigo-950/40 transition-all" title="View SQL">
            <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>
          </button>
        </div>
        <SqlViewerModal :open="showVehiclesSql" :sql="vehiclesSql" title="Vehicles" :tables="['vehicles']" @close="showVehiclesSql = false" />
        <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <div v-for="v in vehicles" :key="v.id"
            class="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-5">

            <!-- View mode -->
            <template v-if="editingId !== v.id">
              <div class="flex items-start justify-between mb-3">
                <div>
                  <h3 class="text-base font-bold text-gray-900 dark:text-white">
                    {{ v.year }} {{ v.make }} {{ v.model }}
                  </h3>
                  <p v-if="v.trim" class="text-sm text-gray-500 dark:text-gray-400">{{ v.trim }}</p>
                </div>
                <div class="text-right">
                  <div class="text-lg font-bold text-green-600 dark:text-green-400">{{ fmtCurrency(v.estimated_value) }}</div>
                  <div class="text-xs text-gray-400">Estimated value</div>
                </div>
              </div>

              <!-- Per-vehicle value chart -->
              <div v-if="vehicleHasHistory(v.id)" class="mb-3">
                <VChart :option="vehicleChartOption(v.id)!" style="height: 150px; width: 100%;" autoresize />
              </div>

              <!-- Persistent AI valuation notes -->
              <div v-if="v.valuation_notes" class="mb-3">
                <button
                  @click="collapsedNotes[v.id] = !collapsedNotes[v.id]"
                  class="flex items-center gap-1 text-xs text-indigo-600 dark:text-indigo-400 font-medium hover:text-indigo-700 dark:hover:text-indigo-300 transition-colors"
                >
                  <svg
                    class="w-3 h-3 transition-transform"
                    :class="{ 'rotate-90': !collapsedNotes[v.id] }"
                    viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"
                  ><polyline points="9 18 15 12 9 6"/></svg>
                  AI Analysis
                </button>
                <div v-if="!collapsedNotes[v.id]" class="mt-1.5 p-2.5 bg-indigo-50 dark:bg-indigo-950/30 border border-indigo-100 dark:border-indigo-900 rounded-lg">
                  <p class="text-xs text-gray-600 dark:text-gray-400 leading-relaxed">{{ v.valuation_notes }}</p>
                  <div v-if="v.value_last_updated" class="text-[10px] text-gray-400 dark:text-gray-500 mt-1.5">
                    Updated {{ fmtDate(v.value_last_updated) }}
                  </div>
                </div>
              </div>

              <div class="grid grid-cols-2 sm:grid-cols-3 gap-3 mb-3 text-sm">
                <div>
                  <div class="text-xs text-gray-400">Mileage</div>
                  <div class="font-medium text-gray-900 dark:text-white">
                    {{ v.mileage ? fmt(v.mileage, 'number') + ' mi' : '--' }}
                  </div>
                </div>
                <div>
                  <div class="text-xs text-gray-400">Condition</div>
                  <span v-if="v.condition"
                    class="inline-block mt-0.5 px-2 py-0.5 text-xs font-medium rounded-full"
                    :class="conditionColor(v.condition)">
                    {{ conditionLabels[v.condition] || v.condition }}
                  </span>
                  <span v-else class="text-gray-500">--</span>
                </div>
                <div>
                  <div class="text-xs text-gray-400">Purchase Price</div>
                  <div class="font-medium text-gray-900 dark:text-white">
                    {{ v.purchase_price ? fmtCurrency(v.purchase_price) : '--' }}
                  </div>
                  <div v-if="v.purchase_price && v.estimated_value" class="text-xs mt-0.5"
                    :class="v.depreciation > 0 ? 'text-red-500' : 'text-green-600 dark:text-green-400'">
                    {{ v.depreciation > 0 ? '-' : '+' }}{{ fmtCurrency(Math.abs(v.depreciation)) }}
                  </div>
                </div>
              </div>

              <div v-if="v.notes" class="text-xs text-gray-500 dark:text-gray-400 mb-3 italic">{{ v.notes }}</div>

              <div class="flex items-center justify-between pt-3 border-t border-gray-100 dark:border-gray-800">
                <span class="text-xs text-gray-400">
                  Last valued: {{ fmtDate(v.value_last_updated) }}
                </span>
                <div class="flex items-center gap-2">
                  <button @click="refreshValue(v.id)" :disabled="refreshingId === v.id"
                    class="px-3 py-1 text-xs font-medium text-indigo-600 dark:text-indigo-400 bg-indigo-50 dark:bg-indigo-950/40 hover:bg-indigo-100 dark:hover:bg-indigo-900/40 rounded-lg transition-colors disabled:opacity-50">
                    {{ refreshingId === v.id ? 'Refreshing...' : 'Refresh Value' }}
                  </button>
                  <button @click="startEdit(v)"
                    class="px-3 py-1 text-xs font-medium text-gray-600 dark:text-gray-400 bg-gray-100 dark:bg-gray-800 hover:bg-gray-200 dark:hover:bg-gray-700 rounded-lg transition-colors">
                    Edit
                  </button>
                  <button v-if="confirmDeleteId !== v.id" @click="confirmDeleteId = v.id"
                    class="px-3 py-1 text-xs font-medium text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-950/40 hover:bg-red-100 dark:hover:bg-red-900/40 rounded-lg transition-colors">
                    Delete
                  </button>
                  <template v-else>
                    <button @click="deleteVehicle(v.id)"
                      class="px-3 py-1 text-xs font-medium text-white bg-red-600 hover:bg-red-700 rounded-lg transition-colors">
                      Confirm
                    </button>
                    <button @click="confirmDeleteId = null"
                      class="px-3 py-1 text-xs font-medium text-gray-500 hover:text-gray-700 dark:hover:text-gray-300 transition-colors">
                      Cancel
                    </button>
                  </template>
                </div>
              </div>
            </template>

            <!-- Edit mode -->
            <template v-else>
              <h3 class="text-base font-bold text-gray-900 dark:text-white mb-4">
                {{ v.year }} {{ v.make }} {{ v.model }}
                <span v-if="v.trim" class="text-sm font-normal text-gray-500 dark:text-gray-400">{{ v.trim }}</span>
              </h3>
              <div class="grid grid-cols-2 gap-4 mb-4">
                <div>
                  <label class="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">Mileage</label>
                  <input v-model.number="editForm.mileage" type="number" min="0"
                    class="w-full px-3 py-2 text-sm border border-gray-200 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:ring-2 focus:ring-indigo-500 focus:border-transparent" />
                </div>
                <div>
                  <label class="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">Condition</label>
                  <select v-model="editForm.condition"
                    class="w-full px-3 py-2 text-sm border border-gray-200 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:ring-2 focus:ring-indigo-500 focus:border-transparent">
                    <option value="excellent">Excellent</option>
                    <option value="very_good">Very Good</option>
                    <option value="good">Good</option>
                    <option value="fair">Fair</option>
                    <option value="poor">Poor</option>
                  </select>
                </div>
                <div>
                  <label class="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">Purchase Price</label>
                  <input v-model.number="editForm.purchase_price" type="number" min="0"
                    class="w-full px-3 py-2 text-sm border border-gray-200 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:ring-2 focus:ring-indigo-500 focus:border-transparent" />
                </div>
              </div>
              <div class="mb-4">
                <label class="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">Notes</label>
                <textarea v-model="editForm.notes" rows="2"
                  class="w-full px-3 py-2 text-sm border border-gray-200 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:ring-2 focus:ring-indigo-500 focus:border-transparent"></textarea>
              </div>
              <div class="flex items-center gap-3">
                <button @click="saveEdit(v.id)" :disabled="editLoading"
                  class="px-4 py-2 text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-700 rounded-lg transition-colors disabled:opacity-50">
                  {{ editLoading ? 'Saving...' : 'Save' }}
                </button>
                <button @click="cancelEdit" :disabled="editLoading"
                  class="px-4 py-2 text-sm font-medium text-gray-600 dark:text-gray-400 bg-gray-100 dark:bg-gray-800 hover:bg-gray-200 dark:hover:bg-gray-700 rounded-lg transition-colors">
                  Cancel
                </button>
              </div>
            </template>
          </div>
        </div>
      </div>

      <!-- Empty State -->
      <div v-if="!hasVehicles && !showAddForm" class="text-center py-16">
        <div class="text-gray-400 dark:text-gray-500 text-sm mb-4">No assets tracked yet. Add a vehicle to get started.</div>
        <button @click="showAddForm = true; resetAddForm()"
          class="px-4 py-2 text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-700 rounded-lg transition-colors">
          Add Vehicle
        </button>
      </div>
    </template>
  </div>
</template>
