const BASE = '/api'

async function fetchJson<T>(url: string): Promise<T> {
  const res = await fetch(`${BASE}${url}`, {
    headers: { 'Content-Type': 'application/json' },
  })
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`)
  return res.json()
}

export interface PlanListItem {
  id: number
  name: string
  scenario_type: string
  is_active: boolean
}

export interface CellValue {
  value: number | null
  status: 'actuals' | 'forecast' | 'plan'
}

export type RowStatus = 'actuals' | 'forecast' | 'plan'

export type PlanTableRow = {
  status: RowStatus
  [metric: string]: CellValue | RowStatus
}

export interface PlanTable {
  plan_id: number
  plan_name: string
  years: number[]
  metrics: string[]
  rows: Record<string, PlanTableRow>
}

export const planningApi = {
  listPlans: () =>
    fetchJson<PlanListItem[]>('/plans/'),

  getPlanTable: (id: number) =>
    fetchJson<PlanTable>(`/plans/${id}/table`),
}
