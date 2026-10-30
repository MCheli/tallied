<script setup lang="ts">
/**
 * LeverTornado — how far each lever moves the chance of success when set lower or higher
 * (change in percentage points from ``base``). Rows arrive sorted by swing, largest first.
 */
import { computed } from 'vue'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { BarChart } from 'echarts/charts'
import { GridComponent, LegendComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { useChartDefaults } from '../../composables/useChartDefaults'
import { useFormatters } from '../../composables/useFormatters'
import type { TornadoRow } from '../../composables/usePlanningOutlook'

use([BarChart, GridComponent, LegendComponent, TooltipComponent, CanvasRenderer])

const props = defineProps<{ rows: TornadoRow[]; base: number }>()
const { baseOption, splitLineColor, mobileAxis, mobileLegend, bucketColors, isMobile } = useChartDefaults()
const { percent } = useFormatters()

const rev = computed(() => [...props.rows].reverse())
const option = computed(() => ({
  ...baseOption.value,
  grid: { ...baseOption.value.grid, left: 8, right: 16, top: 8, bottom: 40 },
  legend: { ...mobileLegend(), data: ['Lower setting', 'Higher setting'] },
  tooltip: {
    ...baseOption.value.tooltip, trigger: 'axis' as const, axisPointer: { type: 'shadow' as const },
    formatter: (params: { dataIndex: number }[]) => {
      const l = rev.value[params[0]?.dataIndex ?? 0]
      return `<strong>${l.label}</strong> (plan ${percent(l.base ?? props.base, 0)})`
        + `<br/>${l.lowText}: ${percent(l.low, 0)}<br/>${l.highText}: ${percent(l.high, 0)}`
    },
  },
  xAxis: {
    type: 'value' as const,
    axisLabel: { ...mobileAxis(), formatter: (v: number) => `${v > 0 ? '+' : ''}${Math.round(v * 100)}` },
    name: 'pts', nameGap: 4, splitLine: { lineStyle: { color: splitLineColor.value } },
  },
  yAxis: {
    type: 'category' as const, data: rev.value.map((l) => l.label), axisTick: { show: false }, axisLine: { show: false },
    axisLabel: { ...mobileAxis(), width: isMobile.value ? 110 : 170, overflow: 'truncate' as const },
  },
  series: [
    { name: 'Lower setting', type: 'bar' as const, barGap: '-100%', barWidth: 12,
      itemStyle: { color: bucketColors.value[1], borderRadius: 4 },
      data: rev.value.map((l) => l.low - (l.base ?? props.base)) },
    { name: 'Higher setting', type: 'bar' as const, barWidth: 12,
      itemStyle: { color: bucketColors.value[0], borderRadius: 4 },
      data: rev.value.map((l) => l.high - (l.base ?? props.base)) },
  ],
}))
</script>

<template>
  <v-chart :option="option" autoresize :style="{ height: `${Math.max(220, rows.length * 30 + 60)}px` }" />
</template>
