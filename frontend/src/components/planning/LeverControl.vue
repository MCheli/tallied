<script setup lang="ts">
/**
 * LeverControl — one assumption as a slider plus an exact-value box, formatted by its unit.
 * Percent units are edited as percents in the box (7 means 7%) and stored as fractions.
 */
import { computed } from 'vue'
import InfoTooltip from '../common/InfoTooltip.vue'
import { formatLever, leverStep } from '../../composables/usePlanningOutlook'
import type { AssumptionSpec } from '../../types'

const props = defineProps<{ spec: AssumptionSpec; modelValue: number; changed?: boolean; min?: number; max?: number }>()
const emit = defineEmits<{ (e: 'update:modelValue', v: number): void }>()

const lo = computed(() => props.min ?? props.spec.min)
const hi = computed(() => props.max ?? props.spec.max)
const step = computed(() => leverStep(props.spec))
const isPct = computed(() => props.spec.unit === 'pct')
const boxValue = computed(() => (isPct.value ? +(props.modelValue * 100).toFixed(2) : props.modelValue))

function clamp(v: number) {
  return Math.min(hi.value, Math.max(lo.value, v))
}
function onSlider(e: Event) {
  emit('update:modelValue', clamp(Number((e.target as HTMLInputElement).value)))
}
function onBox(e: Event) {
  const raw = Number((e.target as HTMLInputElement).value)
  if (Number.isNaN(raw)) return
  emit('update:modelValue', clamp(isPct.value ? raw / 100 : raw))
}
</script>

<template>
  <label v-if="spec.unit === 'flag'" class="flex items-center gap-2 text-xs font-medium text-gray-600 dark:text-gray-300 min-w-0">
    <input type="checkbox" class="accent-indigo-600" :checked="modelValue >= 0.5"
      @change="(e) => emit('update:modelValue', (e.target as HTMLInputElement).checked ? 1 : 0)" />
    <span class="min-w-0">{{ spec.display_name }}</span>
    <InfoTooltip :text="spec.description" />
    <span v-if="changed" class="text-[10px] font-semibold text-indigo-600 dark:text-indigo-400" title="Differs from the saved plan">●</span>
  </label>
  <div v-else class="min-w-0">
    <div class="flex items-center justify-between gap-2 mb-1">
      <label :for="`lever-${spec.key}`" class="text-xs font-medium text-gray-600 dark:text-gray-300 truncate">
        {{ spec.display_name }}
        <InfoTooltip :text="spec.description" />
        <span v-if="changed" class="ml-1 text-[10px] font-semibold text-indigo-600 dark:text-indigo-400" title="Differs from the saved plan">●</span>
      </label>
      <span class="text-xs font-semibold text-gray-900 dark:text-white tabular-nums shrink-0">{{ formatLever(modelValue, spec.unit) }}</span>
    </div>
    <div class="flex items-center gap-2">
      <input
        :id="`lever-${spec.key}`" type="range" class="flex-1 min-w-0 accent-indigo-600"
        :min="lo" :max="hi" :step="step" :value="modelValue" @input="onSlider"
      />
      <input
        type="number" :aria-label="`${spec.display_name} exact value`"
        class="w-20 shrink-0 rounded-md border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-800 px-1.5 py-0.5 text-xs text-right tabular-nums text-gray-900 dark:text-white"
        :step="isPct ? 0.25 : step" :value="boxValue" @change="onBox"
      />
    </div>
  </div>
</template>
