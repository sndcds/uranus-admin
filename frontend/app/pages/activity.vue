<script setup lang="ts">
import { useFilterPreferencesStore } from '~/stores/filter-preferences'
import { usePreferenceQuery } from '~/composables/usePreferenceQuery'
import { activityPeriods } from '~/utils/periods'
import { isSpatialType } from '~/utils/geo'
import { entityTypeSchema } from '#shared/contracts'
import type { ActivityPage } from '#shared/contracts'
import { AdminApiError, failure } from '#shared/errors'
import { useOperationsRequest } from '~/composables/useOperationsRequest'
import { activityTypes, activityGroups, activityCounts } from '~/utils/activity'
import { dateTime, adminTimeZone } from '~/utils/presentation'
const preferences = useFilterPreferencesStore()
const query = usePreferenceQuery(
  {
    period: preferences.resolvePeriodForPage('activity'),
    entity_type:
      preferences.sharedGeoScope && !isSpatialType(preferences.activity.entityType)
        ? undefined
        : preferences.activity.entityType,
  },
  (value) => preferences.hydrateActivity(value),
)
const router = useRouter()
const { $adminApi } = useNuxtApp()
const { data, loading, error, load: request } = useOperationsRequest<ActivityPage>()
const entityType = ref('')
const organization = ref('')
const period = ref('24h')
const selectedType = computed(() => {
  const parsed = entityTypeSchema.safeParse(query.value.entity_type)
  return parsed.success ? parsed.data : null
})
const geoScopeId = computed(() =>
  typeof query.value.geo_scope_id === 'string' ? query.value.geo_scope_id : undefined,
)
const availableTypes = computed(() =>
  entityTypeSchema.options.filter((kind) => !geoScopeId.value || isSpatialType(kind)),
)
const title = computed(() =>
  query.value.timestamp_state === 'unknown'
    ? 'Datensätze ohne Zeitstempel'
    : selectedType.value
      ? `Neue ${activityTypes[selectedType.value].plural}`
      : 'Neue Datensätze',
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
async function load() {
  await request(JSON.stringify(query.value), async () => {
    const requestQuery: Record<string, string> = {}
    for (const [key, value] of Object.entries(query.value)) {
      if (typeof value !== 'string') throw new AdminApiError(failure(422))
      requestQuery[key] = value
    }
    return $adminApi.activity(requestQuery)
  })
}
function reset() {
  preferences.activity.entityType = ''
  preferences.activity.period = '24h'
  void router.push({ query: { geo_scope_id: geoScopeId.value } })
}
function apply() {
  preferences.hydratePeriod('activity', period.value)
  void router.push({
    query: {
      geo_scope_id: geoScopeId.value,
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
const technicalItems = computed(() =>
  data.value
    ? [
        {
          label: 'Datenstand',
          value: dateTime(data.value.observed_at),
          datetime: data.value.observed_at,
        },
        {
          label: 'Von',
          value: data.value.from_at ? dateTime(data.value.from_at) : null,
          datetime: data.value.from_at ?? undefined,
        },
        {
          label: 'Bis',
          value: data.value.to_at ? dateTime(data.value.to_at) : null,
          datetime: data.value.to_at ?? undefined,
        },
        { label: 'Anzeigezeitzone', value: adminTimeZone },
        { label: 'Gesamtzahl', value: data.value.pagination.total },
        { label: 'Sichtbare Einträge', value: data.value.items.length },
        { label: 'Einträge je Seite', value: data.value.pagination.page_size },
        {
          label: 'Zeitstempel-Auswahl',
          value: data.value.timestamp_state === 'known' ? 'Bekannt' : 'Unbekannt',
        },
        { label: 'Ohne belegten Erstellungszeitpunkt', value: data.value.unknown_timestamp_count },
      ]
    : [],
)
const hasFilters = computed(
  () =>
    [
      'entity_type',
      'organization_id',
      'entity_key',
      'creation_basis',
      'from_at',
      'to_at',
      'timestamp_state',
    ].some((key) => !!query.value[key]) ||
    (query.value.period && query.value.period !== '24h'),
)
</script>

<template>
  <section class="operations-page" aria-labelledby="activity-title">
    <PageHeader :title="title" :description="description" title-id="activity-title">
      <template #actions
        ><button class="button" :disabled="loading" @click="load">Aktualisieren</button></template
      >
    </PageHeader>
    <FilterBar compact :columns="3" @apply="apply">
      <label
        ><span class="label">Objektart</span>
        <select v-model="entityType" class="input">
          <option value="">Alle Objektarten</option>
          <option v-for="kind in availableTypes" :key="kind" :value="kind">
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
      <template #actions>
        <button class="button-primary" :disabled="loading">Anwenden</button>
        <button type="button" class="button" :disabled="loading" @click="reset">
          Filter zurücksetzen
        </button>
      </template>
    </FilterBar>
    <p v-if="query.creation_basis === 'statistics'" class="muted">
      Neuanlagen der sieben Statistiktypen; Teammitgliedschaften nach Einladungszeitpunkt.
    </p>
    <RequestState :loading="loading" :error="error" :has-data="!!data" @retry="load" />
    <template v-if="data">
      <ResultSummary
        :total="data.pagination.total"
        :visible="data.items.length"
        noun="Datensätze"
        label="Zusammenfassung der Aktivität"
        :description="`${data.unknown_timestamp_count} ohne belegten Erstellungszeitpunkt${data.timestamp_state === 'known' ? ' · separate Auswahl' : ''}`"
      >
        <span v-if="counts.length" class="font-medium">Objektarten auf dieser Seite:</span>
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
      </ResultSummary>
      <InlineAlert v-if="data.timestamp_state === 'unknown'" tone="info">
        Nach Objektschlüssel geordnet; eine zeitliche Reihenfolge ist nicht bekannt.
      </InlineAlert>
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
          <ul class="data-list-dense">
            <ActivityRow
              v-for="item in group.items"
              :key="`${item.entity_type}:${item.entity_key}`"
              :item="item"
              :observed-at="data.observed_at"
              :grouped="!!group.label"
              dense
            />
          </ul>
        </section>
      </DataListShell>
      <EmptyState v-else variant="compact" message="Keine Datensätze für diese Auswahl.">
        <template v-if="hasFilters" #actions
          ><button class="button" @click="reset">Filter zurücksetzen</button></template
        >
      </EmptyState>
      <PaginationBar
        v-if="data.pagination.pages > 0"
        :pagination="data.pagination"
        :loading="loading"
        label="Activity-Seitennavigation"
        :to="(page) => ({ query: { ...query, page } })"
      />
      <TechnicalInfoBar :items="technicalItems" :show-title="false" />
    </template>
  </section>
</template>
