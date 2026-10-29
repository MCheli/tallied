/**
 * Equity composition for the Property page (UND-PROP-001).
 *
 * Equity = value − mortgage balance. It splits into principal paid (original loan − balance),
 * the down payment (purchase price − original loan) and appreciation (value − purchase price).
 * Without a purchase price the last two cannot be told apart, so they are reported as null and
 * `needsPurchasePrice` is true. The page must never label the down payment as appreciation.
 */
export interface EquityInputs {
  value: number | null | undefined
  mortgageBalance: number | null | undefined
  originalAmount: number | null | undefined
  purchasePrice: number | null | undefined
}

export interface EquityComposition {
  totalEquity: number
  equityPct: number
  principalPaid: number
  downPayment: number | null
  appreciation: number | null
  remaining: number
  needsPurchasePrice: boolean
  /** Bar widths as percent of property value; null segments are omitted. */
  widths: { downPayment: number; appreciation: number; principalPaid: number; remaining: number }
}

export function equityComposition(i: EquityInputs): EquityComposition | null {
  const value = i.value ?? 0
  const balance = i.mortgageBalance ?? 0
  if (!value) return null
  const original = i.originalAmount ?? null
  const principalPaid = original != null ? Math.max(0, original - balance) : 0
  const purchase = i.purchasePrice ?? null
  const needsPurchasePrice = purchase == null || original == null
  const downPayment = !needsPurchasePrice ? Math.max(0, purchase! - original!) : null
  const appreciation = !needsPurchasePrice ? value - purchase! : null
  const totalEquity = value - balance
  const pct = (n: number | null) => (n != null && n > 0 ? (n / value) * 100 : 0)
  return {
    totalEquity,
    equityPct: (totalEquity / value) * 100,
    principalPaid,
    downPayment,
    appreciation,
    remaining: balance,
    needsPurchasePrice,
    widths: {
      downPayment: pct(downPayment),
      appreciation: pct(appreciation),
      principalPaid: pct(principalPaid),
      remaining: pct(balance),
    },
  }
}

/** The purchase price the owner recorded: a history row labelled "Purchase price" or a sale record. */
export function purchasePriceFromHistory(
  history: { source: string; value: number; details?: Record<string, unknown> | null }[],
): number | null {
  const explicit = history.find((h) => h.details && (h.details as { valuation_source?: string }).valuation_source === 'Purchase price')
  if (explicit) return explicit.value
  const sale = history.find((h) => h.source === 'sale')
  return sale ? sale.value : null
}
