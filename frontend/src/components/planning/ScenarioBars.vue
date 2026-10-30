<script setup lang="ts">
/** ScenarioBars — chance of success under each macro scenario, one colour, target as a rule. */
import { computed } from 'vue'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { BarChart } from 'echarts/charts'
import { GridComponent, MarkLineComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { useChartDefaults } from '../../composables/useChartDefaults'
import { useFormatters } from '../../composables/useFormatters'
import type { ScenarioResult } from '../../types'

use([BarChart, GridComponent, MarkLineComponent, TooltipComponent, CanvasRenderer])

const props = defineProps<{ scenarios: ScenarioResult[]; target: number; selected: string }>()
const emit = defineEmits<{ (e: 'select', key: string): void }>()
const { baseOption, splitLineColor, mutedTextColor, mobileAxis, COLORS, isMobile } = useChartDefaults()
const { percent, money } = useFormatters()

const rows = computed(() => [...props.scenarios].reverse())
const option = computed(() => ({
  ...baseOption.value,
  grid: { ...baseOption.value.grid, left: 8, right: 44, top: 28 },
  tooltip: {
    ...baseOption.value.tooltip, trigger: 'item' as const,
    formatter: (p: { dataIndex: number }) => {
      const s = rows.value[p.dataIndex]
      return `<strong>${s.label}</strong><br/>${s.description}<br/>Chance of success: ${percent(s.success_rate, 0)}`
        + `<br/>Median at the end: ${money(s.median_end)}<br/>Bad case (10th pct) at the end: ${money(s.p10_end)}`
        + '<br/><em>Click to draw this scenario above</em>'
    },
    extraCssText: 'max-width: 300px; white-space: normal;',
  },
  xAxis: {
    type: 'value' as const, min: 0, max: 1, interval: 0.5,
    axisLabel: { ...mobileAxis(), formatter: (v: number) => percent(v, 0) },
    splitLine: { lineStyle: { color: splitLineColor.value } },
  },
  yAxis: {
    type: 'category' as const, data: rows.value.map((s) => s.label),
    axisTick: { show: false }, axisLine: { show: false },
    axisLabel: { ...mobileAxis(), width: isMobile.value ? 120 : 210, overflow: 'truncate' as const },
  },
  series: [{
    type: 'bar' as const, barWidth: 14,
    data: rows.value.map((s) => ({
      value: s.success_rate,
      itemStyle: { color: COLORS[0], opacity: s.key === props.selected ? 1 : 0.55, borderRadius: [0, 4, 4, 0] },
    })),
    label: { show: true, position: 'right' as const, formatter: (p: { value: number }) => percent(p.value, 0), color: mutedTextColor.value, fontSize: 11 },
    markLine: {
      silent: true, symbol: 'none', lineStyle: { color: mutedTextColor.value, type: 'solid' as const, width: 1 },
      label: { formatter: `Target ${percent(props.target, 0)}`, color: mutedTextColor.value, fontSize: 10 },
      data: [{ xAxis: props.target }],
    },
  }],
}))

function onClick(p: { dataIndex: number }) {
  emit('select', rows.value[p.dataIndex].key)
}
</script>

<template>
  <v-chart :option="option" autoresize :style="{ height: `${Math.max(220, scenarios.length * 34 + 40)}px` }" @click="onClick" />
</template>
