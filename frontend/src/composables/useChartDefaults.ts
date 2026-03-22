import { computed } from 'vue'

const COLORS = [
  '#6366f1', // indigo
  '#22c55e', // green
  '#f59e0b', // amber
  '#ef4444', // red
  '#06b6d4', // cyan
  '#8b5cf6', // violet
  '#ec4899', // pink
  '#14b8a6', // teal
]

export function useChartDefaults() {
  const isDark = computed(() => document.documentElement.classList.contains('dark'))

  const baseOption = computed(() => ({
    color: COLORS,
    backgroundColor: 'transparent',
    textStyle: {
      color: isDark.value ? '#9ca3af' : '#6b7280',
      fontFamily: 'system-ui, sans-serif',
    },
    grid: {
      left: 60,
      right: 20,
      top: 40,
      bottom: 40,
      containLabel: false,
    },
    tooltip: {
      trigger: 'axis' as const,
      backgroundColor: isDark.value ? '#1f2937' : '#fff',
      borderColor: isDark.value ? '#374151' : '#e5e7eb',
      textStyle: {
        color: isDark.value ? '#f3f4f6' : '#111827',
      },
    },
  }))

  return { baseOption, COLORS, isDark }
}
