<script setup lang="ts">
import { ref, computed, onMounted, watch, nextTick } from 'vue'
import InfoTooltip from '../components/common/InfoTooltip.vue'

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000'

// ── Types ─────────────────────────────────────────────────────────────────────

interface ColumnInfo {
  name: string
  type: string
  nullable: boolean
  primary_key: boolean
  default: string | null
}

interface ForeignKey {
  column: string
  references_table: string
  references_column: string
}

interface TableSchema {
  name: string
  columns: ColumnInfo[]
  foreign_keys: ForeignKey[]
  row_count: number
}

interface Edge {
  from_table: string
  from_column: string
  to_table: string
  to_column: string
}

interface SchemaResponse {
  tables: TableSchema[]
  edges: Edge[]
}

interface PreviewResponse {
  table: string
  columns: string[]
  rows: Record<string, unknown>[]
  total: number
  limit: number
  offset: number
}

interface QueryResponse {
  columns: string[]
  rows: Record<string, unknown>[]
  row_count: number
  query: string
}

type TableCategory = 'financial' | 'investments' | 'property' | 'planning' | 'system'

// ── API helpers ───────────────────────────────────────────────────────────────

async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const headers: Record<string, string> = {}
  if (options?.method && options.method !== 'GET') {
    headers['Content-Type'] = 'application/json'
  }
  const res = await fetch(`${API_BASE}${path}`, {
    headers,
    ...options,
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(`${res.status}: ${text}`)
  }
  return res.json()
}

// ── State ─────────────────────────────────────────────────────────────────────

const schema = ref<SchemaResponse | null>(null)
const schemaLoading = ref(false)
const schemaError = ref<string | null>(null)

const selectedTable = ref<string | null>(null)
const centerMode = ref<'schema' | 'data'>('schema')

const searchQuery = ref('')
const sqlText = ref('')
const sqlRunning = ref(false)
const sqlError = ref<string | null>(null)
const sqlResult = ref<QueryResponse | null>(null)
const sqlPanelOpen = ref(true)

const previewData = ref<PreviewResponse | null>(null)
const previewLoading = ref(false)
const previewError = ref<string | null>(null)
const previewOffset = ref(0)
const PAGE_SIZE = 20

const erdContainer = ref<HTMLDivElement | null>(null)
const isDark = computed(() => typeof document !== 'undefined' && isDark)

// ── Category classification ───────────────────────────────────────────────────

const categoryMap: Record<string, TableCategory> = {}

const categoryPatterns: { category: TableCategory; patterns: string[] }[] = [
  { category: 'financial', patterns: ['accounts', 'transactions', 'balance_snapshots', 'w2_records'] },
  { category: 'investments', patterns: ['rsu_grants', 'vest_events', 'stock_prices', 'retirement'] },
  { category: 'property', patterns: ['mortgages', 'property_valuations', 'property'] },
  { category: 'planning', patterns: ['plan_', 'actual_snapshots', 'forecasts', 'contribution_configs'] },
  { category: 'system', patterns: ['users', 'import_logs', 'import_sessions', 'plaid_links', 'alembic'] },
]

function classifyTable(name: string): TableCategory {
  if (categoryMap[name]) return categoryMap[name]
  for (const { category, patterns } of categoryPatterns) {
    for (const p of patterns) {
      if (name === p || name.startsWith(p)) {
        categoryMap[name] = category
        return category
      }
    }
  }
  categoryMap[name] = 'system'
  return 'system'
}

const categoryColors: Record<TableCategory, { bg: string; border: string; text: string; badge: string; dot: string }> = {
  financial: {
    bg: 'bg-blue-50 dark:bg-blue-950/30',
    border: 'border-blue-200 dark:border-blue-800',
    text: 'text-blue-700 dark:text-blue-300',
    badge: 'bg-blue-100 dark:bg-blue-900 text-blue-700 dark:text-blue-300',
    dot: 'bg-blue-500',
  },
  investments: {
    bg: 'bg-emerald-50 dark:bg-emerald-950/30',
    border: 'border-emerald-200 dark:border-emerald-800',
    text: 'text-emerald-700 dark:text-emerald-300',
    badge: 'bg-emerald-100 dark:bg-emerald-900 text-emerald-700 dark:text-emerald-300',
    dot: 'bg-emerald-500',
  },
  property: {
    bg: 'bg-amber-50 dark:bg-amber-950/30',
    border: 'border-amber-200 dark:border-amber-800',
    text: 'text-amber-700 dark:text-amber-300',
    badge: 'bg-amber-100 dark:bg-amber-900 text-amber-700 dark:text-amber-300',
    dot: 'bg-amber-500',
  },
  planning: {
    bg: 'bg-purple-50 dark:bg-purple-950/30',
    border: 'border-purple-200 dark:border-purple-800',
    text: 'text-purple-700 dark:text-purple-300',
    badge: 'bg-purple-100 dark:bg-purple-900 text-purple-700 dark:text-purple-300',
    dot: 'bg-purple-500',
  },
  system: {
    bg: 'bg-gray-50 dark:bg-gray-800/30',
    border: 'border-gray-200 dark:border-gray-700',
    text: 'text-gray-600 dark:text-gray-400',
    badge: 'bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400',
    dot: 'bg-gray-400',
  },
}

const categoryLabels: Record<TableCategory, string> = {
  financial: 'Financial',
  investments: 'Investments',
  property: 'Property',
  planning: 'Planning',
  system: 'System',
}

// ── Computed ──────────────────────────────────────────────────────────────────

const tables = computed(() => schema.value?.tables ?? [])
const edges = computed(() => schema.value?.edges ?? [])

const filteredTables = computed(() => {
  const q = searchQuery.value.toLowerCase().trim()
  const all = tables.value
  if (!q) return all
  return all.filter(t => t.name.toLowerCase().includes(q))
})

const groupedTables = computed(() => {
  const groups: Record<TableCategory, TableSchema[]> = {
    financial: [],
    investments: [],
    property: [],
    planning: [],
    system: [],
  }
  for (const t of filteredTables.value) {
    const cat = classifyTable(t.name)
    groups[cat].push(t)
  }
  // Sort each group alphabetically
  for (const cat of Object.keys(groups) as TableCategory[]) {
    groups[cat].sort((a, b) => a.name.localeCompare(b.name))
  }
  return groups
})

const selectedTableSchema = computed(() =>
  tables.value.find(t => t.name === selectedTable.value) ?? null
)

const relatedTables = computed(() => {
  if (!selectedTable.value) return new Set<string>()
  const related = new Set<string>()
  for (const e of edges.value) {
    if (e.from_table === selectedTable.value) related.add(e.to_table)
    if (e.to_table === selectedTable.value) related.add(e.from_table)
  }
  return related
})

// FK columns for the selected table's preview
const fkColumns = computed(() => {
  if (!selectedTableSchema.value) return new Map<string, { table: string; column: string }>()
  const map = new Map<string, { table: string; column: string }>()
  for (const fk of selectedTableSchema.value.foreign_keys) {
    map.set(fk.column, { table: fk.references_table, column: fk.references_column })
  }
  // Also check edges
  for (const e of edges.value) {
    if (e.from_table === selectedTable.value) {
      map.set(e.from_column, { table: e.to_table, column: e.to_column })
    }
  }
  return map
})

const previewCurrentPage = computed(() =>
  previewData.value ? Math.floor(previewOffset.value / PAGE_SIZE) + 1 : 1
)

const previewTotalPages = computed(() =>
  previewData.value ? Math.ceil(previewData.value.total / PAGE_SIZE) : 0
)

// ── ERD Layout ────────────────────────────────────────────────────────────────

const CARD_W = 240
const CARD_GAP_X = 40
const CARD_GAP_Y = 30
const COLS = 4
const CARD_HEADER_H = 36
const CARD_ROW_H = 22
const CARD_PAD_Y = 8

function cardHeight(t: TableSchema): number {
  return CARD_HEADER_H + t.columns.length * CARD_ROW_H + CARD_PAD_Y * 2
}

interface CardLayout {
  table: TableSchema
  x: number
  y: number
  w: number
  h: number
}

const cardLayouts = computed((): CardLayout[] => {
  const layouts: CardLayout[] = []
  // Group by category for nicer layout
  const ordered: TableSchema[] = []
  for (const cat of ['financial', 'investments', 'property', 'planning', 'system'] as TableCategory[]) {
    const group = tables.value.filter(t => classifyTable(t.name) === cat)
    group.sort((a, b) => a.name.localeCompare(b.name))
    ordered.push(...group)
  }

  // Place cards in columns, tracking per-column Y
  const colYs = Array(COLS).fill(0)

  for (const t of ordered) {
    // Pick the shortest column
    let minCol = 0
    for (let c = 1; c < COLS; c++) {
      if (colYs[c] < colYs[minCol]) minCol = c
    }
    const x = minCol * (CARD_W + CARD_GAP_X) + 20
    const y = colYs[minCol] + 20
    const h = cardHeight(t)
    layouts.push({ table: t, x, y, w: CARD_W, h })
    colYs[minCol] = y + h + CARD_GAP_Y
  }
  return layouts
})

const svgWidth = computed(() => COLS * (CARD_W + CARD_GAP_X) + 40)
const svgHeight = computed(() => {
  let max = 0
  for (const c of cardLayouts.value) {
    if (c.y + c.h > max) max = c.y + c.h
  }
  return max + 40
})

interface EdgePath {
  edge: Edge
  path: string
}

const edgePaths = computed((): EdgePath[] => {
  const layoutMap = new Map<string, CardLayout>()
  for (const cl of cardLayouts.value) {
    layoutMap.set(cl.table.name, cl)
  }

  return edges.value.map(e => {
    const from = layoutMap.get(e.from_table)
    const to = layoutMap.get(e.to_table)
    if (!from || !to) return null

    // Find column index for positioning
    const fromColIdx = from.table.columns.findIndex(c => c.name === e.from_column)
    const toColIdx = to.table.columns.findIndex(c => c.name === e.to_column)

    const fromY = from.y + CARD_HEADER_H + CARD_PAD_Y + (fromColIdx >= 0 ? fromColIdx : 0) * CARD_ROW_H + CARD_ROW_H / 2
    const toY = to.y + CARD_HEADER_H + CARD_PAD_Y + (toColIdx >= 0 ? toColIdx : 0) * CARD_ROW_H + CARD_ROW_H / 2

    // Connect from right edge of from card to left edge of to card (or vice versa)
    let fromX: number, toX: number
    if (from.x + from.w < to.x) {
      fromX = from.x + from.w
      toX = to.x
    } else if (to.x + to.w < from.x) {
      fromX = from.x
      toX = to.x + to.w
    } else {
      // Overlapping columns: connect via right sides
      fromX = from.x + from.w
      toX = to.x + to.w
    }

    const midX = (fromX + toX) / 2
    const path = `M ${fromX} ${fromY} C ${midX} ${fromY}, ${midX} ${toY}, ${toX} ${toY}`
    return { edge: e, path }
  }).filter(Boolean) as EdgePath[]
})

// ── Loaders ───────────────────────────────────────────────────────────────────

async function loadSchema() {
  schemaLoading.value = true
  schemaError.value = null
  try {
    const res = await fetch(`${API_BASE}/api/admin/schema`)
    if (!res.ok) throw new Error(`${res.status}`)
    schema.value = await res.json()
  } catch (e) {
    schemaError.value = e instanceof Error ? e.message : 'Failed to load schema'
  } finally {
    schemaLoading.value = false
  }
}

async function loadPreview(tableName: string, offset = 0) {
  previewLoading.value = true
  previewError.value = null
  try {
    previewData.value = await apiFetch<PreviewResponse>(
      `/api/admin/tables/${encodeURIComponent(tableName)}/preview?limit=${PAGE_SIZE}&offset=${offset}`
    )
    previewOffset.value = offset
  } catch (e) {
    previewError.value = e instanceof Error ? e.message : 'Failed to load preview'
  } finally {
    previewLoading.value = false
  }
}

async function runSql() {
  if (!sqlText.value.trim()) return
  sqlRunning.value = true
  sqlError.value = null
  sqlResult.value = null
  try {
    sqlResult.value = await apiFetch<QueryResponse>('/api/admin/query', {
      method: 'POST',
      body: JSON.stringify({ sql: sqlText.value.trim(), limit: 100 }),
    })
  } catch (e) {
    sqlError.value = e instanceof Error ? e.message : 'Query failed'
  } finally {
    sqlRunning.value = false
  }
}

// ── Interactions ──────────────────────────────────────────────────────────────

function selectTable(name: string) {
  selectedTable.value = name
  centerMode.value = 'data'
  loadPreview(name, 0)
}

function selectTableFromErd(name: string) {
  selectedTable.value = name
  // Stay in schema mode, just highlight
}

function clickErdCard(name: string) {
  if (selectedTable.value === name) {
    // Double-click behavior: show data
    centerMode.value = 'data'
    loadPreview(name, 0)
  } else {
    selectTableFromErd(name)
  }
}

function jumpToFk(tableName: string, columnName: string, value: unknown) {
  if (value === null || value === undefined) return
  selectedTable.value = tableName
  sqlText.value = `SELECT * FROM ${tableName} WHERE ${columnName} = '${value}' LIMIT 20`
  centerMode.value = 'data'
  loadPreview(tableName, 0)
}

function prevPage() {
  if (!selectedTable.value || previewOffset.value === 0) return
  loadPreview(selectedTable.value, Math.max(0, previewOffset.value - PAGE_SIZE))
}

function nextPage() {
  if (!selectedTable.value || !previewData.value) return
  if (previewOffset.value + PAGE_SIZE >= previewData.value.total) return
  loadPreview(selectedTable.value, previewOffset.value + PAGE_SIZE)
}

function handleSqlKeydown(e: KeyboardEvent) {
  if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
    e.preventDefault()
    runSql()
  }
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function formatType(raw: string): string {
  const t = raw.toUpperCase()
  if (t.includes('VARCHAR') || t.includes('TEXT') || t.includes('CHAR')) return 'string'
  if (t.includes('INTEGER') || t.includes('INT') || t.includes('BIGINT') || t.includes('SMALLINT')) return 'int'
  if (t.includes('NUMERIC') || t.includes('DECIMAL') || t.includes('FLOAT') || t.includes('DOUBLE') || t.includes('REAL')) return 'decimal'
  if (t.includes('BOOLEAN') || t.includes('BOOL')) return 'bool'
  if (t.includes('TIMESTAMP') || t.includes('DATETIME')) return 'timestamp'
  if (t.includes('DATE')) return 'date'
  if (t.includes('JSON')) return 'json'
  if (t.includes('UUID')) return 'uuid'
  return raw.toLowerCase()
}

function formatCellValue(val: unknown): string {
  if (val === null || val === undefined) return '\u2014'
  if (typeof val === 'object') return JSON.stringify(val)
  return String(val)
}

function isColumnPk(tableName: string, colName: string): boolean {
  const t = tables.value.find(tb => tb.name === tableName)
  if (!t) return false
  return t.columns.some(c => c.name === colName && c.primary_key)
}

function isColumnFk(tableName: string, colName: string): boolean {
  const t = tables.value.find(tb => tb.name === tableName)
  if (!t) return false
  if (t.foreign_keys.some(fk => fk.column === colName)) return true
  return edges.value.some(e => e.from_table === tableName && e.from_column === colName)
}

// Watch for table selection to scroll ERD card into view
watch(selectedTable, () => {
  if (centerMode.value === 'schema' && selectedTable.value && erdContainer.value) {
    nextTick(() => {
      const card = erdContainer.value?.querySelector(`[data-table="${selectedTable.value}"]`)
      card?.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'nearest' })
    })
  }
})

// ── Init ──────────────────────────────────────────────────────────────────────

onMounted(loadSchema)
</script>

<template>
  <div class="flex flex-col h-[calc(100vh-120px)] min-h-0">
    <!-- Header -->
    <div class="flex items-center justify-between mb-4 flex-shrink-0">
      <div class="flex items-center gap-2">
        <h2 class="text-lg font-bold text-gray-900 dark:text-white">Database</h2>
        <InfoTooltip text="<strong>Database Schema Canvas</strong><br>Browse your database tables, view their relationships, preview data, and run SQL queries." />
      </div>
      <div class="flex items-center gap-2 text-xs text-gray-400 dark:text-gray-500">
        <span v-if="schema">{{ tables.length }} tables</span>
        <span v-if="schema">&middot;</span>
        <span v-if="schema">{{ edges.length }} relationships</span>
      </div>
    </div>

    <!-- Loading state -->
    <div v-if="schemaLoading" class="flex items-center justify-center flex-1">
      <div class="text-center">
        <div class="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-500 mx-auto mb-3"></div>
        <p class="text-sm text-gray-500 dark:text-gray-400">Loading database schema...</p>
      </div>
    </div>

    <!-- Error state -->
    <div v-else-if="schemaError" class="flex items-center justify-center flex-1">
      <div class="text-center">
        <p class="text-sm text-red-500 mb-2">{{ schemaError }}</p>
        <button @click="loadSchema" class="px-3 py-1.5 text-xs font-medium bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition-colors">
          Retry
        </button>
      </div>
    </div>

    <!-- Main content -->
    <div v-else-if="schema" class="flex gap-4 flex-1 min-h-0">

      <!-- ═══ Left Panel: Table List ═══ -->
      <aside class="w-[250px] flex-shrink-0 flex flex-col bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl overflow-hidden">
        <div class="px-3 py-2.5 border-b border-gray-100 dark:border-gray-800 flex items-center gap-1.5">
          <span class="text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">Tables</span>
          <InfoTooltip text="<strong>Table List</strong><br>Click a table to preview its data. Tables are grouped by category: financial, investments, property, planning, and system." />
        </div>

        <!-- Search -->
        <div class="px-3 py-2 border-b border-gray-100 dark:border-gray-800">
          <input
            v-model="searchQuery"
            type="text"
            placeholder="Filter tables..."
            class="w-full px-2.5 py-1.5 text-xs bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg text-gray-800 dark:text-gray-200 placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 focus:border-indigo-500"
          />
        </div>

        <!-- Table groups -->
        <div class="flex-1 overflow-y-auto">
          <template v-for="cat in (['financial', 'investments', 'property', 'planning', 'system'] as TableCategory[])" :key="cat">
            <div v-if="groupedTables[cat].length > 0">
              <!-- Category header -->
              <div class="px-3 py-1.5 flex items-center gap-2 sticky top-0 bg-gray-50 dark:bg-gray-800/60 z-10">
                <span :class="['w-2 h-2 rounded-full flex-shrink-0', categoryColors[cat].dot]"></span>
                <span class="text-[10px] font-semibold uppercase tracking-wider text-gray-400 dark:text-gray-500">{{ categoryLabels[cat] }}</span>
                <span class="text-[10px] text-gray-300 dark:text-gray-600">({{ groupedTables[cat].length }})</span>
              </div>
              <!-- Tables in group -->
              <ul>
                <li
                  v-for="t in groupedTables[cat]"
                  :key="t.name"
                  @click="selectTable(t.name)"
                  :class="[
                    'px-3 py-2 cursor-pointer transition-colors',
                    selectedTable === t.name
                      ? 'bg-indigo-50 dark:bg-indigo-950/60'
                      : 'hover:bg-gray-50 dark:hover:bg-gray-800/40'
                  ]"
                >
                  <div class="flex items-center justify-between gap-2">
                    <span
                      :class="[
                        'text-xs font-medium truncate',
                        selectedTable === t.name
                          ? 'text-indigo-700 dark:text-indigo-300'
                          : 'text-gray-800 dark:text-gray-200'
                      ]"
                    >{{ t.name }}</span>
                    <span class="text-[10px] text-gray-400 dark:text-gray-500 tabular-nums flex-shrink-0">
                      {{ t.row_count.toLocaleString() }}
                    </span>
                  </div>
                </li>
              </ul>
            </div>
          </template>
        </div>
      </aside>

      <!-- ═══ Center Panel ═══ -->
      <div class="flex-1 min-w-0 flex flex-col gap-4 min-h-0">

        <!-- Center content area -->
        <div class="flex-1 min-h-0 flex flex-col bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl overflow-hidden">

          <!-- Tab bar -->
          <div class="flex items-center justify-between px-4 py-2 border-b border-gray-100 dark:border-gray-800 flex-shrink-0">
            <div class="flex gap-1">
              <button
                @click="centerMode = 'schema'"
                :class="[
                  'px-3 py-1.5 rounded-lg text-xs font-medium transition-colors',
                  centerMode === 'schema'
                    ? 'bg-indigo-100 dark:bg-indigo-900/50 text-indigo-700 dark:text-indigo-300'
                    : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800'
                ]"
              >
                Schema
              </button>
              <button
                @click="centerMode = 'data'; if (selectedTable && !previewData) loadPreview(selectedTable, 0)"
                :class="[
                  'px-3 py-1.5 rounded-lg text-xs font-medium transition-colors',
                  centerMode === 'data'
                    ? 'bg-indigo-100 dark:bg-indigo-900/50 text-indigo-700 dark:text-indigo-300'
                    : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800'
                ]"
              >
                Data
              </button>
            </div>
            <div class="flex items-center gap-2">
              <span v-if="centerMode === 'data' && selectedTable" class="text-xs font-medium text-gray-700 dark:text-gray-300">
                {{ selectedTable }}
              </span>
              <InfoTooltip
                :text="centerMode === 'schema'
                  ? '<strong>Schema View</strong><br>Visual map of your database tables and their relationships. Click a card to select it; click again to view its data. Primary keys shown in gold, foreign keys in blue.'
                  : '<strong>Data Preview</strong><br>Browse rows from the selected table. Click a foreign key value (blue links) to jump to the referenced table.'"
              />
            </div>
          </div>

          <!-- Schema mode (ERD) -->
          <div v-if="centerMode === 'schema'" ref="erdContainer" class="flex-1 overflow-auto bg-gray-50 dark:bg-gray-950/50">
            <svg :width="svgWidth" :height="svgHeight" class="block">
              <!-- Relationship lines -->
              <g>
                <path
                  v-for="(ep, i) in edgePaths"
                  :key="'edge-' + i"
                  :d="ep.path"
                  fill="none"
                  stroke-width="1.5"
                  :stroke="selectedTable && (ep.edge.from_table === selectedTable || ep.edge.to_table === selectedTable) ? '#6366f1' : '#9ca3af'"
                  :stroke-opacity="selectedTable && (ep.edge.from_table === selectedTable || ep.edge.to_table === selectedTable) ? 0.8 : 0.3"
                  stroke-dasharray="4 3"
                  class="transition-all duration-200"
                />
                <!-- Arrow heads -->
                <circle
                  v-for="(ep, i) in edgePaths"
                  :key="'arrow-' + i"
                  :cx="ep.path.split(' ').slice(-2)[0]"
                  :cy="ep.path.split(' ').slice(-1)[0]"
                  r="3"
                  :fill="selectedTable && (ep.edge.from_table === selectedTable || ep.edge.to_table === selectedTable) ? '#6366f1' : '#9ca3af'"
                  :fill-opacity="selectedTable && (ep.edge.from_table === selectedTable || ep.edge.to_table === selectedTable) ? 0.8 : 0.3"
                />
              </g>

              <!-- Table cards -->
              <g v-for="cl in cardLayouts" :key="cl.table.name" :data-table="cl.table.name">
                <!-- Card background -->
                <rect
                  :x="cl.x" :y="cl.y" :width="cl.w" :height="cl.h"
                  rx="8" ry="8"
                  :class="{
                    'cursor-pointer': true,
                  }"
                  :fill="selectedTable === cl.table.name ? (isDark ? '#1e1b4b' : '#eef2ff') : (isDark ? '#111827' : '#ffffff')"
                  :stroke="selectedTable === cl.table.name ? '#6366f1' : relatedTables.has(cl.table.name) ? '#818cf8' : (isDark ? '#374151' : '#e5e7eb')"
                  :stroke-width="selectedTable === cl.table.name ? 2 : 1"
                  @click="clickErdCard(cl.table.name)"
                  class="transition-all duration-200"
                />

                <!-- Header background -->
                <rect
                  :x="cl.x" :y="cl.y" :width="cl.w" :height="CARD_HEADER_H"
                  :rx="8" :ry="8"
                  :fill="selectedTable === cl.table.name ? '#6366f1' : {
                    financial: '#3b82f6',
                    investments: '#10b981',
                    property: '#f59e0b',
                    planning: '#8b5cf6',
                    system: '#6b7280'
                  }[classifyTable(cl.table.name)]"
                  :fill-opacity="selectedTable === cl.table.name ? 1 : 0.85"
                  @click="clickErdCard(cl.table.name)"
                  class="cursor-pointer"
                />
                <!-- Bottom corners of header (make square) -->
                <rect
                  :x="cl.x" :y="cl.y + CARD_HEADER_H - 8" :width="cl.w" :height="8"
                  :fill="selectedTable === cl.table.name ? '#6366f1' : {
                    financial: '#3b82f6',
                    investments: '#10b981',
                    property: '#f59e0b',
                    planning: '#8b5cf6',
                    system: '#6b7280'
                  }[classifyTable(cl.table.name)]"
                  :fill-opacity="selectedTable === cl.table.name ? 1 : 0.85"
                  @click="clickErdCard(cl.table.name)"
                  class="cursor-pointer"
                />

                <!-- Table name -->
                <text
                  :x="cl.x + 10" :y="cl.y + CARD_HEADER_H / 2 + 1"
                  dominant-baseline="middle"
                  fill="white"
                  font-size="12"
                  font-weight="600"
                  font-family="ui-monospace, monospace"
                  @click="clickErdCard(cl.table.name)"
                  class="cursor-pointer select-none"
                >{{ cl.table.name }}</text>

                <!-- Row count badge -->
                <text
                  :x="cl.x + cl.w - 10" :y="cl.y + CARD_HEADER_H / 2 + 1"
                  dominant-baseline="middle"
                  text-anchor="end"
                  fill="rgba(255,255,255,0.7)"
                  font-size="10"
                  font-family="ui-sans-serif, system-ui, sans-serif"
                  @click="clickErdCard(cl.table.name)"
                  class="cursor-pointer select-none"
                >{{ cl.table.row_count.toLocaleString() }} rows</text>

                <!-- Columns -->
                <g v-for="(col, ci) in cl.table.columns" :key="col.name">
                  <text
                    :x="cl.x + 10"
                    :y="cl.y + CARD_HEADER_H + CARD_PAD_Y + ci * CARD_ROW_H + CARD_ROW_H / 2 + 1"
                    dominant-baseline="middle"
                    :fill="col.primary_key ? '#d97706' : isColumnFk(cl.table.name, col.name) ? '#6366f1' : (isDark ? '#d1d5db' : '#374151')"
                    :font-weight="col.primary_key ? '600' : '400'"
                    font-size="11"
                    font-family="ui-monospace, monospace"
                  >
                    <tspan v-if="col.primary_key" font-size="10">&#x1F511; </tspan>
                    <tspan v-else-if="isColumnFk(cl.table.name, col.name)" font-size="10">&#x1F517; </tspan>
                    {{ col.name }}
                  </text>
                  <!-- Type badge -->
                  <text
                    :x="cl.x + cl.w - 10"
                    :y="cl.y + CARD_HEADER_H + CARD_PAD_Y + ci * CARD_ROW_H + CARD_ROW_H / 2 + 1"
                    dominant-baseline="middle"
                    text-anchor="end"
                    :fill="isDark ? '#6b7280' : '#9ca3af'"
                    font-size="10"
                    font-family="ui-sans-serif, system-ui, sans-serif"
                  >{{ formatType(col.type) }}</text>

                  <!-- Nullable indicator -->
                  <text
                    v-if="col.nullable"
                    :x="cl.x + cl.w - 10 - (formatType(col.type).length * 6) - 6"
                    :y="cl.y + CARD_HEADER_H + CARD_PAD_Y + ci * CARD_ROW_H + CARD_ROW_H / 2 + 1"
                    dominant-baseline="middle"
                    text-anchor="end"
                    :fill="isDark ? '#4b5563' : '#d1d5db'"
                    font-size="9"
                    font-family="ui-sans-serif, system-ui, sans-serif"
                  >?</text>
                </g>
              </g>
            </svg>
          </div>

          <!-- Data mode (Table Preview) -->
          <div v-else-if="centerMode === 'data'" class="flex-1 overflow-auto min-h-0">
            <!-- No table selected -->
            <div v-if="!selectedTable" class="flex items-center justify-center h-full">
              <p class="text-sm text-gray-400 dark:text-gray-500">Select a table from the left panel to preview its data</p>
            </div>

            <!-- Loading -->
            <div v-else-if="previewLoading" class="flex items-center justify-center h-48">
              <div class="animate-spin rounded-full h-6 w-6 border-b-2 border-indigo-500"></div>
            </div>

            <!-- Error -->
            <div v-else-if="previewError" class="flex items-center justify-center h-48">
              <p class="text-sm text-red-500">{{ previewError }}</p>
            </div>

            <!-- Data table -->
            <div v-else-if="previewData" class="flex flex-col h-full">
              <div class="flex-1 overflow-auto">
                <table class="w-full text-xs">
                  <thead class="sticky top-0 z-10">
                    <tr class="bg-gray-50 dark:bg-gray-800/80">
                      <th
                        v-for="col in previewData.columns"
                        :key="col"
                        :class="[
                          'px-3 py-2.5 text-left font-semibold whitespace-nowrap border-b border-gray-200 dark:border-gray-700',
                          isColumnPk(selectedTable!, col) ? 'text-amber-600 dark:text-amber-400' :
                          isColumnFk(selectedTable!, col) ? 'text-indigo-600 dark:text-indigo-400' :
                          'text-gray-600 dark:text-gray-300'
                        ]"
                      >
                        <span class="flex items-center gap-1">
                          <span v-if="isColumnPk(selectedTable!, col)" class="text-[10px]">&#x1F511;</span>
                          <span v-if="isColumnFk(selectedTable!, col)" class="text-[10px]">&#x1F517;</span>
                          {{ col }}
                          <span
                            v-if="selectedTableSchema"
                            class="ml-1 text-[9px] font-normal px-1 py-0.5 rounded bg-gray-100 dark:bg-gray-700 text-gray-400 dark:text-gray-500"
                          >{{ formatType(selectedTableSchema.columns.find(c => c.name === col)?.type ?? '') }}</span>
                        </span>
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr
                      v-for="(row, idx) in previewData.rows"
                      :key="idx"
                      class="border-b border-gray-50 dark:border-gray-800/50 hover:bg-gray-50/60 dark:hover:bg-gray-800/30 transition-colors"
                    >
                      <td
                        v-for="col in previewData.columns"
                        :key="col"
                        class="px-3 py-2 whitespace-nowrap max-w-[240px] truncate"
                        :title="formatCellValue(row[col])"
                      >
                        <!-- FK value: clickable link -->
                        <button
                          v-if="fkColumns.has(col) && row[col] != null"
                          @click.stop="jumpToFk(fkColumns.get(col)!.table, fkColumns.get(col)!.column, row[col])"
                          class="text-indigo-600 dark:text-indigo-400 hover:underline font-medium"
                        >{{ formatCellValue(row[col]) }}</button>
                        <!-- Normal value -->
                        <span v-else :class="row[col] === null || row[col] === undefined ? 'text-gray-300 dark:text-gray-600 italic' : 'text-gray-700 dark:text-gray-300'">
                          {{ formatCellValue(row[col]) }}
                        </span>
                      </td>
                    </tr>
                    <tr v-if="previewData.rows.length === 0">
                      <td :colspan="previewData.columns.length" class="px-4 py-8 text-center text-gray-400 dark:text-gray-500 text-sm">
                        No rows found
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>

              <!-- Pagination -->
              <div class="flex items-center justify-between px-4 py-2.5 border-t border-gray-100 dark:border-gray-800 bg-white dark:bg-gray-900 flex-shrink-0">
                <button
                  @click="prevPage"
                  :disabled="previewOffset === 0"
                  :class="[
                    'px-3 py-1.5 rounded-lg text-xs font-medium transition-colors',
                    previewOffset === 0
                      ? 'text-gray-300 dark:text-gray-600 cursor-not-allowed'
                      : 'text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800'
                  ]"
                >&larr; Prev</button>
                <span class="text-xs text-gray-500 dark:text-gray-400 tabular-nums">
                  {{ previewOffset + 1 }}&ndash;{{ Math.min(previewOffset + PAGE_SIZE, previewData.total) }}
                  of {{ previewData.total.toLocaleString() }}
                  <span class="text-gray-300 dark:text-gray-600 mx-1">|</span>
                  Page {{ previewCurrentPage }} / {{ previewTotalPages }}
                </span>
                <button
                  @click="nextPage"
                  :disabled="previewOffset + PAGE_SIZE >= previewData.total"
                  :class="[
                    'px-3 py-1.5 rounded-lg text-xs font-medium transition-colors',
                    previewOffset + PAGE_SIZE >= previewData.total
                      ? 'text-gray-300 dark:text-gray-600 cursor-not-allowed'
                      : 'text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800'
                  ]"
                >Next &rarr;</button>
              </div>
            </div>
          </div>
        </div>

        <!-- ═══ Bottom Panel: SQL Runner ═══ -->
        <div :class="[
          'flex-shrink-0 bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl overflow-hidden transition-all duration-200',
          sqlPanelOpen ? 'h-[300px]' : 'h-10'
        ]">
          <!-- Header -->
          <div
            @click="sqlPanelOpen = !sqlPanelOpen"
            class="flex items-center justify-between px-4 py-2 border-b border-gray-100 dark:border-gray-800 cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800/40 transition-colors flex-shrink-0"
          >
            <div class="flex items-center gap-1.5">
              <span class="text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">SQL Runner</span>
              <InfoTooltip text="<strong>SQL Runner</strong><br>Execute raw SQL queries against the database. Results limited to 100 rows. Press <code>Cmd+Enter</code> or <code>Ctrl+Enter</code> to run." />
            </div>
            <div class="flex items-center gap-2">
              <span v-if="sqlResult" class="text-[10px] text-gray-400 dark:text-gray-500 tabular-nums">
                {{ sqlResult.row_count }} row{{ sqlResult.row_count !== 1 ? 's' : '' }}
              </span>
              <svg
                xmlns="http://www.w3.org/2000/svg"
                viewBox="0 0 20 20"
                fill="currentColor"
                class="w-4 h-4 text-gray-400 dark:text-gray-500 transition-transform duration-200"
                :style="{ transform: sqlPanelOpen ? 'rotate(0deg)' : 'rotate(180deg)' }"
              >
                <path fill-rule="evenodd" d="M5.23 7.21a.75.75 0 011.06.02L10 11.168l3.71-3.938a.75.75 0 111.08 1.04l-4.25 4.5a.75.75 0 01-1.08 0l-4.25-4.5a.75.75 0 01.02-1.06z" clip-rule="evenodd" />
              </svg>
            </div>
          </div>

          <!-- SQL content -->
          <div v-if="sqlPanelOpen" class="flex flex-col h-[calc(100%-40px)]">
            <!-- Input area -->
            <div class="flex gap-2 px-3 py-2 flex-shrink-0">
              <textarea
                v-model="sqlText"
                @keydown="handleSqlKeydown"
                placeholder="SELECT * FROM accounts LIMIT 10"
                rows="3"
                class="flex-1 px-3 py-2 text-xs font-mono bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg text-gray-800 dark:text-gray-200 placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 focus:border-indigo-500 resize-none"
              ></textarea>
              <button
                @click="runSql"
                :disabled="sqlRunning || !sqlText.trim()"
                :class="[
                  'px-4 py-2 rounded-lg text-xs font-semibold transition-colors self-end',
                  sqlRunning || !sqlText.trim()
                    ? 'bg-gray-200 dark:bg-gray-700 text-gray-400 dark:text-gray-500 cursor-not-allowed'
                    : 'bg-indigo-600 hover:bg-indigo-700 text-white'
                ]"
              >
                <span v-if="sqlRunning" class="flex items-center gap-1.5">
                  <svg class="animate-spin h-3 w-3" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" fill="none"/><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/></svg>
                  Running...
                </span>
                <span v-else>Run</span>
              </button>
            </div>

            <!-- SQL error -->
            <div v-if="sqlError" class="px-3 py-2 flex-shrink-0">
              <div class="px-3 py-2 bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-800 rounded-lg text-xs text-red-600 dark:text-red-400 font-mono break-all">
                {{ sqlError }}
              </div>
            </div>

            <!-- SQL results -->
            <div v-if="sqlResult" class="flex-1 overflow-auto min-h-0 px-3 pb-2">
              <div class="border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden">
                <table class="w-full text-xs">
                  <thead class="sticky top-0 z-10">
                    <tr class="bg-gray-50 dark:bg-gray-800">
                      <th
                        v-for="col in sqlResult.columns"
                        :key="col"
                        class="px-3 py-2 text-left font-semibold text-gray-600 dark:text-gray-300 whitespace-nowrap border-b border-gray-200 dark:border-gray-700"
                      >{{ col }}</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr
                      v-for="(row, idx) in sqlResult.rows"
                      :key="idx"
                      class="border-b border-gray-50 dark:border-gray-800/50 hover:bg-gray-50/60 dark:hover:bg-gray-800/30"
                    >
                      <td
                        v-for="col in sqlResult.columns"
                        :key="col"
                        class="px-3 py-1.5 text-gray-700 dark:text-gray-300 whitespace-nowrap max-w-[200px] truncate"
                        :title="formatCellValue(row[col])"
                      >{{ formatCellValue(row[col]) }}</td>
                    </tr>
                    <tr v-if="sqlResult.rows.length === 0">
                      <td :colspan="sqlResult.columns.length" class="px-4 py-4 text-center text-gray-400 dark:text-gray-500">
                        Query returned no rows
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>

            <!-- Empty state -->
            <div v-if="!sqlResult && !sqlError && !sqlRunning" class="flex-1 flex items-center justify-center">
              <p class="text-xs text-gray-300 dark:text-gray-600">Press Cmd+Enter to run a query</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
