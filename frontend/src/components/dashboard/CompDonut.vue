<script setup lang="ts">
import { computed } from 'vue'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { PieChart } from 'echarts/charts'
import { TooltipComponent, LegendComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { useChartDefaults } from '../../composables/useChartDefaults'
import { useFormatters } from '../../composables/useFormatters'

use([PieChart, TooltipComponent, LegendComponent, CanvasRenderer])

const props = defineProps<{ salary: number; rsu: number }>()
const { baseOption, isMobile, mobileLegend } = useChartDefaults()
const { currency, compact } = useFormatters()

const option = computed(() => ({
  ...baseOption.value,
  tooltip: {
    ...baseOption.value.tooltip,
    trigger: 'item' as const,
    formatter: (p: { name: string; value: number; percent: number }) => `${p.name}: ${currency(p.value)} (${p.percent}%)`,
  },
  legend: mobileLegend(),
  series: [
    {
      type: 'pie',
      radius: ['50%', '72%'],
      center: ['50%', '46%'],
      avoidLabelOverlap: false,
      label: {
        show: true,
        position: 'center',
        formatter: () => compact(props.salary + props.rsu),
        fontSize: isMobile.value ? 16 : 18,
        fontWeight: 'bold' as const,
        color: baseOption.value.textStyle.color,
      },
      emphasis: { label: { show: true, fontSize: 20, fontWeight: 'bold' as const } },
      data: [
        { value: props.salary, name: 'Salary', itemStyle: { color: '#3b82f6' } },
        { value: props.rsu, name: 'RSU Income', itemStyle: { color: '#22c55e' } },
      ],
    },
  ],
}))
</script>

<template>
  <v-chart :option="option" autoresize :style="{ height: isMobile ? '260px' : '320px' }" />
</template>
