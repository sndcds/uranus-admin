<script setup lang="ts">
import { ref, watch, onMounted, onBeforeUnmount } from 'vue'
import type { EntitySection, EntityPage } from '#shared/contracts'
import { asFailure, type ApiFailure } from '#shared/errors'
import { entitySections, entityFactLabel } from '~/utils/entities'
const props = defineProps<{ section: EntitySection }>()
const route = useRoute()
const router = useRouter()
const { $adminApi } = useNuxtApp()
const data = ref<EntityPage | null>(null)
const loading = ref(false)
const error = ref<ApiFailure | null>(null)
const q = ref(''),
  organization = ref(''),
  status = ref('')
let generation = 0
async function load() {
  const id = ++generation
  loading.value = true
  data.value = null
  error.value = null
  q.value = typeof route.query.q === 'string' ? route.query.q : ''
  organization.value =
    typeof route.query.organization_id === 'string' ? route.query.organization_id : ''
  status.value = typeof route.query.status === 'string' ? route.query.status : ''
  try {
    const query: Record<string, string> = {}
    for (const [key, value] of Object.entries(route.query)) {
      if (typeof value !== 'string') throw new Error('Invalid query')
      query[key] = value
    }
    const result = await $adminApi.entities(props.section, query)
    if (id === generation) data.value = result
  } catch (cause) {
    if (id === generation) error.value = asFailure(cause)
  } finally {
    if (id === generation) loading.value = false
  }
}
function apply() {
  void router.push({
    query: {
      q: q.value || undefined,
      organization_id: organization.value || undefined,
      status: status.value || undefined,
      page: '1',
    },
  })
}
onMounted(load)
watch(() => route.query, load)
watch(
  useState('admin-access-revision', () => 0),
  load,
)
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
      <label
        ><span class="label">Suche</span
        ><input v-model="q" maxlength="200" class="input" type="search"
      /></label>
      <label
        ><span class="label">Organisation UUID</span><input v-model="organization" class="input"
      /></label>
      <label v-if="section === 'events' || section === 'users'"
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
        ><NuxtLink :to="`/${section}`" class="button">Filter zurücksetzen</NuxtLink>
      </div>
    </FilterBar>
    <RequestState :loading="loading" :error="error" :has-data="!!data" @retry="load" />
    <template v-if="data">
      <ResultSummary
        :total="data.pagination.total"
        :visible="data.items.length"
        noun="Datensätze"
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
        :to="(page) => ({ query: { ...route.query, page: String(page) } })"
      />
    </template>
  </div>
</template>
