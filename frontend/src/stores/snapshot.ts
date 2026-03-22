import { ref } from 'vue'
import { defineStore } from 'pinia'
import { api } from '../api/client'
import type { SnapshotResponse, IncomeBreakdown } from '../types'

export const useSnapshotStore = defineStore('snapshot', () => {
  const data = ref<SnapshotResponse | null>(null)
  const income = ref<IncomeBreakdown | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)

  async function fetchSnapshot() {
    loading.value = true
    error.value = null
    try {
      data.value = await api.getSnapshot()
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Failed to load snapshot'
    } finally {
      loading.value = false
    }
  }

  async function fetchIncome() {
    try {
      income.value = await api.getIncomeCurrent()
    } catch {
      // income might not be available
    }
  }

  return { data, income, loading, error, fetchSnapshot, fetchIncome }
})
