<script setup lang="ts">
/**
 * StackedYears — stacked bars by age in today's dollars (what a retired year costs; where the
 * money comes from). Series keep a fixed colour each; empty series are dropped from the legend.
 */
import { computed } from 'vue'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { BarChart } from 'echarts/charts'
import { GridComponent, LegendComponent, MarkLineComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { useChartDefaults } from '../../composables/useChartDefaults'
import { useFormatters } from '../../composables/useFormatters'
import type { Milestone } from '../../types'
import { milestoneMarks } from '../../composables/usePlanningOutlook'

use([BarChart, GridComponent, LegendComponent, MarkLineComponent, TooltipComponent, CanvasRenderer])

const props = withDefaults(defineProps<{
  ages: number[]
  series: { name: string; data: number[]; color: string }[]
  milestones?: Milestone[]
  height?: number
}>(), { milestones: () => [], height: 280 })

const { baseOption, axisLineColor, splitLineColor, mutedTextColor, mobileAxis, mobileLegend, isDark } = useChartDefaults()
const { compact, money } = useFormatters()

const shown = computed(() => props.series.filter((s) => s.data.some((v) => v > 0)))
const option = computed(() => {
  const marks = milestoneMarks(props.milestones, props.ages)
  return {
    ...baseOption.value,
    grid: { ...baseOption.value.grid, bottom: 56 },
    legend: { ...mobileLegend(), type: 'plain' as const },
    tooltip: {
      ...baseOption.value.tooltip, axisPointer: { type: 'shadow' as const },
      formatter: (params: { dataIndex: number; seriesName: string; value: number; marker: string }[]) => {
        const i = params[0]?.dataIndex ?? 0
        let total = 0
        const lines = params.filter((p) => p.value > 0).map((p) => { total += p.value; return `${p.marker} ${p.seriesName}: ${money(p.value)}` })
        return `<strong>Age ${props.ages[i]}</strong><br/>${lines.join('<br/>')}<br/><strong>Total: ${money(total)}</strong>`
      },
    },
    xAxis: {
      type: 'category' as const, data: props.ages,
      axisLine: { lineStyle: { color: axisLineColor.value } }, axisTick: { show: false }, axisLabel: { ...mobileAxis() },
    },
    yAxis: {
      type: 'value' as const,
      axisLabel: { ...mobileAxis(), formatter: (v: number) => compact(v) },
      splitLine: { lineStyle: { color: splitLineColor.value } },
    },
    series: shown.value.map((s, i) => ({
      name: s.name, type: 'bar' as const, stack: 'y', barCategoryGap: '25%', data: s.data,
      itemStyle: { color: s.color, borderColor: isDark.value ? '#111827' : '#ffffff', borderWidth: 1 },
      markLine: i === 0 && marks.length ? {
        silent: true, symbol: 'none', lineStyle: { color: mutedTextColor.value, type: 'solid' as const, width: 1, opacity: 0.6 },
        label: { formatter: (p: { data: { name: string } }) => p.data.name, color: mutedTextColor.value, fontSize: 9, position: 'insideEndTop' as const },
        data: marks.map((m) => ({ xAxis: m.index, name: m.label })),
      } : undefined,
    })),
  }
})
</script>

<template>
  <v-chart :option="option" autoresize :style="{ height: `${height}px` }" />
</template>
