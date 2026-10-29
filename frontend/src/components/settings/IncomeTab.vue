<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { api } from '../../api/client'
import { useFormatters } from '../../composables/useFormatters'
import InfoTooltip from '../common/InfoTooltip.vue'
import type { W2Record } from '../../types'

const { currency } = useFormatters()

// Every numeric W-2 field the Income page reads. Grouped for the form.
type W2Field = keyof Omit<W2Record, 'id' | 'tax_year'>
const FIELD_GROUPS: { title: string; fields: { key: W2Field; label: string }[] }[] = [
  {
    title: 'Pay',
    fields: [
      { key: 'gross_pay', label: 'Gross pay (Box 5 Medicare wages)' },
      { key: 'base_salary', label: 'Base salary' },
      { key: 'rsu_income', label: 'RSU income' },
      { key: 'w2_wages', label: 'Box 1 wages' },
    ],
  },
  {
    title: 'Taxes',
    fields: [
      { key: 'federal_tax', label: 'Federal tax (Box 2)' },
      { key: 'state_tax', label: 'State tax (Box 17)' },
      { key: 'social_security', label: 'Social Security tax (Box 4)' },
      { key: 'medicare', label: 'Medicare tax (Box 6)' },
    ],
  },
  {
    title: 'Retirement',
    fields: [
      { key: 'pretax_401k', label: 'Pre-tax 401(k) (Box 12 D)' },
      { key: 'roth_401k', label: 'Roth 401(k) (Box 12 AA)' },
    ],
  },
  {
    title: 'Benefits',
    fields: [
      { key: 'cafeteria_125', label: 'Cafeteria / FSA (Section 125)' },
      { key: 'transit', label: 'Transit (Box 14)' },
      { key: 'employer_health', label: 'Employer health (Box 12 DD)' },
    ],
  },
]

type W2Form = { tax_year: number } & Record<W2Field, number | null>

const emptyW2Form = (): W2Form => ({
  tax_year: new Date().getFullYear(),
  gross_pay: null, base_salary: null, rsu_income: null, w2_wages: null,
  federal_tax: null, state_tax: null, social_security: null, medicare: null,
  pretax_401k: null, roth_401k: null,
  cafeteria_125: null, transit: null, employer_health: null,
})

function formFromRecord(w2: W2Record): W2Form {
  const f = emptyW2Form()
  f.tax_year = w2.tax_year
  for (const group of FIELD_GROUPS) for (const { key } of group.fields) f[key] = w2[key]
  return f
}

// A cleared input is sent as null, which the backend stores as NULL for that
// field (it only skips keys that are absent). Blank means "not known".
function payload(form: W2Form): Record<string, unknown> {
  const out: Record<string, unknown> = { tax_year: form.tax_year }
  for (const group of FIELD_GROUPS) for (const { key } of group.fields) {
    const v = form[key]
    out[key] = v === null || v === undefined || (typeof v === 'string' && v === '') ? null : v
  }
  return out
}

const w2Records = ref<W2Record[]>([])
const loading = ref(false)
const error = ref<string | null>(null)
const editingYear = ref<number | null>(null)
const showNewForm = ref(false)
const form = ref<W2Form>(emptyW2Form())

async function loadIncome() {
  loading.value = true
  error.value = null
  try {
    const data = await api.getIncomeHistory()
    w2Records.value = [...data.w2_records].sort((a, b) => b.tax_year - a.tax_year)
  } catch (e) {
    error.value = 'Failed to load W-2 records: ' + (e instanceof Error ? e.message : String(e))
  }
  loading.value = false
}

function startNew() {
  editingYear.value = null
  form.value = emptyW2Form()
  showNewForm.value = true
  error.value = null
}

function startEdit(w2: W2Record) {
  editingYear.value = w2.tax_year
  form.value = formFromRecord(w2)
  showNewForm.value = true
  error.value = null
}

function cancelForm() {
  showNewForm.value = false
  editingYear.value = null
  form.value = emptyW2Form()
}

async function save() {
  error.value = null
  try {
    await api.createW2(payload(form.value)) // upsert by tax_year
    cancelForm()
    await loadIncome()
  } catch (e) {
    error.value = 'Failed to save W-2: ' + (e instanceof Error ? e.message : String(e))
  }
}

const v = (n: number | null | undefined) => n ?? 0

// Same definitions as the Income page.
const totalTax = (w: W2Record) => v(w.federal_tax) + v(w.state_tax) + v(w.social_security) + v(w.medicare)
const total401k = (w: W2Record) => v(w.pretax_401k) + v(w.roth_401k)
const takeHome = (w: W2Record) =>
  v(w.gross_pay) - totalTax(w) - total401k(w) - v(w.cafeteria_125) - v(w.transit)

onMounted(loadIncome)

const inputClass = 'w-full px-3 py-1.5 text-sm rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white'
</script>

<template>
  <div class="min-w-0 bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 overflow-hidden">
    <div class="flex flex-wrap items-center justify-between gap-2 px-5 py-4 border-b border-gray-200 dark:border-gray-800">
      <h3 class="text-sm font-semibold text-gray-900 dark:text-white">
        W-2 Records
        <InfoTooltip text="One record per tax year. These feed the Income page, the Dashboard's compensation tiles and the Planning engine. Add every box you have; a blank field is stored as unknown." />
      </h3>
      <button
        @click="showNewForm ? cancelForm() : startNew()"
        class="px-3 py-1.5 text-sm rounded-lg bg-indigo-600 text-white hover:bg-indigo-700 transition-colors font-medium"
      >
        {{ showNewForm ? 'Cancel' : 'Add W-2' }}
      </button>
    </div>

    <!-- Form (add or edit) -->
    <div v-if="showNewForm" class="px-5 py-4 border-b border-gray-200 dark:border-gray-800 bg-gray-50 dark:bg-gray-800/50 space-y-4">
      <div class="max-w-[12rem]">
        <label class="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">Tax year</label>
        <input v-model.number="form.tax_year" type="number" :disabled="editingYear !== null" :class="[inputClass, 'disabled:opacity-60']" />
      </div>
      <div v-for="group in FIELD_GROUPS" :key="group.title">
        <div class="text-[11px] uppercase tracking-wider font-semibold text-gray-400 dark:text-gray-500 mb-2">{{ group.title }}</div>
        <div class="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-3">
          <div v-for="f in group.fields" :key="f.key">
            <label class="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">{{ f.label }}</label>
            <input v-model.number="form[f.key]" type="number" step="0.01" :class="inputClass" placeholder="—" />
          </div>
        </div>
      </div>
      <div class="flex gap-2">
        <button @click="save" class="px-3 py-1.5 text-sm rounded-lg bg-indigo-600 text-white hover:bg-indigo-700 transition-colors font-medium">
          {{ editingYear !== null ? 'Save changes' : 'Save' }}
        </button>
        <button @click="cancelForm" class="px-3 py-1.5 text-sm rounded-lg border border-gray-300 dark:border-gray-600 text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors">Cancel</button>
      </div>
    </div>

    <div v-if="error" class="px-5 py-3 text-sm text-red-600 dark:text-red-400 border-b border-gray-100 dark:border-gray-800">{{ error }}</div>

    <div v-if="loading" class="flex items-center justify-center h-32">
      <div class="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-500"></div>
    </div>

    <!-- Table: scrolls inside its own container on narrow screens -->
    <div v-else class="overflow-x-auto min-w-0">
      <table class="w-full min-w-[48rem] text-sm">
        <thead>
          <tr class="border-b border-gray-100 dark:border-gray-800">
            <th class="text-left px-5 py-3 font-medium text-gray-500 dark:text-gray-400">Year</th>
            <th class="text-right px-5 py-3 font-medium text-gray-500 dark:text-gray-400">Gross</th>
            <th class="text-right px-5 py-3 font-medium text-gray-500 dark:text-gray-400">Base</th>
            <th class="text-right px-5 py-3 font-medium text-gray-500 dark:text-gray-400">RSU</th>
            <th class="text-right px-5 py-3 font-medium text-gray-500 dark:text-gray-400">Total tax</th>
            <th class="text-right px-5 py-3 font-medium text-gray-500 dark:text-gray-400">401(k)</th>
            <th class="text-right px-5 py-3 font-medium text-gray-500 dark:text-gray-400">Take-home</th>
            <th class="text-right px-5 py-3 font-medium text-gray-500 dark:text-gray-400"></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="w2 in w2Records" :key="w2.tax_year" class="border-b border-gray-50 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-gray-800"
            :class="editingYear === w2.tax_year ? 'bg-indigo-50/50 dark:bg-indigo-950/30' : ''">
            <td class="px-5 py-3 text-gray-900 dark:text-white font-medium">{{ w2.tax_year }}</td>
            <td class="px-5 py-3 text-right text-gray-900 dark:text-white whitespace-nowrap">{{ currency(w2.gross_pay) }}</td>
            <td class="px-5 py-3 text-right text-gray-600 dark:text-gray-400 whitespace-nowrap">{{ currency(w2.base_salary) }}</td>
            <td class="px-5 py-3 text-right text-gray-600 dark:text-gray-400 whitespace-nowrap">{{ currency(w2.rsu_income) }}</td>
            <td class="px-5 py-3 text-right text-red-600 dark:text-red-400 whitespace-nowrap">{{ currency(totalTax(w2)) }}</td>
            <td class="px-5 py-3 text-right text-gray-600 dark:text-gray-400 whitespace-nowrap">{{ currency(total401k(w2)) }}</td>
            <td class="px-5 py-3 text-right text-gray-900 dark:text-white whitespace-nowrap">{{ currency(takeHome(w2)) }}</td>
            <td class="px-5 py-3 text-right">
              <button @click="startEdit(w2)" class="text-indigo-600 dark:text-indigo-400 hover:text-indigo-800 dark:hover:text-indigo-300 text-sm font-medium">Edit</button>
            </td>
          </tr>
          <tr v-if="w2Records.length === 0 && !loading">
            <td colspan="8" class="px-5 py-8 text-center text-gray-500 dark:text-gray-400">
              No W-2 records yet. Add one here or import a W-2 from the Income page.
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
