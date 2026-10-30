import { describe, expect, it } from 'vitest'
import { valuationLabel } from '../src/composables/useValuationLabel'

describe('valuationLabel', () => {
  it('labels an AI estimate with confidence, model and date', () => {
    expect(valuationLabel({
      estimated_value: 22000,
      valuation_source: 'ai',
      valuation_confidence: 'medium',
      valuation_model: 'claude-sonnet-5-5',
      value_last_updated: '2026-10-29T08:00:00',
    })).toBe('AI estimate · medium confidence · claude-sonnet-5-5 · Oct 29, 2026')
  })

  it('labels a researched estimate built from recent sale prices', () => {
    expect(valuationLabel({
      estimated_value: 6500,
      valuation_source: 'research',
      valuation_confidence: 'medium',
      valuation_model: 'claude-opus-5-5',
      value_last_updated: '2026-10-30T08:00:00',
    })).toBe('Researched estimate (recent sale prices) · medium confidence · claude-opus-5-5 · Oct 30, 2026')
  })

  it('says so when there is no estimate', () => {
    expect(valuationLabel({ estimated_value: null })).toBe('No estimate yet')
  })

  it('handles a value with no label fields', () => {
    expect(valuationLabel({ estimated_value: 1 })).toBe('AI estimate')
  })
})
