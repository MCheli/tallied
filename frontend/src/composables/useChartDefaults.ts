import { computed } from 'vue'
import { useThemeStore } from '../stores/theme'
import { useMediaQuery } from './useMediaQuery'

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

/**
 * Chart styling that follows the theme and the viewport.
 *
 * Returns:
 *   baseOption    spread into every ECharts option: colours, text colour, grid (containLabel: true,
 *                 tighter on phones), themed tooltip. Reactive: re-evaluates when dark mode or width changes.
 *   COLORS        the series palette.
 *   isDark        boolean computed from the theme store.
 *   isMobile      ref<boolean>, true under 640px.
 *   axisLineColor / splitLineColor   computed colours for axisLine / splitLine (no more hard-coded hex in views).
 *   mobileAxis()  axisLabel options for phones (small font, auto interval, hideOverlap) — merge into xAxis/yAxis.axisLabel.
 *   mobileLegend() legend options for phones (bottom, scrollable, small font) — spread into `legend`.
 *   On desktop both helpers return sensible defaults, so views can always spread them.
 */
export function useChartDefaults() {
  const theme = useThemeStore()
  const isDark = computed(() => theme.dark)
  const isMobile = useMediaQuery('(max-width: 640px)')

  const axisLineColor = computed(() => (isDark.value ? '#374151' : '#e5e7eb'))
  const splitLineColor = computed(() => (isDark.value ? '#1f2937' : '#f3f4f6'))
  const mutedTextColor = computed(() => (isDark.value ? '#9ca3af' : '#6b7280'))

  const baseOption = computed(() => ({
    color: COLORS,
    backgroundColor: 'transparent',
    textStyle: {
      color: mutedTextColor.value,
      fontFamily: 'system-ui, sans-serif',
    },
    grid: isMobile.value
      ? { left: 8, right: 8, top: 32, bottom: 8, containLabel: true }
      : { left: 16, right: 16, top: 40, bottom: 24, containLabel: true },
    tooltip: {
      trigger: 'axis' as const,
      confine: true,
      backgroundColor: isDark.value ? '#1f2937' : '#fff',
      borderColor: isDark.value ? '#374151' : '#e5e7eb',
      textStyle: {
        color: isDark.value ? '#f3f4f6' : '#111827',
      },
    },
  }))

  function mobileAxis() {
    return isMobile.value
      ? { fontSize: 10, interval: 'auto' as const, rotate: 0, hideOverlap: true, color: mutedTextColor.value }
      : { fontSize: 11, hideOverlap: true, color: mutedTextColor.value }
  }

  function mobileLegend() {
    return isMobile.value
      ? { bottom: 0, type: 'scroll' as const, itemGap: 8, itemWidth: 12, itemHeight: 8, textStyle: { fontSize: 10, color: mutedTextColor.value } }
      : { bottom: 0, type: 'scroll' as const, itemGap: 16, textStyle: { fontSize: 11, color: mutedTextColor.value } }
  }

  return { baseOption, COLORS, isDark, isMobile, axisLineColor, splitLineColor, mutedTextColor, mobileAxis, mobileLegend }
}
