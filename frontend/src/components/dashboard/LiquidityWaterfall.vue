<script setup lang="ts">
import { computed } from 'vue'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { BarChart } from 'echarts/charts'
import { GridComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { useChartDefaults } from '../../composables/useChartDefaults'
import { useFormatters } from '../../composables/useFormatters'
import { waterfallNetWorth, waterfallSteps } from '../../composables/useDashboardTiles'
import type { LiquidityLayer } from '../../types'

use([BarChart, GridComponent, TooltipComponent, CanvasRenderer])

const props = defineProps<{ layers: LiquidityLayer[] }>()
const { baseOption, isMobile, axisLineColor, splitLineColor, mobileAxis } = useChartDefaults()
const { currency, compact } = useFormatters()

const layerColors: Record<string, string> = {
  'Cash': '#3b82f6',
  'Investments': '#22c55e',
  'Home Equity': '#f59e0b',
  'Retirement': '#8b5cf6',
  'Credit Cards': '#ef4444',
  'Other Loans': '#f97316',
}

const option = computed(() => {
  // Layer totals already include only include_in_nw accounts, so the running sum is the net worth tile.
  const steps = waterfallSteps(props.layers)
  const netWorth = waterfallNetWorth(props.layers)
  const categories = [...steps.map(s => s.name), 'Net Worth']
  // Negative layers hang down from the running total: invisible base = start + total, visible = |total|.
  const invisible = [...steps.map(s => (s.total >= 0 ? s.start : s.start + s.total)), 0]
  const visible = [...steps.map(s => Math.abs(s.total)), netWorth]
  const signed = [...steps.map(s => s.total), netWorth]
  const colors = [...steps.map(s => layerColors[s.name] || '#6366f1'), '#6366f1']

  return {
    ...baseOption.value,
    tooltip: {
      ...baseOption.value.tooltip,
      trigger: 'axis' as const,
      formatter: (params: unknown) => {
        const list = (Array.isArray(params) ? params : [params]) as { seriesName: string; name: string; dataIndex: number }[]
        const p = list.find(s => s.seriesName === 'Value')
        if (!p) return ''
        return `<strong>${p.name}</strong><br/>${currency(signed[p.dataIndex])}`
      },
    },
    xAxis: {
      type: 'category' as const,
      data: categories,
      axisLabel: { ...mobileAxis(), interval: 0, rotate: isMobile.value ? 30 : 0 },
      axisLine: { lineStyle: { color: axisLineColor.value } },
    },
    yAxis: {
      type: 'value' as const,
      axisLabel: { ...mobileAxis(), formatter: (v: number) => compact(v) },
      splitLine: { lineStyle: { color: splitLineColor.value } },
    },
    series: [
      {
        name: 'Invisible',
        type: 'bar',
        stack: 'waterfall',
        itemStyle: { color: 'transparent' },
        data: invisible,
        emphasis: { itemStyle: { color: 'transparent' } },
        tooltip: { show: false },
      },
      {
        name: 'Value',
        type: 'bar',
        stack: 'waterfall',
        data: visible.map((v, i) => ({
          value: v,
          itemStyle: { color: colors[i], borderRadius: signed[i] >= 0 ? [4, 4, 0, 0] : [0, 0, 4, 4] },
        })),
        label: {
          show: !isMobile.value,
          position: 'top',
          formatter: (p: { dataIndex: number }) => compact(signed[p.dataIndex]),
          color: baseOption.value.textStyle.color,
          fontSize: 11,
        },
      },
    ],
  }
})
</script>

<template>
  <v-chart :option="option" autoresize :style="{ height: isMobile ? '260px' : '320px' }" />
</template>
