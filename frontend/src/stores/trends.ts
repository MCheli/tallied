import { ref } from 'vue'
import { defineStore } from 'pinia'
import { api } from '../api/client'
import type { NetWorthSeries, AccountWithBalance } from '../types'

export const useTrendsStore = defineStore('trends', () => {
  const netWorth = ref<NetWorthSeries | null>(null)
  const accounts = ref<AccountWithBalance[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)

  async function fetchNetWorth(from?: string, to?: string) {
    loading.value = true
    error.value = null
    try {
      netWorth.value = await api.getNetWorth(from, to)
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Failed to load net worth'
    } finally {
      loading.value = false
    }
  }

  async function fetchAccounts() {
    try {
      accounts.value = await api.getAccounts()
    } catch {
      accounts.value = []
    }
  }

  return { netWorth, accounts, loading, error, fetchNetWorth, fetchAccounts }
})
