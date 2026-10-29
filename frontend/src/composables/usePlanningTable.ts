/**
 * Column groups and row helpers for the Planning projection table.
 * The Savings group (expenses_annual, savings_rate) is gone: the backend never had values for it.
 */
export interface MetricGroup {
  label: string
  metrics: string[]
}

export const METRIC_GROUPS: MetricGroup[] = [
  { label: 'Income', metrics: ['gross_income', 'base_salary', 'rsu_income'] },
  { label: 'Tax & Take-home', metrics: ['tax_paid', 'take_home', 'contributions_401k'] },
  { label: 'Wealth', metrics: ['net_worth', 'liquid_net_worth', 'investment_balance', 'retirement_balance', 'home_equity', 'mortgage_balance'] },
]

export const METRIC_LABELS: Record<string, string> = {
  gross_income: 'Gross Income',
  base_salary: 'Base Salary',
  rsu_income: 'RSU Income',
  tax_paid: 'Tax Paid',
  take_home: 'Take-Home',
  contributions_401k: '401(k)',
  net_worth: 'Net Worth',
  liquid_net_worth: 'Liquid NW',
  investment_balance: 'Investments',
  retirement_balance: 'Retirement',
  home_equity: 'Home Equity',
  mortgage_balance: 'Mortgage',
}

/** Metrics in display order, limited to what the table actually returned. */
export function orderedMetrics(available: string[]): string[] {
  const set = new Set(available)
  return METRIC_GROUPS.flatMap((g) => g.metrics.filter((m) => set.has(m)))
}

/** Years at or after the retirement year are shaded as retired. */
export function isRetiredYear(year: number, retirementYear: number | null | undefined): boolean {
  return retirementYear != null && year >= retirementYear
}

export const LOWER_IS_BETTER = new Set(['mortgage_balance', 'tax_paid'])
