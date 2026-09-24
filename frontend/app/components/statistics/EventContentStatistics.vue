<script setup lang="ts">
import { computed, watch, onMounted } from 'vue'
import type { LocationQuery } from 'vue-router'
import {
  geoScopeIdSchema,
  eventContentPeriodSchema,
  eventReleaseStatusSchema,
  type EventContentStatistics,
  type EventContentQuery,
} from '#shared/contracts'
import { useOperationsRequest } from '~/composables/useOperationsRequest'
import type { TechnicalFact } from '~/utils/operations'
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
const { data, loading, error, load: requestData } = useOperationsRequest<EventContentStatistics>()
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
const technicalItems = computed<TechnicalFact[]>(() =>
  data.value
    ? [
        { label: 'Zeitraum', value: eventContentPeriods[data.value.period] },
        {
          label: 'Von',
          value: data.value.from_at
            ? statisticsDate(data.value.from_at, data.value.timezone)
            : null,
          datetime: data.value.from_at ?? undefined,
        },
        {
          label: 'Bis (exklusiv)',
          value: data.value.to_at ? statisticsDate(data.value.to_at, data.value.timezone) : null,
          datetime: data.value.to_at ?? undefined,
        },
        { label: 'Zeitzone', value: data.value.timezone },
        {
          label: 'Status',
          value: data.value.status ? eventStatusLabels[data.value.status] : 'Alle',
        },
        { label: 'Events', value: data.value.event_count },
        {
          label: 'Vergleich von',
          value: data.value.comparison
            ? statisticsDate(data.value.comparison.from_at, data.value.timezone)
            : null,
          datetime: data.value.comparison?.from_at,
        },
        {
          label: 'Vergleich bis (exklusiv)',
          value: data.value.comparison
            ? statisticsDate(data.value.comparison.to_at, data.value.timezone)
            : null,
          datetime: data.value.comparison?.to_at,
        },
        {
          label: 'Aktualisiert',
          value: statisticsDate(data.value.observed_at, data.value.timezone),
          datetime: data.value.observed_at,
        },
        { label: 'Scope', value: props.query.geo_scope_id ? 'Gewähltes Gebiet' : 'Systemweit' },
        {
          label: 'Geo Scope',
          value: typeof props.query.geo_scope_id === 'string' ? props.query.geo_scope_id : null,
          mono: true,
        },
      ]
    : [],
)
async function load() {
  const key = JSON.stringify([
    Object.entries(props.query).sort(([a], [b]) => a.localeCompare(b)),
    period.value,
  ])
  await requestData(key, async () => {
    for (const key of Object.keys(props.query))
      if (!['view', 'period', 'status', 'compare', 'geo_scope_id'].includes(key))
        throw new Error('Invalid query')
    const request: EventContentQuery = { period: eventContentPeriodSchema.parse(period.value) }
    if (props.query.geo_scope_id !== undefined)
      request.geo_scope_id = geoScopeIdSchema.parse(props.query.geo_scope_id)
    if (props.query.status !== undefined)
      request.status = eventReleaseStatusSchema.parse(props.query.status)
    if (props.query.compare !== undefined) {
      if (props.query.compare !== 'previous') throw new Error('Invalid comparison')
      request.compare = 'previous'
    }
    return $adminApi.eventContent(request)
  })
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
</script>
<template>
  <div class="operations-page event-content-workspace">
    <div
      class="operations-workspace-toolbar flex flex-wrap items-end gap-3"
      aria-label="Event-Inhalte filtern"
    >
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
      <label class="flex min-h-11 items-center gap-2 text-xs"
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
      <button class="button button-compact" :disabled="loading" @click="load">
        <AppIcon name="refresh" :size="14" />Aktualisieren
      </button>
    </div>
    <p v-if="query.geo_scope_id" class="text-xs text-slate-600">
      Rankings und Anteile beziehen sich auf Veranstaltungen im gewählten Gebiet.
    </p>
    <p class="operations-meta">
      Erstellt, nicht Veranstaltungsdatum. Ein Event kann mehreren Kategorien, Genres oder Typen
      zugeordnet sein. Die Anteile beziehen sich jeweils auf alle Events im gewählten
      Erstellungszeitraum und summieren sich nicht zwingend zu 100 %.
    </p>
    <RequestState :loading="loading" :error="error" :has-data="!!data" @retry="load" />
    <template v-if="data">
      <div
        class="analytics-kpi-strip event-content-metrics"
        :aria-busy="loading"
        aria-label="Event-Inhalte Kennzahlen"
      >
        <section class="analytics-kpi" aria-label="Events erstellt">
          <h3 class="text-xs text-slate-600">Events erstellt</h3>
          <strong class="block text-lg tabular-nums">{{ metric(data.event_count) }}</strong>
          <p class="text-xs">
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
          class="analytics-kpi"
          :aria-label="dimension.coverage"
        >
          <h3 class="text-xs text-slate-600">{{ dimension.coverage }}</h3>
          <strong class="block text-lg tabular-nums"
            >{{ percentage(data.coverage[dimension.key].coverage_percent) }} %</strong
          >
          <p class="text-xs">
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
        compact
        message="Keine Events im gewählten Erstellungszeitraum."
      />
      <div class="grid min-w-0 gap-3 md:grid-cols-2 xl:grid-cols-3">
        <RankingBarChart
          v-for="dimension in dimensions"
          :key="dimension.key"
          :title="dimension.title"
          :ranking="data[dimension.key]"
          :total-events="data.event_count"
        />
      </div>
      <p v-if="data.comparison" class="operations-meta">Vergleich: gleichlange Vorperiode.</p>
      <TechnicalInfoBar :items="technicalItems" :show-title="false" />
    </template>
  </div>
</template>
