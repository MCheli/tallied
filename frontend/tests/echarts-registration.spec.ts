import { describe, expect, it } from 'vitest'
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join } from 'node:path'

// ECharts is tree-shaken: a series type that is used but not registered with use([...]) blanks the whole
// chart at runtime (2026-10-30: scatter markers blanked every vehicle chart). Typecheck and the dev server
// cannot see it, so check the source.
const SERIES = { line: 'LineChart', bar: 'BarChart', pie: 'PieChart', scatter: 'ScatterChart', effectScatter: 'EffectScatterChart', heatmap: 'HeatmapChart', gauge: 'GaugeChart', radar: 'RadarChart', boxplot: 'BoxplotChart', candlestick: 'CandlestickChart', sankey: 'SankeyChart', treemap: 'TreemapChart', funnel: 'FunnelChart', custom: 'CustomChart' } as const

function files(dir: string): string[] {
  return readdirSync(dir).flatMap(name => {
    const p = join(dir, name)
    return statSync(p).isDirectory() ? files(p) : /\.(vue|ts)$/.test(name) ? [p] : []
  })
}

describe('echarts registration', () => {
  it('every series type a component uses is registered in that component', () => {
    const problems: string[] = []
    for (const file of files(join(__dirname, '../src'))) {
      const src = readFileSync(file, 'utf8')
      if (!src.includes("from 'echarts/charts'")) continue
      for (const [type, chart] of Object.entries(SERIES)) {
        const used = new RegExp(`type:\\s*['"]${type}['"]`).test(src)
        if (used && !new RegExp(`\\b${chart}\\b`).test(src)) problems.push(`${file.split('/src/')[1]} uses '${type}' without ${chart}`)
      }
    }
    expect(problems).toEqual([])
  })
})
