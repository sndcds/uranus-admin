<script setup lang="ts">
import EmptyState from '~/components/EmptyState.vue'
import SectionHeader from '~/components/SectionHeader.vue'
import { computed } from 'vue'
import { arc, pie } from 'd3-shape'
import type { StatisticsSeries } from '#shared/contracts'
import { statisticsTypes } from '~/utils/statistics'
import { metric } from '~/utils/presentation'
const props = defineProps<{ showScope?: boolean; series: StatisticsSeries[] }>()
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
  <section
    class="statistics-panel statistics-distribution section-subtle p-3"
    aria-labelledby="distribution-title"
  >
    <SectionHeader title-id="distribution-title" title="Verteilung nach Entitätstyp" />
    <p v-if="showScope" class="mt-2 text-xs text-slate-600">
      Verteilung über Gebiets- und systemweite Serien.
    </p>
    <div
      v-if="total"
      class="statistics-distribution-body mt-3 flex flex-col items-center gap-4 sm:flex-row"
    >
      <svg
        class="w-36 shrink-0"
        viewBox="0 0 210 210"
        role="img"
        aria-label="Anteile der neu angelegten Entitäten"
      >
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
      <ul class="statistics-distribution-list w-full min-w-0 flex-1">
        <li
          v-for="seriesItem in sorted"
          :key="seriesItem.entity_type"
          class="flex items-center gap-2 py-2 text-xs"
        >
          <span
            class="statistics-dot"
            :style="{ background: statisticsTypes[seriesItem.entity_type].color }"
          />
          <span
            >{{ statisticsTypes[seriesItem.entity_type].label
            }}<template v-if="showScope">
              · {{ seriesItem.scope === 'geo' ? 'Gebiet' : 'Systemweit' }}</template
            ></span
          >
          <strong class="ml-auto font-semibold">{{ metric(seriesItem.total) }}</strong
          ><span class="statistics-percentage whitespace-nowrap text-xs text-slate-500"
            >({{ Math.round((seriesItem.total / total) * 100) }} %)</span
          >
        </li>
      </ul>
    </div>
    <EmptyState v-else compact message="Keine neuen Entitäten in diesem Zeitraum." />
  </section>
</template>
