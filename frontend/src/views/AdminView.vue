<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { adminApi, type AdminTable, type AdminTableData, type AdminAccountRelated } from '../api/admin'

// ── State ────────────────────────────────────────────────────────────────────

const tablesLoading = ref(false)
const tablesError = ref<string | null>(null)
const tables = ref<AdminTable[]>([])

const selectedTable = ref<string | null>(null)
const tableLoading = ref(false)
const tableError = ref<string | null>(null)
const tableData = ref<AdminTableData | null>(null)

const PAGE_SIZE = 50
const currentOffset = ref(0)

const relatedLoading = ref(false)
const relatedError = ref<string | null>(null)
const relatedData = ref<AdminAccountRelated | null>(null)
const selectedAccountId = ref<string | null>(null)
const expandedRelatedSection = ref<'snapshots' | 'transactions' | null>('snapshots')

// ── Derived ──────────────────────────────────────────────────────────────────

const currentPage = computed(() =>
  tableData.value ? Math.floor(currentOffset.value / PAGE_SIZE) + 1 : 1
)

const totalPages = computed(() =>
  tableData.value ? Math.ceil(tableData.value.total / PAGE_SIZE) : 0
)

const rangeStart = computed(() => currentOffset.value + 1)
const rangeEnd = computed(() =>
  tableData.value ? Math.min(currentOffset.value + PAGE_SIZE, tableData.value.total) : 0
)

const isAccountsTable = computed(() => selectedTable.value === 'accounts')

// ── Loaders ──────────────────────────────────────────────────────────────────

async function loadTables() {
  tablesLoading.value = true
  tablesError.value = null
  try {
    tables.value = await adminApi.getTables()
  } catch (e) {
    tablesError.value = e instanceof Error ? e.message : 'Failed to load tables'
  } finally {
    tablesLoading.value = false
  }
}

async function loadTableData(offset = 0) {
  if (!selectedTable.value) return
  tableLoading.value = true
  tableError.value = null
  relatedData.value = null
  selectedAccountId.value = null
  try {
    tableData.value = await adminApi.getTableData(selectedTable.value, PAGE_SIZE, offset)
    currentOffset.value = offset
  } catch (e) {
    tableError.value = e instanceof Error ? e.message : 'Failed to load table data'
  } finally {
    tableLoading.value = false
  }
}

async function loadRelated(accountId: string) {
  relatedLoading.value = true
  relatedError.value = null
  relatedData.value = null
  try {
    relatedData.value = await adminApi.getAccountRelated(accountId)
  } catch (e) {
    relatedError.value = e instanceof Error ? e.message : 'Failed to load related data'
  } finally {
    relatedLoading.value = false
  }
}

// ── Interactions ─────────────────────────────────────────────────────────────

function selectTable(name: string) {
  if (selectedTable.value === name) return
  selectedTable.value = name
  tableData.value = null
  relatedData.value = null
  selectedAccountId.value = null
  loadTableData(0)
}

function prevPage() {
  if (currentOffset.value === 0) return
  loadTableData(Math.max(0, currentOffset.value - PAGE_SIZE))
}

function nextPage() {
  if (!tableData.value) return
  if (currentOffset.value + PAGE_SIZE >= tableData.value.total) return
  loadTableData(currentOffset.value + PAGE_SIZE)
}

function handleRowClick(row: Record<string, unknown>) {
  if (!isAccountsTable.value) return
  const id = row['id'] as string | undefined
  if (!id) return
  if (selectedAccountId.value === id) {
    // toggle off
    selectedAccountId.value = null
    relatedData.value = null
    return
  }
  selectedAccountId.value = id
  loadRelated(id)
}

// ── Helpers ──────────────────────────────────────────────────────────────────

function formatCellValue(val: unknown): string {
  if (val === null || val === undefined) return '—'
  if (typeof val === 'object') return JSON.stringify(val)
  return String(val)
}

function formatDate(dateStr: string | null): string {
  if (!dateStr) return '—'
  // Dates come as ISO strings — show just the date part for compactness
  return dateStr.slice(0, 10)
}

function relatedTableColumns(rows: Record<string, unknown>[]): string[] {
  if (!rows.length) return []
  return Object.keys(rows[0])
}

// ── Init ─────────────────────────────────────────────────────────────────────

onMounted(loadTables)
</script>

<template>
  <div>
    <h2 class="text-lg font-bold text-gray-900 dark:text-white mb-6">Admin — Database Browser</h2>

    <div class="flex gap-4 items-start">

      <!-- Left panel: table list -->
      <aside class="w-60 flex-shrink-0">
        <div class="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl overflow-hidden">
          <div class="px-4 py-3 border-b border-gray-100 dark:border-gray-800">
            <span class="text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">Tables</span>
          </div>

          <!-- Loading -->
          <div v-if="tablesLoading" class="flex justify-center py-8">
            <div class="animate-spin rounded-full h-6 w-6 border-b-2 border-indigo-500"></div>
          </div>

          <!-- Error -->
          <div v-else-if="tablesError" class="px-4 py-4 text-xs text-red-500">{{ tablesError }}</div>

          <!-- List -->
          <ul v-else class="py-1">
            <li
              v-for="t in tables"
              :key="t.table"
              @click="selectTable(t.table)"
              :class="[
                'px-4 py-2.5 cursor-pointer transition-colors',
                selectedTable === t.table
                  ? 'bg-indigo-50 dark:bg-indigo-950'
                  : 'hover:bg-gray-50 dark:hover:bg-gray-800'
              ]"
            >
              <div class="flex items-center justify-between gap-2">
                <span
                  :class="[
                    'text-sm font-medium truncate',
                    selectedTable === t.table
                      ? 'text-indigo-700 dark:text-indigo-300'
                      : 'text-gray-800 dark:text-gray-200'
                  ]"
                >{{ t.table }}</span>
                <span class="text-xs text-gray-400 dark:text-gray-500 flex-shrink-0 tabular-nums">
                  {{ t.row_count.toLocaleString() }}
                </span>
              </div>
              <div v-if="t.most_recent_date" class="mt-0.5 text-xs text-gray-400 dark:text-gray-500">
                last {{ formatDate(t.most_recent_date) }}
              </div>
            </li>
          </ul>
        </div>
      </aside>

      <!-- Right panel: table data -->
      <div class="flex-1 min-w-0">

        <!-- Empty state -->
        <div
          v-if="!selectedTable"
          class="flex items-center justify-center h-64 bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl"
        >
          <p class="text-sm text-gray-400 dark:text-gray-500">Select a table to browse its data</p>
        </div>

        <template v-else>
          <!-- Table panel -->
          <div class="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl overflow-hidden">

            <!-- Header -->
            <div class="flex items-center justify-between px-4 py-3 border-b border-gray-100 dark:border-gray-800">
              <span class="text-sm font-semibold text-gray-900 dark:text-white">{{ selectedTable }}</span>
              <span v-if="tableData" class="text-xs text-gray-500 dark:text-gray-400 tabular-nums">
                {{ rangeStart.toLocaleString() }}–{{ rangeEnd.toLocaleString() }} of {{ tableData.total.toLocaleString() }} records
              </span>
            </div>

            <!-- Table loading -->
            <div v-if="tableLoading" class="flex justify-center py-16">
              <div class="animate-spin rounded-full h-7 w-7 border-b-2 border-indigo-500"></div>
            </div>

            <!-- Table error -->
            <div v-else-if="tableError" class="px-4 py-8 text-sm text-red-500 text-center">{{ tableError }}</div>

            <!-- Data table -->
            <div v-else-if="tableData" class="overflow-x-auto">
              <table class="w-full text-xs">
                <thead>
                  <tr class="bg-gray-50 dark:bg-gray-800/60">
                    <th
                      v-for="col in tableData.columns"
                      :key="col"
                      class="px-3 py-2.5 text-left font-semibold text-gray-600 dark:text-gray-300 whitespace-nowrap border-b border-gray-100 dark:border-gray-800"
                    >{{ col }}</th>
                  </tr>
                </thead>
                <tbody>
                  <tr
                    v-for="(row, idx) in tableData.rows"
                    :key="idx"
                    :class="[
                      'border-b border-gray-50 dark:border-gray-800/50 transition-colors',
                      isAccountsTable
                        ? 'cursor-pointer hover:bg-indigo-50/60 dark:hover:bg-indigo-950/40'
                        : 'hover:bg-gray-50/60 dark:hover:bg-gray-800/30',
                      isAccountsTable && selectedAccountId === row['id']
                        ? 'bg-indigo-50 dark:bg-indigo-950/50'
                        : ''
                    ]"
                    @click="handleRowClick(row)"
                  >
                    <td
                      v-for="col in tableData.columns"
                      :key="col"
                      class="px-3 py-2 text-gray-700 dark:text-gray-300 whitespace-nowrap max-w-[220px] truncate"
                      :title="formatCellValue(row[col])"
                    >{{ formatCellValue(row[col]) }}</td>
                  </tr>
                  <tr v-if="tableData.rows.length === 0">
                    <td :colspan="tableData.columns.length" class="px-4 py-8 text-center text-gray-400 dark:text-gray-500">
                      No rows found
                    </td>
                  </tr>
                </tbody>
              </table>

              <!-- Pagination -->
              <div
                v-if="tableData.total > PAGE_SIZE"
                class="flex items-center justify-between px-4 py-3 border-t border-gray-100 dark:border-gray-800"
              >
                <button
                  @click="prevPage"
                  :disabled="currentOffset === 0"
                  :class="[
                    'px-3 py-1.5 rounded-lg text-xs font-medium transition-colors',
                    currentOffset === 0
                      ? 'text-gray-300 dark:text-gray-600 cursor-not-allowed'
                      : 'text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800'
                  ]"
                >← Prev</button>

                <span class="text-xs text-gray-500 dark:text-gray-400 tabular-nums">
                  Page {{ currentPage }} of {{ totalPages }}
                </span>

                <button
                  @click="nextPage"
                  :disabled="currentOffset + PAGE_SIZE >= tableData.total"
                  :class="[
                    'px-3 py-1.5 rounded-lg text-xs font-medium transition-colors',
                    currentOffset + PAGE_SIZE >= tableData.total
                      ? 'text-gray-300 dark:text-gray-600 cursor-not-allowed'
                      : 'text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800'
                  ]"
                >Next →</button>
              </div>
            </div>
          </div>

          <!-- Accounts related-data drawer -->
          <div
            v-if="isAccountsTable && selectedAccountId"
            class="mt-4 bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl overflow-hidden"
          >
            <div class="flex items-center justify-between px-4 py-3 border-b border-gray-100 dark:border-gray-800">
              <span class="text-sm font-semibold text-gray-900 dark:text-white">
                Related data — account <span class="font-mono text-indigo-600 dark:text-indigo-400">{{ selectedAccountId }}</span>
              </span>
              <button
                @click="selectedAccountId = null; relatedData = null"
                class="text-xs text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 transition-colors"
              >✕ Close</button>
            </div>

            <!-- Related loading -->
            <div v-if="relatedLoading" class="flex justify-center py-10">
              <div class="animate-spin rounded-full h-6 w-6 border-b-2 border-indigo-500"></div>
            </div>

            <!-- Related error -->
            <div v-else-if="relatedError" class="px-4 py-6 text-sm text-red-500 text-center">{{ relatedError }}</div>

            <!-- Related content -->
            <div v-else-if="relatedData" class="divide-y divide-gray-100 dark:divide-gray-800">

              <!-- Section tabs -->
              <div class="flex gap-1 px-4 py-2 bg-gray-50 dark:bg-gray-800/40">
                <button
                  v-for="section in (['snapshots', 'transactions'] as const)"
                  :key="section"
                  @click="expandedRelatedSection = section"
                  :class="[
                    'px-3 py-1.5 rounded-md text-xs font-medium transition-colors capitalize',
                    expandedRelatedSection === section
                      ? 'bg-white dark:bg-gray-700 text-indigo-700 dark:text-indigo-300 shadow-sm'
                      : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200'
                  ]"
                >
                  {{ section === 'snapshots' ? 'Balance Snapshots' : 'Transactions' }}
                  <span class="ml-1 text-gray-400 dark:text-gray-500 tabular-nums">
                    ({{ section === 'snapshots'
                        ? relatedData.balance_snapshots.length
                        : relatedData.transactions.length }})
                  </span>
                </button>
              </div>

              <!-- Balance snapshots -->
              <div v-if="expandedRelatedSection === 'snapshots'" class="overflow-x-auto">
                <table v-if="relatedData.balance_snapshots.length" class="w-full text-xs">
                  <thead>
                    <tr class="bg-gray-50 dark:bg-gray-800/60">
                      <th
                        v-for="col in relatedTableColumns(relatedData.balance_snapshots)"
                        :key="col"
                        class="px-3 py-2.5 text-left font-semibold text-gray-600 dark:text-gray-300 whitespace-nowrap border-b border-gray-100 dark:border-gray-800"
                      >{{ col }}</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr
                      v-for="(row, idx) in relatedData.balance_snapshots"
                      :key="idx"
                      class="border-b border-gray-50 dark:border-gray-800/50 hover:bg-gray-50/60 dark:hover:bg-gray-800/30"
                    >
                      <td
                        v-for="col in relatedTableColumns(relatedData.balance_snapshots)"
                        :key="col"
                        class="px-3 py-2 text-gray-700 dark:text-gray-300 whitespace-nowrap max-w-[200px] truncate"
                        :title="formatCellValue(row[col])"
                      >{{ formatCellValue(row[col]) }}</td>
                    </tr>
                  </tbody>
                </table>
                <p v-else class="px-4 py-6 text-sm text-gray-400 dark:text-gray-500 text-center">No balance snapshots</p>
              </div>

              <!-- Transactions -->
              <div v-if="expandedRelatedSection === 'transactions'" class="overflow-x-auto">
                <table v-if="relatedData.transactions.length" class="w-full text-xs">
                  <thead>
                    <tr class="bg-gray-50 dark:bg-gray-800/60">
                      <th
                        v-for="col in relatedTableColumns(relatedData.transactions)"
                        :key="col"
                        class="px-3 py-2.5 text-left font-semibold text-gray-600 dark:text-gray-300 whitespace-nowrap border-b border-gray-100 dark:border-gray-800"
                      >{{ col }}</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr
                      v-for="(row, idx) in relatedData.transactions"
                      :key="idx"
                      class="border-b border-gray-50 dark:border-gray-800/50 hover:bg-gray-50/60 dark:hover:bg-gray-800/30"
                    >
                      <td
                        v-for="col in relatedTableColumns(relatedData.transactions)"
                        :key="col"
                        class="px-3 py-2 text-gray-700 dark:text-gray-300 whitespace-nowrap max-w-[200px] truncate"
                        :title="formatCellValue(row[col])"
                      >{{ formatCellValue(row[col]) }}</td>
                    </tr>
                  </tbody>
                </table>
                <p v-else class="px-4 py-6 text-sm text-gray-400 dark:text-gray-500 text-center">No transactions</p>
              </div>

            </div>
          </div>

        </template>
      </div>
    </div>
  </div>
</template>
