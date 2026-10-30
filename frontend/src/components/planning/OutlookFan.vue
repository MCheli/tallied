<script setup lang="ts">
/**
 * OutlookFan — percentile bands of a Monte Carlo quantity by age (today's dollars).
 * Outer band 10th–90th percentile, inner band 25th–75th, line = median. One hue (magnitude).
 * Props: bands, ages, retirementAge (vertical rule), from (first index to draw), height.
 */
import { computed } from 'vue'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { LineChart } from 'echarts/charts'
import { GridComponent, LegendComponent, MarkLineComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { useChartDefaults } from '../../composables/useChartDefaults'
import { useFormatters } from '../../composables/useFormatters'
import { bandSeries, milestoneMarks } from '../../composables/usePlanningOutlook'
import type { Bands, Milestone } from '../../types'

use([LineChart, GridComponent, LegendComponent, MarkLineComponent, TooltipComponent, CanvasRenderer])

const props = withDefaults(defineProps<{
  bands: Bands
  ages: number[]
  retirementAge?: number | null
  from?: number
  height?: number
  medianLabel?: string
  milestones?: Milestone[]
  overlay?: { name: string; data: number[] } | null
}>(), { retirementAge: null, from: 0, height: 340, medianLabel: 'Median', milestones: () => [], overlay: null })

const { baseOption, axisLineColor, splitLineColor, mutedTextColor, mobileAxis, mobileLegend, bandColor, isMobile, bucketColors } = useChartDefaults()
const { compact, money } = useFormatters()

const option = computed(() => {
  const cut = (a: number[]) => a.slice(props.from)
  const sliced: Bands = { p10: cut(props.bands.p10), p25: cut(props.bands.p25), p50: cut(props.bands.p50), p75: cut(props.bands.p75), p90: cut(props.bands.p90) }
  const s = bandSeries(sliced)
  const ages = props.ages.slice(props.from)
  const marks = milestoneMarks(props.milestones, ages)
  const ri = props.retirementAge != null ? ages.indexOf(props.retirementAge) : -1
  const stackBase = (name: string, stack: string, data: number[]) => ({
    name, type: 'line' as const, stack, data, symbol: 'none', lineStyle: { opacity: 0 }, silent: true,
    tooltip: { show: false },
  })
  return {
    ...baseOption.value,
    grid: { ...baseOption.value.grid, bottom: isMobile.value ? 36 : 40 },
    legend: { ...mobileLegend(), data: ['10–90%', '25–75%', props.medianLabel, ...(props.overlay ? [props.overlay.name] : [])] },
    tooltip: {
      ...baseOption.value.tooltip,
      trigger: 'axis' as const,
      formatter: (params: { dataIndex: number }[]) => {
        const i = params[0]?.dataIndex ?? 0
        const extra = props.overlay ? `<br/>${props.overlay.name}: ${money(props.overlay.data.slice(props.from)[i])}` : ''
        const mark = marks.filter((m) => m.index === i).map((m) => `<br/><em>${m.title}</em>`).join('')
        return `<strong>Age ${ages[i]}</strong>${mark}<br/>`
          + `90th percentile: ${money(sliced.p90[i])}<br/>75th: ${money(sliced.p75[i])}<br/>`
          + `<strong>Median: ${money(sliced.p50[i])}</strong><br/>25th: ${money(sliced.p25[i])}<br/>10th: ${money(sliced.p10[i])}${extra}`
      },
    },
    xAxis: {
      type: 'category' as const, data: ages, boundaryGap: false,
      axisLine: { lineStyle: { color: axisLineColor.value } }, axisTick: { show: false },
      axisLabel: { ...mobileAxis() },
    },
    yAxis: {
      type: 'value' as const,
      axisLabel: { ...mobileAxis(), formatter: (v: number) => compact(v) },
      splitLine: { lineStyle: { color: splitLineColor.value } },
    },
    series: [
      stackBase('outer-base', 'outer', s.outerBase),
      { name: '10–90%', type: 'line' as const, stack: 'outer', data: s.outerWidth, symbol: 'none',
        lineStyle: { opacity: 0 }, areaStyle: { color: bandColor, opacity: 0.14 }, itemStyle: { color: bandColor, opacity: 0.3 } },
      stackBase('inner-base', 'inner', s.innerBase),
      { name: '25–75%', type: 'line' as const, stack: 'inner', data: s.innerWidth, symbol: 'none',
        lineStyle: { opacity: 0 }, areaStyle: { color: bandColor, opacity: 0.28 }, itemStyle: { color: bandColor, opacity: 0.6 } },
      {
        name: props.medianLabel, type: 'line' as const, data: s.median, symbol: 'none',
        lineStyle: { width: 2, color: bandColor }, itemStyle: { color: bandColor },
        markLine: ri >= 0 || marks.length ? {
          silent: true, symbol: 'none',
          lineStyle: { color: mutedTextColor.value, type: 'solid' as const, width: 1, opacity: 0.5 },
          label: { color: mutedTextColor.value, fontSize: 9, position: 'insideEndTop' as const,
                   formatter: (p: { data: { name: string } }) => p.data.name },
          data: [
            ...(ri >= 0 ? [{ xAxis: ri, name: `Retire ${props.retirementAge}`, lineStyle: { opacity: 1, width: 1.5 } }] : []),
            ...marks.filter((m) => m.index !== ri).map((m) => ({ xAxis: m.index, name: m.label })),
          ],
        } : undefined,
      },
      ...(props.overlay ? [{
        name: props.overlay.name, type: 'line' as const, data: props.overlay.data.slice(props.from), symbol: 'none',
        lineStyle: { width: 1.5, color: bucketColors.value[4] }, itemStyle: { color: bucketColors.value[4] },
      }] : []),
    ],
  }
})
</script>

<template>
  <v-chart :option="option" autoresize :style="{ height: `${height}px` }" />
</template>
