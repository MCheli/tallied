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
const { baseOption } = useChartDefaults()
const { currency } = useFormatters()

const groupColors: Record<string, string> = {
  'Cash': '#3b82f6',
  'Investments': '#22c55e',
  'Home Equity': '#f59e0b',
  'Retirement': '#8b5cf6',
}

const option = computed(() => {
  const groups = Object.keys(props.data.groups)

  return {
    ...baseOption.value,
    tooltip: {
      ...baseOption.value.tooltip,
      trigger: 'axis' as const,
      formatter: (params: any) => {
        if (!Array.isArray(params) || params.length === 0) return ''
        let html = `<strong>${params[0].name}</strong>`
        let total = 0
        for (const p of params) {
          html += `<br/>${p.marker} ${p.seriesName}: ${currency(p.value)}`
          total += p.value
        }
        html += `<br/><strong>Total: ${currency(total)}</strong>`
        return html
      },
    },
    legend: {
      bottom: 0,
      textStyle: { color: baseOption.value.textStyle.color },
    },
    grid: { left: 60, right: 20, top: 20, bottom: 40 },
    xAxis: {
      type: 'category' as const,
      data: props.data.dates,
      axisLabel: {
        color: baseOption.value.textStyle.color,
        fontSize: 11,
        interval: Math.floor(props.data.dates.length / 8),
      },
      axisLine: { lineStyle: { color: '#e5e7eb' } },
    },
    yAxis: {
      type: 'value' as const,
      axisLabel: {
        color: baseOption.value.textStyle.color,
        formatter: (v: number) => {
          if (Math.abs(v) >= 1_000_000) return `$${(v / 1_000_000).toFixed(1)}M`
          return `$${(v / 1_000).toFixed(0)}K`
        },
      },
      splitLine: { lineStyle: { color: '#e5e7eb33' } },
    },
    series: groups.map(name => ({
      name,
      type: 'line',
      stack: 'total',
      data: props.data.groups[name],
      smooth: true,
      symbol: 'none',
      lineStyle: { width: 1, color: groupColors[name] || '#6366f1' },
      itemStyle: { color: groupColors[name] || '#6366f1' },
      areaStyle: { opacity: 0.4 },
    })),
  }
})
</script>

<template>
  <v-chart :option="option" autoresize style="height: 400px" />
</template>
