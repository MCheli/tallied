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
  source: string  // 'simplefin' | 'manual'
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
  balance_date?: string | null
  include_in_nw?: boolean
}

export interface LiquidityLayer {
  name: string
  total: number
  accounts: LayerAccount[]
  as_of?: string | null
}

export interface SnapshotResponse {
  layers: LiquidityLayer[]
  net_worth: number
  liquid_net_worth: number
  total_comp_annual: number | null
  net_worth_12mo_change: number | null
  as_of?: string | null
}

export interface IncomeBreakdown {
  salary: number
  rsu_income: number
  total_comp: number
  rsu_pct: number
  /** "w2" when the W-2 records the split, "vests" when RSU income comes from vest records */
  source?: 'w2' | 'vests' | 'none'
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

// ── Settings: connections, email receipts, import history ──
export interface ImportLogEntry {
  id: number
  source: string
  capture_mode: string | null
  status: string
  records_created: number
  error_message: string | null
  created_at: string | null
}

export interface SimpleFinStatus {
  connected: boolean
  last_synced_at?: string | null
  created_at?: string | null
}

export interface SimpleFinAccountConfig {
  id: number
  simplefin_account_id: string
  account_name: string
  account_type: string | null
  display_group: string | null
  institution: string | null
  sync_balances: boolean
  sync_transactions: boolean
  local_account_id: string | null
}

export interface SimpleFinAccountType {
  account_type: string
  display_group: string
}

export interface SimpleFinConnectResult {
  connected: boolean
  accounts_found: number
  accounts: { simplefin_account_id: string; account_name: string; institution: string; account_type: string | null }[]
  warnings: string[]
}

export interface SimpleFinSyncStatus {
  job_id: number | null
  status: 'none' | 'running' | 'succeeded' | 'failed' | string
  trigger?: string
  started_at?: string | null
  finished_at?: string | null
  balances_synced?: number
  txn_added?: number
  txn_updated?: number
  error?: string | null
}

export interface ForwardingEmail {
  id: number
  email: string
  is_active: boolean
  created_at: string | null
}

export interface EmailReceiptItem {
  id: number
  from_email: string
  subject: string
  status: string
  transaction_id: string | null
  parsed_data: { merchant?: string; amount?: number; date?: string; category?: string } | null
  error_message: string | null
  created_at: string | null
}

// ── Dashboard / Cash payloads ────────────────────────────────────────────────
export interface LargeTransaction {
  id: string
  date: string
  amount: number
  merchant: string | null
  category: string | null
  source: string | null
  account_name: string
}

// ── RSU ──
export interface VestEventDetail {
  id: number
  vest_date: string | null
  vest_period: number | null
  shares: number
  fmv_at_vest: number | null
  shares_withheld: number | null
  shares_released: number | null
  total_taxes_paid: number | null
  is_actual: boolean
  tax_status: string | null
  gain_per_share: number | null
}

export interface RSUGrantDetail {
  id: string
  company: string | null
  symbol: string | null
  grant_date: string | null
  total_shares: number | null
  vested_shares: number | null
  unvested_shares: number | null
  sellable_shares: number | null
  held_value: number
  unvested_value: number
  sellable_value: number
  vest_events: VestEventDetail[]
}

export interface RSUGrantsResponse {
  grants: RSUGrantDetail[]
  current_price: number | null
  symbol: string | null
}

export interface UpcomingVest {
  grant_id: string
  grant_date: string | null
  vest_date: string
  shares: number
  est_value: number | null
}

export interface TaxLotAggregate {
  shares: number
  market_value: number
  cost_basis: number
  gain: number
  est_tax: number
  net_proceeds: number
}

export interface VestIncomeYear {
  value: number
  actual: number
  projected: number
  is_projected: boolean
  is_mixed: boolean
}

export interface RSUSummary {
  held_shares: number
  total_granted: number
  vested_shares: number
  unvested_shares: number
  sellable_shares: number
  held_value: number
  unvested_value: number
  sellable_value: number
  current_price: number | null
  symbol: string | null
  upcoming_vests: UpcomingVest[]
  vesting_income_by_year: Record<string, VestIncomeYear>
  tax_lots?: {
    long_term: TaxLotAggregate
    short_term: TaxLotAggregate
    all: TaxLotAggregate
    lots: unknown[]
    unallocated_sellable_shares: number
    assumed_rates: { ltcg: number; stcg: number; state: number }
  }
}

export interface PricePoint {
  date: string
  price: number
}

export interface PriceHistoryResponse {
  symbol: string
  points: PricePoint[]
}

// ── 401(k) ──
export interface RetirementAccountSummary {
  id: number
  plan_name: string | null
  provider: string | null
  total_balance: number
  vested_balance: number
  roth_balance: number
  pretax_balance: number
  employer_match_balance: number
  other_balance: number
  pretax_deferral_rate: number
  roth_deferral_rate: number
  total_employee_contributions: number
  total_employer_contributions: number
  roth_basis: number
  account_return: number
  return_period_start: string | null
  statement_start: string | null
  statement_end: string | null
  estimated_monthly_income: number
  updated_at: string | null
}

export interface RetirementHoldingSummary {
  id: number
  fund_name: string
  ticker: string | null
  balance: number | null
  allocation_pct: number | null
  gain_loss: number | null
  live_price: number | null
}

export interface RetirementSnapshotPoint {
  date: string
  balance: number
  roth: number | null
  pretax: number | null
  employer: number | null
}

export interface RetirementSummary {
  account: RetirementAccountSummary | null
  balance_breakdown?: {
    roth: number
    pretax: number
    employer: number
    other: number
    roth_pct: number
    pretax_pct: number
    employer_pct: number
  }
  holdings: RetirementHoldingSummary[]
  snapshots: RetirementSnapshotPoint[]
}

// ── Property ──
export interface PropertySummary {
  property: {
    address: string | null
    value: number | null
    valuation_source: string | null
    valuation_date: string | null
    purchase_price: number | null
    account_id?: string
  } | null
  mortgage: {
    balance: number | null
    rate: number | null
    monthly_payment: number | null
    original_amount: number | null
    origination_date: string | null
    maturity_date: string | null
    escrow: number | null
  } | null
  equity: number | null
  payment_breakdown: { total: number; principal: number; interest: number; escrow: number } | null
}

export interface AmortizationRow {
  date: string
  principal: number
  interest: number
  escrow: number
  balance: number
  is_past: boolean
}

export interface AmortizationResponse {
  schedule: AmortizationRow[]
  current_month_index?: number | null
  summary: {
    original_amount: number
    current_balance: number | null
    payoff_date: string | null
    months_remaining: number
    total_interest_paid: number
    total_interest_remaining: number
    total_principal_paid: number
  } | null
}

export interface PropertyValuePoint {
  date: string
  value: number
  source: 'tax_assessment' | 'realtor_estimate' | 'sale' | 'ai_projection' | 'manual' | string
  is_projected: boolean
  details?: Record<string, unknown> | null
}

export interface PropertyValueHistoryResponse {
  history: PropertyValuePoint[]
  commentary: string | null
  property_details: Record<string, unknown> | null
  projection_note?: string | null
  refreshed?: boolean
}

export type ValuationSourceLabel = 'Manual' | 'Redfin' | 'Zillow' | 'Appraisal' | 'Tax Assessment' | 'Purchase price'

// ── Assets ──
export interface Vehicle {
  id: number
  year: number
  make: string
  model: string
  trim: string | null
  vin?: string | null
  mileage: number | null
  condition: string | null
  purchase_price: number | null
  purchase_date: string | null
  estimated_value: number | null
  value_last_updated: string | null
  notes: string | null
  valuation_notes: string | null
  valuation_source: 'ai' | 'manual' | null
  valuation_model: string | null
  valuation_confidence: 'high' | 'medium' | 'low' | null
  depreciation: number | null
}

export interface AssetsSummary {
  total_value: number
  total_purchase_price: number | null
  total_depreciation: number | null
  vehicles_with_purchase_price: number
  vehicle_count: number
  vehicles: Vehicle[]
}

export interface VehicleHistoryPoint { date: string; value: number; source: string; is_projected: boolean }
export interface VehicleHistory { vehicle_id: number; history: VehicleHistoryPoint[] }
export interface AggregateVehicleHistory {
  dates: string[]
  total: number[]
  vehicles: Record<string, (number | null)[]>
  is_projected: boolean[]
}
export interface VehicleRefreshResult {
  estimated_value: number
  updated: boolean
  confidence: 'high' | 'medium' | 'low'
  model: string
  reasoning: string
  annual_depreciation_pct: number
}
export interface VehicleInput {
  year: number
  make: string
  model: string
  trim?: string
  vin?: string
  mileage?: number
  condition?: string
  purchase_price?: number
  purchase_date?: string
  notes?: string
}

// ── Platform: API keys, usage, webhooks ──────────────────────────────────────
export interface ApiKey {
  id: number
  name: string
  key_prefix: string
  permissions: string
  is_active: boolean
  last_used: string | null
  created_at: string | null
}
export interface ApiKeyCreated extends ApiKey { key: string }
export interface EndpointUsage { path: string; method: string; count: number }
export interface KeyUsageInfo {
  key_id: number
  key_name: string
  total_requests: number
  requests_last_24h: number
  requests_last_hour: number
  avg_latency_ms: number
  top_endpoints: EndpointUsage[]
}
export interface UsageSummary {
  total_requests_today: number
  requests_last_hour: number
  total_requests_all_time: number
  avg_latency_ms: number
  top_endpoints: EndpointUsage[]
  per_key: KeyUsageInfo[]
}
export interface Webhook {
  id: number
  url: string
  events: string[]
  is_active: boolean
  created_at: string | null
  last_delivery: string | null
  failure_count: number
}
export interface WebhookCreated extends Webhook { secret: string }
export interface WebhookTestResult { success: boolean; status_code?: number; error?: string }

// ── Platform: database explorer and credentials ──────────────────────────────
export interface SchemaColumnInfo {
  name: string
  type: string
  nullable: boolean
  primary_key: boolean
  default: string | null
  description?: string
}
export interface SchemaForeignKey { column: string; references_table: string; references_column: string }
export interface SchemaTable {
  name: string
  description?: string
  columns: SchemaColumnInfo[]
  foreign_keys: SchemaForeignKey[]
  row_count: number
}
export interface SchemaEdge { from_table: string; from_column: string; to_table: string; to_column: string }
export interface SchemaResponse { tables: SchemaTable[]; edges: SchemaEdge[] }
export interface TablePreview {
  table: string
  columns: string[]
  rows: Record<string, unknown>[]
  total: number
  limit: number
  offset: number
}
export interface QueryResult { columns: string[]; rows: Record<string, unknown>[]; row_count: number; query: string }
export interface DbCredential {
  id: number
  name: string
  pg_username: string
  access_level: string
  is_active: boolean
  created_at: string | null
  expires_at: string | null
}
export interface DbCredentialCreated extends DbCredential {
  password: string
  host: string
  port: number
  database: string
  schema_name: string
  connection_string: string
}

// ── Platform: admin portal ───────────────────────────────────────────────────
export interface PlatformUser {
  id: number
  email: string
  display_name: string
  auth_provider: string
  is_admin: boolean
  is_active: boolean
  status: string
  created_at: string | null
  last_login: string | null
  tenant_count: number
  tenants: string[]
}
export interface PlatformTenant {
  id: number
  display_name: string
  slug: string
  schema_name: string
  is_active: boolean
  created_at: string | null
  member_count: number
  owner_email: string | null
  owner_name: string | null
}
export interface PlatformStats { total_users: number; active_users: number; total_tenants: number; active_tenants: number }
export interface PlatformUserMembership { tenant_id: number; display_name: string; slug: string; role: string; is_default: boolean }
export interface PlatformUserDetail {
  id: number
  email: string
  display_name: string
  auth_provider: string
  is_admin: boolean
  is_active: boolean
  status: string
  created_at: string | null
  last_login: string | null
  tenants: PlatformUserMembership[]
  api_key_count: number
  db_credential_count: number
}
export interface PlatformTenantMember { user_id: number; email: string; display_name: string; role: string; is_default: boolean }
export interface PlatformTenantDetail {
  id: number
  display_name: string
  slug: string
  schema_name: string
  is_active: boolean
  created_at: string | null
  members: PlatformTenantMember[]
  table_counts: Record<string, number>
}

// ── Auth ─────────────────────────────────────────────────────────────────────
export interface AuthTenant { id: number; display_name: string; slug: string }
export interface AuthUser {
  id: number
  email: string
  display_name: string
  is_admin: boolean
  status: string
  current_tenant: AuthTenant | null
  tenants: AuthTenant[]
}
export interface AuthMeResponse { user: AuthUser | null; authenticated: boolean }
export interface AuthConfig { dev_mode: boolean; google_sso: boolean }

// ── Document import ──────────────────────────────────────────────────────────
export interface ImportConfig { context: string; guidance: string; examples: string[]; expected_fields: string[] }
export interface ImportChangeField {
  column: string
  old_value: unknown
  new_value: unknown
  is_new?: boolean
  source?: string
  display_name?: string
  format?: string
  /** Value the backend will store when it differs from the displayed new_value (e.g. parsed dates). */
  _store_value?: unknown
}
export interface ImportChange {
  id: string
  table: string
  action: string
  tax_year?: number | null
  record_label?: string
  record_key?: string | null
  fields: ImportChangeField[]
  data?: Record<string, unknown>
}
export interface ImportMissingField { field: string; message: string }
export interface ImportChatMessage { role: string; content: string; timestamp?: string; action?: ImportChatAction | null }
export interface ImportChatAction { action: string; table: string; column: string; value: unknown; tax_year?: number | null }
export interface ImportUploadResult {
  session_id: string
  status: string
  filename: string
  context: string
  ai_summary: string
  missing_fields: ImportMissingField[]
  proposed_changes: ImportChange[]
  findings_count: number
}
export interface ImportSessionResponse {
  session_id: string
  status: string
  context: string
  filename: string
  ai_summary: string
  missing_fields: ImportMissingField[]
  proposed_changes: ImportChange[]
  chat_messages: ImportChatMessage[]
  changes_applied: number | null
}
export interface ImportChatResponse { response: string; action: ImportChatAction | null; messages: ImportChatMessage[] }
