export function useFormatters() {
  const currency = (val: number | null | undefined) => {
    if (val == null) return '\u2014'
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      maximumFractionDigits: 0,
    }).format(val)
  }

  const pct = (val: number | null | undefined, decimals = 1) => {
    if (val == null) return '\u2014'
    return `${(val * 100).toFixed(decimals)}%`
  }

  const compact = (val: number | null | undefined) => {
    if (val == null) return '\u2014'
    if (Math.abs(val) >= 1_000_000) return `$${(val / 1_000_000).toFixed(1)}M`
    if (Math.abs(val) >= 1_000) return `$${(val / 1_000).toFixed(0)}K`
    return currency(val)
  }

  const dateShort = (val: string | null | undefined) => {
    if (!val) return '\u2014'
    return new Date(val).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
  }

  return { currency, pct, compact, dateShort }
}
