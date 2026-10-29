<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from 'vue'
import { useFormatters } from '../../composables/useFormatters'
import InfoTooltip from '../common/InfoTooltip.vue'
import DataTable from '../common/DataTable.vue'
import type { Transaction } from '../../types'

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
}>()

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
          <h3 class="text-sm font-semibold text-gray-900 dark:text-white">Transactions <InfoTooltip text="Every transaction in the selected period, newest first, including income and transfers. Red = money out, green = money in. Search matches merchant, category and notes.&lt;br&gt;&lt;br&gt;&lt;strong&gt;Source:&lt;/strong&gt; transactions from SimpleFIN, email receipts, manual entry and the seed." /></h3>
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
            <td class="text-gray-600 dark:text-gray-400 whitespace-nowrap">{{ tx.category || dash }}</td>
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
