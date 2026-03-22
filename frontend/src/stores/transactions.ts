import { ref, reactive } from 'vue'
import { defineStore } from 'pinia'
import { api } from '../api/client'
import type { Transaction, CategorySummary, RecurringExpense, MonthlySpending } from '../types'

export const useTransactionStore = defineStore('transactions', () => {
  const items = ref<Transaction[]>([])
  const total = ref(0)
  const loading = ref(false)
  const error = ref<string | null>(null)

  const filters = reactive({
    from_date: '',
    to_date: '',
    category: '',
    category_group: '',
    account_id: '',
    merchant: '',
    page: 1,
    page_size: 25,
    search: '',
  })

  const categoryBreakdown = ref<CategorySummary[]>([])
  const recurring = ref<RecurringExpense[]>([])
  const monthlyTrend = ref<MonthlySpending[]>([])

  async function fetchTransactions() {
    loading.value = true
    error.value = null
    try {
      const params: Record<string, unknown> = {
        ...filters,
        offset: (filters.page - 1) * filters.page_size,
        limit: filters.page_size,
      }
      const result = await api.getTransactions(params)
      items.value = result.items
      total.value = result.total
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Failed to load transactions'
    } finally {
      loading.value = false
    }
  }

  async function fetchCategoryBreakdown(from?: string, to?: string) {
    try {
      categoryBreakdown.value = await api.getSpendingByCategory(from, to)
    } catch {
      categoryBreakdown.value = []
    }
  }

  async function fetchRecurring() {
    try {
      recurring.value = await api.getRecurring()
    } catch {
      recurring.value = []
    }
  }

  async function fetchMonthlyTrend() {
    try {
      monthlyTrend.value = await api.getMonthlyTrend()
    } catch {
      monthlyTrend.value = []
    }
  }

  return {
    items, total, loading, error, filters,
    categoryBreakdown, recurring, monthlyTrend,
    fetchTransactions, fetchCategoryBreakdown, fetchRecurring, fetchMonthlyTrend,
  }
})
