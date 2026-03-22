<script setup lang="ts">
import { computed } from 'vue'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { LineChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent, MarkLineComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { useChartDefaults } from '../../composables/useChartDefaults'
import { useFormatters } from '../../composables/useFormatters'
import type { ProjectionRow } from '../../types'

use([LineChart, GridComponent, TooltipComponent, LegendComponent, MarkLineComponent, CanvasRenderer])

const props = defineProps<{ projections: ProjectionRow[] }>()
const { baseOption } = useChartDefaults()
const { currency } = useFormatters()

const buckets = [
  { key: 'cash', label: 'Cash', color: '#3b82f6' },
  { key: 'investments', label: 'Investments', color: '#22c55e' },
  { key: 'company_stock', label: 'Company Stock', color: '#06b6d4' },
  { key: 'home_equity', label: 'Home Equity', color: '#f59e0b' },
  { key: 'retirement_bal', label: 'Retirement', color: '#8b5cf6' },
]

const retirementAge = computed(() => {
  const row = props.projections.find(r => r.phase === 'retired')
  return row?.age ?? null
})

const option = computed(() => {
  const ages = props.projections.map(r => r.age)

  const series = buckets.map((b, i) => ({
    name: b.label,
    type: 'line' as const,
    stack: 'total',
    data: props.projections.map(r => (r as any)[b.key] as number),
    smooth: true,
    symbol: 'none',
    lineStyle: { width: 1, color: b.color },
    itemStyle: { color: b.color },
    areaStyle: { opacity: 0.35 },
    ...(i === 0 && retirementAge.value
      ? {
          markLine: {
            silent: true,
            data: [
              {
                xAxis: retirementAge.value,
                label: {
                  formatter: 'Retirement',
                  color: baseOption.value.textStyle.color,
                  fontSize: 11,
                },
                lineStyle: { type: 'dashed' as const, color: '#ef4444', width: 1.5 },
              },
            ],
          },
        }
      : {}),
  }))

  return {
    ...baseOption.value,
    tooltip: {
      ...baseOption.value.tooltip,
      trigger: 'axis' as const,
      formatter: (params: any) => {
        if (!Array.isArray(params) || params.length === 0) return ''
        const idx = params[0].dataIndex
        const row = props.projections[idx]
        let html = `<strong>Age ${row.age} (${row.year})</strong> - ${row.phase}`
        let total = 0
        for (const p of params) {
          html += `<br/>${p.marker} ${p.seriesName}: ${currency(p.value)}`
          total += p.value
        }
        html += `<br/><strong>Net Worth: ${currency(total)}</strong>`
        return html
      },
    },
    legend: {
      bottom: 0,
      textStyle: { color: baseOption.value.textStyle.color },
    },
    grid: { left: 70, right: 20, top: 20, bottom: 50 },
    xAxis: {
      type: 'category' as const,
      data: ages,
      name: 'Age',
      nameLocation: 'middle' as const,
      nameGap: 30,
      axisLabel: { color: baseOption.value.textStyle.color },
    },
    yAxis: {
      type: 'value' as const,
      axisLabel: {
        color: baseOption.value.textStyle.color,
        formatter: (v: number) => {
          if (Math.abs(v) >= 1_000_000) return `$${(v / 1_000_000).toFixed(1)}M`
          return `$${(v / 1_000).toFixed(0)}K`
        },
      },
      splitLine: { lineStyle: { color: '#e5e7eb33' } },
    },
    series,
  }
})
</script>

<template>
  <v-chart :option="option" autoresize style="height: 420px" />
</template>
