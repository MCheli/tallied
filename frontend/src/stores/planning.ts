import { ref } from 'vue'
import { defineStore } from 'pinia'
import { api } from '../api/client'
import type {
  PlanListItem,
  PlanResponse,
  SensitivityResponse,
  VarianceResponse,
  PlanCreate,
  PlanUpdate,
} from '../types'

export const usePlanningStore = defineStore('planning', () => {
  const plans = ref<PlanListItem[]>([])
  const activePlan = ref<PlanResponse | null>(null)
  const sensitivity = ref<SensitivityResponse | null>(null)
  const variance = ref<VarianceResponse[] | null>(null)
  const comparedPlans = ref<PlanResponse[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)

  async function fetchPlans() {
    loading.value = true
    error.value = null
    try {
      plans.value = await api.getPlans()
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Failed to load plans'
    } finally {
      loading.value = false
    }
  }

  async function fetchPlan(id: number) {
    loading.value = true
    error.value = null
    try {
      activePlan.value = await api.getPlan(id)
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Failed to load plan'
    } finally {
      loading.value = false
    }
  }

  async function createPlan(data: PlanCreate) {
    loading.value = true
    error.value = null
    try {
      const plan = await api.createPlan(data)
      activePlan.value = plan
      await fetchPlans()
      return plan
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Failed to create plan'
      return null
    } finally {
      loading.value = false
    }
  }

  async function updatePlan(id: number, data: PlanUpdate) {
    error.value = null
    try {
      activePlan.value = await api.updatePlan(id, data)
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Failed to update plan'
    }
  }

  async function deletePlan(id: number) {
    loading.value = true
    error.value = null
    try {
      await api.deletePlan(id)
      if (activePlan.value?.id === id) activePlan.value = null
      await fetchPlans()
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Failed to delete plan'
    } finally {
      loading.value = false
    }
  }

  async function fetchSensitivity(id: number) {
    try {
      sensitivity.value = await api.getSensitivity(id)
    } catch {
      sensitivity.value = null
    }
  }

  async function fetchVariance(id: number) {
    try {
      const result = await api.getVariance(id)
      variance.value = Array.isArray(result) ? result : [result]
    } catch {
      variance.value = null
    }
  }

  async function fetchComparison(ids: number[]) {
    try {
      const result = await api.comparePlans(ids)
      comparedPlans.value = result.plans
    } catch {
      comparedPlans.value = []
    }
  }

  return {
    plans, activePlan, sensitivity, variance, comparedPlans, loading, error,
    fetchPlans, fetchPlan, createPlan, updatePlan, deletePlan,
    fetchSensitivity, fetchVariance, fetchComparison,
  }
})
