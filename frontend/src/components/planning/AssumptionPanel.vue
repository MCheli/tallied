<script setup lang="ts">
import { computed } from 'vue'
import { useFormatters } from '../../composables/useFormatters'
import type { AssumptionResponse } from '../../types'

const props = defineProps<{ assumptions: AssumptionResponse[] }>()
const emit = defineEmits<{ (e: 'update', key: string, value: number): void }>()
const { currency, pct } = useFormatters()

const grouped = computed(() => {
  const map: Record<string, AssumptionResponse[]> = {}
  for (const a of props.assumptions) {
    const cat = a.category || 'other'
    if (!map[cat]) map[cat] = []
    map[cat].push(a)
  }
  return map
})

const categoryLabels: Record<string, string> = {
  career: 'Career & Income',
  markets: 'Market Returns',
  spending: 'Spending & Savings',
  tax: 'Taxes',
  housing: 'Housing',
  other: 'Other',
}

const PERCENTAGE_KEYS = new Set([
  'total_comp_growth', 'rsu_pct_of_comp', 'rsu_pct_annual_increase', 'rsu_pct_cap',
  'rsu_tax_rate', 'investment_return', 'retirement_return', 'stock_price_growth',
  'inflation', 'home_appreciation', 'retirement_tax_rate',
])

const INTEGER_KEYS = new Set(['retirement_age'])

function isPercentage(a: AssumptionResponse): boolean {
  return PERCENTAGE_KEYS.has(a.key)
}

function isInteger(a: AssumptionResponse): boolean {
  return INTEGER_KEYS.has(a.key)
}

function formatValue(a: AssumptionResponse): string {
  if (isPercentage(a)) return pct(a.value)
  if (isInteger(a)) return String(Math.round(a.value))
  return currency(a.value)
}

function getStep(a: AssumptionResponse): number {
  if (isPercentage(a)) return 0.005
  if (isInteger(a)) return 1
  if (a.value > 10000) return 1000
  if (a.value > 1000) return 100
  return 10
}

function getMin(a: AssumptionResponse): number {
  if (isInteger(a)) return 30
  return 0
}

function getMax(a: AssumptionResponse): number {
  if (isPercentage(a)) return 1
  if (isInteger(a)) return 80
  if (a.value > 100000) return a.value * 3
  return Math.max(a.value * 5, 1000)
}

function onInput(key: string, event: Event) {
  const target = event.target as HTMLInputElement
  emit('update', key, parseFloat(target.value))
}
</script>

<template>
  <div class="space-y-4">
    <div
      v-for="(items, category) in grouped"
      :key="category"
      class="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800"
    >
      <details open>
        <summary class="px-4 py-3 cursor-pointer text-sm font-semibold text-gray-900 dark:text-white hover:bg-gray-50 dark:hover:bg-gray-800 rounded-t-xl">
          {{ categoryLabels[category] || category }}
        </summary>
        <div class="px-4 pb-4 space-y-4">
          <div v-for="a in items" :key="a.key">
            <div class="flex items-center justify-between mb-1">
              <label class="text-xs font-medium text-gray-700 dark:text-gray-300">{{ a.display_name }}</label>
              <span class="text-xs font-semibold text-indigo-600 dark:text-indigo-400">{{ formatValue(a) }}</span>
            </div>
            <input
              type="range"
              :value="a.value"
              :min="getMin(a)"
              :max="getMax(a)"
              :step="getStep(a)"
              @input="onInput(a.key, $event)"
              class="w-full h-1.5 bg-gray-200 dark:bg-gray-700 rounded-lg appearance-none cursor-pointer accent-indigo-600"
            />
            <p v-if="a.description" class="text-[10px] text-gray-400 mt-0.5">{{ a.description }}</p>
          </div>
        </div>
      </details>
    </div>
  </div>
</template>
