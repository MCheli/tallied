// ── Accounts ──
export interface Account {
  id: string
  name: string
  institution: string | null
  account_type: string
  display_group: string
  include_in_nw: boolean
  is_active: boolean
  notes: string | null
  source: string  // 'monarch' | 'simplefin' | 'plaid' | 'manual'
  created_at: string | null
  updated_at: string | null
}

export interface AccountWithBalance extends Account {
  current_balance: number | null
  balance_date: string | null
}

// ── Transactions ──
export interface Transaction {
  id: string
  account_id: string | null
  date: string
  amount: number | null
  merchant: string | null
  category: string | null
  category_group: string | null
  is_recurring: boolean
  notes: string | null
  source: string | null
  created_at: string | null
}

export interface TransactionFilter {
  from_date?: string
  to_date?: string
  category?: string
  category_group?: string
  account_id?: string
  merchant?: string
}

export interface CategorySummary {
  category: string
  category_group: string | null
  total: number
  count: number
  pct_of_total: number
}

export interface RecurringExpense {
  merchant: string
  category: string
  avg_monthly: number
  months_seen: number
  last_date: string
}

export interface MonthlySpending {
  month: string
  total: number
  count: number
}

// ── Snapshot ──
export interface LayerAccount {
  id: string
  name: string
  balance: number
}

export interface LiquidityLayer {
  name: string
  total: number
  accounts: LayerAccount[]
}

export interface SnapshotResponse {
  layers: LiquidityLayer[]
  net_worth: number
  liquid_net_worth: number
  total_comp_annual: number | null
  net_worth_12mo_change: number | null
}

export interface IncomeBreakdown {
  salary: number
  rsu_income: number
  total_comp: number
  rsu_pct: number
}

export interface BalanceHistory {
  dates: string[]
  balances: number[]
}

export interface NetWorthSeries {
  dates: string[]
  groups: Record<string, number[]>
  totals: number[]
}

// ── Planning ──
export interface AssumptionInput {
  key: string
  value: number
  display_name?: string
  description?: string
  category?: string
  sensitivity?: string
}

export interface AssumptionResponse {
  key: string
  display_name: string
  category: string
  value: number
  description: string
  sensitivity: string
}

export interface ProjectionRow {
  year: number
  age: number
  phase: string
  salary: number
  rsu_income: number
  total_comp: number
  cash: number
  investments: number
  company_stock: number
  home_equity: number
  retirement_bal: number
  net_worth: number
  withdrawal: number
}

export interface PlanResponse {
  id: number
  name: string
  description: string | null
  scenario_type: string
  is_active: boolean
  assumptions: AssumptionResponse[]
  projections: ProjectionRow[]
  created_at: string
  updated_at: string
}

export interface PlanListItem {
  id: number
  name: string
  scenario_type: string
  is_active: boolean
  created_at: string
}

export interface VarianceMetric {
  plan: number
  forecast: number | null
  actual: number
  plan_var_pct: number
  forecast_var_pct: number | null
}

export interface VarianceResponse {
  year: number
  metrics: Record<string, VarianceMetric>
}

export interface SensitivityItem {
  key: string
  display_name: string
  base_value: number
  impact_low: number
  impact_high: number
}

export interface SensitivityResponse {
  items: SensitivityItem[]
  target_metric: string
  target_year: number
}

export interface PlanCompareResponse {
  plans: PlanResponse[]
}

export interface PlanCreate {
  name: string
  description?: string
  scenario_type?: string
  assumptions: AssumptionInput[]
}

export interface PlanUpdate {
  name?: string
  description?: string
  assumptions?: AssumptionInput[]
}

// ── Import ──
export interface ImportPayload {
  source: string
  capture_mode: string
  captured_at?: string
  raw_data: Record<string, unknown> | string
}

export interface ImportResponse {
  import_id: number
  status: string
  records_created: number
  parsed_summary: Record<string, unknown> | null
}

// ── Income ──
export interface W2Record {
  id: number
  tax_year: number
  gross_pay: number | null
  w2_wages: number | null
  federal_tax: number | null
  state_tax: number | null
  social_security: number | null
  medicare: number | null
  pretax_401k: number | null
  roth_401k: number | null
  cafeteria_125: number | null
  transit: number | null
  employer_health: number | null
  base_salary: number | null
  rsu_income: number | null
}

export interface RSUGrant {
  id: number
  company: string
  grant_date: string | null
  total_shares: number
  vested_shares: number
  unvested_shares: number
  sellable_shares: number
  share_price: number | null
}

export interface IncomeHistory {
  w2_records: W2Record[]
  rsu_grants: RSUGrant[]
}
