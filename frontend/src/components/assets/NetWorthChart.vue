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
const { currency, compact, date: fmtDate } = useFormatters()

const groupColors: Record<string, string> = {
  'Cash': '#3b82f6',
  'Investments': '#22c55e',
  'Company Stock': '#06b6d4',
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
  const pairs = (values: number[]) => values.map((v, i) => [props.data.dates[i], v] as [string, number])

  return {
    ...baseOption.value,
    tooltip: {
      ...baseOption.value.tooltip,
      trigger: 'axis' as const,
      formatter: (params: unknown) => {
        const list = (Array.isArray(params) ? params : [params]) as { seriesName: string; value: [string, number]; marker: string }[]
        if (!list.length) return ''
        let html = `<strong>${fmtDate(list[0].value[0])}</strong>`
        let total = 0
        for (const p of list) {
          html += `<br/>${p.marker} ${p.seriesName}: ${currency(p.value[1])}`
          total += p.value[1]
        }
        html += `<br/><strong>Net worth: ${currency(total)}</strong>`
        return html
      },
    },
    legend: { ...mobileLegend(), data: [...assets, ...liabilities] },
    grid: { ...baseOption.value.grid, bottom: isMobile.value ? 28 : 36 },
    xAxis: {
      type: 'time' as const,
      axisLabel: { ...mobileAxis(), formatter: { month: '{MMM}', year: '{yyyy}', day: '{MMM} {d}' }, hideOverlap: true },
      axisLine: { lineStyle: { color: axisLineColor.value } },
      splitLine: { show: false },
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
        data: pairs(props.data.groups[name]),
        smooth: false,
        symbol: 'none',
        lineStyle: { width: 1, color: groupColors[name] || '#6366f1' },
        itemStyle: { color: groupColors[name] || '#6366f1' },
        areaStyle: { opacity: 0.4 },
      })),
      ...liabilities.map(name => ({
        name,
        type: 'line' as const,
        data: pairs(props.data.groups[name]),
        smooth: false,
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
