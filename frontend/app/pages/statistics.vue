<script setup lang="ts">
import VenueScopeBadge from '~/components/VenueScopeBadge.vue'
import { useFilterPreferencesStore } from '~/stores/filter-preferences'
import EventContentStatistics from '~/components/statistics/EventContentStatistics.vue'
import { statisticsPeriods, supportsPeriod } from '~/utils/periods'
import { usePreferenceQuery } from '~/composables/usePreferenceQuery'
import InlineAlert from '~/components/InlineAlert.vue'
import RecordSection from '~/components/RecordSection.vue'
import DenseTable from '~/components/DenseTable.vue'
import { useOperationsRequest } from '~/composables/useOperationsRequest'
import type { TechnicalFact } from '~/utils/operations'
import { computed, ref, onMounted, watch } from 'vue'
import type { EntityStatistics, StatisticsEntity } from '#shared/contracts'
import { entityTypes, invitationPresentation } from '~/utils/entityPresentation'
import { metric } from '~/utils/presentation'
import {
  statisticsTypes,
  statisticsOrder,
  statisticsIntervals,
  statisticsIntervalAllowed,
  statisticsDate,
  statisticsActivityLink,
  statisticsRecentLink,
  statisticsDateBoundary,
} from '~/utils/statistics'
import EntityTimelineChart from '~/components/statistics/EntityTimelineChart.vue'
import EntityMetricCard from '~/components/statistics/EntityMetricCard.vue'
import EntityDistributionChart from '~/components/statistics/EntityDistributionChart.vue'
const preferences = useFilterPreferencesStore()
const route = useRoute()
const contentEntry = route.query.view === 'event-content'
const preferredPeriod = preferences.resolvePeriodForPage(
  contentEntry ? 'eventContent' : 'statistics',
)
const query = usePreferenceQuery(
  contentEntry
    ? { view: 'event-content', period: preferredPeriod }
    : {
        period: preferredPeriod,
        interval: statisticsIntervalAllowed(preferredPeriod, preferences.statistics.interval)
          ? preferences.statistics.interval
          : 'auto',
        compare: preferences.statistics.compare ? 'previous' : undefined,
      },
  (value, previous) => {
    if (value.view === 'event-content') {
      if (!previous || value.period !== previous.period)
        preferences.hydratePeriod('eventContent', value.period)
    } else preferences.hydrateStatistics(value, previous)
  },
  contentEntry,
)
const contentView = computed(() => query.value.view === 'event-content')
function setView(view: 'creation' | 'event-content') {
  const targetPeriod = preferences.resolvePeriodForPage(
    view === 'creation' ? 'statistics' : 'eventContent',
  )
  void router.push({
    query: {
      view,
      geo_scope_id: query.value.geo_scope_id,
      period:
        view === 'creation' && !supportsPeriod('statistics', preferences.sharedPeriod)
          ? undefined
          : targetPeriod,
      ...(view === 'creation'
        ? {
            interval: statisticsIntervalAllowed(targetPeriod, preferences.statistics.interval)
              ? preferences.statistics.interval
              : 'auto',
          }
        : {}),
      compare: query.value.compare === 'previous' ? 'previous' : undefined,
    },
  })
}
const router = useRouter()
const { $adminApi } = useNuxtApp()
const { data, loading, error, load: request } = useOperationsRequest<EntityStatistics | null>()
const knownTimezone = ref<string | null>(null)
const selected = computed({
    get: () => preferences.statistics.selectedTypes,
    set: (value: StatisticsEntity[]) => {
      preferences.statistics.selectedTypes = value
    },
  }),
  highlighted = ref<StatisticsEntity | null>(null)
const customOpen = ref(false),
  customFrom = ref(''),
  customTo = ref(''),
  customError = ref('')
const period = computed(() =>
  query.value.from_at
    ? 'custom'
    : typeof query.value.period === 'string'
      ? query.value.period
      : '24h',
)
const interval = computed(() =>
  typeof query.value.interval === 'string' ? query.value.interval : 'auto',
)
const compare = computed(() => query.value.compare === 'previous')
const total = computed(() => data.value?.series.reduce((sum, s) => sum + s.total, 0) ?? 0)
const ordered = computed(() =>
  statisticsOrder
    .map((type) => data.value?.series.find((s) => s.entity_type === type))
    .filter((s) => s !== undefined),
)
const recentColumns = [
  { key: 'created_at', label: 'Zeitpunkt' },
  { key: 'entity_type', label: 'Typ' },
  { key: 'entity_name', label: 'Name', rowHeader: true },
  { key: 'organization_name', label: 'Kontext' },
] as const
const tableColumns = computed(() => [
  { key: 'start_at' as const, label: 'Intervallbeginn', rowHeader: true },
  ...ordered.value.map((series) => ({
    key: series.entity_type,
    label:
      statisticsTypes[series.entity_type].label +
      (query.value.geo_scope_id ? ` · ${series.scope === 'geo' ? 'Gebiet' : 'Systemweit'}` : ''),
  })),
])
const tableRows = computed<({ start_at: string } & Partial<Record<StatisticsEntity, number>>)[]>(
  () =>
    data.value?.series[0]?.points.map((point, index) => ({
      start_at: point.start_at,
      ...Object.fromEntries(
        ordered.value.map((series) => [series.entity_type, series.points[index]?.count]),
      ),
    })) ?? [],
)
const technicalItems = computed<TechnicalFact[]>(() =>
  data.value
    ? [
        {
          label: 'Von',
          value: statisticsDate(data.value.from_at, data.value.timezone),
          datetime: data.value.from_at,
        },
        {
          label: 'Bis (exklusiv)',
          value: statisticsDate(data.value.to_at, data.value.timezone),
          datetime: data.value.to_at,
        },
        { label: 'Zeitzone', value: data.value.timezone },
        { label: 'Intervall', value: statisticsIntervals[data.value.interval] },
        { label: 'Anzahl Intervalle', value: data.value.series[0]?.points.length },
        {
          label: 'Aktualisiert',
          value: statisticsDate(data.value.observed_at, data.value.timezone),
          datetime: data.value.observed_at,
        },
        { label: 'Vergleich aktiv', value: !!data.value.previous_from_at },
        {
          label: 'Scope',
          value: query.value.geo_scope_id ? 'Gebiet und systemweite Serien' : 'Systemweit',
        },
        {
          label: 'Geo Scope',
          value: typeof query.value.geo_scope_id === 'string' ? query.value.geo_scope_id : null,
          mono: true,
        },
      ]
    : [],
)
let lastQuery = ''
async function load() {
  const key = JSON.stringify(Object.entries(query.value).sort(([a], [b]) => a.localeCompare(b)))
  if (key !== lastQuery) highlighted.value = null
  lastQuery = key
  await request(key, async () => {
    if (contentView.value) return null
    const requestQuery: Record<string, string> = {}
    for (const [key, value] of Object.entries(query.value)) {
      if (key === 'view' && value === 'creation') continue
      if (
        !['period', 'interval', 'compare', 'from_at', 'to_at', 'geo_scope_id'].includes(key) ||
        typeof value !== 'string'
      )
        throw new Error('Invalid query')
      requestQuery[key] = value
    }
    return $adminApi.statistics(requestQuery)
  })
  if (data.value) knownTimezone.value = data.value.timezone
}
function setPeriod(value: string) {
  preferences.hydratePeriod('statistics', value)
  customOpen.value = false
  void router.push({
    query: {
      geo_scope_id: query.value.geo_scope_id,
      period: value,
      interval: 'auto',
      compare: compare.value ? 'previous' : undefined,
    },
  })
}
function setQuery(key: string, value: string | undefined) {
  void router.push({ query: { ...query.value, [key]: value } })
}
function toggle(type: StatisticsEntity) {
  selected.value = selected.value.includes(type)
    ? selected.value.filter((item) => item !== type)
    : [...selected.value, type]
}
function applyCustom() {
  customError.value = ''
  try {
    if (!knownTimezone.value) return
    const zone = knownTimezone.value
    const start = statisticsDateBoundary(customFrom.value, zone),
      end = statisticsDateBoundary(customTo.value, zone, true)
    if (
      Date.parse(end) <= Date.parse(start) ||
      Date.parse(end) - Date.parse(start) > 365 * 86400000
    )
      throw new Error('range')
    customOpen.value = false
    void router.push({
      query: {
        geo_scope_id: query.value.geo_scope_id,
        period: 'custom',
        from_at: start,
        to_at: end,
        interval: 'auto',
        compare: compare.value ? 'previous' : undefined,
      },
    })
  } catch {
    customError.value = 'Bitte einen gültigen Zeitraum von höchstens 365 Tagen auswählen.'
  }
}
function intervalAllowed(value: string) {
  return statisticsIntervalAllowed(
    period.value,
    value,
    typeof query.value.from_at === 'string' ? query.value.from_at : undefined,
    typeof query.value.to_at === 'string' ? query.value.to_at : undefined,
  )
}

onMounted(load)
watch(() => query.value, load)
</script>
<template>
  <section class="statistics-page operations-page" aria-labelledby="statistics-title">
    <PageHeader
      :title="contentView ? 'Event-Inhalte' : 'Neue Entitäten'"
      title-id="statistics-title"
      :description="
        contentView
          ? 'Kategorien, Genres und Veranstaltungstypen neu angelegter Events analysieren.'
          : 'Neuanlagen im Zeitverlauf analysieren und vergleichen.'
      "
    />
    <nav class="analytics-view-nav" aria-label="Statistikbereich">
      <button class="analytics-toggle" :aria-pressed="!contentView" @click="setView('creation')">
        Erstellung
      </button>
      <button
        class="analytics-toggle"
        :aria-pressed="contentView"
        @click="setView('event-content')"
      >
        Event-Inhalte
      </button>
    </nav>
    <EventContentStatistics v-if="contentView" :query="query" />
    <template v-else>
      <div
        class="statistics-period-bar operations-workspace-toolbar flex flex-wrap items-center gap-2"
      >
        <div
          class="statistics-periods flex flex-wrap items-center gap-1"
          aria-label="Statistikzeitraum"
        >
          <button
            v-for="(label, value) in statisticsPeriods"
            :key="value"
            :aria-pressed="period === value"
            class="analytics-toggle"
            @click="setPeriod(value)"
          >
            {{ label }}
          </button>
          <button
            :aria-expanded="customOpen"
            :aria-pressed="period === 'custom'"
            class="analytics-toggle"
            aria-controls="statistics-custom-range"
            @click="customOpen = !customOpen"
          >
            Benutzerdefiniert <AppIcon name="calendar" :size="15" />
          </button>
        </div>
        <label
          class="statistics-compare inline-flex min-h-11 flex-wrap items-center gap-2 text-xs text-slate-600"
          ><span>Zeitraum vergleichen</span
          ><input
            type="checkbox"
            class="h-4 w-4 accent-fuchsia-700"
            role="switch"
            :checked="compare"
            @change="
              setQuery(
                'compare',
                ($event.target as HTMLInputElement).checked ? 'previous' : undefined,
              )
            "
          /><span class="statistics-previous-label text-xs text-slate-500"
            >Gleichlange Vorperiode</span
          ></label
        >
        <div class="statistics-period-actions flex w-full items-center gap-2 sm:ml-auto sm:w-auto">
          <div class="min-w-0 flex items-center gap-2">
            <label for="statistics-interval" class="operations-meta">Intervall</label>
            <select
              id="statistics-interval"
              :value="interval"
              class="input"
              aria-label="Intervall"
              @change="setQuery('interval', ($event.target as HTMLSelectElement).value)"
            >
              <option value="auto">
                Automatisch{{ data ? ` · ${statisticsIntervals[data.interval]}` : '' }}
              </option>
              <option
                v-for="(label, value) in statisticsIntervals"
                :key="value"
                :value="value"
                :disabled="!intervalAllowed(value)"
              >
                {{ label }}
              </option>
            </select>
          </div>
          <button
            class="statistics-refresh button"
            aria-label="Zahlen aktualisieren"
            title="Zahlen aktualisieren"
            :disabled="loading"
            @click="load"
          >
            <AppIcon name="refresh" :size="16" />Aktualisieren
          </button>
        </div>
      </div>
      <form
        v-if="customOpen"
        id="statistics-custom-range"
        class="statistics-custom section-subtle flex flex-wrap items-end gap-3 p-3"
        @submit.prevent="applyCustom"
      >
        <label
          ><span class="label">Von</span
          ><input v-model="customFrom" class="input" type="date" required
        /></label>
        <label
          ><span class="label">Bis einschließlich</span
          ><input v-model="customTo" class="input" type="date" required
        /></label>
        <button class="button-primary" :disabled="!knownTimezone">Zeitraum anwenden</button
        ><span class="muted">{{ knownTimezone ?? 'Zeitzone wird geladen …' }}</span>
        <InlineAlert v-if="customError" tone="error">{{ customError }}</InlineAlert>
      </form>
      <RequestState :loading="loading" :error="error" :has-data="!!data" @retry="load" />

      <div v-if="loading && !data" class="space-y-3" aria-hidden="true">
        <div class="grid grid-cols-2 gap-3 md:grid-cols-4">
          <div v-for="n in 4" :key="n" class="h-28 rounded-xl bg-slate-100" />
        </div>
        <div class="h-80 rounded-xl bg-slate-100" />
      </div>
      <template v-if="data">
        <EmptyState v-if="!total" compact message="Keine neuen Entitäten in diesem Zeitraum." />
        <div
          class="statistics-metrics analytics-kpi-strip"
          aria-label="Kennzahlen"
          :aria-busy="loading"
        >
          <EntityMetricCard
            v-for="series in ordered"
            :key="series.entity_type"
            :series="series"
            :show-scope="!!query.geo_scope_id"
            :selected="selected.includes(series.entity_type)"
            @toggle="toggle(series.entity_type)"
            @highlight="highlighted = series.entity_type"
            @unhighlight="highlighted = null"
          />
        </div>
        <EntityTimelineChart
          :show-scope="!!query.geo_scope_id"
          :series="ordered"
          :from-at="data.from_at"
          :to-at="data.to_at"
          :timezone="data.timezone"
          :selected-types="selected"
          :highlighted="highlighted"
          @toggle="toggle"
          @highlight="highlighted = $event"
        />
        <EntityDistributionChart :show-scope="!!query.geo_scope_id" :series="ordered" />
        <RecordSection title="Neueste Entitäten" surface="plain" class="statistics-recent">
          <template #actions>
            <NuxtLink :to="statisticsActivityLink(data)" class="action-link text-xs"
              >Alle neuen Entitäten anzeigen <AppIcon name="arrow" :size="15"
            /></NuxtLink>
          </template>
          <DenseTable
            caption="Zuletzt angelegte Entitäten"
            :columns="recentColumns"
            :rows="data.recent"
            :row-key="(row) => `${row.entity_type}:${row.entity_key}`"
            empty-message="Keine neuen Entitäten in diesem Zeitraum."
          >
            <template #cell-created_at="{ row }"
              ><time :datetime="row.created_at">{{
                statisticsDate(row.created_at, data.timezone)
              }}</time></template
            >
            <template #cell-entity_type="{ row }">
              <span
                class="inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-xs"
                :class="
                  row.entity_type === 'team_invitation'
                    ? invitationPresentation.tone
                    : entityTypes[row.entity_type].tone
                "
                ><AppIcon :name="statisticsTypes[row.entity_type].icon" :size="13" />{{
                  statisticsTypes[row.entity_type].singular
                }}</span
              >
              <VenueScopeBadge
                v-if="row.entity_type === 'venue' && row.venue_scope"
                :scope="row.venue_scope"
                class="mt-1"
              />
            </template>
            <template #actions="{ row }"
              ><NuxtLink
                :to="statisticsRecentLink(row.action.href)"
                class="button button-compact"
                :aria-label="`Öffnen: ${row.entity_name}`"
                >Öffnen</NuxtLink
              ></template
            >
          </DenseTable>
        </RecordSection>
        <p class="statistics-footnote flex flex-wrap justify-between gap-2 text-xs text-slate-500">
          Teameinladungen zählen nach dem zuletzt gespeicherten Einladungszeitpunkt; erneute
          Einladungen sind keine separate Versandhistorie.
        </p>
        <details class="statistics-data-table section-panel p-3 text-sm text-slate-600">
          <summary class="min-h-11 cursor-pointer content-center font-semibold">
            Daten als Tabelle · {{ metric(total) }} neue Entitäten<template
              v-if="query.geo_scope_id"
            >
              (Gebiet und Systemweit)</template
            >
          </summary>
          <DenseTable
            class="mt-3"
            :caption="`Anzahl pro Zeitintervall, Zeitzone ${data.timezone}`"
            :columns="tableColumns"
            :rows="tableRows"
            :row-key="(row) => row.start_at"
            mobile="scroll"
          >
            <template #cell-start_at="{ row }"
              ><time :datetime="row.start_at">{{
                statisticsDate(row.start_at, data.timezone)
              }}</time></template
            >
          </DenseTable>
        </details>
        <TechnicalInfoBar :items="technicalItems" :show-title="false" />
      </template>
    </template>
  </section>
</template>
<style src="~/assets/css/statistics.css" />
