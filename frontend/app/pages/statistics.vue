<script setup lang="ts">
import InlineAlert from '~/components/InlineAlert.vue'
import SectionHeader from '~/components/SectionHeader.vue'
import { computed, ref, onMounted, onBeforeUnmount, watch } from 'vue'
import type { EntityStatistics, StatisticsEntity } from '#shared/contracts'
import { asFailure } from '#shared/errors'
import type { ApiFailure } from '#shared/errors'
import { entityTypes, invitationPresentation } from '~/utils/entityPresentation'
import { metric } from '~/utils/presentation'
import {
  statisticsTypes,
  statisticsOrder,
  statisticsPeriods,
  statisticsIntervals,
  statisticsDate,
  statisticsActivityLink,
  statisticsRecentLink,
  statisticsDateBoundary,
} from '~/utils/statistics'
import EntityTimelineChart from '~/components/statistics/EntityTimelineChart.vue'
import EntityMetricCard from '~/components/statistics/EntityMetricCard.vue'
import EntityDistributionChart from '~/components/statistics/EntityDistributionChart.vue'
const route = useRoute(),
  router = useRouter()
const { $adminApi } = useNuxtApp()
const data = ref<EntityStatistics | null>(null),
  loading = ref(false),
  error = ref<ApiFailure | null>(null)
const knownTimezone = ref<string | null>(null)
const selected = ref<StatisticsEntity[]>([...statisticsOrder]),
  highlighted = ref<StatisticsEntity | null>(null)
const customOpen = ref(false),
  customFrom = ref(''),
  customTo = ref(''),
  customError = ref('')
const period = computed(() =>
  route.query.from_at
    ? 'custom'
    : typeof route.query.period === 'string'
      ? route.query.period
      : '24h',
)
const interval = computed(() =>
  typeof route.query.interval === 'string' ? route.query.interval : 'auto',
)
const compare = computed(() => route.query.compare === 'previous')
const total = computed(() => data.value?.series.reduce((sum, s) => sum + s.total, 0) ?? 0)
const ordered = computed(() =>
  statisticsOrder
    .map((type) => data.value?.series.find((s) => s.entity_type === type))
    .filter((s) => s !== undefined),
)
let generation = 0
async function load() {
  const current = ++generation
  loading.value = true
  error.value = null
  data.value = null
  highlighted.value = null
  try {
    const query: Record<string, string> = {}
    for (const [key, value] of Object.entries(route.query)) {
      if (
        !['period', 'interval', 'compare', 'from_at', 'to_at'].includes(key) ||
        typeof value !== 'string'
      )
        throw new Error('Invalid query')
      query[key] = value
    }
    const result = await $adminApi.statistics(query)
    if (current === generation) {
      data.value = result
      knownTimezone.value = result.timezone
    }
  } catch (cause) {
    if (current === generation) error.value = asFailure(cause)
  } finally {
    if (current === generation) loading.value = false
  }
}
function setPeriod(value: string) {
  customOpen.value = false
  void router.push({
    query: { period: value, interval: 'auto', compare: compare.value ? 'previous' : undefined },
  })
}
function setQuery(key: string, value: string | undefined) {
  void router.push({ query: { ...route.query, [key]: value } })
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
  const duration =
    period.value === 'custom' &&
    typeof route.query.from_at === 'string' &&
    typeof route.query.to_at === 'string'
      ? Date.parse(route.query.to_at) - Date.parse(route.query.from_at)
      : ({ '24h': 1, '7d': 7, '30d': 30, '90d': 90 }[period.value] ?? 1) * 86400000
  return (
    Math.ceil(
      duration / ({ '15m': 900000, '1h': 3600000, '6h': 21600000, '1d': 86400000 }[value] ?? 1),
    ) +
      2 <=
    500
  )
}
onMounted(load)
watch(() => route.query, load)
onBeforeUnmount(() => {
  generation++
})
</script>
<template>
  <section class="statistics-page space-y-5" aria-labelledby="statistics-title">
    <PageHeader
      title="Neue Entitäten"
      title-id="statistics-title"
      description="Übersicht über neu angelegte Benutzer, Organisationen, Veranstaltungsorte, Räume, Veranstaltungen sowie Partneranfragen und Teameinladungen."
    />
    <div class="statistics-period-bar panel flex flex-wrap items-center gap-3 p-4">
      <div
        class="statistics-periods flex flex-wrap items-center gap-2"
        aria-label="Statistikzeitraum"
      >
        <button
          v-for="(label, value) in statisticsPeriods"
          :key="value"
          :aria-pressed="period === value"
          :class="period === value ? 'button-primary' : 'button'"
          @click="setPeriod(value)"
        >
          {{ label }}
        </button>
        <button
          :aria-expanded="customOpen"
          :class="period === 'custom' ? 'button-primary' : 'button'"
          @click="customOpen = !customOpen"
        >
          Benutzerdefiniert <AppIcon name="calendar" :size="15" />
        </button>
      </div>
      <label
        class="statistics-compare inline-flex flex-wrap items-center gap-2 text-sm text-slate-600"
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
          >Vorheriger Zeitraum</span
        ></label
      >
      <div class="statistics-period-actions flex w-full items-center gap-2 sm:ml-auto sm:w-auto">
        <label
          ><span class="sr-only">Intervall</span
          ><select
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
          </select></label
        >
        <button
          class="statistics-refresh button"
          aria-label="Zahlen aktualisieren"
          title="Zahlen aktualisieren"
          :disabled="loading"
          @click="load"
        >
          <AppIcon name="refresh" :size="16" />
        </button>
      </div>
    </div>
    <form
      v-if="customOpen"
      class="statistics-custom statistics-panel flex flex-wrap items-end gap-3 panel p-4 sm:p-5"
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
    <RequestState :loading="loading" :error="error" @retry="load" />

    <div v-if="loading" class="space-y-3" aria-hidden="true">
      <div class="h-80 rounded-2xl bg-slate-100" />
      <div class="grid grid-cols-2 gap-3 md:grid-cols-4">
        <div v-for="n in 4" :key="n" class="h-32 rounded-2xl bg-slate-100" />
      </div>
    </div>
    <template v-if="data">
      <EmptyState v-if="!total" message="Keine neuen Entitäten in diesem Zeitraum." />
      <EntityTimelineChart
        :series="ordered"
        :from-at="data.from_at"
        :to-at="data.to_at"
        :timezone="data.timezone"
        :selected-types="selected"
        :highlighted="highlighted"
        @toggle="toggle"
        @highlight="highlighted = $event"
      />
      <div
        class="statistics-metrics grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-4"
        aria-label="Kennzahlen"
      >
        <EntityMetricCard
          v-for="series in ordered"
          :key="series.entity_type"
          :series="series"
          :selected="selected.includes(series.entity_type)"
          @toggle="toggle(series.entity_type)"
          @highlight="highlighted = series.entity_type"
          @unhighlight="highlighted = null"
        />
      </div>
      <div class="statistics-bottom grid min-w-0 gap-5 xl:grid-cols-2">
        <section
          class="statistics-panel statistics-recent panel p-4 sm:p-5"
          aria-labelledby="recent-title"
        >
          <SectionHeader title-id="recent-title" title="Neueste Entitäten" />
          <div
            v-if="data.recent.length"
            class="statistics-table-scroll mt-3 max-w-full overflow-x-auto"
          >
            <table class="admin-table">
              <caption class="sr-only">
                Zuletzt angelegte Entitäten
              </caption>
              <thead>
                <tr>
                  <th>Zeitpunkt</th>
                  <th>Typ</th>
                  <th>Name</th>
                  <th>Organisation / Kontext</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="item in data.recent" :key="`${item.entity_type}:${item.entity_key}`">
                  <td>{{ statisticsDate(item.created_at, data.timezone) }}</td>
                  <td>
                    <span
                      class="inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-xs"
                      :class="
                        item.entity_type === 'team_invitation'
                          ? invitationPresentation.tone
                          : entityTypes[item.entity_type].tone
                      "
                      :style="{ '--series-color': statisticsTypes[item.entity_type].color }"
                      ><AppIcon :name="statisticsTypes[item.entity_type].icon" :size="13" />{{
                        statisticsTypes[item.entity_type].singular
                      }}</span
                    >
                  </td>
                  <td>
                    <NuxtLink :to="statisticsRecentLink(item.action.href)">{{
                      item.entity_name
                    }}</NuxtLink>
                  </td>
                  <td>{{ item.organization_name ?? '—' }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <EmptyState v-else message="Keine neuen Entitäten in diesem Zeitraum." />
          <NuxtLink
            :to="statisticsActivityLink(data)"
            class="statistics-all-link mt-4 inline-flex items-center gap-2 text-sm font-semibold text-fuchsia-700 hover:underline"
            >Alle neuen Entitäten anzeigen <AppIcon name="arrow" :size="15"
          /></NuxtLink>
        </section>
        <EntityDistributionChart :series="ordered" />
      </div>
      <div class="statistics-footnote flex flex-wrap justify-between gap-2 text-xs text-slate-500">
        <span
          >{{ statisticsDate(data.from_at, data.timezone) }} –
          {{ statisticsDate(data.to_at, data.timezone) }} · {{ data.timezone }}</span
        ><span
          >{{ data.series[0]?.points.length }} Zeitintervalle · Aktualisiert
          {{ statisticsDate(data.observed_at, data.timezone) }}</span
        >
      </div>
      <p class="statistics-footnote flex flex-wrap justify-between gap-2 text-xs text-slate-500">
        Teameinladungen zählen nach dem zuletzt gespeicherten Einladungszeitpunkt; erneute
        Einladungen sind keine separate Versandhistorie.
      </p>
      <details class="statistics-data-table panel p-4 text-sm text-slate-600">
        <summary class="cursor-pointer font-semibold">
          Daten als Tabelle · {{ metric(total) }} neue Entitäten
        </summary>
        <div class="statistics-table-scroll mt-3 max-w-full overflow-x-auto">
          <table class="admin-table">
            <caption class="sr-only">
              Anzahl pro Zeitintervall, Zeitzone
              {{
                data.timezone
              }}
            </caption>
            <thead>
              <tr>
                <th>Intervallbeginn</th>
                <th v-for="series in ordered" :key="series.entity_type">
                  {{ statisticsTypes[series.entity_type].label }}
                </th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(point, index) in data.series[0]?.points" :key="point.start_at">
                <th>
                  {{ statisticsDate(point.start_at, data.timezone) }}
                  {{ statisticsDate(point.start_at, data.timezone, 'time').split(' ').at(-1) }}
                </th>
                <td v-for="series in ordered" :key="series.entity_type">
                  {{ series.points[index]?.count }}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </details>
    </template>
  </section>
</template>
<style src="~/assets/css/statistics.css" />
