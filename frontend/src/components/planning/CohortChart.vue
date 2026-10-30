<script setup lang="ts">
/**
 * CohortChart — the plan retired into every complete historical sequence since 1928.
 * Bars up: money left at the plan-to age (today's $), status "lasted". Short bars below the
 * axis: the money ran out (status "ran out"); the tooltip gives the age.
 */
import { computed } from 'vue'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { BarChart } from 'echarts/charts'
import { GridComponent, LegendComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { useChartDefaults } from '../../composables/useChartDefaults'
import { useFormatters } from '../../composables/useFormatters'
import type { Cohort } from '../../types'

use([BarChart, GridComponent, LegendComponent, TooltipComponent, CanvasRenderer])

const props = defineProps<{ cohorts: Cohort[]; planToAge: number }>()
const { baseOption, axisLineColor, splitLineColor, mobileAxis, mobileLegend, statusColors } = useChartDefaults()
const { compact, money } = useFormatters()

const option = computed(() => {
  const max = Math.max(1, ...props.cohorts.map((c) => c.end_real))
  const stub = -max * 0.06
  return {
    ...baseOption.value,
    grid: { ...baseOption.value.grid, bottom: 40 },
    legend: { ...mobileLegend(), data: ['Lasted', 'Ran out'] },
    tooltip: {
      ...baseOption.value.tooltip, trigger: 'item' as const,
      formatter: (p: { dataIndex: number }) => {
        const c = props.cohorts[p.dataIndex]
        return c.success
          ? `<strong>Retire into ${c.start_year}</strong><br/>Lasted to ${props.planToAge}<br/>Left at the end: ${money(c.end_real)}<br/>Lowest along the way: ${money(c.lowest_real)}`
          : `<strong>Retire into ${c.start_year}</strong><br/>Ran out at age ${c.failure_age ?? '—'}`
      },
    },
    xAxis: {
      type: 'category' as const, data: props.cohorts.map((c) => String(c.start_year)),
      axisLine: { lineStyle: { color: axisLineColor.value } }, axisTick: { show: false }, axisLabel: { ...mobileAxis() },
    },
    yAxis: {
      type: 'value' as const,
      axisLabel: { ...mobileAxis(), formatter: (v: number) => (v < 0 ? '' : compact(v)) },
      splitLine: { lineStyle: { color: splitLineColor.value } },
    },
    series: [
      { name: 'Lasted', type: 'bar' as const, stack: 'c', barCategoryGap: '20%',
        itemStyle: { color: statusColors.value.good, borderRadius: [4, 4, 0, 0] },
        data: props.cohorts.map((c) => (c.success ? c.end_real : null)) },
      { name: 'Ran out', type: 'bar' as const, stack: 'c',
        itemStyle: { color: statusColors.value.critical, borderRadius: [0, 0, 4, 4] },
        data: props.cohorts.map((c) => (c.success ? null : stub)) },
    ],
  }
})
</script>

<template>
  <v-chart :option="option" autoresize style="height: 260px" />
</template>
