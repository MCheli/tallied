<script setup lang="ts">
import { computed } from 'vue'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { LineChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent, MarkLineComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { useChartDefaults } from '../../composables/useChartDefaults'
import { useFormatters } from '../../composables/useFormatters'
import type { PlanResponse } from '../../types'

use([LineChart, GridComponent, TooltipComponent, LegendComponent, MarkLineComponent, CanvasRenderer])

const props = defineProps<{ plans: PlanResponse[] }>()
const { baseOption, COLORS } = useChartDefaults()
const { currency } = useFormatters()

const retirementAge = computed(() => {
  if (props.plans.length === 0) return null
  const row = props.plans[0].projections.find(r => r.phase === 'retired')
  return row?.age ?? null
})

const option = computed(() => {
  // Collect all unique ages across plans
  const allAges = new Set<number>()
  for (const plan of props.plans) {
    for (const row of plan.projections) {
      allAges.add(row.age)
    }
  }
  const ages = Array.from(allAges).sort((a, b) => a - b)

  const series = props.plans.map((plan, i) => {
    const ageMap = new Map(plan.projections.map(r => [r.age, r.net_worth]))
    return {
      name: plan.name,
      type: 'line' as const,
      data: ages.map(age => ageMap.get(age) ?? null),
      smooth: true,
      symbol: 'none',
      lineStyle: { width: 2, color: COLORS[i % COLORS.length] },
      itemStyle: { color: COLORS[i % COLORS.length] },
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
    }
  })

  return {
    ...baseOption.value,
    tooltip: {
      ...baseOption.value.tooltip,
      trigger: 'axis' as const,
      formatter: (params: any) => {
        if (!Array.isArray(params) || params.length === 0) return ''
        let html = `<strong>Age ${params[0].name}</strong>`
        for (const p of params) {
          if (p.value != null) {
            html += `<br/>${p.marker} ${p.seriesName}: ${currency(p.value)}`
          }
        }
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
