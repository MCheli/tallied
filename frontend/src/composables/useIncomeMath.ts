import type { W2Record } from '../types'

/**
 * The one definition of how a W-2 year is split (UND-INC-001).
 *
 *   taxes          = federal + state + social security + medicare
 *   retirement     = pretax 401k + roth 401k
 *   pretaxBenefits = cafeteria 125 + transit        (employee money, deducted from pay)
 *   employerHealth = Box 12 DD                       (employer-paid, informational: never deducted)
 *   takeHome       = gross − taxes − retirement − pretaxBenefits
 *
 * gross is total pay: an imported W-2 records box 1, which already leaves out pre-tax 401(k) and pre-tax
 * benefits, so the backend sends total_pay (box 1 plus those) and the shared salary/RSU split.
 *
 * takeHome + taxes + retirement + pretaxBenefits = gross, which is what the stacked bar shows.
 * Every tile, the waterfall, the stacked bar and the year-over-year table use these numbers.
 */
export interface IncomeSplit {
  gross: number
  baseSalary: number
  rsuIncome: number
  other: number
  federal: number
  state: number
  socialSecurity: number
  medicare: number
  taxes: number
  effectiveRate: number
  pretax401k: number
  roth401k: number
  retirement: number
  cafeteria: number
  transit: number
  pretaxBenefits: number
  employerHealth: number
  takeHome: number
  takeHomeRate: number
}

export interface WaterfallStep {
  label: string
  value: number
  kind: 'deduction' | 'end' | 'start'
  group: 'benefit' | 'gross' | 'retirement' | 'takeHome' | 'tax'
}

const n = (v: number | null | undefined): number => (v == null || Number.isNaN(v) ? 0 : v)

export function splitW2(w: Partial<W2Record> | null | undefined): IncomeSplit {
  const gross = n(w?.total_pay ?? w?.gross_pay)
  const federal = n(w?.federal_tax)
  const state = n(w?.state_tax)
  const socialSecurity = n(w?.social_security)
  const medicare = n(w?.medicare)
  const pretax401k = n(w?.pretax_401k)
  const roth401k = n(w?.roth_401k)
  const cafeteria = n(w?.cafeteria_125)
  const transit = n(w?.transit)
  const employerHealth = n(w?.employer_health)
  const baseSalary = n(w?.salary_split ?? w?.base_salary)
  const rsuIncome = n(w?.rsu_split ?? w?.rsu_income)

  const taxes = federal + state + socialSecurity + medicare
  const retirement = pretax401k + roth401k
  const pretaxBenefits = cafeteria + transit
  const takeHome = gross - taxes - retirement - pretaxBenefits

  return {
    gross,
    baseSalary,
    rsuIncome,
    other: Math.max(0, gross - baseSalary - rsuIncome),
    federal,
    state,
    socialSecurity,
    medicare,
    taxes,
    effectiveRate: gross > 0 ? taxes / gross : 0,
    pretax401k,
    roth401k,
    retirement,
    cafeteria,
    transit,
    pretaxBenefits,
    employerHealth,
    takeHome,
    takeHomeRate: gross > 0 ? takeHome / gross : 0,
  }
}

/** Steps for the gross-to-take-home waterfall; the final step equals split.takeHome. */
export function waterfallSteps(split: IncomeSplit): WaterfallStep[] {
  const all: WaterfallStep[] = [
    { label: 'Federal', value: split.federal, kind: 'deduction', group: 'tax' },
    { label: 'State', value: split.state, kind: 'deduction', group: 'tax' },
    { label: 'Soc. Security', value: split.socialSecurity, kind: 'deduction', group: 'tax' },
    { label: 'Medicare', value: split.medicare, kind: 'deduction', group: 'tax' },
    { label: '401(k) Pretax', value: split.pretax401k, kind: 'deduction', group: 'retirement' },
    { label: '401(k) Roth', value: split.roth401k, kind: 'deduction', group: 'retirement' },
    { label: 'Cafeteria/FSA', value: split.cafeteria, kind: 'deduction', group: 'benefit' },
    { label: 'Transit', value: split.transit, kind: 'deduction', group: 'benefit' },
  ]
  const deductions = all.filter(d => d.value > 0)
  return [
    { label: 'Gross Pay', value: split.gross, kind: 'start', group: 'gross' },
    ...deductions,
    { label: 'Take-Home', value: split.takeHome, kind: 'end', group: 'takeHome' },
  ]
}

/** Running totals after each waterfall step (the last one is take-home). */
export function waterfallRunningTotals(steps: WaterfallStep[]): number[] {
  let running = 0
  return steps.map(s => {
    if (s.kind === 'start') running = s.value
    else if (s.kind === 'deduction') running -= s.value
    else running = s.value
    return running
  })
}

export function useIncomeMath() {
  return { splitW2, waterfallSteps, waterfallRunningTotals }
}
