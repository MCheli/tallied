<script setup lang="ts">
import { computed } from 'vue'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { BarChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { useChartDefaults } from '../../composables/useChartDefaults'
import { useFormatters } from '../../composables/useFormatters'
import type { LiquidityLayer } from '../../types'

use([BarChart, GridComponent, TooltipComponent, LegendComponent, CanvasRenderer])

const props = defineProps<{ layers: LiquidityLayer[] }>()
const { baseOption } = useChartDefaults()
const { currency } = useFormatters()

const layerColors: Record<string, string> = {
  'Cash': '#3b82f6',
  'Investments': '#22c55e',
  'Home Equity': '#f59e0b',
  'Retirement': '#8b5cf6',
}

const option = computed(() => {
  const categories = props.layers.map(l => l.name)
  const invisible: number[] = []
  const visible: number[] = []
  const colors: string[] = []

  let running = 0
  for (const layer of props.layers) {
    invisible.push(running)
    visible.push(layer.total)
    colors.push(layerColors[layer.name] || '#6366f1')
    running += layer.total
  }

  // Add total bar
  categories.push('Net Worth')
  invisible.push(0)
  visible.push(running)
  colors.push('#6366f1')

  return {
    ...baseOption.value,
    tooltip: {
      ...baseOption.value.tooltip,
      trigger: 'axis' as const,
      formatter: (params: any) => {
        const p = Array.isArray(params) ? params.find((s: any) => s.seriesName === 'Value') : params
        if (!p) return ''
        return `<strong>${p.name}</strong><br/>${currency(p.value)}`
      },
    },
    xAxis: {
      type: 'category' as const,
      data: categories,
      axisLabel: { color: baseOption.value.textStyle.color },
      axisLine: { lineStyle: { color: '#e5e7eb' } },
    },
    yAxis: {
      type: 'value' as const,
      axisLabel: {
        color: baseOption.value.textStyle.color,
        formatter: (v: number) => {
          if (Math.abs(v) >= 1_000_000) return `$${(v / 1_000_000).toFixed(1)}M`
          if (Math.abs(v) >= 1_000) return `$${(v / 1_000).toFixed(0)}K`
          return `$${v}`
        },
      },
      splitLine: { lineStyle: { color: '#e5e7eb33' } },
    },
    series: [
      {
        name: 'Invisible',
        type: 'bar',
        stack: 'waterfall',
        itemStyle: { color: 'transparent' },
        data: invisible,
        emphasis: { itemStyle: { color: 'transparent' } },
      },
      {
        name: 'Value',
        type: 'bar',
        stack: 'waterfall',
        data: visible.map((v, i) => ({
          value: v,
          itemStyle: { color: colors[i], borderRadius: [4, 4, 0, 0] },
        })),
        label: {
          show: true,
          position: 'top',
          formatter: (p: any) => {
            if (Math.abs(p.value) >= 1_000_000) return `$${(p.value / 1_000_000).toFixed(1)}M`
            return `$${(p.value / 1_000).toFixed(0)}K`
          },
          color: baseOption.value.textStyle.color,
          fontSize: 11,
        },
      },
    ],
  }
})
</script>

<template>
  <v-chart :option="option" autoresize style="height: 320px" />
</template>
