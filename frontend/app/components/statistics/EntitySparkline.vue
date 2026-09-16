<script setup lang="ts">
import { computed } from 'vue'
import { scaleLinear, scaleTime } from 'd3-scale'
import { line, area } from 'd3-shape'
import type { StatisticsSeries } from '#shared/contracts'
const props = defineProps<{ points: StatisticsSeries['points']; color: string }>()
const paths = computed(() => {
  const points = props.points
  if (!points.length) return { line: '', area: '' }
  const x = scaleTime()
    .domain([new Date(points[0]!.start_at), new Date(points.at(-1)!.end_at)])
    .range([0, 160])
  const y = scaleLinear()
    .domain([0, Math.max(1, ...points.map((p) => p.count))])
    .range([25, 2])
  return {
    line:
      line<StatisticsSeries['points'][number]>()
        .x((p) => x(new Date(p.start_at)))
        .y((p) => y(p.count))(points) ?? '',
    area:
      area<StatisticsSeries['points'][number]>()
        .x((p) => x(new Date(p.start_at)))
        .y0(28)
        .y1((p) => y(p.count))(points) ?? '',
  }
})
</script>
<template>
  <svg
    viewBox="0 0 160 30"
    preserveAspectRatio="none"
    aria-hidden="true"
    class="statistics-sparkline"
  >
    <path :d="paths.area" :fill="color" fill-opacity="0.08" />
    <path
      :d="paths.line"
      :stroke="color"
      fill="none"
      stroke-width="1.5"
      vector-effect="non-scaling-stroke"
    />
  </svg>
</template>
