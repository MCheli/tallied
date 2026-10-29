import { fetchJson } from './client'

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
  current_age?: number
  retirement_age?: number
  retirement_year?: number
}

/** Planning calls go through the shared /api/v1 client (credentials + 401 refresh). */
export const planningApi = {
  listPlans: () => fetchJson<PlanListItem[]>('/plans/'),
  getPlanTable: (id: number) => fetchJson<PlanTable>(`/plans/${id}/table`),
}
