<script setup lang="ts">
import { computed } from 'vue'
import { arc, pie } from 'd3-shape'
import type { StatisticsSeries } from '#shared/contracts'
import { statisticsTypes } from '~/utils/statistics'
import { metric } from '~/utils/presentation'
const props = defineProps<{ series: StatisticsSeries[] }>()
const sorted = computed(() => [...props.series].sort((a, b) => b.total - a.total))
const total = computed(() => props.series.reduce((sum, s) => sum + s.total, 0))
const slices = computed(() =>
  pie<StatisticsSeries>()
    .sort(null)
    .value((s) => s.total)(sorted.value),
)
const shape = arc<(typeof slices.value)[number]>().innerRadius(63).outerRadius(98).padAngle(0.01)
</script>
<template>
  <section class="statistics-panel statistics-distribution" aria-labelledby="distribution-title">
    <h3 id="distribution-title">Verteilung nach Entitätstyp</h3>
    <div v-if="total" class="statistics-distribution-body">
      <svg viewBox="0 0 210 210" role="img" aria-label="Anteile der neu angelegten Entitäten">
        <g transform="translate(105,105)">
          <path
            v-for="slice in slices"
            :key="slice.data.entity_type"
            :d="shape(slice) ?? ''"
            :fill="statisticsTypes[slice.data.entity_type].color"
          >
            <title>
              {{ statisticsTypes[slice.data.entity_type].label }}: {{ slice.data.total }}
            </title>
          </path>
          <text text-anchor="middle" y="0" class="donut-total">{{ metric(total) }}</text>
          <text text-anchor="middle" y="21" class="donut-caption">neue Entitäten</text>
        </g>
      </svg>
      <ul>
        <li v-for="seriesItem in sorted" :key="seriesItem.entity_type">
          <span
            class="statistics-dot"
            :style="{ background: statisticsTypes[seriesItem.entity_type].color }"
          />
          <span>{{ statisticsTypes[seriesItem.entity_type].label }}</span>
          <strong>{{ metric(seriesItem.total) }}</strong
          ><span class="statistics-percentage"
            >({{ Math.round((seriesItem.total / total) * 100) }} %)</span
          >
        </li>
      </ul>
    </div>
    <p v-else class="statistics-empty">Keine neuen Entitäten in diesem Zeitraum.</p>
  </section>
</template>
