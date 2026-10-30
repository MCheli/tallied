import { describe, expect, it } from 'vitest'
import {
  bridgeSeries, costSeries, eventSummary, milestoneMarks, priceAt, retireAgeRows, templateAges, tornadoFromSensitivity,
  tornadoFromSprint,
} from '../src/composables/usePlanningOutlook'
import type { EventTemplate, Milestone, OutlookRow } from '../src/types'

function row(age: number, phase: 'working' | 'retired', deflator: number, over: Partial<OutlookRow> = {}): OutlookRow {
  return {
    year: 2026 + age - 60, age, phase, salary: 0, rsu_income: 0, total_comp: 0, saved: 0, contrib_401k: 0, spending: 0,
    withdrawal: 0, social_security: 0, other_income: 0, healthcare: 0, housing: 0, src_taxable: 0, src_roth_basis: 0,
    src_401k: 0, src_401k_penalty: 0, equity_payout: 0, mortgage_payoff: 0, gap_costs: 0, extra_spend: 0, magi: 0,
    cash: 0, investments: 0, company_stock: 0, retirement_bal: 0, home_equity: 0, net_worth: 0, liquid_real: 0,
    net_worth_real: 0, deflator, ...over,
  }
}

const rows: OutlookRow[] = [
  row(60, 'working', 1.1),
  row(61, 'retired', 1.21, { spending: 110_000, housing: 11_000, healthcare: 22_000, extra_spend: 5_500, src_taxable: 99_000, src_roth_basis: 11_000 }),
  row(62, 'retired', 1.331, { spending: 121_000, healthcare: 12_100, src_401k: 60_500, src_401k_penalty: 12_100, social_security: 24_200, other_income: 12_100 }),
]

describe('planning year series', () => {
  it('deflates each year by the price level at its start', () => {
    expect(priceAt(rows, 0)).toBe(1)
    expect(priceAt(rows, 1)).toBe(1.1)
    expect(priceAt(rows, 2)).toBe(1.21)
  })

  it('breaks a retired year into living, housing, health and other costs', () => {
    const c = costSeries(rows)
    expect(c.ages).toEqual([61, 62])
    expect(c.living).toEqual([100_000, 100_000])
    expect(c.housing).toEqual([10_000, 0])
    expect(c.health).toEqual([20_000, 10_000])
    expect(c.other).toEqual([5_000, 0])
  })

  it('shows where the money for the early years comes from, up to an age', () => {
    const b = bridgeSeries(rows, 62)
    expect(b.ages).toEqual([61, 62])
    expect(b.taxable).toEqual([90_000, 0])
    expect(b.roth).toEqual([10_000, 0])
    expect(b.k401).toEqual([0, 50_000])
    expect(b.penalty).toEqual([0, 10_000])
    expect(b.social).toEqual([0, 20_000])
    expect(b.work).toEqual([0, 10_000])
    expect(bridgeSeries(rows, 61).ages).toEqual([61])
  })

  it('puts milestones on the age axis (59½ on 60) and drops those outside it', () => {
    const ms: Milestone[] = [
      { age: 55, label: '55', title: 'Rule of 55', detail: '' },
      { age: 59.5, label: '59½', title: 'Penalty-free', detail: '' },
      { age: 70, label: '70', title: 'Largest SS', detail: '' },
    ]
    const marks = milestoneMarks(ms, [56, 57, 58, 59, 60, 61])
    expect(marks.map((m) => [m.label, m.index])).toEqual([['59½', 4]])
  })

  it('compares the milestone retirement ages plus the plan age', () => {
    const byAge = [48, 50, 52, 55, 58, 60, 62, 65].map((age) => ({ age }))
    expect(retireAgeRows(byAge, 52).map((r) => r.age)).toEqual([50, 52, 55, 60, 62, 65])
  })

  it('places a fixed-age template (long-term care at 85) whatever the current age', () => {
    const ltc: EventTemplate = { kind: 'recurring_expense', label: 'Long-term care', start: 'fixed', start_offset: 0, start_value: 85, end: 'fixed', end_value: 87, amount: 70_800, pct: 0, help: '' }
    expect(templateAges(ltc, 30, 55)).toEqual({ start_age: 85, end_age: 87 })
  })

  it('summarises layoffs and acquisitions in words', () => {
    expect(eventSummary({ kind: 'layoff', start_age: 36, end_age: null, amount: 0, pct: 0, params: { gap_months: 6, next_pay_pct: 0.9, next_equity: 1 } }))
      .toBe('Age 36 · 6 months out, then 90% pay')
    expect(eventSummary({ kind: 'layoff', start_age: 40, end_age: null, amount: 0, pct: 0, params: { never_reemployed: 1, part_time_income: 30_000 } }))
      .toBe('Age 40 · no next job, $30K/yr part-time')
    expect(eventSummary({ kind: 'acquisition', start_age: 31, end_age: null, amount: 0, pct: 0.2 }))
      .toBe('Age 31 · deal +20%, then no equity')
  })

  it('maps both kinds of sensitivity onto one tornado shape, keeping per-row baselines', () => {
    const s = tornadoFromSensitivity([{ key: 'inflation', label: 'Inflation', unit: 'pct', base_value: 0.03, low_value: 0.02, high_value: 0.04, success_low: 0.7, success_high: 0.5 }])
    expect(s[0]).toEqual({ label: 'Inflation', lowText: '2%', highText: '4%', low: 0.7, high: 0.5 })
    const t = tornadoFromSprint([{ label: 'Gap between jobs', low_label: '0 months', high_label: '12 months', base: 0.6, success_low: 0.65, success_high: 0.5 }])
    expect(t[0]).toEqual({ label: 'Gap between jobs', lowText: '0 months', highText: '12 months', low: 0.65, high: 0.5, base: 0.6 })
  })
})
