<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useDataExplorer, PAGE_TABLES, type DataContext } from '../../composables/useDataExplorer'
import { getFormConfig, type TableFormConfig } from '../../config/tableFormConfigs'

const API_BASE = import.meta.env.VITE_API_URL || ''

// ── Types ────────────────────────────────────────────────────────────────────

interface ColumnInfo {
  name: string
  type: string
  nullable: boolean
  primary_key: boolean
  default: string | null
  description?: string
}

interface ForeignKey {
  column: string
  references_table: string
  references_column: string
}

interface TableSchema {
  name: string
  description?: string
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

// ── State ────────────────────────────────────────────────────────────────────

const { isOpen, context, closeData } = useDataExplorer()

const schema = ref<SchemaResponse | null>(null)
const schemaLoading = ref(false)
const schemaError = ref<string | null>(null)

const activeTable = ref<string | null>(null)
const previewData = ref<PreviewResponse | null>(null)
const previewLoading = ref(false)
const previewError = ref<string | null>(null)
const previewOffset = ref(0)
const PAGE_SIZE = 20

// Entry form state
const mode = ref<'browse' | 'create' | 'edit'>('browse')
const formData = ref<Record<string, any>>({})
const editingId = ref<string | null>(null)
const saving = ref(false)
const saveError = ref<string | null>(null)
const saveSuccess = ref(false)
const deleting = ref(false)

// ── Computed ─────────────────────────────────────────────────────────────────

const tables = computed(() => schema.value?.tables ?? [])
const edges = computed(() => schema.value?.edges ?? [])

const relevantTables = computed(() => {
  const names = PAGE_TABLES[context.value] ?? []
  return names.map(name => tables.value.find(t => t.name === name)).filter(Boolean) as TableSchema[]
})

const activeTableSchema = computed(() =>
  tables.value.find(t => t.name === activeTable.value) ?? null
)

const activeFormConfig = computed<TableFormConfig | null>(() =>
  activeTable.value ? getFormConfig(activeTable.value) ?? null : null
)

const fkColumns = computed(() => {
  if (!activeTableSchema.value) return new Map<string, { table: string; column: string }>()
  const map = new Map<string, { table: string; column: string }>()
  for (const fk of activeTableSchema.value.foreign_keys) {
    map.set(fk.column, { table: fk.references_table, column: fk.references_column })
  }
  for (const e of edges.value) {
    if (e.from_table === activeTable.value) {
      map.set(e.from_column, { table: e.to_table, column: e.to_column })
    }
  }
  return map
})

const currentPage = computed(() =>
  previewData.value ? Math.floor(previewOffset.value / PAGE_SIZE) + 1 : 1
)

const totalPages = computed(() =>
  previewData.value ? Math.ceil(previewData.value.total / PAGE_SIZE) : 0
)

const contextLabel = computed(() => {
  const labels: Record<DataContext, string> = {
    spending: 'Spending', income: 'Income', cash: 'Cash', rsu: 'RSU',
    retirement: 'Retirement', property: 'Property', assets: 'Assets',
  }
  return labels[context.value] ?? context.value
})

const headerTitle = computed(() => {
  if (!activeTable.value) return null
  if (!activeFormConfig.value) return activeTable.value
  if (mode.value === 'create') return `New ${activeFormConfig.value.displayName.replace(/s$/, '')}`
  if (mode.value === 'edit') return `Edit ${activeFormConfig.value.displayName.replace(/s$/, '')}`
  return activeFormConfig.value.displayName
})

// ── API ──────────────────────────────────────────────────────────────────────

async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const headers: Record<string, string> = {}
  if (options?.method && options.method !== 'GET') {
    headers['Content-Type'] = 'application/json'
  }
  const res = await fetch(`${API_BASE}${path}`, {
    credentials: 'include',
    headers,
    ...options,
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(`${res.status}: ${text}`)
  }
  return res.json()
}

async function loadSchema() {
  if (schema.value) return
  schemaLoading.value = true
  schemaError.value = null
  try {
    schema.value = await apiFetch<SchemaResponse>('/api/v1/admin/schema')
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
      `/api/v1/admin/tables/${encodeURIComponent(tableName)}/preview?limit=${PAGE_SIZE}&offset=${offset}`
    )
    previewOffset.value = offset
  } catch (e) {
    previewError.value = e instanceof Error ? e.message : 'Failed to load preview'
  } finally {
    previewLoading.value = false
  }
}

async function saveRecord() {
  if (!activeTable.value || !activeFormConfig.value) return
  saving.value = true
  saveError.value = null
  saveSuccess.value = false
  try {
    if (mode.value === 'edit' && editingId.value != null) {
      await apiFetch(`/api/v1/admin/tables/${encodeURIComponent(activeTable.value)}/rows/${encodeURIComponent(editingId.value)}`, {
        method: 'PUT',
        body: JSON.stringify({ data: formData.value }),
      })
    } else {
      await apiFetch(`/api/v1/admin/tables/${encodeURIComponent(activeTable.value)}/rows`, {
        method: 'POST',
        body: JSON.stringify({ data: formData.value }),
      })
    }
    saveSuccess.value = true
    setTimeout(() => {
      saveSuccess.value = false
      mode.value = 'browse'
      loadPreview(activeTable.value!, previewOffset.value)
    }, 600)
  } catch (e) {
    saveError.value = e instanceof Error ? e.message : 'Failed to save'
  } finally {
    saving.value = false
  }
}

async function deleteRecord() {
  if (!activeTable.value || !editingId.value) return
  deleting.value = true
  try {
    await apiFetch(`/api/v1/admin/tables/${encodeURIComponent(activeTable.value)}/rows/${encodeURIComponent(editingId.value)}`, {
      method: 'DELETE',
    })
    mode.value = 'browse'
    loadPreview(activeTable.value, previewOffset.value)
  } catch (e) {
    saveError.value = e instanceof Error ? e.message : 'Failed to delete'
  } finally {
    deleting.value = false
  }
}

// ── Actions ──────────────────────────────────────────────────────────────────

function selectTable(name: string) {
  activeTable.value = name
  mode.value = 'browse'
  formData.value = {}
  editingId.value = null
  saveError.value = null
  loadPreview(name, 0)
}

function startCreate() {
  if (!activeFormConfig.value) return
  mode.value = 'create'
  editingId.value = null
  saveError.value = null
  formData.value = {}
  for (const field of activeFormConfig.value.fields) {
    if (field.type === 'checkbox') formData.value[field.name] = false
  }
}

function startEdit(row: Record<string, unknown>) {
  if (!activeFormConfig.value) return
  mode.value = 'edit'
  saveError.value = null
  editingId.value = String(row[activeFormConfig.value.pk] ?? '')
  formData.value = {}
  for (const field of activeFormConfig.value.fields) {
    const val = row[field.name]
    if (field.type === 'checkbox') {
      formData.value[field.name] = !!val
    } else if (field.type === 'date' && val) {
      formData.value[field.name] = String(val).substring(0, 10)
    } else {
      formData.value[field.name] = val ?? ''
    }
  }
}

function cancelForm() {
  mode.value = 'browse'
  saveError.value = null
}

function jumpToFk(tableName: string, _columnName: string, value: unknown) {
  if (value === null || value === undefined) return
  activeTable.value = tableName
  loadPreview(tableName, 0)
}

function prevPage() {
  if (!activeTable.value || previewOffset.value === 0) return
  loadPreview(activeTable.value, Math.max(0, previewOffset.value - PAGE_SIZE))
}

function nextPage() {
  if (!activeTable.value || !previewData.value) return
  if (previewOffset.value + PAGE_SIZE >= previewData.value.total) return
  loadPreview(activeTable.value, previewOffset.value + PAGE_SIZE)
}

function close() {
  activeTable.value = null
  previewData.value = null
  previewError.value = null
  mode.value = 'browse'
  formData.value = {}
  closeData()
}

// ── Helpers ──────────────────────────────────────────────────────────────────

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
  if (typeof val === 'boolean') return val ? 'Yes' : 'No'
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

function formatTableName(name: string): string {
  return name.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
}

// ── Watchers ─────────────────────────────────────────────────────────────────

watch(isOpen, (open) => {
  if (open) {
    loadSchema()
    activeTable.value = null
    previewData.value = null
    mode.value = 'browse'
    formData.value = {}
  }
})
</script>

<template>
  <Teleport to="body">
    <div v-if="isOpen" class="fixed inset-0 z-[100] flex items-center justify-center">
      <!-- Backdrop -->
      <div class="absolute inset-0 bg-black/50 backdrop-blur-sm" @click="close"></div>

      <!-- Modal -->
      <div class="relative w-[92vw] max-w-6xl max-h-[88vh] bg-white dark:bg-gray-900 rounded-xl shadow-2xl border border-gray-200 dark:border-gray-700 flex overflow-hidden">

        <!-- Left: Table list -->
        <div class="w-56 flex-shrink-0 border-r border-gray-200 dark:border-gray-700 flex flex-col bg-gray-50 dark:bg-gray-800/50">
          <div class="px-4 py-3 border-b border-gray-200 dark:border-gray-700">
            <div class="flex items-center gap-2">
              <svg class="w-4 h-4 text-gray-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M3 5v14c0 1.66 4.03 3 9 3s9-1.34 9-3V5"/><path d="M3 12c0 1.66 4.03 3 9 3s9-1.34 9-3"/>
              </svg>
              <h3 class="text-xs font-semibold text-gray-700 dark:text-gray-200 uppercase tracking-wider">{{ contextLabel }} Data</h3>
            </div>
          </div>

          <div v-if="schemaLoading" class="flex items-center justify-center py-8">
            <div class="animate-spin rounded-full h-5 w-5 border-b-2 border-indigo-500"></div>
          </div>
          <div v-else-if="schemaError" class="px-4 py-4 text-xs text-red-500">{{ schemaError }}</div>
          <div v-else class="flex-1 overflow-y-auto py-2">
            <button
              v-for="t in relevantTables"
              :key="t.name"
              @click="selectTable(t.name)"
              :class="[
                'w-full text-left px-4 py-2.5 text-xs transition-colors',
                activeTable === t.name
                  ? 'bg-indigo-50 dark:bg-indigo-950/50 text-indigo-700 dark:text-indigo-300 font-medium'
                  : 'text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700/50'
              ]"
            >
              <div class="font-medium">{{ formatTableName(t.name) }}</div>
              <div class="text-[10px] mt-0.5 opacity-60">{{ t.name }} &middot; {{ t.row_count.toLocaleString() }} rows</div>
            </button>
          </div>
        </div>

        <!-- Right: Content -->
        <div class="flex-1 flex flex-col min-w-0">
          <!-- Header -->
          <div class="flex items-center justify-between px-5 py-3 border-b border-gray-200 dark:border-gray-700 flex-shrink-0">
            <div class="flex items-center gap-3">
              <svg class="w-4 h-4 text-gray-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18"/><path d="M3 15h18"/><path d="M9 3v18"/>
              </svg>
              <h3 v-if="headerTitle" class="text-sm font-semibold text-gray-900 dark:text-white">{{ headerTitle }}</h3>
              <h3 v-else class="text-sm font-medium text-gray-400 dark:text-gray-500">Select a table</h3>
              <span v-if="previewData && mode === 'browse'" class="text-[10px] text-gray-400 dark:text-gray-500 tabular-nums">
                {{ previewData.total.toLocaleString() }} rows
              </span>
            </div>
            <div class="flex items-center gap-2">
              <button
                v-if="activeTable && mode === 'browse' && activeFormConfig"
                @click="startCreate"
                class="px-3 py-1.5 text-xs font-medium bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition-colors"
              >Add New</button>
              <button
                @click="close"
                class="p-1.5 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 transition-colors"
              >
                <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M18 6L6 18"/><path d="M6 6l12 12"/>
                </svg>
              </button>
            </div>
          </div>

          <!-- Table description -->
          <div v-if="activeFormConfig?.description && mode === 'browse'" class="px-5 py-2 bg-gray-50 dark:bg-gray-800/50 border-b border-gray-200 dark:border-gray-700 flex-shrink-0">
            <p class="text-[11px] text-gray-500 dark:text-gray-400 leading-relaxed">{{ activeFormConfig.description }}</p>
          </div>
          <div v-else-if="activeTableSchema?.description && mode === 'browse'" class="px-5 py-2 bg-gray-50 dark:bg-gray-800/50 border-b border-gray-200 dark:border-gray-700 flex-shrink-0">
            <p class="text-[11px] text-gray-500 dark:text-gray-400 leading-relaxed">{{ activeTableSchema.description }}</p>
          </div>

          <!-- Empty state -->
          <div v-if="!activeTable" class="flex-1 flex items-center justify-center">
            <div class="text-center">
              <svg class="w-10 h-10 text-gray-200 dark:text-gray-700 mx-auto mb-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
                <rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18"/><path d="M3 15h18"/><path d="M9 3v18"/>
              </svg>
              <p class="text-sm text-gray-400 dark:text-gray-500">Select a table to preview its data</p>
            </div>
          </div>

          <!-- ═══ BROWSE MODE ═══ -->
          <template v-else-if="mode === 'browse'">
            <!-- Loading -->
            <div v-if="previewLoading" class="flex items-center justify-center py-16">
              <div class="animate-spin rounded-full h-6 w-6 border-b-2 border-indigo-500"></div>
            </div>

            <!-- Error -->
            <div v-else-if="previewError" class="flex items-center justify-center py-16">
              <p class="text-sm text-red-500">{{ previewError }}</p>
            </div>

            <!-- Data table -->
            <div v-else-if="previewData" class="flex-1 overflow-auto min-h-0">
              <table class="w-full text-xs">
                <thead class="sticky top-0 z-10">
                  <tr class="bg-gray-50 dark:bg-gray-800/80">
                    <th
                      v-for="col in previewData.columns"
                      :key="col"
                      :class="[
                        'px-3 py-2.5 text-left font-semibold whitespace-nowrap border-b border-gray-200 dark:border-gray-700',
                        isColumnPk(activeTable!, col) ? 'text-amber-600 dark:text-amber-400' :
                        isColumnFk(activeTable!, col) ? 'text-indigo-600 dark:text-indigo-400' :
                        'text-gray-600 dark:text-gray-300'
                      ]"
                    >
                      <span class="flex items-center gap-1">
                        <span v-if="isColumnPk(activeTable!, col)" class="text-[10px]">&#x1F511;</span>
                        <span v-if="isColumnFk(activeTable!, col)" class="text-[10px]">&#x1F517;</span>
                        {{ col }}
                        <span
                          v-if="activeTableSchema"
                          class="ml-1 text-[9px] font-normal px-1 py-0.5 rounded bg-gray-100 dark:bg-gray-700 text-gray-400 dark:text-gray-500"
                        >{{ formatType(activeTableSchema.columns.find(c => c.name === col)?.type ?? '') }}</span>
                        <span
                          v-if="activeTableSchema?.columns.find(c => c.name === col)?.description"
                          class="relative ml-0.5 inline-flex items-center"
                        >
                          <span class="w-3.5 h-3.5 inline-flex items-center justify-center rounded-full bg-gray-200 dark:bg-gray-600 text-gray-500 dark:text-gray-300 text-[8px] font-bold cursor-help peer">i</span>
                          <span class="absolute left-1/2 -translate-x-1/2 bottom-full mb-1.5 hidden peer-hover:block w-max max-w-[260px] px-2.5 py-1.5 text-[10px] font-normal leading-snug text-white bg-gray-800 dark:bg-gray-700 rounded-lg shadow-lg z-50 whitespace-normal">
                            {{ activeTableSchema?.columns.find(c => c.name === col)?.description }}
                          </span>
                        </span>
                      </span>
                    </th>
                    <!-- Edit column when form config exists -->
                    <th v-if="activeFormConfig" class="px-3 py-2.5 border-b border-gray-200 dark:border-gray-700 w-12"></th>
                  </tr>
                </thead>
                <tbody>
                  <tr
                    v-for="(row, idx) in previewData.rows"
                    :key="idx"
                    :class="[
                      'border-b border-gray-50 dark:border-gray-800/50 hover:bg-gray-50/60 dark:hover:bg-gray-800/30 transition-colors',
                      activeFormConfig ? 'cursor-pointer' : ''
                    ]"
                    @click="activeFormConfig ? startEdit(row) : undefined"
                  >
                    <td
                      v-for="col in previewData.columns"
                      :key="col"
                      class="px-3 py-2 whitespace-nowrap max-w-[240px] truncate"
                      :title="formatCellValue(row[col])"
                    >
                      <button
                        v-if="fkColumns.has(col) && row[col] != null"
                        @click.stop="jumpToFk(fkColumns.get(col)!.table, fkColumns.get(col)!.column, row[col])"
                        class="text-indigo-600 dark:text-indigo-400 hover:underline font-medium"
                      >{{ formatCellValue(row[col]) }}</button>
                      <span v-else :class="row[col] === null || row[col] === undefined ? 'text-gray-300 dark:text-gray-600 italic' : 'text-gray-700 dark:text-gray-300'">
                        {{ formatCellValue(row[col]) }}
                      </span>
                    </td>
                    <td v-if="activeFormConfig" class="px-3 py-2 text-right">
                      <span class="text-gray-300 dark:text-gray-600 text-[10px]">Edit &rarr;</span>
                    </td>
                  </tr>
                  <tr v-if="previewData.rows.length === 0">
                    <td :colspan="previewData.columns.length + (activeFormConfig ? 1 : 0)" class="px-4 py-8 text-center text-gray-400 dark:text-gray-500 text-sm">
                      No rows found
                      <button v-if="activeFormConfig" @click="startCreate" class="block mx-auto mt-1 text-xs text-indigo-600 dark:text-indigo-400 hover:underline">
                        Add the first one
                      </button>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>

            <!-- Pagination -->
            <div v-if="previewData && previewData.total > PAGE_SIZE" class="flex items-center justify-between px-5 py-2.5 border-t border-gray-100 dark:border-gray-800 bg-white dark:bg-gray-900 flex-shrink-0">
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
                Page {{ currentPage }} / {{ totalPages }}
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
          </template>

          <!-- ═══ CREATE / EDIT FORM ═══ -->
          <template v-else-if="activeFormConfig && (mode === 'create' || mode === 'edit')">
            <div class="flex-1 overflow-auto min-h-0 px-6 py-5">
              <div class="max-w-2xl mx-auto space-y-4">
                <div v-for="field in activeFormConfig.fields" :key="field.name" class="group">
                  <!-- Checkbox fields -->
                  <template v-if="field.type === 'checkbox'">
                    <label class="flex items-start gap-3 cursor-pointer">
                      <input
                        type="checkbox"
                        v-model="formData[field.name]"
                        class="mt-0.5 h-4 w-4 rounded border-gray-300 dark:border-gray-600 text-indigo-600 focus:ring-indigo-500 dark:bg-gray-800"
                      />
                      <div>
                        <span class="text-xs font-medium text-gray-700 dark:text-gray-200">{{ field.label }}</span>
                        <p class="text-[11px] text-gray-400 dark:text-gray-500 leading-relaxed mt-0.5">{{ field.description }}</p>
                      </div>
                    </label>
                  </template>

                  <!-- All other fields -->
                  <template v-else>
                    <label class="block">
                      <div class="flex items-center gap-1.5 mb-1">
                        <span class="text-xs font-medium text-gray-700 dark:text-gray-200">{{ field.label }}</span>
                        <span v-if="field.required" class="text-red-400 text-[10px]">*</span>
                      </div>
                      <p class="text-[11px] text-gray-400 dark:text-gray-500 leading-relaxed mb-1.5">{{ field.description }}</p>

                      <!-- Select -->
                      <select
                        v-if="field.type === 'select'"
                        v-model="formData[field.name]"
                        class="w-full px-3 py-2 text-xs rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
                      >
                        <option value="">— Select —</option>
                        <option v-for="opt in field.options" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
                      </select>

                      <!-- Textarea -->
                      <textarea
                        v-else-if="field.type === 'textarea'"
                        v-model="formData[field.name]"
                        :placeholder="field.placeholder"
                        rows="3"
                        class="w-full px-3 py-2 text-xs rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 resize-none"
                      />

                      <!-- Number / Date / Text -->
                      <input
                        v-else
                        :type="field.type === 'number' ? 'number' : field.type === 'date' ? 'date' : 'text'"
                        v-model="formData[field.name]"
                        :placeholder="field.placeholder"
                        :required="field.required"
                        :step="field.step"
                        class="w-full px-3 py-2 text-xs rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
                      />
                    </label>
                  </template>
                </div>
              </div>
            </div>

            <!-- Form footer -->
            <div class="flex items-center justify-between px-6 py-3 border-t border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800/50 flex-shrink-0">
              <div class="flex items-center gap-2">
                <button
                  v-if="mode === 'edit'"
                  @click="deleteRecord"
                  :disabled="deleting"
                  class="px-3 py-1.5 text-xs font-medium text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-950/30 rounded-lg transition-colors disabled:opacity-50"
                >{{ deleting ? 'Deleting...' : 'Delete' }}</button>
              </div>
              <div class="flex items-center gap-2">
                <p v-if="saveError" class="text-xs text-red-500 mr-2 max-w-xs truncate" :title="saveError">{{ saveError }}</p>
                <p v-if="saveSuccess" class="text-xs text-green-500 mr-2">Saved!</p>
                <button @click="cancelForm"
                  class="px-4 py-1.5 text-xs font-medium text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg transition-colors"
                >Cancel</button>
                <button @click="saveRecord" :disabled="saving"
                  class="px-4 py-1.5 text-xs font-medium bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition-colors disabled:opacity-50"
                >{{ saving ? 'Saving...' : mode === 'create' ? 'Create' : 'Save Changes' }}</button>
              </div>
            </div>
          </template>
        </div>
      </div>
    </div>
  </Teleport>
</template>
