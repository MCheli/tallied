import { describe, expect, it } from 'vitest'
import { splitW2, waterfallSteps, waterfallRunningTotals } from '../src/composables/useIncomeMath'

// Claudius Banks, tax year 2025 (fixtures/test_documents/MANIFEST.md)
const CLAUDIUS_2025 = {
  gross_pay: 210000,
  base_salary: 145000,
  rsu_income: 65000,
  federal_tax: 38500,
  state_tax: 10400,
  social_security: 10918.2,
  medicare: 3045,
  pretax_401k: 10000,
  roth_401k: 5000,
  cafeteria_125: 2300,
  transit: 900,
  employer_health: 8600,
}

describe('useIncomeMath', () => {
  it('take-home is gross minus taxes, 401(k) and employee pre-tax benefits; employer health is never deducted', () => {
    const s = splitW2(CLAUDIUS_2025)
    expect(s.taxes).toBeCloseTo(62863.2, 2)
    expect(s.retirement).toBe(15000)
    expect(s.pretaxBenefits).toBe(3200)
    expect(s.employerHealth).toBe(8600)
    expect(s.takeHome).toBeCloseTo(128936.8, 2)
    expect(s.takeHomeRate).toBeCloseTo(128936.8 / 210000, 6)
    expect(s.effectiveRate).toBeCloseTo(62863.2 / 210000, 6)
  })

  it('the stacked bar sums to gross exactly', () => {
    const s = splitW2(CLAUDIUS_2025)
    expect(s.takeHome + s.taxes + s.retirement + s.pretaxBenefits).toBeCloseTo(s.gross, 6)
  })

  it('the waterfall lands on the take-home tile', () => {
    const s = splitW2(CLAUDIUS_2025)
    const steps = waterfallSteps(s)
    const totals = waterfallRunningTotals(steps)
    expect(steps[0].label).toBe('Gross Pay')
    expect(steps.at(-1)?.label).toBe('Take-Home')
    expect(totals.at(-2)).toBeCloseTo(s.takeHome, 6) // running total after the last deduction
    expect(totals.at(-1)).toBeCloseTo(s.takeHome, 6) // the final bar
    expect(steps.some(st => st.label === 'Health Ins.')).toBe(false)
  })

  it('treats missing fields as zero and hides zero deductions', () => {
    const s = splitW2({ gross_pay: 1000, federal_tax: 100 })
    expect(s.takeHome).toBe(900)
    expect(waterfallSteps(s).map(x => x.label)).toEqual(['Gross Pay', 'Federal', 'Take-Home'])
    expect(splitW2(null).gross).toBe(0)
  })
})
