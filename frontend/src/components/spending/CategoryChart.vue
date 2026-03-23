<script setup lang="ts">
import { computed } from 'vue'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { BarChart } from 'echarts/charts'
import { GridComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { useChartDefaults } from '../../composables/useChartDefaults'
import { useFormatters } from '../../composables/useFormatters'
import type { CategorySummary } from '../../types'

use([BarChart, GridComponent, TooltipComponent, CanvasRenderer])

const props = defineProps<{ categories: CategorySummary[] }>()
const { baseOption } = useChartDefaults()
const { currency } = useFormatters()

const option = computed(() => {
  const sorted = [...props.categories]
    .sort((a, b) => Math.abs(b.total) - Math.abs(a.total))
    .slice(0, 15)
  const cats = sorted.map(c => c.category).reverse()
  const values = sorted.map(c => Math.abs(c.total)).reverse()

  return {
    ...baseOption.value,
    grid: { left: 10, right: 20, top: 10, bottom: 10, containLabel: true },
    tooltip: {
      ...baseOption.value.tooltip,
      trigger: 'axis' as const,
      formatter: (params: any) => {
        const p = Array.isArray(params) ? params[0] : params
        return `${p.name}: ${currency(p.value)}`
      },
    },
    xAxis: {
      type: 'value' as const,
      axisLabel: {
        color: baseOption.value.textStyle.color,
        formatter: (v: number) => v >= 1000 ? `$${(v / 1000).toFixed(0)}K` : `$${v.toFixed(0)}`,
        hideOverlap: true,
      },
      splitNumber: 3,
      splitLine: { lineStyle: { color: '#e5e7eb33' } },
    },
    yAxis: {
      type: 'category' as const,
      data: cats,
      axisLabel: {
        color: baseOption.value.textStyle.color,
        fontSize: 11,
        width: 120,
        overflow: 'truncate' as const,
      },
    },
    series: [
      {
        type: 'bar',
        data: values,
        itemStyle: { color: '#6366f1', borderRadius: [0, 4, 4, 0] },
        barMaxWidth: 24,
      },
    ],
  }
})
</script>

<template>
  <v-chart :option="option" autoresize style="height: 400px" />
</template>
