<script setup lang="ts">
/**
 * SuccessCurve — chance of success against one lever (retirement age or spending), with the
 * target as a horizontal rule and the plan's own setting marked.
 */
import { computed } from 'vue'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { LineChart } from 'echarts/charts'
import { GridComponent, MarkLineComponent, MarkPointComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { useChartDefaults } from '../../composables/useChartDefaults'
import { useFormatters } from '../../composables/useFormatters'

use([LineChart, GridComponent, MarkLineComponent, MarkPointComponent, TooltipComponent, CanvasRenderer])

const props = withDefaults(defineProps<{
  x: number[]
  y: number[]
  kind: 'age' | 'usd'
  target: number
  current: number
  height?: number
}>(), { height: 240 })

const { baseOption, axisLineColor, splitLineColor, mutedTextColor, mobileAxis, COLORS } = useChartDefaults()
const { percent, compact, money } = useFormatters()

const option = computed(() => {
  const label = (v: number) => (props.kind === 'age' ? String(v) : compact(v))
  const ci = props.x.reduce((best, v, i) => (Math.abs(v - props.current) < Math.abs(props.x[best] - props.current) ? i : best), 0)
  return {
    ...baseOption.value,
    grid: { ...baseOption.value.grid, top: 24 },
    tooltip: {
      ...baseOption.value.tooltip,
      formatter: (params: { dataIndex: number }[]) => {
        const i = params[0]?.dataIndex ?? 0
        const what = props.kind === 'age' ? `Retire at ${props.x[i]}` : `Spend ${money(props.x[i])}/yr`
        return `<strong>${what}</strong><br/>Chance of success: ${percent(props.y[i], 0)}`
      },
    },
    xAxis: {
      type: 'category' as const, data: props.x.map(label), boundaryGap: false,
      name: props.kind === 'age' ? 'Retirement age' : 'Retirement spending (today\'s $)', nameLocation: 'middle' as const, nameGap: 26,
      nameTextStyle: { color: mutedTextColor.value, fontSize: 11 },
      axisLine: { lineStyle: { color: axisLineColor.value } }, axisTick: { show: false }, axisLabel: { ...mobileAxis() },
    },
    yAxis: {
      type: 'value' as const, min: 0, max: 1,
      axisLabel: { ...mobileAxis(), formatter: (v: number) => percent(v, 0) },
      splitLine: { lineStyle: { color: splitLineColor.value } },
    },
    series: [{
      type: 'line' as const, data: props.y, symbol: 'circle', symbolSize: 6, showSymbol: false,
      lineStyle: { width: 2, color: COLORS[0] }, itemStyle: { color: COLORS[0] },
      markLine: {
        silent: true, symbol: 'none',
        lineStyle: { color: mutedTextColor.value, type: 'solid' as const, width: 1 },
        label: { formatter: `Target ${percent(props.target, 0)}`, color: mutedTextColor.value, fontSize: 10, position: 'insideEndTop' as const },
        data: [{ yAxis: props.target }],
      },
      markPoint: {
        symbol: 'circle', symbolSize: 10,
        itemStyle: { color: COLORS[0], borderColor: '#fff', borderWidth: 2 },
        label: { show: true, position: 'top' as const, formatter: `Plan ${percent(props.y[ci], 0)}`, color: mutedTextColor.value, fontSize: 10 },
        data: [{ coord: [ci, props.y[ci]] }],
      },
    }],
  }
})
</script>

<template>
  <v-chart :option="option" autoresize :style="{ height: `${height}px` }" />
</template>
