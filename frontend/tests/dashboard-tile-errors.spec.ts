import { describe, expect, it } from 'vitest'
import { useTile } from '../src/composables/useDashboardTiles'

describe('dashboard tiles load independently (LOOK-005)', () => {
  it('one failing endpoint leaves the other tiles populated and reports its own error', async () => {
    const rsu = useTile<{ held_value: number }>()
    const spending = useTile<{ total: number }>()
    const property = useTile<{ equity: number }>()

    await Promise.allSettled([
      rsu.load(async () => ({ held_value: 1000 })),
      spending.load(async () => { throw new Error('503: AI features need FINANCE_ANTHROPIC_API_KEY') }),
      property.load(async () => ({ equity: 150000 })),
    ])

    expect(rsu.data.value).toEqual({ held_value: 1000 })
    expect(property.data.value).toEqual({ equity: 150000 })
    expect(spending.data.value).toBeNull()
    expect(spending.error.value).toContain('503')
    expect(rsu.error.value).toBeNull()
    expect([rsu, spending, property].every(t => t.loading.value === false)).toBe(true)
  })

  it('clears a previous error on a successful reload', async () => {
    const tile = useTile<number>()
    await tile.load(async () => { throw new Error('boom') })
    expect(tile.error.value).toBe('boom')
    await tile.load(async () => 42)
    expect(tile.error.value).toBeNull()
    expect(tile.data.value).toBe(42)
  })
})
