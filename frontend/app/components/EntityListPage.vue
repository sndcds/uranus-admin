<script setup lang="ts">
import { computed, ref, watch, onMounted, onBeforeUnmount } from 'vue'
import { useFilterPreferencesStore } from '~/stores/filter-preferences'
import { usePreferenceQuery } from '~/composables/usePreferenceQuery'
import type { EntitySection, EntityPage, TemporalFilter } from '#shared/contracts'
import { asFailure, type ApiFailure } from '#shared/errors'
import {
  entitySections,
  entityFactLabel,
  entityFilterCapabilities,
  temporalLabels,
  temporalFromQuery,
} from '~/utils/entities'
const props = defineProps<{ section: EntitySection }>()
const preferences = useFilterPreferencesStore()
const route = useRoute()
// Applied list URLs include page and represent complete history snapshots.
const remembered = route.query.page ? {} : preferences.entities[props.section]
const query = usePreferenceQuery(
  { ...remembered, ...(Object.values(remembered).some(Boolean) ? { page: '1' } : {}) },
  (value) => preferences.hydrateEntity(props.section, value),
  true,
)
const router = useRouter()
const { $adminApi } = useNuxtApp()
const data = ref<EntityPage | null>(null)
const loading = ref(false)
const error = ref<ApiFailure | null>(null)
const q = ref(''),
  organization = ref(''),
  status = ref('')
const temporal = ref<TemporalFilter | ''>('')
const hasTemporal = computed(() => entityFilterCapabilities[props.section].temporal)
const appliedTemporal = computed(() =>
  hasTemporal.value ? temporalFromQuery(query.value.temporal) : '',
)
let generation = 0
async function load() {
  const id = ++generation
  loading.value = true
  data.value = null
  error.value = null
  q.value = typeof query.value.q === 'string' ? query.value.q : ''
  organization.value =
    typeof query.value.organization_id === 'string' ? query.value.organization_id : ''
  status.value = typeof query.value.status === 'string' ? query.value.status : ''
  temporal.value = hasTemporal.value ? temporalFromQuery(query.value.temporal) : ''
  try {
    const requestQuery: Record<string, string> = {}
    for (const [key, value] of Object.entries(query.value)) {
      if (typeof value !== 'string') throw new Error('Invalid query')
      requestQuery[key] = value
    }
    const result = await $adminApi.entities(props.section, requestQuery)
    if (id === generation) data.value = result
  } catch (cause) {
    if (id === generation) error.value = asFailure(cause)
  } finally {
    if (id === generation) loading.value = false
  }
}
function apply() {
  preferences.hydrateEntity(props.section, {
    q: q.value,
    status: status.value,
    temporal: temporal.value,
  })
  void router.push({
    query: {
      q: q.value || undefined,
      organization_id: organization.value || undefined,
      status: status.value || undefined,
      temporal: hasTemporal.value ? temporal.value || undefined : undefined,
      page: '1',
    },
  })
}
function reset() {
  preferences.resetEntity(props.section)
  q.value = status.value = organization.value = temporal.value = ''
  void router.push({ query: { page: '1' } })
}
onMounted(load)
watch(() => query.value, load)
onBeforeUnmount(() => {
  generation++
})
</script>
<template>
  <div class="space-y-5">
    <PageHeader
      :title="entitySections[section].title"
      description="Datensätze durchsuchen, Beziehungen und Arbeitsstand prüfen."
    >
      <template v-if="section === 'venues' || section === 'spaces'"
        ><NuxtLink to="/venues" class="button">Orte</NuxtLink
        ><NuxtLink to="/spaces" class="button">Räume</NuxtLink></template
      >
    </PageHeader>
    <FilterBar @apply="apply">
      <EntitySearch
        v-model="q"
        :entity-type="entitySections[section].type"
        :organization-id="organization"
        :status="status"
        :temporal="hasTemporal ? temporal : undefined"
        @apply="apply"
        @select="router.push($event.action.href)"
      />
      <label v-if="hasTemporal">
        <span class="label">Zeitraum</span>
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
            ><option value="released">Veröffentlicht</option>
            <option value="draft">Entwurf</option>
            <option value="review">In Prüfung</option>
            <option value="cancelled">Abgesagt</option>
            <option value="deferred">Verschoben</option>
            <option value="rescheduled">Neuer Termin</option></template
          >
        </select></label
      >
      <div class="flex flex-wrap items-end gap-2">
        <button class="button-primary" type="submit">Anwenden</button
        ><button type="button" class="button" @click="reset">Filter zurücksetzen</button>
      </div>
    </FilterBar>
    <RequestState :loading="loading" :error="error" :has-data="!!data" @retry="load" />
    <template v-if="data">
      <ResultSummary
        :total="data.pagination.total"
        :visible="data.items.length"
        noun="Datensätze"
        :description="appliedTemporal ? `Zeitraum: ${temporalLabels[appliedTemporal]}` : undefined"
        :observed-at="data.observed_at"
      />
      <DataListShell v-if="data.items.length" as="ul"
        ><template v-for="item in data.items" :key="item.entity_key"
          ><ActivityRow :item="item" :observed-at="data.observed_at"
            ><template #context
              ><div class="mt-1 flex flex-wrap gap-x-3 text-xs text-slate-500">
                <template v-for="(value, key) in item.facts" :key="key"
                  ><span v-if="value !== null && key !== 'description'"
                    >{{ entityFactLabel(section, key) }}:
                    {{ typeof value === 'boolean' ? (value ? 'Ja' : 'Nein') : value }}</span
                  ></template
                >
              </div></template
            ></ActivityRow
          ></template
        ></DataListShell
      >
      <EmptyState v-else message="Keine Datensätze für diese Filter." />
      <PaginationBar
        :pagination="data.pagination"
        :loading="loading"
        :to="(page) => ({ query: { ...query, page: String(page) } })"
      />
    </template>
  </div>
</template>
