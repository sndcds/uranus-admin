<script setup lang="ts">
import { computed, ref, watch, onMounted } from 'vue'
import { useFilterPreferencesStore } from '~/stores/filter-preferences'
import { usePreferenceQuery } from '~/composables/usePreferenceQuery'
import {
  sharedPeriodSchema,
  type EntitySection,
  type EntityPage,
  type TemporalFilter,
  type SharedPeriod,
} from '#shared/contracts'
import { supportsGeoEntity } from '~/utils/geo'
import { entityPeriods } from '~/utils/periods'
import { AdminApiError, failure } from '#shared/errors'
import { useOperationsRequest } from '~/composables/useOperationsRequest'
import { dateTime, adminTimeZone } from '~/utils/presentation'
import { activityStatus } from '~/utils/activity'
import {
  entitySections,
  eventStatusLabels,
  entityFilterCapabilities,
  temporalLabels,
  temporalFromQuery,
} from '~/utils/entities'
const props = defineProps<{ section: EntitySection }>()
const preferences = useFilterPreferencesStore()
const route = useRoute()
// Applied list URLs include page and represent complete history snapshots.
const remembered = route.query.page ? {} : preferences.entityDefaults(props.section)
const query = usePreferenceQuery(
  { ...remembered, ...(Object.values(remembered).some(Boolean) ? { page: '1' } : {}) },
  (value, previous) =>
    preferences.hydrateEntity(
      props.section,
      value,
      previous ? value.period !== previous.period : Object.hasOwn(route.query, 'period'),
    ),
  true,
)
const router = useRouter()
const { $adminApi } = useNuxtApp()
const { data, loading, error, load: request } = useOperationsRequest<EntityPage>()
const q = ref(''),
  organization = ref(''),
  status = ref('')
const temporal = ref<TemporalFilter | ''>('')
const period = ref<SharedPeriod | ''>('')
const hasTemporal = computed(() => entityFilterCapabilities[props.section].temporal)
const hasGeo = computed(() => supportsGeoEntity(entitySections[props.section].type))
const appliedGeoScopeId = computed(() =>
  hasGeo.value && typeof query.value.geo_scope_id === 'string'
    ? query.value.geo_scope_id
    : undefined,
)
const appliedTemporal = computed(() =>
  hasTemporal.value ? temporalFromQuery(query.value.temporal) : '',
)
const resultDescription = computed(() => {
  const created = sharedPeriodSchema.safeParse(query.value.period)
  return (
    [
      typeof query.value.q === 'string' && query.value.q ? `Suche: ${query.value.q}` : '',
      typeof query.value.status === 'string' && query.value.status
        ? `Status: ${activityStatus(query.value.status)}`
        : '',
      created.success ? `Erstellt: ${entityPeriods[created.data]}` : '',
      appliedGeoScopeId.value && preferences.sharedGeoScope?.id === appliedGeoScopeId.value
        ? `Gebiet: ${preferences.sharedGeoScope.name}`
        : '',
      appliedTemporal.value ? `Terminlage: ${temporalLabels[appliedTemporal.value]}` : '',
    ]
      .filter(Boolean)
      .join(' · ') || undefined
  )
})
async function load() {
  q.value = typeof query.value.q === 'string' ? query.value.q : ''
  organization.value =
    typeof query.value.organization_id === 'string' ? query.value.organization_id : ''
  status.value = typeof query.value.status === 'string' ? query.value.status : ''
  const parsedPeriod = sharedPeriodSchema.safeParse(query.value.period)
  period.value = parsedPeriod.success ? parsedPeriod.data : ''
  temporal.value = hasTemporal.value ? temporalFromQuery(query.value.temporal) : ''
  await request(JSON.stringify([props.section, query.value]), async () => {
    const requestQuery: Record<string, string> = {}
    for (const [key, value] of Object.entries(query.value)) {
      if (typeof value !== 'string') throw new AdminApiError(failure(422))
      requestQuery[key] = value
    }
    return $adminApi.entities(props.section, requestQuery)
  })
}

function apply() {
  preferences.hydrateEntity(
    props.section,
    {
      q: q.value,
      status: status.value,
      temporal: temporal.value,
      period: period.value,
    },
    period.value !== (query.value.period ?? ''),
  )
  void router.push({
    query: {
      ...(appliedGeoScopeId.value ? { geo_scope_id: appliedGeoScopeId.value } : {}),
      q: q.value || undefined,
      period: period.value || undefined,
      organization_id: organization.value || undefined,
      status: status.value || undefined,
      temporal: hasTemporal.value ? temporal.value || undefined : undefined,
      page: '1',
    },
  })
}
function reset() {
  preferences.resetEntity(props.section)
  q.value = status.value = organization.value = temporal.value = period.value = ''
  void router.push({
    query: {
      page: '1',
      ...(appliedGeoScopeId.value ? { geo_scope_id: appliedGeoScopeId.value } : {}),
    },
  })
}
onMounted(load)
watch(() => query.value, load)
const technicalItems = computed(() =>
  data.value
    ? [
        {
          label: 'Datenstand',
          value: dateTime(data.value.observed_at),
          datetime: data.value.observed_at,
          timezone: adminTimeZone,
        },
        { label: 'Objektart', value: entitySections[props.section].title },
        { label: 'Gesamtzahl', value: data.value.pagination.total },
        { label: 'Sichtbare Einträge', value: data.value.items.length },
        { label: 'Einträge je Seite', value: data.value.pagination.page_size },
      ]
    : [],
)
const hasFilters = computed(() =>
  ['q', 'period', 'temporal', 'status', 'organization_id'].some((key) => !!query.value[key]),
)
</script>
<template>
  <div class="operations-page">
    <PageHeader
      :title="entitySections[section].title"
      description="Datensätze durchsuchen, Beziehungen und Arbeitsstand prüfen."
    >
      <template #actions>
        <template v-if="section === 'venues' || section === 'spaces'">
          <NuxtLink
            to="/venues"
            class="action-link"
            :aria-current="section === 'venues' ? 'page' : undefined"
            >Orte</NuxtLink
          >
          <NuxtLink
            to="/spaces"
            class="action-link"
            :aria-current="section === 'spaces' ? 'page' : undefined"
            >Räume</NuxtLink
          >
        </template>
        <button class="button" :disabled="loading" @click="load">Aktualisieren</button>
      </template>
    </PageHeader>
    <FilterBar
      compact
      :columns="
        hasTemporal && entityFilterCapabilities[section].status
          ? 4
          : hasTemporal || entityFilterCapabilities[section].status
            ? 3
            : 2
      "
      @apply="apply"
    >
      <EntitySearch
        class="sm:col-span-1!"
        v-model="q"
        :entity-type="entitySections[section].type"
        :organization-id="organization"
        :status="status"
        :period="period"
        :geo-scope-id="appliedGeoScopeId"
        :temporal="hasTemporal ? temporal : undefined"
        @apply="apply"
        @select="router.push($event.action.href)"
      />
      <label v-if="entityFilterCapabilities[section].period">
        <span class="label">Erstellt</span>
        <select v-model="period" class="input" @change="apply">
          <option value="">Alle</option>
          <option v-for="(label, value) in entityPeriods" :key="value" :value="value">
            {{ label }}
          </option>
        </select>
      </label>
      <label v-if="hasTemporal">
        <span class="label">Terminlage</span>
        <select v-model="temporal" class="input" @change="apply">
          <option value="">Alle</option>
          <option v-for="(label, value) in temporalLabels" :key="value" :value="value">
            {{ label }}
          </option>
        </select>
      </label>
      <label v-if="entityFilterCapabilities[section].status"
        ><span class="label">Status</span
        ><select v-model="status" class="input">
          <option value="">Alle</option>
          <template v-if="section === 'users'"
            ><option value="active">Aktiv</option>
            <option value="inactive">Nicht aktiv</option></template
          ><template v-else
            ><option v-for="(label, value) in eventStatusLabels" :key="value" :value="value">
              {{ label }}
            </option></template
          >
        </select></label
      >
      <template #actions>
        <button class="button-primary" type="submit">Anwenden</button
        ><button type="button" class="button" @click="reset">Filter zurücksetzen</button>
      </template>
    </FilterBar>
    <RequestState :loading="loading" :error="error" :has-data="!!data" @retry="load" />
    <template v-if="data">
      <ResultSummary
        class="min-w-0 [overflow-wrap:anywhere]"
        :total="data.pagination.total"
        :visible="data.items.length"
        noun="Datensätze"
        :description="resultDescription"
      />
      <DataListShell
        v-if="data.items.length"
        :aria-busy="loading"
        :class="{ 'collection-context-only': section === 'spaces' }"
      >
        <div class="collection-header" aria-hidden="true">
          <span>Datensatz</span><span>Kontext</span><span>Fakten</span
          ><span>Status / Erstellt</span>
        </div>
        <ul class="data-list-dense" :aria-label="entitySections[section].title">
          <EntityCollectionRow
            v-for="item in data.items"
            :key="item.entity_key"
            :item="item"
            :section="section"
          />
        </ul>
      </DataListShell>
      <EmptyState v-else variant="compact" message="Keine Datensätze für diese Auswahl.">
        <template v-if="hasFilters" #actions
          ><button class="button" @click="reset">Filter zurücksetzen</button></template
        >
      </EmptyState>
      <PaginationBar
        :pagination="data.pagination"
        :loading="loading"
        :to="(page) => ({ query: { ...query, page: String(page) } })"
      />
      <TechnicalInfoBar :items="technicalItems" :show-title="false" />
    </template>
  </div>
</template>
