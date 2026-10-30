import type { WeeklyRecap } from '../types'

const local = (iso: string) => new Date(`${iso}T00:00:00`)
const iso = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`

export function addDays(day: string, n: number): string {
  const d = local(day)
  d.setDate(d.getDate() + n)
  return iso(d)
}

/** "Oct 18 – 24, 2026", or "Sep 27 – Oct 3, 2026" across a month. */
export function weekLabel(start: string, end: string): string {
  const s = local(start), e = local(end)
  const month = (d: Date) => d.toLocaleDateString('en-US', { month: 'short' })
  const tail = s.getMonth() === e.getMonth() ? `${e.getDate()}` : `${month(e)} ${e.getDate()}`
  return `${month(s)} ${s.getDate()} – ${tail}, ${e.getFullYear()}`
}

const usd = (v: number) => new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(Math.abs(v))

/** One plain sentence from the numbers; no model writes it, so it is never a guess. */
export function recapHeadline(r: WeeklyRecap): string {
  const parts: string[] = []
  if (r.spending <= 0) parts.push('No spending this week')
  else {
    let s = `You spent ${usd(r.spending)}`
    if (r.prior_weekly_avg > 0) {
      const pct = Math.round(((r.spending - r.prior_weekly_avg) / r.prior_weekly_avg) * 100)
      s += Math.abs(pct) < 5 ? ', about your usual week' : `, ${Math.abs(pct)}% ${pct > 0 ? 'more' : 'less'} than your 4-week average of ${usd(r.prior_weekly_avg)}`
    }
    if (r.categories[0]) s += `; the most went to ${r.categories[0].category} (${usd(r.categories[0].total)})`
    parts.push(s)
  }
  if (r.net_worth_change != null) {
    parts.push(r.net_worth_change === 0 ? 'Net worth held steady' : `Net worth ${r.net_worth_change > 0 ? 'rose' : 'fell'} ${usd(r.net_worth_change)}`)
  }
  const ahead = r.upcoming_bills.length + r.upcoming_vests.length
  if (ahead) {
    const bills = r.upcoming_bills.reduce((t, b) => t + b.amount, 0)
    const bits = []
    if (r.upcoming_bills.length) bits.push(`${r.upcoming_bills.length} bill${r.upcoming_bills.length > 1 ? 's' : ''} (~${usd(bills)})`)
    if (r.upcoming_vests.length) bits.push(`${r.upcoming_vests.length === 1 ? 'an RSU vest' : `${r.upcoming_vests.length} RSU vests`}`)
    parts.push(`Next week: ${bits.join(' and ')}`)
  }
  return parts.join('. ') + '.'
}
