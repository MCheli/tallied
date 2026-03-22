<script setup lang="ts">
import { computed } from 'vue'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { BarChart } from 'echarts/charts'
import { GridComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { useChartDefaults } from '../../composables/useChartDefaults'
import { useFormatters } from '../../composables/useFormatters'
import type { SensitivityItem } from '../../types'

use([BarChart, GridComponent, TooltipComponent, CanvasRenderer])

const props = defineProps<{ items: SensitivityItem[] }>()
const { baseOption } = useChartDefaults()
const { compact } = useFormatters()

const option = computed(() => {
  const sorted = [...props.items].sort(
    (a, b) => Math.abs(b.impact_high - b.impact_low) - Math.abs(a.impact_high - a.impact_low)
  )

  const categories = sorted.map(i => i.display_name)
  const lowValues = sorted.map(i => i.impact_low - i.base_value)
  const highValues = sorted.map(i => i.impact_high - i.base_value)

  return {
    ...baseOption.value,
    grid: { left: 10, right: 20, top: 10, bottom: 10, containLabel: true },
    tooltip: {
      ...baseOption.value.tooltip,
      trigger: 'axis' as const,
      formatter: (params: any) => {
        if (!Array.isArray(params) || params.length === 0) return ''
        const idx = params[0].dataIndex
        const item = sorted[idx]
        return `<strong>${item.display_name}</strong><br/>
          Base: ${compact(item.base_value)}<br/>
          Low: ${compact(item.impact_low)}<br/>
          High: ${compact(item.impact_high)}`
      },
    },
    xAxis: {
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
    yAxis: {
      type: 'category' as const,
      data: categories,
      axisLabel: { color: baseOption.value.textStyle.color, fontSize: 11 },
    },
    series: [
      {
        name: 'Downside',
        type: 'bar',
        stack: 'tornado',
        data: lowValues,
        itemStyle: { color: '#ef4444', borderRadius: [4, 0, 0, 4] },
        barMaxWidth: 20,
      },
      {
        name: 'Upside',
        type: 'bar',
        stack: 'tornado',
        data: highValues,
        itemStyle: { color: '#22c55e', borderRadius: [0, 4, 4, 0] },
        barMaxWidth: 20,
      },
    ],
  }
})
</script>

<template>
  <v-chart :option="option" autoresize style="height: 400px" />
</template>
