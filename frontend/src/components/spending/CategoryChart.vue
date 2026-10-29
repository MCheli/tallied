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
const { baseOption, isMobile, splitLineColor, mobileAxis } = useChartDefaults()
const { currency, compact } = useFormatters()

const top = computed(() => [...props.categories].sort((a, b) => Math.abs(b.total) - Math.abs(a.total)).slice(0, 15))

const option = computed(() => {
  const cats = top.value.map(c => c.category).reverse()
  const values = top.value.map(c => Math.abs(c.total)).reverse()

  return {
    ...baseOption.value,
    grid: { left: 4, right: 12, top: 4, bottom: 4, containLabel: true },
    tooltip: {
      ...baseOption.value.tooltip,
      trigger: 'axis' as const,
      formatter: (params: unknown) => {
        const p = (Array.isArray(params) ? params[0] : params) as { name: string; value: number }
        return `${p.name}: ${currency(p.value)}`
      },
    },
    xAxis: {
      type: 'value' as const,
      axisLabel: { ...mobileAxis(), formatter: (v: number) => compact(v) },
      splitNumber: 3,
      splitLine: { lineStyle: { color: splitLineColor.value } },
    },
    yAxis: {
      type: 'category' as const,
      data: cats,
      axisLabel: { ...mobileAxis(), width: isMobile.value ? 90 : 120, overflow: 'truncate' as const, interval: 0 },
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

const height = computed(() => `${Math.max(180, Math.min(400, 24 + top.value.length * 26))}px`)
</script>

<template>
  <v-chart :option="option" autoresize :style="{ height }" />
</template>
