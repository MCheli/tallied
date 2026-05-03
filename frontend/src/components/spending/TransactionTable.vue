<script setup lang="ts">
import { computed, ref } from 'vue'
import { useFormatters } from '../../composables/useFormatters'
import InfoTooltip from '../common/InfoTooltip.vue'
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
  if (!accountId) return '—'
  return props.accountNames?.[accountId] || accountId
}

const emit = defineEmits<{
  (e: 'page-change', page: number): void
  (e: 'search', term: string): void
}>()

const searchTerm = ref('')

function onSearch() {
  emit('search', searchTerm.value)
}

const { currency, dateShort } = useFormatters()

const totalPages = computed(() => Math.ceil(props.total / props.pageSize))
</script>

<template>
  <div class="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 overflow-hidden">
    <div class="px-5 py-4 border-b border-gray-200 dark:border-gray-800">
      <div class="flex items-center justify-between">
        <div>
          <h3 class="text-sm font-semibold text-gray-900 dark:text-white">Transactions <InfoTooltip text="All transactions for the selected time period, sorted by date (newest first). Amounts: negative (red) = expenses, positive (green) = income/deposits. Use the search box to filter by merchant name.&lt;br&gt;&lt;br&gt;&lt;strong&gt;Source:&lt;/strong&gt; Transactions table. Sources include Plaid (automatic bank sync) and Monarch (historical import)." /></h3>
          <p class="text-xs text-gray-500 dark:text-gray-400 mt-0.5">{{ total }} total</p>
        </div>
        <div class="w-64">
          <input
            v-model="searchTerm"
            @input="onSearch"
            type="text"
            placeholder="Search transactions..."
            class="w-full px-3 py-1.5 text-sm rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
          />
        </div>
      </div>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="flex items-center justify-center h-48">
      <div class="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-500"></div>
    </div>

    <!-- Table -->
    <div v-else class="overflow-x-auto">
      <table class="w-full text-sm">
        <thead>
          <tr class="border-b border-gray-100 dark:border-gray-800">
            <th class="text-left px-5 py-3 font-medium text-gray-500 dark:text-gray-400">Date</th>
            <th class="text-left px-5 py-3 font-medium text-gray-500 dark:text-gray-400">Merchant</th>
            <th class="text-left px-5 py-3 font-medium text-gray-500 dark:text-gray-400">Account</th>
            <th class="text-left px-5 py-3 font-medium text-gray-500 dark:text-gray-400">Category</th>
            <th class="text-right px-5 py-3 font-medium text-gray-500 dark:text-gray-400">Amount</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="tx in transactions"
            :key="tx.id"
            class="border-b border-gray-50 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-gray-800"
          >
            <td class="px-5 py-3 text-gray-600 dark:text-gray-400 whitespace-nowrap">{{ dateShort(tx.date) }}</td>
            <td class="px-5 py-3 text-gray-900 dark:text-white">{{ tx.merchant || '\u2014' }}</td>
            <td class="px-5 py-3 text-gray-500 dark:text-gray-400 text-xs whitespace-nowrap">{{ accountLabel(tx.account_id) }}</td>
            <td class="px-5 py-3 text-gray-600 dark:text-gray-400">{{ tx.category || '\u2014' }}</td>
            <td
              class="px-5 py-3 text-right font-medium whitespace-nowrap"
              :class="(tx.amount ?? 0) >= 0 ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'"
            >
              {{ currency(tx.amount) }}
            </td>
          </tr>
          <tr v-if="transactions.length === 0">
            <td colspan="5" class="px-5 py-8 text-center text-gray-500 dark:text-gray-400">
              No transactions found
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Pagination -->
    <div v-if="totalPages > 1" class="flex items-center justify-between px-5 py-3 border-t border-gray-100 dark:border-gray-800">
      <button
        @click="emit('page-change', page - 1)"
        :disabled="page <= 1"
        class="px-3 py-1.5 text-sm rounded-lg border border-gray-200 dark:border-gray-700 disabled:opacity-40 hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
      >
        Previous
      </button>
      <span class="text-sm text-gray-500 dark:text-gray-400">
        Page {{ page }} of {{ totalPages }}
      </span>
      <button
        @click="emit('page-change', page + 1)"
        :disabled="page >= totalPages"
        class="px-3 py-1.5 text-sm rounded-lg border border-gray-200 dark:border-gray-700 disabled:opacity-40 hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
      >
        Next
      </button>
    </div>
  </div>
</template>
