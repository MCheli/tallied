/** The single em dash used as the null placeholder everywhere. */
export const DASH = '—'

/**
 * Null-safe formatters. Every page formats through these, never a local helper.
 *
 *   money(n, { compact?, cents? })  "$12,345" / "$12.3K" (compact) / "$12,345.67" (cents)
 *   currency(n)                     alias of money(n)
 *   compact(n)                      "$1.2M" / "$12K" / "$345"
 *   percent(ratio, digits = 1)      0.123 -> "12.3%"   (pct is the older alias)
 *   date(iso)                       "Oct 29, 2026"     (dateShort is the older alias)
 *   monthYear(iso)                  "Oct 2026"
 *   number(n, digits = 0)           "1,234"
 *   dash                            "—"
 * All return the dash for null/undefined/NaN.
 */
export function useFormatters() {
  const isNil = (v: unknown): v is null | undefined => v == null || (typeof v === 'number' && Number.isNaN(v))

  const money = (val: number | null | undefined, opts: { compact?: boolean; cents?: boolean } = {}) => {
    if (isNil(val)) return DASH
    if (opts.compact) return compact(val)
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      maximumFractionDigits: opts.cents ? 2 : 0,
      minimumFractionDigits: opts.cents ? 2 : 0,
    }).format(val)
  }

  const currency = (val: number | null | undefined) => money(val)

  const compact = (val: number | null | undefined) => {
    if (isNil(val)) return DASH
    const sign = val < 0 ? '-' : ''
    const abs = Math.abs(val)
    if (abs >= 1_000_000) return `${sign}$${(abs / 1_000_000).toFixed(1)}M`
    if (abs >= 1_000) return `${sign}$${(abs / 1_000).toFixed(0)}K`
    return money(val)
  }

  const percent = (ratio: number | null | undefined, digits = 1) => {
    if (isNil(ratio)) return DASH
    return `${(ratio * 100).toFixed(digits)}%`
  }
  const pct = percent

  const number = (val: number | null | undefined, digits = 0) => {
    if (isNil(val)) return DASH
    return new Intl.NumberFormat('en-US', { maximumFractionDigits: digits, minimumFractionDigits: digits }).format(val)
  }

  const parseDate = (val: string | Date) => {
    if (val instanceof Date) return val
    // Date-only strings are parsed as local dates, so "2026-10-29" does not shift a day in US time zones.
    const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(val)
    return m ? new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3])) : new Date(val)
  }

  const date = (val: string | Date | null | undefined) => {
    if (!val) return DASH
    const d = parseDate(val)
    if (Number.isNaN(d.getTime())) return DASH
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
  }
  const dateShort = date

  const monthYear = (val: string | Date | null | undefined) => {
    if (!val) return DASH
    const d = parseDate(typeof val === 'string' && /^\d{4}-\d{2}$/.test(val) ? `${val}-01` : val)
    if (Number.isNaN(d.getTime())) return DASH
    return d.toLocaleDateString('en-US', { month: 'short', year: 'numeric' })
  }

  return { money, currency, compact, percent, pct, number, date, dateShort, monthYear, dash: DASH }
}
