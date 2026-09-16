<script setup lang="ts">
import { computed, ref, onMounted, onBeforeUnmount, watch } from 'vue'
import { scaleTime, scaleLinear } from 'd3-scale'
import { line } from 'd3-shape'
import { bisector } from 'd3-array'
import type { StatisticsSeries, StatisticsEntity } from '#shared/contracts'
import { statisticsTypes, statisticsDate } from '~/utils/statistics'
import { metric } from '~/utils/presentation'
import AppIcon from '~/components/AppIcon.vue'
const props = defineProps<{
  series: StatisticsSeries[]
  fromAt: string
  toAt: string
  timezone: string
  selectedTypes: StatisticsEntity[]
  highlighted: StatisticsEntity | null
}>()
defineEmits<{ toggle: [type: StatisticsEntity]; highlight: [type: StatisticsEntity | null] }>()
const host = ref<HTMLElement | null>(null)
const width = ref(900)
const active = ref<number | null>(null)
const height = 234,
  left = 43,
  right = 14,
  top = 18,
  bottom = 34
let observer: ResizeObserver | undefined
onMounted(() => {
  observer = new ResizeObserver(([entry]) => {
    if (entry) width.value = Math.max(260, entry.contentRect.width)
  })
  if (host.value) observer.observe(host.value)
})
onBeforeUnmount(() => observer?.disconnect())
watch(
  () => props.series,
  () => {
    active.value = null
  },
)
const visible = computed(() =>
  props.series.filter((s) => props.selectedTypes.includes(s.entity_type)),
)
const points = computed(() => props.series[0]?.points ?? [])
const x = computed(() =>
  scaleTime()
    .domain([new Date(props.fromAt), new Date(props.toAt)])
    .range([left, width.value - right]),
)
const y = computed(() =>
  scaleLinear()
    .domain([0, Math.max(1, ...visible.value.flatMap((s) => s.points.map((p) => p.count)))])
    .nice()
    .range([height - bottom, top]),
)
const yTicks = computed(() => y.value.ticks(5).filter(Number.isInteger))
const xTicks = computed(() => x.value.ticks(Math.max(2, Math.floor(width.value / 145))))
const paths = computed(() =>
  visible.value.map((s) => ({
    ...s,
    path:
      line<StatisticsSeries['points'][number]>()
        .x((p) => x.value(new Date(p.start_at)))
        .y((p) => y.value(p.count))(s.points) ?? '',
  })),
)
const point = computed(() => (active.value === null ? null : points.value[active.value]))
const tooltipX = computed(() =>
  point.value
    ? Math.max(4, Math.min(width.value - 224, x.value(new Date(point.value.start_at)) + 18))
    : 0,
)
const tickMode = computed(() =>
  Date.parse(props.toAt) - Date.parse(props.fromAt) <= 86400000 ? 'time' : 'day',
)
function hover(event: PointerEvent) {
  const bounds = (event.currentTarget as SVGElement).getBoundingClientRect()
  const date = x.value.invert(((event.clientX - bounds.left) * width.value) / bounds.width)
  active.value = bisector<StatisticsSeries['points'][number], number>((p) =>
    Date.parse(p.start_at),
  ).center(points.value, date.getTime())
}
function keyboard(event: KeyboardEvent) {
  if (event.key === 'Escape') {
    active.value = null
    return
  }
  if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return
  event.preventDefault()
  active.value =
    event.key === 'Home'
      ? 0
      : event.key === 'End'
        ? points.value.length - 1
        : Math.max(
            0,
            Math.min(
              points.value.length - 1,
              (active.value ?? 0) + (event.key === 'ArrowLeft' ? -1 : 1),
            ),
          )
}
</script>
<template>
  <section class="statistics-panel statistics-timeline" aria-labelledby="timeline-title">
    <div class="statistics-chart-heading">
      <h3 id="timeline-title">Neue Entitäten im Zeitverlauf</h3>
      <span
        title="Anzahl neu angelegter Datensätze pro Zeitintervall. Leere Intervalle zählen als null."
        ><AppIcon name="info" :size="15"
      /></span>
    </div>
    <p id="timeline-help" class="sr-only">
      Mit den Pfeiltasten Zeitintervalle erkunden. Escape schließt die Werteanzeige. Serien über die
      Legende auswählen.
    </p>
    <div ref="host" class="statistics-chart-surface">
      <svg
        :viewBox="`0 0 ${width} ${height}`"
        :height="height"
        role="img"
        aria-label="Neue Entitäten im Zeitverlauf"
        tabindex="0"
        aria-describedby="timeline-help"
        @pointermove="hover"
        @pointerdown="hover"
        @pointerleave="active = null"
        @keydown="keyboard"
      >
        <g class="statistics-y-axis">
          <g v-for="tick in yTicks" :key="tick">
            <line
              :x1="left"
              :x2="width - right"
              :y1="y(tick)"
              :y2="y(tick)"
              class="statistics-gridline"
            />
            <text :x="left - 9" :y="y(tick) + 4" text-anchor="end">{{ tick }}</text>
          </g>
        </g>
        <g class="statistics-x-axis">
          <g v-for="tick in xTicks" :key="tick.getTime()">
            <line
              :x1="x(tick)"
              :x2="x(tick)"
              :y1="top"
              :y2="height - bottom"
              class="statistics-gridline"
            />
            <text
              :x="Math.max(35, Math.min(width - 40, x(tick)))"
              :y="height - 12"
              text-anchor="middle"
            >
              {{ statisticsDate(tick, timezone, tickMode) }}
            </text>
          </g>
        </g>
        <text
          :transform="`translate(11,${height / 2}) rotate(-90)`"
          text-anchor="middle"
          class="statistics-axis-label"
        >
          Anzahl
        </text>
        <path
          v-for="entry in paths"
          :key="entry.entity_type"
          class="statistics-series"
          :data-entity="entry.entity_type"
          :d="entry.path"
          fill="none"
          :stroke="statisticsTypes[entry.entity_type].color"
          :stroke-width="highlighted === entry.entity_type ? 2.5 : 1.6"
          :opacity="highlighted && highlighted !== entry.entity_type ? 0.22 : 1"
          vector-effect="non-scaling-stroke"
        />
        <g v-if="point && active !== null && visible.length">
          <line
            :x1="x(new Date(point.start_at))"
            :x2="x(new Date(point.start_at))"
            :y1="top"
            :y2="height - bottom"
            stroke="#64748b"
            stroke-dasharray="5 4"
          />
          <circle
            v-for="entry in visible"
            :key="entry.entity_type"
            :cx="x(new Date(point.start_at))"
            :cy="y(entry.points[active]!.count)"
            r="4"
            fill="white"
            :stroke="statisticsTypes[entry.entity_type].color"
            stroke-width="2"
          />
        </g>
      </svg>
      <div
        v-if="point && active !== null && visible.length"
        class="statistics-tooltip"
        :style="{ left: `${tooltipX}px` }"
        role="status"
      >
        <strong
          >{{ statisticsDate(point.start_at, timezone, 'day') }} ·
          {{ statisticsDate(point.start_at, timezone, 'time') }}</strong
        >
        <small>bis {{ statisticsDate(point.end_at, timezone, 'time') }}</small>
        <div v-for="entry in visible" :key="entry.entity_type">
          <span
            class="statistics-dot"
            :style="{ background: statisticsTypes[entry.entity_type].color }"
          /><span>{{ statisticsTypes[entry.entity_type].label }}</span
          ><b>{{ metric(entry.points[active]!.count) }}</b>
        </div>
      </div>
      <p v-if="!visible.length" class="statistics-no-series">Wähle mindestens eine Serie aus.</p>
    </div>
    <div class="statistics-legend" aria-label="Serien auswählen">
      <button
        v-for="entry in series"
        :key="entry.entity_type"
        :aria-pressed="selectedTypes.includes(entry.entity_type)"
        :class="{ inactive: !selectedTypes.includes(entry.entity_type) }"
        @click="$emit('toggle', entry.entity_type)"
        @pointerenter="$emit('highlight', entry.entity_type)"
        @pointerleave="$emit('highlight', null)"
        @focus="$emit('highlight', entry.entity_type)"
        @blur="$emit('highlight', null)"
      >
        <span
          class="statistics-dot"
          :style="{ background: statisticsTypes[entry.entity_type].color }"
        />{{ statisticsTypes[entry.entity_type].label }}
      </button>
    </div>
  </section>
</template>
