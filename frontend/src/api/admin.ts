const BASE = '/api'

async function fetchJson<T>(url: string): Promise<T> {
  const res = await fetch(`${BASE}${url}`, {
    headers: { 'Content-Type': 'application/json' },
  })
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`)
  return res.json()
}

export interface AdminTable {
  table: string
  row_count: number
  date_column: string | null
  most_recent_date: string | null
}

export interface AdminTableData {
  table: string
  columns: string[]
  total: number
  limit: number
  offset: number
  rows: Record<string, unknown>[]
}

export interface AdminAccountRelated {
  account_id: string
  balance_snapshots: Record<string, unknown>[]
  transactions: Record<string, unknown>[]
  [key: string]: unknown
}

export const adminApi = {
  getTables: () =>
    fetchJson<AdminTable[]>('/admin/tables'),

  getTableData: (tableName: string, limit = 50, offset = 0) =>
    fetchJson<AdminTableData>(
      `/admin/tables/${encodeURIComponent(tableName)}?limit=${limit}&offset=${offset}`
    ),

  getAccountRelated: (id: string) =>
    fetchJson<AdminAccountRelated>(`/admin/accounts/${encodeURIComponent(id)}/related`),
}
