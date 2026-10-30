<script setup lang="ts">
import { computed } from 'vue'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { LineChart } from 'echarts/charts'
import { GridComponent, LegendComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { useChartDefaults } from '../../composables/useChartDefaults'
import { useFormatters } from '../../composables/useFormatters'
import type { MonthPace } from '../../types'

use([LineChart, GridComponent, LegendComponent, TooltipComponent, CanvasRenderer])

const props = defineProps<{ data: MonthPace }>()
const { baseOption, isDark, isMobile, splitLineColor, mobileAxis, mobileLegend } = useChartDefaults()
const { currency, compact, monthYear } = useFormatters()

const thisLabel = computed(() => monthYear(`${props.data.month}-01`))
const lastLabel = computed(() => monthYear(`${props.data.last_month}-01`))

// compact() rounds $1,200 and $1,400 both to "$1K"; the axis needs one decimal in thousands.
const axisMoney = (v: number) => (Math.abs(v) < 1000 ? `$${v}` : `$${(v / 1000).toFixed(Number.isInteger(v / 1000) ? 0 : 1)}K`)

const option = computed(() => {
  const accent = '#6366f1'
  const grey = isDark.value ? '#4b5563' : '#d1d5db'
  const days = Array.from({ length: props.data.days_in_month }, (_, i) => String(i + 1))
  const thisSeries = props.data.this_month
  return {
    ...baseOption.value,
    tooltip: {
      ...baseOption.value.tooltip,
      formatter: (params: unknown) => {
        const list = (Array.isArray(params) ? params : [params]) as { seriesName: string; value: number | undefined; marker: string; axisValue: string }[]
        if (!list.length) return ''
        let html = `<strong>Day ${list[0].axisValue}</strong>`
        for (const p of list) if (p.value != null) html += `<br/>${p.marker} ${p.seriesName}: ${currency(p.value)}`
        return html
      },
    },
    legend: { ...mobileLegend(), data: [thisLabel.value, lastLabel.value] },
    grid: { ...baseOption.value.grid, top: 24, bottom: isMobile.value ? 28 : 36 },
    xAxis: {
      type: 'category' as const,
      data: days,
      boundaryGap: false,
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { ...mobileAxis(), interval: isMobile.value ? 6 : 4 },
    },
    yAxis: {
      type: 'value' as const,
      axisLabel: { ...mobileAxis(), formatter: axisMoney },
      splitLine: { lineStyle: { color: splitLineColor.value } },
    },
    series: [
      {
        name: lastLabel.value,
        type: 'line' as const,
        data: props.data.last_month_series,
        showSymbol: false,
        lineStyle: { width: 2.5, color: grey },
        itemStyle: { color: grey },
        z: 1,
      },
      {
        name: thisLabel.value,
        type: 'line' as const,
        data: thisSeries,
        showSymbol: false,
        lineStyle: { width: 3, color: accent },
        itemStyle: { color: accent },
        areaStyle: { color: accent, opacity: isDark.value ? 0.18 : 0.12 },
        endLabel: {
          show: thisSeries.length > 0,
          formatter: () => compact(props.data.this_total),
          color: accent,
          fontWeight: 600,
        },
        z: 2,
      },
    ],
  }
})
</script>

<template>
  <VChart :option="option" autoresize :style="{ height: isMobile ? '240px' : '280px' }" />
</template>
