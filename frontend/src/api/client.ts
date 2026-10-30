import type {
  AccountWithBalance,
  CategorySummary,
  IncomeBreakdown,
  IncomeHistory,
  MonthlySpending,
  NetWorthSeries,
  MonthPace,
  WeeklyRecap,
  Household,
  PlanCatalogue,
  PlanCompareResponse,
  PlanCreate,
  PlanEvent,
  PlanEventInput,
  PlanOutlook,
  SprintResult,
  WhatIfRequest,
  PlanListItem,
  PlanResponse,
  PlanUpdate,
  RecurringExpense,
  SensitivityResponse,
  SnapshotResponse,
  Transaction,
  CategoryOption,
  CategoryRule,
  VarianceResponse,
  ImportLogEntry,
  PropertySummary,
  AmortizationResponse,
  PropertyValueHistoryResponse,
  AssetsSummary,
  Vehicle,
  VehicleHistory,
  AggregateVehicleHistory,
  VehicleRefreshResult,
  VehicleInput,
  LargeTransaction,
  SimpleFinStatus,
  SimpleFinAccountConfig,
  SimpleFinAccountType,
  SimpleFinConnectResult,
  SimpleFinSyncStatus,
  ForwardingEmail,
  EmailReceiptItem,
  RSUGrantsResponse,
  RSUSummary,
  PriceHistoryResponse,
  RetirementSummary,
  ApiKey,
  ApiKeyCreated,
  UsageSummary,
  Webhook,
  WebhookCreated,
  WebhookTestResult,
  SchemaResponse,
  TablePreview,
  QueryResult,
  DbCredential,
  DbCredentialCreated,
  PlatformUser,
  PlatformTenant,
  PlatformStats,
  PlatformUserDetail,
  PlatformTenantDetail,
  AuthMeResponse,
  AuthConfig,
  ImportConfig,
  ImportUploadResult,
  ImportSessionResponse,
  ImportChatResponse,
} from '../types'

const BASE = '/api/v1'
const API_ROOT = import.meta.env.VITE_API_URL || ''

export function buildQuery(params?: Record<string, unknown>): string {
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

function errorFor(res: Response, text: string): Error {
  return new Error(`${res.status}: ${text}`)
}

/**
 * The one request path: credentials, the JSON content type (unless the body is FormData),
 * and one retry after a 401 when the refresh token still works. Returns the Response of
 * the last attempt; callers decide how to read it.
 */
export async function request(url: string, options: RequestInit = {}, opts: { retry?: boolean } = {}): Promise<Response> {
  const isForm = typeof FormData !== 'undefined' && options.body instanceof FormData
  const init: RequestInit = {
    credentials: 'include',
    ...options,
    headers: isForm ? options.headers : { 'Content-Type': 'application/json', ...(options.headers || {}) },
  }
  const res = await fetch(`${BASE}${url}`, init)
  if (res.status !== 401 || opts.retry === false) return res
  // Try to refresh the access token once, shared across concurrent 401s
  if (!refreshPromise) {
    refreshPromise = tryRefreshToken().finally(() => { refreshPromise = null })
  }
  const refreshed = await refreshPromise
  if (!refreshed) return res
  return fetch(`${BASE}${url}`, init)
}

export async function fetchJson<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await request(url, options)
  if (!res.ok) throw errorFor(res, await res.text())
  return res.json()
}

/** Like fetchJson but never tries a token refresh (for the auth endpoints themselves). */
export async function fetchJsonNoRetry<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await request(url, options, { retry: false })
  if (!res.ok) throw errorFor(res, await res.text())
  return res.json()
}

/** For endpoints that answer 204 or an irrelevant body. */
export async function fetchVoid(url: string, options?: RequestInit): Promise<void> {
  const res = await request(url, options)
  if (!res.ok) throw errorFor(res, await res.text())
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
  updateTransaction: (id: string, data: Partial<Pick<Transaction, 'category' | 'category_group' | 'notes'>>) =>
    fetchJson<Transaction>(`/transactions/${encodeURIComponent(id)}`, { method: 'PUT', body: JSON.stringify(data) }),
  getCategories: () => fetchJson<CategoryOption[]>('/transactions/categories'),
  getCategoryRules: () => fetchJson<CategoryRule[]>('/transactions/category-rules'),
  createCategoryRule: (data: { pattern: string; match: 'exact' | 'prefix' | 'contains'; category: string; category_group: string }) =>
    fetchJson<{ rule: CategoryRule; recategorized: number }>('/transactions/category-rules', { method: 'POST', body: JSON.stringify(data) }),

  // Spending
  getSpendingByCategory: (from?: string, to?: string, accountTypes?: string[]) =>
    fetchJson<CategorySummary[]>('/spending/by-category' + buildQuery({
      from_date: from, to_date: to,
      account_types: accountTypes && accountTypes.length ? accountTypes.join(',') : undefined,
    })),
  getRecurring: (from?: string, to?: string, accountTypes?: string[]) =>
    fetchJson<RecurringExpense[]>('/spending/recurring' + buildQuery({
      from_date: from, to_date: to,
      account_types: accountTypes && accountTypes.length ? accountTypes.join(',') : undefined,
    })),
  getMonthlyTrend: (from?: string, to?: string, accountTypes?: string[]) =>
    fetchJson<MonthlySpending[]>('/spending/monthly-trend' + buildQuery({
      from_date: from, to_date: to,
      account_types: accountTypes && accountTypes.length ? accountTypes.join(',') : undefined,
    })),
  getExcludedCategories: () => fetchJson<string[]>('/spending/excluded-categories'),
  getLargeTransactions: (opts: { threshold?: number; days?: number; limit?: number; excludeIncome?: boolean; accountType?: string } = {}) =>
    fetchJson<LargeTransaction[]>('/transactions/large' + buildQuery({
      threshold: opts.threshold, days: opts.days, limit: opts.limit,
      exclude_income: opts.excludeIncome ? 'true' : undefined, account_type: opts.accountType,
    })),

  // Page summaries used by the Dashboard
  getRsuSummary: () => fetchJson<RSUSummary>('/rsu/summary'),
  getPropertySummary: () => fetchJson<PropertySummary>('/property/summary'),
  getAssetsSummary: () => fetchJson<AssetsSummary>('/assets/summary'),

  // Trends
  getNetWorth: (from?: string, to?: string) =>
    fetchJson<NetWorthSeries>('/trends/net-worth' + buildQuery({ from_date: from, to_date: to })),
  getMonthPace: (month?: string) => fetchJson<MonthPace>('/recap/month-pace' + buildQuery({ month })),
  getWeeklyRecap: (weekStart?: string) => fetchJson<WeeklyRecap>('/recap/weekly' + buildQuery({ week_start: weekStart })),
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
  deletePlan: (id: number) => fetchVoid(`/plans/${id}`, { method: 'DELETE' }),
  comparePlans: (ids: number[]) =>
    fetchJson<PlanCompareResponse>(`/plans/compare?ids=${ids.join(',')}`),
  getSensitivity: (id: number) => fetchJson<SensitivityResponse>(`/plans/${id}/sensitivity`),
  getVariance: (id: number) => fetchJson<VarianceResponse[]>(`/plans/${id}/variance`),

  // Planning v2: outlook, what-if, life events
  planning: {
    catalogue: () => fetchJson<PlanCatalogue>('/plans/catalogue'),
    household: () => fetchJson<Household>('/plans/household'),
    setBirthDate: (birth_date: string) =>
      fetchJson<Household>('/plans/household', { method: 'PUT', body: JSON.stringify({ birth_date }) }),
    sprint: (id: number, body: WhatIfRequest) =>
      fetchJson<SprintResult>(`/plans/${id}/sprint`, { method: 'POST', body: JSON.stringify(body) }),
    outlook: (id: number, regime = 'base', analysis = true) =>
      fetchJson<PlanOutlook>(`/plans/${id}/outlook` + buildQuery({ regime, analysis: analysis ? undefined : 'false' })),
    whatIf: (id: number, body: WhatIfRequest) =>
      fetchJson<PlanOutlook>(`/plans/${id}/what-if`, { method: 'POST', body: JSON.stringify(body) }),
    addEvent: (planId: number, data: PlanEventInput) =>
      fetchJson<PlanEvent>(`/plans/${planId}/events`, { method: 'POST', body: JSON.stringify(data) }),
    updateEvent: (eventId: number, data: Partial<PlanEventInput>) =>
      fetchJson<PlanEvent>(`/plans/events/${eventId}`, { method: 'PUT', body: JSON.stringify(data) }),
    deleteEvent: (eventId: number) => fetchVoid(`/plans/events/${eventId}`, { method: 'DELETE' }),
  },

  // Import history
  getImportLog: () => fetchJson<ImportLogEntry[]>('/import/logs'),

  // SimpleFIN connection
  simplefin: {
    status: () => fetchJson<SimpleFinStatus>('/simplefin/status'),
    accounts: () => fetchJson<SimpleFinAccountConfig[]>('/simplefin/accounts'),
    accountTypes: () => fetchJson<SimpleFinAccountType[]>('/simplefin/account-types'),
    connect: (setup_token: string) =>
      fetchJson<SimpleFinConnectResult>('/simplefin/connect', { method: 'POST', body: JSON.stringify({ setup_token }) }),
    refreshCredentials: (setup_token: string) =>
      fetchJson<{ refreshed: boolean }>('/simplefin/refresh-credentials', { method: 'POST', body: JSON.stringify({ setup_token }) }),
    updateAccount: (id: number, data: { sync_balances?: boolean; sync_transactions?: boolean; account_type?: string }) =>
      fetchJson<SimpleFinAccountConfig>(`/simplefin/accounts/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
    sync: () => fetchJson<{ job_id: number | null; status: string; queued?: boolean; detail?: string }>('/simplefin/sync', { method: 'POST' }),
    syncStatus: () => fetchJson<SimpleFinSyncStatus>('/simplefin/sync/status'),
    disconnect: () => fetchJson<{ disconnected: boolean }>('/simplefin/disconnect', { method: 'DELETE' }),
  },

  // Email receipts
  email: {
    forwardingAddresses: () => fetchJson<ForwardingEmail[]>('/email-forwarding'),
    addForwardingAddress: (email: string) =>
      fetchJson<ForwardingEmail>('/email-forwarding', { method: 'POST', body: JSON.stringify({ email }) }),
    removeForwardingAddress: (id: number) =>
      fetchJson<{ status: string }>(`/email-forwarding/${id}`, { method: 'DELETE' }),
    receipts: (limit = 20) => fetchJson<EmailReceiptItem[]>(`/email-import/receipts?limit=${limit}`),
  },

  // RSU
  rsu: {
    getSummary: () => fetchJson<RSUSummary>('/rsu/summary'),
    getGrants: () => fetchJson<RSUGrantsResponse>('/rsu/grants'),
    getPriceHistory: (symbol: string, range = '5y') =>
      fetchJson<PriceHistoryResponse>('/rsu/price-history' + buildQuery({ symbol, range })),
  },

  // 401(k)
  retirement: {
    getSummary: () => fetchJson<RetirementSummary>('/retirement/summary'),
    updateRates: (pretax: number, roth: number) =>
      fetchJson<{ pretax_deferral_rate: number; roth_deferral_rate: number; total_deferral_rate: number }>(
        '/retirement/rates',
        { method: 'PUT', body: JSON.stringify({ pretax_deferral_rate: pretax, roth_deferral_rate: roth }) },
      ),
  },

  // Account management
  createAccount: (data: Record<string, unknown>) =>
    fetchJson<AccountWithBalance>('/accounts/', { method: 'POST', body: JSON.stringify(data) }),
  updateAccount: (id: string, data: Record<string, unknown>) =>
    fetchJson<AccountWithBalance>(`/accounts/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  getAccountRelatedCounts: (id: string) =>
    fetchJson<Record<string, number>>(`/accounts/${id}/related-counts`),
  deleteAccount: (id: string, cascade: boolean = false) =>
    fetchVoid(`/accounts/${id}${cascade ? '?cascade=true' : ''}`, { method: 'DELETE' }),

  // W2 management
  createW2: (data: Record<string, unknown>) =>
    fetchJson<Record<string, unknown>>('/income/w2', { method: 'POST', body: JSON.stringify(data) }),


  // Property
  property: {
    summary: () => fetchJson<PropertySummary>('/property/summary'),
    amortization: () => fetchJson<AmortizationResponse>('/property/amortization'),
    valueHistory: () => fetchJson<PropertyValueHistoryResponse>('/property/value-history'),
    addValuation: (data: { value: number; source: string; valuation_date?: string }) =>
      fetchJson<{ id: number; value: number; date: string; source: string }>('/property/valuation', { method: 'POST', body: JSON.stringify(data) }),
    refreshHistory: () => fetchJson<PropertyValueHistoryResponse>('/property/refresh-history', { method: 'POST' }),
  },

  // Assets (vehicles)
  assets: {
    summary: () => fetchJson<AssetsSummary>('/assets/summary'),
    aggregateHistory: () => fetchJson<AggregateVehicleHistory>('/assets/value-history/aggregate'),
    vehicleHistory: (id: number) => fetchJson<VehicleHistory>(`/assets/vehicles/${id}/value-history`),
    createVehicle: (data: VehicleInput) => fetchJson<Vehicle>('/assets/vehicles', { method: 'POST', body: JSON.stringify(data) }),
    updateVehicle: (id: number, data: { mileage?: number | null; condition?: string | null; notes?: string | null; purchase_price?: number | null; purchase_date?: string | null; vin?: string | null; trim?: string | null }) =>
      fetchJson<Vehicle>(`/assets/vehicles/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
    deleteVehicle: (id: number) => fetchJson<{ deleted: boolean }>(`/assets/vehicles/${id}`, { method: 'DELETE' }),
    refreshValue: (id: number) => fetchJson<VehicleRefreshResult>(`/assets/vehicles/${id}/refresh-value`, { method: 'POST' }),
  },

  // Auth (no refresh retry: these are the endpoints a refresh would call)
  auth: {
    config: () => fetchJsonNoRetry<AuthConfig>('/auth/config'),
    me: () => fetchJsonNoRetry<AuthMeResponse>('/auth/me'),
    login: (email: string, password: string) =>
      fetchJsonNoRetry<AuthMeResponse>('/auth/login', { method: 'POST', body: JSON.stringify({ email, password }) }),
    logout: () => fetchJsonNoRetry<{ message: string }>('/auth/logout', { method: 'POST' }),
    refresh: () => fetchJsonNoRetry<AuthMeResponse>('/auth/refresh', { method: 'POST' }),
    selectTenant: (tenant_id: number) =>
      fetchJsonNoRetry<AuthMeResponse>('/auth/select-tenant', { method: 'POST', body: JSON.stringify({ tenant_id }) }),
  },

  // API keys and usage
  keys: {
    list: () => fetchJson<ApiKey[]>('/api-keys/'),
    create: (name: string, permissions: string) =>
      fetchJson<ApiKeyCreated>('/api-keys/', { method: 'POST', body: JSON.stringify({ name, permissions }) }),
    revoke: (id: number) => fetchJson<{ message: string }>(`/api-keys/${id}`, { method: 'DELETE' }),
    usage: () => fetchJson<UsageSummary>('/api-keys/usage/summary'),
  },

  // Outbound webhooks
  webhooks: {
    list: () => fetchJson<Webhook[]>('/webhooks/'),
    create: (url: string, events: string[]) =>
      fetchJson<WebhookCreated>('/webhooks/', { method: 'POST', body: JSON.stringify({ url, events }) }),
    update: (id: number, data: { url?: string; events?: string[]; is_active?: boolean }) =>
      fetchJson<Webhook>(`/webhooks/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
    remove: (id: number) => fetchJson<{ message: string }>(`/webhooks/${id}`, { method: 'DELETE' }),
    test: (id: number) => fetchJson<WebhookTestResult>(`/webhooks/${id}/test`, { method: 'POST' }),
  },

  // Database explorer (tenant schema) and direct credentials
  admin: {
    schema: () => fetchJson<SchemaResponse>('/admin/schema'),
    preview: (table: string, limit: number, offset: number) =>
      fetchJson<TablePreview>(`/admin/tables/${encodeURIComponent(table)}/preview` + buildQuery({ limit, offset })),
    query: (sql: string, limit = 100) =>
      fetchJson<QueryResult>('/admin/query', { method: 'POST', body: JSON.stringify({ sql, limit }) }),
    createRow: (table: string, data: Record<string, unknown>) =>
      fetchJson<{ row: Record<string, unknown> }>(`/admin/tables/${encodeURIComponent(table)}/rows`, { method: 'POST', body: JSON.stringify({ data }) }),
    updateRow: (table: string, id: string | number, data: Record<string, unknown>) =>
      fetchJson<{ row: Record<string, unknown> }>(`/admin/tables/${encodeURIComponent(table)}/rows/${encodeURIComponent(String(id))}`, { method: 'PUT', body: JSON.stringify({ data }) }),
    deleteRow: (table: string, id: string | number) =>
      fetchJson<{ deleted: boolean }>(`/admin/tables/${encodeURIComponent(table)}/rows/${encodeURIComponent(String(id))}`, { method: 'DELETE' }),
  },
  dbCredentials: {
    list: () => fetchJson<DbCredential[]>('/db-credentials/'),
    create: (data: { name: string; access_level: string; expires_in_days: number | null }) =>
      fetchJson<DbCredentialCreated>('/db-credentials/', { method: 'POST', body: JSON.stringify(data) }),
    revoke: (id: number) => fetchVoid(`/db-credentials/${id}`, { method: 'DELETE' }),
  },

  // Platform admin (admin users only)
  platform: {
    users: () => fetchJson<PlatformUser[]>('/platform/users'),
    user: (id: number | string) => fetchJson<PlatformUserDetail>(`/platform/users/${id}`),
    updateUser: (id: number, data: { is_active?: boolean; is_admin?: boolean }) =>
      fetchJson<PlatformUserDetail>(`/platform/users/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
    approveUser: (id: number) => fetchJson<Record<string, unknown>>(`/platform/users/${id}/approve`, { method: 'POST' }),
    tenants: () => fetchJson<PlatformTenant[]>('/platform/tenants'),
    tenant: (id: number | string) => fetchJson<PlatformTenantDetail>(`/platform/tenants/${id}`),
    updateTenant: (id: number, data: { is_active?: boolean }) =>
      fetchJson<PlatformTenantDetail>(`/platform/tenants/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
    stats: () => fetchJson<PlatformStats>('/platform/stats'),
  },

  // Document import (unified review flow)
  import: {
    config: (context: string) => fetchJson<ImportConfig>(`/import/config/${context}`),
    upload: (file: File, context: string) => {
      const form = new FormData()
      form.append('file', file)
      form.append('context', context)
      return fetchJson<ImportUploadResult>('/import/upload', { method: 'POST', body: form })
    },
    session: (id: string) => fetchJson<ImportSessionResponse>(`/import/${id}`),
    accept: (id: string, accepted_change_ids: string[]) =>
      fetchJson<{ accepted: number }>(`/import/${id}/accept`, { method: 'PUT', body: JSON.stringify({ accepted_change_ids }) }),
    confirm: (id: string) =>
      fetchJson<{ status: string; changes_applied: number; results: unknown[] }>(`/import/${id}/confirm`, { method: 'POST' }),
    chat: (id: string, message: string) =>
      fetchJson<ImportChatResponse>(`/import/${id}/chat`, { method: 'POST', body: JSON.stringify({ message }) }),
    applyAction: (id: string) =>
      fetchJson<{ applied: boolean; message: string }>(`/import/${id}/apply-action`, { method: 'POST' }),
  },
}
