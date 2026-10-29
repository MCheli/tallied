<script setup lang="ts">
import { computed } from 'vue'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { BarChart } from 'echarts/charts'
import { GridComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { useChartDefaults } from '../../composables/useChartDefaults'
import { useFormatters } from '../../composables/useFormatters'
import type { MonthlySpending } from '../../types'

use([BarChart, GridComponent, TooltipComponent, CanvasRenderer])

const props = defineProps<{ data: MonthlySpending[] }>()
const { baseOption, isMobile, axisLineColor, splitLineColor, mobileAxis } = useChartDefaults()
const { currency, compact, monthYear } = useFormatters()

const option = computed(() => {
  const months = props.data.map(d => d.month)
  const values = props.data.map(d => Math.abs(d.total))

  return {
    ...baseOption.value,
    tooltip: {
      ...baseOption.value.tooltip,
      trigger: 'axis' as const,
      formatter: (params: unknown) => {
        const p = (Array.isArray(params) ? params[0] : params) as { name: string; value: number }
        return `${monthYear(p.name)}<br/>Spending: ${currency(p.value)}`
      },
    },
    xAxis: {
      type: 'category' as const,
      data: months,
      axisLabel: {
        ...mobileAxis(),
        formatter: (v: string) => (isMobile.value ? monthYear(v).replace(' 20', " '") : monthYear(v)),
      },
      axisLine: { lineStyle: { color: axisLineColor.value } },
    },
    yAxis: {
      type: 'value' as const,
      axisLabel: { ...mobileAxis(), formatter: (v: number) => compact(v) },
      splitLine: { lineStyle: { color: splitLineColor.value } },
    },
    series: [
      {
        type: 'bar',
        data: values,
        itemStyle: {
          color: {
            type: 'linear' as const,
            x: 0, y: 0, x2: 0, y2: 1,
            colorStops: [
              { offset: 0, color: '#6366f1' },
              { offset: 1, color: 'rgba(99,102,241,0.5)' },
            ],
          },
          borderRadius: [4, 4, 0, 0],
        },
        barMaxWidth: 48,
      },
    ],
  }
})
</script>

<template>
  <v-chart :option="option" autoresize :style="{ height: isMobile ? '220px' : '280px' }" />
</template>
