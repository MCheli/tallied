<script setup lang="ts">
/**
 * CompositionChart — what the wealth is made of, year by year, on the plan line (every return at
 * its median), in today's dollars. Stacked areas in the fixed bucket order.
 */
import { computed } from 'vue'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { LineChart } from 'echarts/charts'
import { GridComponent, LegendComponent, MarkLineComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { useChartDefaults } from '../../composables/useChartDefaults'
import { useFormatters } from '../../composables/useFormatters'
import type { Milestone, OutlookRow } from '../../types'
import { milestoneMarks } from '../../composables/usePlanningOutlook'

use([LineChart, GridComponent, LegendComponent, MarkLineComponent, TooltipComponent, CanvasRenderer])

const props = withDefaults(defineProps<{ rows: OutlookRow[]; retirementAge: number; milestones?: Milestone[] }>(), { milestones: () => [] })
const { baseOption, axisLineColor, splitLineColor, mutedTextColor, mobileAxis, mobileLegend, bucketColors, isDark } = useChartDefaults()
const { compact, money } = useFormatters()

const BUCKETS: { key: keyof OutlookRow; label: string }[] = [
  { key: 'cash', label: 'Cash' },
  { key: 'investments', label: 'Taxable investments' },
  { key: 'company_stock', label: 'Company stock' },
  { key: 'retirement_bal', label: '401(k)' },
  { key: 'home_equity', label: 'Home equity' },
]

const option = computed(() => {
  const ages = props.rows.map((r) => r.age)
  const ri = ages.indexOf(props.retirementAge)
  return {
    ...baseOption.value,
    grid: { ...baseOption.value.grid, bottom: 64 },
    // Five entries: a wrapping legend, never a paged one, so every bucket is named.
    legend: { ...mobileLegend(), type: 'plain' as const },
    tooltip: {
      ...baseOption.value.tooltip,
      formatter: (params: { dataIndex: number; seriesName: string; value: number; marker: string }[]) => {
        const i = params[0]?.dataIndex ?? 0
        let total = 0
        const lines = params.map((p) => { total += p.value; return `${p.marker} ${p.seriesName}: ${money(p.value)}` })
        return `<strong>Age ${ages[i]} (${props.rows[i].year})</strong><br/>${lines.join('<br/>')}<br/><strong>Net worth: ${money(total)}</strong>`
      },
    },
    xAxis: {
      type: 'category' as const, data: ages, boundaryGap: false,
      axisLine: { lineStyle: { color: axisLineColor.value } }, axisTick: { show: false }, axisLabel: { ...mobileAxis() },
    },
    yAxis: {
      type: 'value' as const,
      axisLabel: { ...mobileAxis(), formatter: (v: number) => compact(v) },
      splitLine: { lineStyle: { color: splitLineColor.value } },
    },
    series: BUCKETS.map((b, i) => ({
      name: b.label, type: 'line' as const, stack: 'nw', symbol: 'none',
      lineStyle: { width: 1, color: isDark.value ? '#111827' : '#ffffff' },
      itemStyle: { color: bucketColors.value[i] },
      areaStyle: { color: bucketColors.value[i], opacity: 0.85 },
      data: props.rows.map((r) => Math.max(0, Number(r[b.key]) / (r.deflator || 1))),
      markLine: i === 0 && ri >= 0 ? {
        silent: true, symbol: 'none', lineStyle: { color: mutedTextColor.value, type: 'solid' as const, width: 1, opacity: 0.5 },
        label: { color: mutedTextColor.value, fontSize: 9, position: 'insideEndTop' as const,
                 formatter: (p: { data: { name: string } }) => p.data.name },
        data: [
          { xAxis: ri, name: `Retire ${props.retirementAge}`, lineStyle: { opacity: 1, width: 1.5 } },
          ...milestoneMarks(props.milestones, ages).filter((m) => m.index !== ri).map((m) => ({ xAxis: m.index, name: m.label })),
        ],
      } : undefined,
    })),
  }
})
</script>

<template>
  <v-chart :option="option" autoresize style="height: 320px" />
</template>
