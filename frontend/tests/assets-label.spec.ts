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

  it('says so when there is no estimate', () => {
    expect(valuationLabel({ estimated_value: null })).toBe('No estimate yet')
  })

  it('handles a value with no label fields', () => {
    expect(valuationLabel({ estimated_value: 1 })).toBe('AI estimate')
  })
})
