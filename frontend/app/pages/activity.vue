<script setup lang="ts">
import { useFilterPreferencesStore } from '~/stores/filter-preferences'
import { usePreferenceQuery } from '~/composables/usePreferenceQuery'
import { activityPeriods } from '~/utils/periods'
import { entityTypeSchema } from '#shared/contracts'
import type { ActivityPage } from '#shared/contracts'
import { asFailure } from '#shared/errors'
import type { ApiFailure } from '#shared/errors'
import { activityTypes, activityGroups, activityCounts } from '~/utils/activity'
import { dateTime, adminTimeZone } from '~/utils/presentation'
const preferences = useFilterPreferencesStore()
const query = usePreferenceQuery(
  {
    period: preferences.resolvePeriodForPage('activity'),
    entity_type: preferences.activity.entityType,
  },
  (value) => preferences.hydrateActivity(value),
)
const router = useRouter()
const { $adminApi } = useNuxtApp()
const data = ref<ActivityPage | null>(null)
const error = ref<ApiFailure | null>(null)
const loading = ref(false)
const entityType = ref('')
const organization = ref('')
const period = ref('24h')
const selectedType = computed(() => {
  const parsed = entityTypeSchema.safeParse(query.value.entity_type)
  return parsed.success ? parsed.data : null
})
const title = computed(() =>
  selectedType.value ? `Neue ${activityTypes[selectedType.value].plural}` : 'Neue Datensätze',
)
const description = computed(() => {
  if (!data.value) return 'Neuanlagen nach Objektart und Erstellungszeitpunkt.'
  const count = data.value.pagination.total
  const label = selectedType.value
    ? count === 1
      ? activityTypes[selectedType.value].label
      : activityTypes[selectedType.value].plural
    : count === 1
      ? 'Datensatz'
      : 'Datensätze'
  if (data.value.timestamp_state === 'unknown')
    return `${count} ${label} ohne belegten Erstellungszeitpunkt.`
  if (query.value.entity_key && !query.value.period && !query.value.from_at && !query.value.to_at)
    return `${count} ${label} für diesen Objektschlüssel.`
  const window =
    data.value.from_at && data.value.to_at
      ? `${dateTime(data.value.from_at)} – ${dateTime(data.value.to_at)}`
      : 'gewählte Zeitgrenzen'
  return `${count} ${label} · ${window}`
})
const groups = computed(() => (data.value ? activityGroups(data.value) : []))
const counts = computed(() => activityCounts(data.value?.items ?? []))
function syncFilters() {
  entityType.value = typeof query.value.entity_type === 'string' ? query.value.entity_type : ''
  organization.value =
    typeof query.value.organization_id === 'string' ? query.value.organization_id : ''
  period.value =
    query.value.timestamp_state === 'unknown'
      ? 'unknown'
      : query.value.from_at || query.value.to_at
        ? 'custom'
        : typeof query.value.period === 'string'
          ? query.value.period
          : '24h'
}
syncFilters()
let requestId = 0
async function load() {
  const id = ++requestId
  loading.value = true
  data.value = null
  error.value = null
  try {
    const requestQuery: Record<string, string> = {}
    for (const [key, value] of Object.entries(query.value)) {
      if (typeof value !== 'string') throw new Error('Invalid query')
      requestQuery[key] = value
    }
    const result = await $adminApi.activity(requestQuery)
    if (id === requestId) data.value = result
  } catch (cause) {
    if (id === requestId) error.value = asFailure(cause)
  } finally {
    if (id === requestId) loading.value = false
  }
}
function reset() {
  preferences.activity.entityType = ''
  preferences.activity.period = '24h'
  void router.push({ query: {} })
}
function apply() {
  preferences.hydratePeriod('activity', period.value)
  void router.push({
    query: {
      creation_basis: query.value.creation_basis === 'statistics' ? 'statistics' : undefined,
      entity_type: entityType.value || undefined,
      organization_id: organization.value || undefined,
      period: ['unknown', 'custom'].includes(period.value) ? undefined : period.value,
      from_at: period.value === 'custom' ? query.value.from_at : undefined,
      to_at: period.value === 'custom' ? query.value.to_at : undefined,
      timestamp_state: period.value === 'unknown' ? 'unknown' : 'known',
      page: '1',
    },
  })
}
onMounted(load)
watch(
  () => query.value,
  () => {
    syncFilters()
    void load()
  },
)
onBeforeUnmount(() => {
  requestId++
})
</script>

<template>
  <section class="space-y-5" aria-labelledby="activity-title">
    <PageHeader :title="title" :description="description" title-id="activity-title" />
    <FilterBar @apply="apply">
      <label
        ><span class="label">Objektart</span>
        <select v-model="entityType" class="input">
          <option value="">Alle Objektarten</option>
          <option v-for="kind in entityTypeSchema.options" :key="kind" :value="kind">
            {{ activityTypes[kind].label }}
          </option>
        </select>
      </label>
      <label
        ><span class="label">Zeitraum</span>
        <select v-model="period" class="input">
          <option v-if="query.from_at || query.to_at" value="custom">Benutzerdefiniert</option>
          <option v-for="(label, value) in activityPeriods" :key="value" :value="value">
            {{ label }}
          </option>
          <option value="unknown">Ohne Zeitstempel</option>
        </select>
      </label>
      <label
        ><span class="label">Organisation (UUID)</span>
        <input
          v-model="organization"
          class="input"
          placeholder="Alle Organisationen"
          spellcheck="false"
        />
      </label>
      <div class="flex flex-wrap items-end gap-2">
        <button class="button-primary" :disabled="loading">Anwenden</button>
        <button type="button" class="button" :disabled="loading" @click="reset">
          Filter zurücksetzen
        </button>
      </div>
    </FilterBar>
    <p v-if="query.creation_basis === 'statistics'" class="muted">
      Neuanlagen der sieben Statistiktypen; Teammitgliedschaften nach Einladungszeitpunkt.
    </p>
    <RequestState :loading="loading" :error="error" @retry="load" />
    <template v-if="data">
      <ResultSummary
        :total="data.pagination.total"
        :visible="data.items.length"
        noun="Datensätze"
        label="Zusammenfassung der Aktivität"
        :description="`${data.unknown_timestamp_count} ohne belegten Erstellungszeitpunkt${data.timestamp_state === 'known' ? ' · separate Auswahl' : ''}`"
      >
        <span
          v-for="entry in counts"
          :key="entry.type"
          class="rounded-md px-2 py-0.5"
          :class="activityTypes[entry.type].tone"
        >
          {{ entry.count }}
          {{
            entry.count === 1 ? activityTypes[entry.type].label : activityTypes[entry.type].plural
          }}
        </span>
        <p v-if="data.timestamp_state === 'known'" class="text-xs text-slate-500">
          Tagesgruppen auf dieser Seite · Zeiten in {{ adminTimeZone }} · Stand:
          {{ dateTime(data.observed_at) }}
        </p>
      </ResultSummary>
      <p
        v-if="data.timestamp_state === 'unknown'"
        class="rounded-xl border border-slate-200 bg-slate-100 px-4 py-3 text-sm text-slate-600"
      >
        Nach Objektschlüssel geordnet; eine zeitliche Reihenfolge ist nicht bekannt.
      </p>
      <DataListShell v-if="data.items.length" :aria-busy="loading">
        <section
          v-for="group in groups"
          :key="group.key"
          :aria-labelledby="group.label ? `activity-day-${group.key}` : undefined"
          :aria-label="group.label ? undefined : 'Datensätze ohne bekannte Reihenfolge'"
        >
          <div v-if="group.label" class="list-group-header">
            <h3 :id="`activity-day-${group.key}`" class="text-xs font-semibold text-slate-700">
              {{ group.label }}
            </h3>
            <span class="text-xs tabular-nums text-slate-500"
              >{{ group.items.length }}
              {{ group.items.length === 1 ? 'Eintrag' : 'Einträge' }}</span
            >
          </div>
          <ul class="divide-y divide-slate-100">
            <ActivityRow
              v-for="item in group.items"
              :key="`${item.entity_type}:${item.entity_key}`"
              :item="item"
              :observed-at="data.observed_at"
              :grouped="!!group.label"
            />
          </ul>
        </section>
      </DataListShell>
      <EmptyState v-else message="Keine Datensätze für diese Filter." />
      <PaginationBar
        v-if="data.pagination.pages > 0"
        :pagination="data.pagination"
        :loading="loading"
        label="Activity-Seitennavigation"
        :to="(page) => ({ query: { ...query, page } })"
      />
    </template>
  </section>
</template>
