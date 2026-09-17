<script setup lang="ts">
import { ref, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import type { LocationQuery } from 'vue-router'
import {
  eventContentPeriodSchema,
  eventReleaseStatusSchema,
  type EventContentStatistics,
  type EventContentQuery,
} from '#shared/contracts'
import { asFailure, type ApiFailure } from '#shared/errors'
import { useFilterPreferencesStore } from '~/stores/filter-preferences'
import { eventContentPeriods } from '~/utils/periods'
import { eventStatusLabels } from '~/utils/entities'
import { metric } from '~/utils/presentation'
import { statisticsDate } from '~/utils/statistics'
import RankingBarChart from './RankingBarChart.vue'
const props = defineProps<{ query: LocationQuery }>()
const preferences = useFilterPreferencesStore()
const router = useRouter()
const { $adminApi } = useNuxtApp()
const data = ref<EventContentStatistics | null>(null),
  loading = ref(false),
  error = ref<ApiFailure | null>(null)
const period = computed(
  () => props.query.period ?? preferences.resolvePeriodForPage('eventContent'),
)
const comparing = computed(() => props.query.compare === 'previous')
const dimensions = [
  {
    key: 'categories',
    title: 'Top 10 Kategorien',
    coverage: 'Kategorie vorhanden',
    missing: 'Kategorie',
  },
  { key: 'genres', title: 'Top 10 Genres', coverage: 'Genre vorhanden', missing: 'Genre' },
  {
    key: 'event_types',
    title: 'Top 10 Event-Typen',
    coverage: 'Event-Typ vorhanden',
    missing: 'Event-Typ',
  },
] as const
const percentage = (value: number) =>
  new Intl.NumberFormat('de-DE', { maximumFractionDigits: 2 }).format(value)
let generation = 0
async function load() {
  const id = ++generation
  loading.value = true
  data.value = null
  error.value = null
  try {
    for (const key of Object.keys(props.query))
      if (!['view', 'period', 'status', 'compare'].includes(key)) throw new Error('Invalid query')
    const request: EventContentQuery = { period: eventContentPeriodSchema.parse(period.value) }
    if (props.query.status !== undefined)
      request.status = eventReleaseStatusSchema.parse(props.query.status)
    if (props.query.compare !== undefined) {
      if (props.query.compare !== 'previous') throw new Error('Invalid comparison')
      request.compare = 'previous'
    }
    const result = await $adminApi.eventContent(request)
    if (id === generation) data.value = result
  } catch (cause) {
    if (id === generation) error.value = asFailure(cause)
  } finally {
    if (id === generation) loading.value = false
  }
}
function setFilter(key: 'period' | 'status' | 'compare', value: string) {
  if (key === 'period') preferences.hydratePeriod('eventContent', value)
  void router.push({
    query: {
      ...props.query,
      view: 'event-content',
      [key]: value || undefined,
      ...(key === 'period' && value === 'all' ? { compare: undefined } : {}),
    },
  })
}
onMounted(load)
watch(() => props.query, load)
onBeforeUnmount(() => {
  generation++
})
</script>
<template>
  <div class="space-y-5">
    <div class="panel flex flex-wrap items-end gap-4 p-4" aria-label="Event-Inhalte filtern">
      <label class="min-w-0"
        ><span class="label">Zeitraum</span>
        <select
          class="input"
          :value="period"
          @change="setFilter('period', ($event.target as HTMLSelectElement).value)"
        >
          <option v-for="(label, value) in eventContentPeriods" :key="value" :value="value">
            {{ label }}
          </option>
        </select>
      </label>
      <label class="min-w-0"
        ><span class="label">Status</span>
        <select
          class="input"
          :value="query.status ?? ''"
          @change="setFilter('status', ($event.target as HTMLSelectElement).value)"
        >
          <option value="">Alle</option>
          <option v-for="(label, value) in eventStatusLabels" :key="value" :value="value">
            {{ label }}
          </option>
        </select>
      </label>
      <label class="flex items-center gap-2 text-sm"
        ><input
          type="checkbox"
          role="switch"
          :checked="comparing"
          :disabled="period === 'all'"
          @change="
            setFilter('compare', ($event.target as HTMLInputElement).checked ? 'previous' : '')
          "
        />Zeitraum vergleichen</label
      >
      <span v-if="period === 'all'" class="text-xs text-slate-500"
        >Für „Alle“ gibt es keine Vorperiode.</span
      >
    </div>
    <p class="text-sm text-slate-600">
      Ein Event kann mehreren Kategorien, Genres oder Typen zugeordnet sein. Die Anteile beziehen
      sich jeweils auf alle Events im gewählten Erstellungszeitraum und summieren sich nicht
      zwingend zu 100 %.
    </p>
    <RequestState :loading="loading" :error="error" @retry="load" />
    <template v-if="data">
      <div
        class="grid min-w-0 gap-3 sm:grid-cols-2 xl:grid-cols-4"
        aria-label="Event-Inhalte Kennzahlen"
      >
        <section class="panel p-4" aria-label="Events erstellt">
          <h3 class="text-sm text-slate-600">Events erstellt</h3>
          <strong class="block text-2xl tabular-nums">{{ metric(data.event_count) }}</strong>
          <p class="text-sm">
            {{ data.period === 'all' ? 'Alle Events' : eventContentPeriods[data.period]
            }}<template v-if="data.status"> · {{ eventStatusLabels[data.status] }}</template>
          </p>
          <p v-if="data.comparison" class="mt-2 text-xs">
            Vorperiode: {{ metric(data.comparison.event_count) }} Events
          </p>
        </section>
        <section
          v-for="dimension in dimensions"
          :key="dimension.key"
          class="panel p-4"
          :aria-label="dimension.coverage"
        >
          <h3 class="text-sm text-slate-600">{{ dimension.coverage }}</h3>
          <strong class="block text-2xl tabular-nums"
            >{{ percentage(data.coverage[dimension.key].coverage_percent) }} %</strong
          >
          <p class="text-sm">
            {{ metric(data.coverage[dimension.key].events_with_assignment) }} von
            {{ metric(data.event_count) }} Events
          </p>
          <p class="mt-1 text-xs text-slate-600">
            {{ metric(data.coverage[dimension.key].events_without_assignment) }} Events ohne
            {{ dimension.missing }}
          </p>
          <p v-if="data.comparison" class="mt-2 text-xs">
            Vorperiode: {{ percentage(data.comparison.coverage[dimension.key].coverage_percent) }} %
          </p>
        </section>
      </div>
      <EmptyState
        v-if="!data.event_count"
        message="Keine Events im gewählten Erstellungszeitraum."
      />
      <div class="grid min-w-0 gap-5 xl:grid-cols-3">
        <RankingBarChart
          v-for="dimension in dimensions"
          :key="dimension.key"
          :title="dimension.title"
          :ranking="data[dimension.key]"
          :total-events="data.event_count"
        />
      </div>
      <p class="text-xs text-slate-500">
        <template v-if="data.from_at && data.to_at"
          >{{ statisticsDate(data.from_at, data.timezone) }} –
          {{ statisticsDate(data.to_at, data.timezone) }} · </template
        >{{ data.timezone }} · Erstellt, nicht Veranstaltungsdatum.
        <template v-if="data.comparison">
          Vergleich: {{ statisticsDate(data.comparison.from_at, data.timezone) }} –
          {{ statisticsDate(data.comparison.to_at, data.timezone) }} (gleichlange
          Vorperiode).</template
        >
      </p>
    </template>
  </div>
</template>
