/**
 * Planning page maths that is not the simulation itself: formatting levers by unit, turning
 * percentile bands into stacked chart series, the "what would need to be true" sentences, event
 * ages from templates, and which levers differ from the saved plan. The simulation runs on the
 * backend (app/engine/retirement_sim.py); nothing here changes its numbers.
 */
import type {
  AssumptionSpec, AssumptionUnit, Bands, EventTemplate, GoalSeekResult, Milestone, MixStats, OutlookRow, PlanEvent,
  PlanOutlook, SensitivityLever, SprintLever,
} from '../types'
import { useFormatters } from './useFormatters'

const { money, compact, percent } = useFormatters()

export function formatLever(value: number | null | undefined, unit: AssumptionUnit): string {
  if (value == null || Number.isNaN(value)) return '—'
  switch (unit) {
    case 'pct': return percent(value, Math.round(value * 1000) % 10 === 0 ? 0 : 1)
    case 'usd': return money(value)
    case 'usd_month': return `${money(value)}/mo`
    case 'age': return String(Math.round(value))
    case 'count': return String(Math.round(value))
    case 'flag': return value >= 0.5 ? 'on' : 'off'
    default: return String(value)
  }
}

export function leverStep(spec: Pick<AssumptionSpec, 'unit' | 'max'>): number {
  switch (spec.unit) {
    case 'pct': return 0.0025
    case 'age': case 'count': case 'flag': return 1
    case 'usd_month': return 50
    case 'usd': return spec.max > 200_000 ? 1000 : 500
    default: return 1
  }
}

/** Bands as two stacked areas (p10..p90 and p25..p75) plus the median line, for ECharts. */
export function bandSeries(b: Bands) {
  const width = (hi: number[], lo: number[]) => hi.map((v, i) => Math.max(0, v - lo[i]))
  return {
    outerBase: b.p10,
    outerWidth: width(b.p90, b.p10),
    innerBase: b.p25,
    innerWidth: width(b.p75, b.p25),
    median: b.p50,
  }
}

export type Tone = 'good' | 'warning' | 'critical'

/** On track at or above the target; close within 15 points; otherwise off track. */
export function successTone(rate: number, target: number): Tone {
  if (rate >= target) return 'good'
  if (rate >= target - 0.15) return 'warning'
  return 'critical'
}

export function toneLabel(t: Tone): string {
  return t === 'good' ? 'On track' : t === 'warning' ? 'Close' : 'Off track'
}

export interface TrueCard {
  key: 'spending' | 'age' | 'savings' | 'returns'
  title: string
  value: string
  detail: string
  met: boolean
}

/**
 * One card per lever that, alone, would get the plan to its target chance of success.
 * When the plan already meets the target the cards say how much room there is instead.
 */
export function whatMustBeTrue(o: Pick<PlanOutlook, 'values' | 'retirement_age' | 'history_reference'>,
                               g: GoalSeekResult): TrueCard[] {
  const target = percent(g.target, 0)
  const already = g.base_success >= g.target
  const spend = o.values.retirement_spending
  const cards: TrueCard[] = []

  if (g.max_spending == null) {
    cards.push({ key: 'spending', title: 'Spending', value: 'Not reachable',
      detail: `Even spending nothing in retirement does not reach ${target} with the other levers as they are.`, met: false })
  } else {
    const diff = g.max_spending - spend
    cards.push({
      key: 'spending', title: already ? 'Spending headroom' : 'Spend at most', value: `${money(g.max_spending)}/yr`,
      detail: diff >= 0
        ? `${money(diff)} a year more than the plan's ${money(spend)} still clears ${target}.`
        : `${money(-diff)} a year less than the plan's ${money(spend)} (today's dollars).`,
      met: diff >= 0,
    })
  }

  if (g.earliest_retirement_age == null) {
    cards.push({ key: 'age', title: 'Retirement age', value: 'Not reachable',
      detail: `No retirement age up to 80 reaches ${target} with the other levers as they are.`, met: false })
  } else {
    const a = g.earliest_retirement_age
    cards.push({
      key: 'age', title: a <= o.retirement_age ? 'Could retire at' : 'Retire at', value: String(a),
      detail: a === o.retirement_age
        ? `The plan's own age is the earliest that reaches ${target}.`
        : a < o.retirement_age
          ? `${o.retirement_age - a} years earlier than the plan's ${o.retirement_age} still reaches ${target}.`
          : `${a - o.retirement_age} years later than the plan's ${o.retirement_age}.`,
      met: a <= o.retirement_age,
    })
  }

  if (already) {
    cards.push({ key: 'savings', title: 'Extra savings', value: 'None needed',
      detail: `The plan's savings already reach ${target}.`, met: true })
  } else if (g.extra_monthly_savings == null) {
    cards.push({ key: 'savings', title: 'Extra savings', value: 'Not reachable',
      detail: `Saving up to $25,000 a month more does not reach ${target} on its own.`, met: false })
  } else {
    cards.push({ key: 'savings', title: 'Save more', value: `+${money(g.extra_monthly_savings)}/mo`,
      detail: `On top of the plan's ${money(o.values.monthly_cash_savings)}/mo, until ${o.retirement_age}.`, met: false })
  }

  const hist = o.history_reference.retired
  if (g.required_return_shift == null) {
    cards.push({ key: 'returns', title: 'Returns', value: 'Not reachable',
      detail: 'No return within 8 points of the assumptions reaches the target on its own.', met: already })
  } else {
    const shift = g.required_return_shift
    const pts = `${Math.abs(shift * 100).toFixed(1)} points`
    cards.push({
      key: 'returns', title: shift <= 0 ? 'Returns could fall' : 'Returns must be', value: shift <= 0 ? pts : `+${pts}`,
      detail: `${percent(g.required_investment_return, 1)} while working and ${percent(g.required_retirement_return, 1)} retired`
        + ` (plan: ${percent(o.values.investment_return, 1)} and ${percent(o.values.retirement_return, 1)}). ${historyLine(hist)}`,
      met: shift <= 0,
    })
  }
  return cards
}

export function historyLine(h: MixStats): string {
  return `A ${Math.round(h.stock_share * 100)}/${Math.round((1 - h.stock_share) * 100)} mix averaged `
    + `${percent(h.nominal_mean, 1)} a year (${percent(h.real_mean, 1)} after inflation), ${h.from_year}–${h.to_year}.`
}

/** Ages for a new event from a template, relative to the current (c) or retirement (r) age. */
export function templateAges(t: EventTemplate, currentAge: number, retirementAge: number) {
  const at = (anchor: 'r' | 'c', off: number) => (anchor === 'r' ? retirementAge : currentAge) + off
  const start = t.start === 'fixed' ? (t.start_value ?? currentAge) : at(t.start, t.start_offset)
  let end: number | null = null
  if (t.end === 'fixed') end = t.end_value ?? null
  else if (t.end) end = at(t.end, t.end_offset ?? 0)
  if (end != null && end < start) end = start
  return { start_age: start, end_age: end }
}

export function eventSummary(e: Pick<PlanEvent, 'kind' | 'start_age' | 'end_age' | 'amount' | 'pct'> & { params?: Record<string, number> | null }): string {
  const ages = e.end_age != null && e.end_age !== e.start_age ? `Ages ${e.start_age}–${e.end_age}` : `Age ${e.start_age}`
  switch (e.kind) {
    case 'part_time': return `${ages} · ${compact(e.amount)}/yr income`
    case 'healthcare': case 'recurring_expense': return `${ages} · ${compact(e.amount)}/yr`
    case 'one_off_expense': return `${ages} · ${compact(e.amount)} once`
    case 'windfall': return `${ages} · +${compact(e.amount)}`
    case 'job_loss': return `${ages} · ${percent(e.pct, 0)} of pay lost`
    case 'rsu_shock': return `${ages} · share price ${e.pct >= 0 ? '+' : ''}${percent(e.pct, 0)}`
    case 'spending_change': return `From ${e.start_age} · spending ${e.pct >= 0 ? '+' : ''}${percent(e.pct, 0)}`
      + (e.amount ? `, ${compact(e.amount)} to move` : '')
    case 'downsize': return `${ages} · next home ${compact(e.amount)}`
    case 'acquisition': return `${ages} · deal ${e.pct >= 0 ? '+' : ''}${percent(e.pct, 0)}, then ${e.amount ? `${compact(e.amount)}/yr equity` : 'no equity'}`
    case 'layoff': {
      const p = e.params ?? {}
      if (p.never_reemployed) return `${ages} · no next job${p.part_time_income ? `, ${compact(p.part_time_income)}/yr part-time` : ''}`
      return `${ages} · ${p.gap_months ?? 6} months out, then ${percent(p.next_pay_pct ?? 1, 0)} pay${p.next_equity === 0 ? ', no equity' : ''}`
    }
    default: return ages
  }
}

/** The levers whose value differs from the saved plan (what "Save" would write). */
export function changedLevers(current: Record<string, number>, saved: Record<string, number>): Record<string, number> {
  const out: Record<string, number> = {}
  for (const [k, v] of Object.entries(current)) {
    if (saved[k] === undefined || Math.abs(saved[k] - v) > 1e-9) out[k] = v
  }
  return out
}

/** Historical cohorts: how many lasted, and the start years that ran out. */
export function cohortStats(cohorts: { start_year: number; success: boolean }[]) {
  const failed = cohorts.filter((c) => !c.success).map((c) => c.start_year)
  return { total: cohorts.length, lasted: cohorts.length - failed.length, failed }
}

/** Compress consecutive years: [1929,1930,1931,1937] -> "1929–1931, 1937". */
export function yearRanges(years: number[]): string {
  const sorted = [...years].sort((a, b) => a - b)
  const parts: string[] = []
  let i = 0
  while (i < sorted.length) {
    let j = i
    while (j + 1 < sorted.length && sorted[j + 1] === sorted[j] + 1) j++
    parts.push(i === j ? String(sorted[i]) : `${sorted[i]}–${sorted[j]}`)
    i = j + 1
  }
  return parts.join(', ')
}

/** Points of change in chance of success, signed: "+12 pts" / "−3 pts". */
export function deltaPts(after: number, before: number): string {
  const d = Math.round((after - before) * 100)
  if (d === 0) return '±0 pts'
  return `${d > 0 ? '+' : '−'}${Math.abs(d)} pts`
}


/** Income paths: total comp growth relative to the inflation assumption (the real raise a year). */
export const INCOME_PATHS = [
  { label: 'Flat', real: 0, help: 'Pay only keeps up with inflation' },
  { label: 'Base', real: 0.01, help: '1% a year above inflation' },
  { label: 'Aggressive', real: 0.04, help: '4% a year above inflation (promotions, bigger refreshes)' },
] as const

/** Today's-dollar price level at the start of row i (the deflator is end-of-period). */
export function priceAt(rows: Pick<OutlookRow, 'deflator'>[], i: number): number {
  return i === 0 ? 1 : rows[i - 1].deflator || 1
}

/** What each retired year costs on the plan line, in today's dollars: living, housing, health, other. */
export function costSeries(rows: OutlookRow[]) {
  const out = { ages: [] as number[], living: [] as number[], housing: [] as number[], health: [] as number[], other: [] as number[] }
  rows.forEach((r, i) => {
    if (r.phase !== 'retired') return
    const k = priceAt(rows, i)
    out.ages.push(r.age)
    out.living.push(Math.round(r.spending / k))
    out.housing.push(Math.round(r.housing / k))
    out.health.push(Math.round(r.healthcare / k))
    out.other.push(Math.round((r.extra_spend + r.mortgage_payoff) / k))
  })
  return out
}

/** Where each retired year's money comes from until ``toAge``, in today's dollars. */
export function bridgeSeries(rows: OutlookRow[], toAge: number) {
  const out = {
    ages: [] as number[], taxable: [] as number[], roth: [] as number[], k401: [] as number[],
    penalty: [] as number[], social: [] as number[], work: [] as number[],
  }
  rows.forEach((r, i) => {
    if (r.phase !== 'retired' || r.age > toAge) return
    const k = priceAt(rows, i)
    out.ages.push(r.age)
    out.taxable.push(Math.round(r.src_taxable / k))
    out.roth.push(Math.round(r.src_roth_basis / k))
    out.k401.push(Math.round(r.src_401k / k))
    out.penalty.push(Math.round(r.src_401k_penalty / k))
    out.social.push(Math.round(r.social_security / k))
    out.work.push(Math.round(r.other_income / k))
  })
  return out
}

/** Category-axis positions for the milestone ages (59½ sits on 60, the first age at or after it). */
export function milestoneMarks(milestones: Milestone[], ages: number[]) {
  return milestones
    .map((m) => ({ ...m, index: ages.findIndex((a) => a >= m.age) }))
    .filter((m) => m.index >= 0 && ages[m.index] - m.age < 1)
}

export interface TornadoRow { label: string; lowText: string; highText: string; low: number; high: number; base?: number }

export function tornadoFromSensitivity(levers: SensitivityLever[]): TornadoRow[] {
  return levers.map((l) => ({
    label: l.label, lowText: formatLever(l.low_value, l.unit), highText: formatLever(l.high_value, l.unit),
    low: l.success_low, high: l.success_high,
  }))
}

export function tornadoFromSprint(levers: SprintLever[]): TornadoRow[] {
  return levers.map((l) => ({
    label: l.label, lowText: l.low_label, highText: l.high_label, low: l.success_low, high: l.success_high, base: l.base,
  }))
}

/** The retirement ages worth comparing: the access milestones that the age curve covers, plus the plan's. */
export function retireAgeRows<T extends { age: number }>(byAge: T[], planAge: number): T[] {
  const wanted = new Set([50, 55, 60, 62, 65, 67, 70, planAge])
  return byAge.filter((r) => wanted.has(r.age))
}
