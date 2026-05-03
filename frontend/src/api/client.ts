import type {
  AccountWithBalance,
  CategorySummary,
  IncomeBreakdown,
  IncomeHistory,
  MonthlySpending,
  NetWorthSeries,
  PlanCompareResponse,
  PlanCreate,
  PlanListItem,
  PlanResponse,
  PlanUpdate,
  RecurringExpense,
  SensitivityResponse,
  SnapshotResponse,
  Transaction,
  VarianceResponse,
  ImportPayload,
  ImportResponse,
} from '../types'

const BASE = '/api/v1'
const API_ROOT = import.meta.env.VITE_API_URL || ''

function buildQuery(params?: Record<string, unknown>): string {
  if (!params) return ''
  const entries = Object.entries(params).filter(([, v]) => v != null && v !== '')
  if (entries.length === 0) return ''
  const qs = new URLSearchParams()
  for (const [k, v] of entries) qs.append(k, String(v))
  return '?' + qs.toString()
}

let refreshPromise: Promise<boolean> | null = null

async function tryRefreshToken(): Promise<boolean> {
  try {
    const res = await fetch(`${API_ROOT}/api/v1/auth/refresh`, {
      method: 'POST',
      credentials: 'include',
    })
    return res.ok
  } catch {
    return false
  }
}

async function fetchJson<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${url}`, {
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    ...options,
  })
  if (res.status === 401) {
    // Try to refresh the access token once
    if (!refreshPromise) {
      refreshPromise = tryRefreshToken().finally(() => { refreshPromise = null })
    }
    const refreshed = await refreshPromise
    if (refreshed) {
      // Retry the original request
      const retry = await fetch(`${BASE}${url}`, {
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        ...options,
      })
      if (!retry.ok) throw new Error(`${retry.status}: ${await retry.text()}`)
      return retry.json()
    }
    throw new Error(`${res.status}: ${await res.text()}`)
  }
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`)
  return res.json()
}

export const api = {
  // Health
  health: () => fetchJson<{ status: string }>('/health'),

  // Snapshot
  getSnapshot: () => fetchJson<SnapshotResponse>('/snapshot'),

  // Accounts
  getAccounts: (params?: Record<string, unknown>) =>
    fetchJson<AccountWithBalance[]>('/accounts/' + buildQuery(params)),
  getAccountBalances: (id: string, from?: string, to?: string) =>
    fetchJson<{ date: string; balance: number; source: string }[]>(
      `/accounts/${id}/balances` + buildQuery({ from_date: from, to_date: to })
    ),

  // Transactions
  getTransactions: (params: Record<string, unknown>) =>
    fetchJson<{ items: Transaction[]; total: number }>('/transactions/' + buildQuery(params)),

  // Spending
  getSpendingByCategory: (from?: string, to?: string) =>
    fetchJson<CategorySummary[]>('/spending/by-category' + buildQuery({ from_date: from, to_date: to })),
  getRecurring: () => fetchJson<RecurringExpense[]>('/spending/recurring'),
  getMonthlyTrend: () => fetchJson<MonthlySpending[]>('/spending/monthly-trend'),

  // Trends
  getNetWorth: (from?: string, to?: string) =>
    fetchJson<NetWorthSeries>('/trends/net-worth' + buildQuery({ from_date: from, to_date: to })),
  getCashFlow: () =>
    fetchJson<{ months: { month: string; changes: Record<string, number> }[] }>('/trends/cash-flow'),

  // Income
  getIncomeHistory: () => fetchJson<IncomeHistory>('/income/history'),
  getIncomeCurrent: () => fetchJson<IncomeBreakdown>('/income/current'),

  // Plans
  getPlans: () => fetchJson<PlanListItem[]>('/plans/'),
  getPlan: (id: number) => fetchJson<PlanResponse>(`/plans/${id}`),
  createPlan: (data: PlanCreate) =>
    fetchJson<PlanResponse>('/plans/', { method: 'POST', body: JSON.stringify(data) }),
  updatePlan: (id: number, data: PlanUpdate) =>
    fetchJson<PlanResponse>(`/plans/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  deletePlan: async (id: number) => {
    const res = await fetch(`${BASE}/plans/${id}`, { method: 'DELETE' })
    if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`)
  },
  comparePlans: (ids: number[]) =>
    fetchJson<PlanCompareResponse>(`/plans/compare?ids=${ids.join(',')}`),
  getSensitivity: (id: number) => fetchJson<SensitivityResponse>(`/plans/${id}/sensitivity`),
  getVariance: (id: number) => fetchJson<VarianceResponse[]>(`/plans/${id}/variance`),

  // Import
  importData: (data: ImportPayload) =>
    fetchJson<ImportResponse>('/import/', { method: 'POST', body: JSON.stringify(data) }),
  getImportLog: () => fetchJson<any[]>('/import/log'),

  // Account management
  createAccount: (data: Record<string, unknown>) =>
    fetchJson<AccountWithBalance>('/accounts/', { method: 'POST', body: JSON.stringify(data) }),
  updateAccount: (id: string, data: Record<string, unknown>) =>
    fetchJson<AccountWithBalance>(`/accounts/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  getAccountRelatedCounts: (id: string) =>
    fetchJson<Record<string, number>>(`/accounts/${id}/related-counts`),
  deleteAccount: async (id: string, cascade: boolean = false) => {
    const res = await fetch(`${BASE}/accounts/${id}${cascade ? '?cascade=true' : ''}`, {
      method: 'DELETE',
      credentials: 'include',
    })
    if (res.status === 204) return
    const text = await res.text()
    throw new Error(`${res.status}: ${text}`)
  },

  // W2 management
  createW2: (data: Record<string, unknown>) =>
    fetchJson<any>('/income/w2', { method: 'POST', body: JSON.stringify(data) }),

  // Forecast
  generateForecast: (years?: number) =>
    fetchJson<any>('/plans/forecasts/generate' + buildQuery({ years_forward: years }), { method: 'POST' }),
}
