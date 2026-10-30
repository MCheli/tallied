<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from 'vue'
import { useFormatters } from '../../composables/useFormatters'
import InfoTooltip from '../common/InfoTooltip.vue'
import DataTable from '../common/DataTable.vue'
import type { CategoryOption, Transaction } from '../../types'
import { api } from '../../api/client'
import { apiErrorMessage } from '../../composables/useApiError'

const props = defineProps<{
  transactions: Transaction[]
  loading: boolean
  page: number
  pageSize: number
  total: number
  accountNames?: Record<string, string>
}>()

function accountLabel(accountId: string | null | undefined): string {
  if (!accountId) return dash
  return props.accountNames?.[accountId] || accountId
}

const emit = defineEmits<{
  (e: 'page-change', page: number): void
  (e: 'search', term: string): void
  (e: 'categorized'): void
}>()

// ── Category editing ────────────────────────────────────────────────────────
const options = ref<CategoryOption[]>([])
const editingId = ref<string | null>(null)
const choice = ref('')            // "category||group", or "__new__"
const newCategory = ref('')
const newGroup = ref('')
const applyToMerchant = ref(true)
const saving = ref(false)
const editError = ref<string | null>(null)

const groupedOptions = computed(() => {
  const groups: Record<string, CategoryOption[]> = {}
  for (const o of options.value) (groups[o.category_group || 'Other'] ||= []).push(o)
  return groups
})

/** Plain-language label for who set a category; shown as the cell's tooltip. */
function sourceLabel(src: string | null | undefined): string {
  if (!src) return ''
  if (src === 'manual') return 'Set by you'
  if (src === 'email') return 'From an email receipt'
  if (src === 'diary') return 'Identified from your diary'
  if (src === 'rule:manual') return 'From your merchant rule'
  if (src === 'rule:research') return 'From a merchant rule Claude researched'
  if (src === 'rule:email') return 'From a merchant rule confirmed by a receipt'
  return `Set by ${src}`
}

async function startEdit(tx: Transaction) {
  editError.value = null
  editingId.value = tx.id
  choice.value = tx.category ? `${tx.category}||${tx.category_group || ''}` : ''
  newCategory.value = ''
  newGroup.value = ''
  applyToMerchant.value = true
  if (options.value.length === 0) {
    try { options.value = await api.getCategories() } catch (e) { editError.value = apiErrorMessage(e, 'Could not load categories') }
  }
}

async function saveEdit(tx: Transaction) {
  let category = '', group = ''
  if (choice.value === '__new__') { category = newCategory.value.trim(); group = newGroup.value.trim() || 'Other' }
  else [category, group] = choice.value.split('||')
  if (!category) { editError.value = 'Pick a category'; return }
  saving.value = true
  editError.value = null
  try {
    await api.updateTransaction(tx.id, { category, category_group: group || null })
    if (applyToMerchant.value && tx.merchant) {
      await api.createCategoryRule({ pattern: tx.merchant, match: 'exact', category, category_group: group || 'Other' })
    }
    if (!options.value.some(o => o.category === category)) options.value = [...options.value, { category, category_group: group || null }]
    editingId.value = null
    emit('categorized')
  } catch (e) {
    editError.value = apiErrorMessage(e, 'Could not save the category')
  } finally {
    saving.value = false
  }
}

const searchTerm = ref('')
let debounce: ReturnType<typeof setTimeout> | null = null

/** Search is debounced 300 ms so typing does not fire a request per keystroke. */
function onSearch() {
  if (debounce) clearTimeout(debounce)
  debounce = setTimeout(() => emit('search', searchTerm.value.trim()), 300)
}
onBeforeUnmount(() => { if (debounce) clearTimeout(debounce) })

const { currency, date, dash } = useFormatters()

const totalPages = computed(() => Math.ceil(props.total / props.pageSize))
</script>

<template>
  <div class="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 min-w-0">
    <div class="px-4 sm:px-5 py-4 border-b border-gray-200 dark:border-gray-800">
      <div class="flex flex-wrap items-center justify-between gap-3">
        <div class="pr-8">
          <h3 class="text-sm font-semibold text-gray-900 dark:text-white">Transactions <InfoTooltip text="Every transaction in the selected period, newest first, including income and transfers. Red = money out, green = money in. Search matches merchant, category and notes. Click a category to change it; tick “Always use this” to make a merchant rule, which also categorizes future synced transactions. Hover a category to see who set it.&lt;br&gt;&lt;br&gt;&lt;strong&gt;Source:&lt;/strong&gt; transactions from SimpleFIN, email receipts, manual entry and the seed." /></h3>
          <p class="text-xs text-gray-500 dark:text-gray-400 mt-0.5">{{ total }} total</p>
        </div>
        <div class="w-full sm:w-64">
          <input
            v-model="searchTerm"
            @input="onSearch"
            type="search"
            placeholder="Search transactions..."
            aria-label="Search transactions"
            class="w-full px-3 py-2 text-sm rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
          />
        </div>
      </div>
    </div>

    <div v-if="loading" class="flex items-center justify-center h-48">
      <div class="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-500"></div>
    </div>

    <div v-else class="px-4 sm:px-5">
      <DataTable :empty="transactions.length === 0" empty-text="No transactions in this period" :columns="5" dense>
        <thead>
          <tr>
            <th>Date</th>
            <th>Merchant</th>
            <th>Account</th>
            <th>Category</th>
            <th class="text-right">Amount</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="tx in transactions" :key="tx.id" class="hover:bg-gray-50 dark:hover:bg-gray-800">
            <td class="text-gray-600 dark:text-gray-400 whitespace-nowrap">{{ date(tx.date) }}</td>
            <td class="text-gray-900 dark:text-white max-w-[12rem] truncate" :title="tx.merchant || ''">{{ tx.merchant || dash }}</td>
            <td class="text-gray-500 dark:text-gray-400 text-xs whitespace-nowrap max-w-[10rem] truncate">{{ accountLabel(tx.account_id) }}</td>
            <td class="text-gray-600 dark:text-gray-400 whitespace-nowrap align-top">
              <div v-if="editingId === tx.id" class="flex flex-col gap-1.5 min-w-[13rem] py-1">
                <select v-model="choice" class="text-xs rounded border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-900 px-2 py-1.5" aria-label="Category">
                  <option value="" disabled>Choose a category</option>
                  <optgroup v-for="(opts, g) in groupedOptions" :key="g" :label="String(g)">
                    <option v-for="o in opts" :key="o.category + g" :value="`${o.category}||${o.category_group || ''}`">{{ o.category }}</option>
                  </optgroup>
                  <option value="__new__">New category…</option>
                </select>
                <template v-if="choice === '__new__'">
                  <input v-model="newCategory" placeholder="Category" class="text-xs rounded border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-900 px-2 py-1.5" />
                  <input v-model="newGroup" placeholder="Group (e.g. Food & Dining)" class="text-xs rounded border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-900 px-2 py-1.5" />
                </template>
                <label v-if="tx.merchant" class="flex items-center gap-1.5 text-[11px] whitespace-normal">
                  <input type="checkbox" v-model="applyToMerchant" />
                  Always use this for “{{ tx.merchant }}”
                </label>
                <p v-if="editError" class="text-[11px] text-red-600 dark:text-red-400 whitespace-normal">{{ editError }}</p>
                <div class="flex gap-1.5">
                  <button @click="saveEdit(tx)" :disabled="saving" class="text-xs px-2.5 py-1 rounded bg-indigo-600 text-white disabled:opacity-50">{{ saving ? 'Saving…' : 'Save' }}</button>
                  <button @click="editingId = null" class="text-xs px-2.5 py-1 rounded border border-gray-300 dark:border-gray-700">Cancel</button>
                </div>
              </div>
              <button v-else @click="startEdit(tx)" :title="sourceLabel(tx.category_source) || 'Set a category'"
                class="text-left hover:text-indigo-600 dark:hover:text-indigo-400 underline decoration-dotted decoration-gray-300 dark:decoration-gray-600 underline-offset-2">
                {{ tx.category || 'Uncategorized' }}
              </button>
            </td>
            <td class="text-right font-medium whitespace-nowrap" :class="(tx.amount ?? 0) >= 0 ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'">
              {{ currency(tx.amount) }}
            </td>
          </tr>
        </tbody>
      </DataTable>
    </div>

    <!-- Pagination -->
    <div v-if="totalPages > 1" class="flex items-center justify-between gap-2 px-4 sm:px-5 py-3 border-t border-gray-100 dark:border-gray-800">
      <button
        @click="emit('page-change', page - 1)"
        :disabled="page <= 1"
        class="px-3 py-2 min-h-[40px] text-sm rounded-lg border border-gray-200 dark:border-gray-700 disabled:opacity-40 hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
      >
        Previous
      </button>
      <span class="text-sm text-gray-500 dark:text-gray-400 text-center">Page {{ page }} of {{ totalPages }}</span>
      <button
        @click="emit('page-change', page + 1)"
        :disabled="page >= totalPages"
        class="px-3 py-2 min-h-[40px] text-sm rounded-lg border border-gray-200 dark:border-gray-700 disabled:opacity-40 hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
      >
        Next
      </button>
    </div>
  </div>
</template>
