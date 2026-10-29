import { useFormatters } from './useFormatters'

/**
 * The label shown next to an AI-estimated value (UND-ASSET-001, rule 2 in PRODUCT.md):
 * "AI estimate · medium confidence · claude-sonnet-5-5 · Oct 29, 2026".
 * Returns "No estimate yet" when there is no value.
 */
export function valuationLabel(v: {
  estimated_value: number | null | undefined
  valuation_source?: string | null
  valuation_confidence?: string | null
  valuation_model?: string | null
  value_last_updated?: string | null
}): string {
  if (v.estimated_value == null) return 'No estimate yet'
  const { date } = useFormatters()
  const parts: string[] = [v.valuation_source === 'manual' ? 'Manual value' : 'AI estimate']
  if (v.valuation_confidence) parts.push(`${v.valuation_confidence} confidence`)
  if (v.valuation_model) parts.push(v.valuation_model)
  if (v.value_last_updated) parts.push(date(v.value_last_updated.slice(0, 10)))
  return parts.join(' · ')
}
