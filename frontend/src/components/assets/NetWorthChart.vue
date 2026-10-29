<script setup lang="ts">
import { computed } from 'vue'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { LineChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { useChartDefaults } from '../../composables/useChartDefaults'
import { useFormatters } from '../../composables/useFormatters'
import type { NetWorthSeries } from '../../types'

use([LineChart, GridComponent, TooltipComponent, LegendComponent, CanvasRenderer])

const props = defineProps<{ data: NetWorthSeries }>()
const { baseOption, isMobile, axisLineColor, splitLineColor, mobileAxis, mobileLegend } = useChartDefaults()
const { currency, compact } = useFormatters()

const groupColors: Record<string, string> = {
  'Cash': '#3b82f6',
  'Investments': '#22c55e',
  'Home Equity': '#f59e0b',
  'Retirement': '#8b5cf6',
  'Credit Cards': '#ef4444',
  'Other Loans': '#f97316',
}

/** A group whose values are never positive is a liability: drawn as its own line, not stacked into the area. */
function isLiability(values: number[]): boolean {
  return values.length > 0 && values.every(v => v <= 0) && values.some(v => v < 0)
}

const option = computed(() => {
  const groups = Object.keys(props.data.groups)
  const assets = groups.filter(g => !isLiability(props.data.groups[g]))
  const liabilities = groups.filter(g => isLiability(props.data.groups[g]))
  const dates = props.data.dates.map(d => d.slice(0, 7))

  return {
    ...baseOption.value,
    tooltip: {
      ...baseOption.value.tooltip,
      trigger: 'axis' as const,
      formatter: (params: unknown) => {
        const list = (Array.isArray(params) ? params : [params]) as { name: string; seriesName: string; value: number; marker: string }[]
        if (!list.length) return ''
        let html = `<strong>${list[0].name}</strong>`
        let total = 0
        for (const p of list) {
          html += `<br/>${p.marker} ${p.seriesName}: ${currency(p.value)}`
          total += p.value
        }
        html += `<br/><strong>Net worth: ${currency(total)}</strong>`
        return html
      },
    },
    legend: { ...mobileLegend(), data: [...assets, ...liabilities] },
    grid: { ...baseOption.value.grid, bottom: isMobile.value ? 28 : 36 },
    xAxis: {
      type: 'category' as const,
      data: dates,
      axisLabel: { ...mobileAxis(), interval: isMobile.value ? Math.max(1, Math.floor(dates.length / 4)) : Math.max(0, Math.floor(dates.length / 8)) },
      axisLine: { lineStyle: { color: axisLineColor.value } },
    },
    yAxis: {
      type: 'value' as const,
      axisLabel: { ...mobileAxis(), formatter: (v: number) => compact(v) },
      splitLine: { lineStyle: { color: splitLineColor.value } },
    },
    series: [
      ...assets.map(name => ({
        name,
        type: 'line' as const,
        stack: 'assets',
        data: props.data.groups[name],
        smooth: true,
        symbol: 'none',
        lineStyle: { width: 1, color: groupColors[name] || '#6366f1' },
        itemStyle: { color: groupColors[name] || '#6366f1' },
        areaStyle: { opacity: 0.4 },
      })),
      ...liabilities.map(name => ({
        name,
        type: 'line' as const,
        data: props.data.groups[name],
        smooth: true,
        symbol: 'none',
        lineStyle: { width: 2, type: 'dashed' as const, color: groupColors[name] || '#ef4444' },
        itemStyle: { color: groupColors[name] || '#ef4444' },
      })),
    ],
  }
})
</script>

<template>
  <v-chart :option="option" autoresize :style="{ height: isMobile ? '300px' : '400px' }" />
</template>
