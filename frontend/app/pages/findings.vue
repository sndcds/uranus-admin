<script setup lang="ts">
import type { FindingFilters } from '#shared/contracts'
import { filtersSchema } from '#shared/contracts'
import { parseFilters, filterQuery } from '~/utils/filters'
const route = useRoute()
const router = useRouter()
const store = useFindingsStore()
const { $adminApi } = useNuxtApp()
const invalidQuery = ref(false)
const severityCounts = computed(() => {
  const items = store.data?.items ?? []
  return `${items.filter((item) => item.severity === 'error').length} Fehler · ${items.filter((item) => item.severity === 'warning').length} Warnungen · ${items.filter((item) => item.severity === 'info').length} Hinweise`
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
}
onMounted(loadRoute)
watch(() => route.query, loadRoute)
function apply(filters: FindingFilters) {
  return router.push({ query: filterQuery(filters) })
}
function page(value: number) {
  return apply({ ...store.filters, page: value })
}
</script>

<template>
  <section class="space-y-4">
    <PageHeader
      title="Priorisierte Arbeitsliste"
      description="Befunde filtern, einordnen und bearbeiten."
    >
      <button
        class="button"
        :disabled="store.loading || invalidQuery"
        @click="store.load($adminApi)"
      >
        <AppIcon name="refresh" :size="16" /> Aktualisieren
      </button>
    </PageHeader>
    <FilterForm :filters="store.filters" @apply="apply" @reset="router.push({ query: {} })" />
    <div
      v-if="invalidQuery"
      role="alert"
      class="rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800"
    >
      Die URL enthält ungültige Filter oder Seitenzahlen.
      <NuxtLink to="/findings" class="font-semibold underline">Filter zurücksetzen</NuxtLink>
    </div>
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
        ><span>{{ severityCounts }} · auf dieser Seite</span></ResultSummary
      >
      <div v-if="store.data.items.length" class="data-list" :aria-busy="store.loading">
        <FindingsList :items="store.data.items" />
      </div>
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
