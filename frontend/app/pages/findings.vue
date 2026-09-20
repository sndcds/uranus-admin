<script setup lang="ts">
import { useTemplateRef } from 'vue'
import SqlEditorModal from '~/components/sql/SqlEditorModal.vue'
import { sqlFindingFromHash } from '~/utils/sql-finding-link'
import InlineAlert from '~/components/InlineAlert.vue'
import type { FindingFilters } from '#shared/contracts'
import { filtersSchema } from '#shared/contracts'
import { parseFilters, filterQuery } from '~/utils/filters'
const route = useRoute()
const router = useRouter()
const store = useFindingsStore()
const { $adminApi } = useNuxtApp()
const invalidQuery = ref(false)
const linkedSqlEditor = useTemplateRef<InstanceType<typeof SqlEditorModal>>('linkedSqlEditor')
function openLinkedSql() {
  const finding = sqlFindingFromHash(route.hash ?? '', store.data?.items ?? [])
  if (finding) linkedSqlEditor.value?.open(finding)
}
watch(() => route.hash, openLinkedSql)
const severityCounts = computed(() => {
  const items = store.data?.items ?? []
  return [
    {
      label: 'Fehler',
      count: items.filter((item) => item.severity === 'error').length,
      tone: 'error' as const,
    },
    {
      label: 'Warnungen',
      count: items.filter((item) => item.severity === 'warning').length,
      tone: 'warning' as const,
    },
    {
      label: 'Hinweise',
      count: items.filter((item) => item.severity === 'info').length,
      tone: 'neutral' as const,
    },
  ]
})
async function loadRoute() {
  const parsed = parseFilters(route.query)
  invalidQuery.value = !parsed
  if (!parsed) {
    store.reset()
    return
  }
  store.syncQuery(parsed)
  await store.load($adminApi)
  openLinkedSql()
}
onMounted(loadRoute)
watch(() => route.query, loadRoute)
function apply(filters: FindingFilters) {
  return router.push({ query: { ...filterQuery(filters), geo_scope_id: route.query.geo_scope_id } })
}
function page(value: number) {
  return apply({ ...store.filters, page: value })
}
</script>

<template>
  <section class="space-y-5">
    <SqlEditorModal ref="linkedSqlEditor" />
    <PageHeader
      title="Priorisierte Arbeitsliste"
      description="Befunde filtern, einordnen und bearbeiten."
    >
      <NuxtLink to="/geocoding" class="button">Standortvorschläge</NuxtLink>
      <button
        class="button"
        :disabled="store.loading || invalidQuery"
        @click="store.load($adminApi)"
      >
        <AppIcon name="refresh" :size="16" /> Aktualisieren
      </button>
    </PageHeader>
    <FilterForm
      :filters="store.filters"
      @apply="apply"
      @reset="router.push({ query: { geo_scope_id: route.query.geo_scope_id } })"
    />
    <InlineAlert v-if="invalidQuery" tone="error">
      Die URL enthält ungültige Filter oder Seitenzahlen.
      <NuxtLink to="/findings" class="font-semibold underline">Filter zurücksetzen</NuxtLink>
    </InlineAlert>
    <RequestState
      :loading="store.loading"
      :error="store.error"
      :has-data="!!store.data"
      :last-success="store.lastSuccess"
      @retry="store.load($adminApi)"
    />
    <template v-if="store.data">
      <ResultSummary
        :total="store.data.pagination.total"
        :visible="store.data.items.length"
        noun="Befunde"
        :description="`${(store.data.mode ?? store.filters.mode) === 'persisted' ? 'Gespeicherte Befunde' : 'Live-Auswertung'} · serverseitig priorisiert`"
        :observed-at="store.data.observed_at"
        ><StatusBadge
          v-for="entry in severityCounts"
          :key="entry.label"
          :label="`${entry.count} ${entry.label}`"
          :tone="entry.tone"
        /><span>· auf dieser Seite</span></ResultSummary
      >
      <DataListShell v-if="store.data.items.length" :aria-busy="store.loading">
        <FindingsList :items="store.data.items" />
      </DataListShell>
      <EmptyState
        v-else
        message="Keine Befunde auf dieser Seite. Filter ändern oder zur ersten Seite wechseln."
      />
      <PaginationBar :pagination="store.data.pagination" :loading="store.loading" @change="page">
        <label class="inline-flex items-center gap-2"
          ><span class="sr-only">Einträge pro Seite</span>
          <select
            :value="store.filters.page_size"
            class="input"
            aria-label="Einträge pro Seite"
            @change="
              apply(
                filtersSchema.parse({
                  ...store.filters,
                  page_size: ($event.target as HTMLSelectElement).value,
                  page: 1,
                }),
              )
            "
          >
            <option v-for="size in [10, 25, 50, 100]" :key="size" :value="size">
              {{ size }} pro Seite
            </option>
          </select>
        </label>
      </PaginationBar>
    </template>
    <p v-if="store.lastSuccess" class="text-xs text-slate-500">
      Letzter erfolgreicher Abruf: {{ dateTime(store.lastSuccess) }} · Europe/Berlin. Gespeicherte
      Befunde enthalten Erstfund und Reviewstatus.
    </p>
  </section>
</template>
