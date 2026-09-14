<script setup lang="ts">
import type { FindingFilters } from '#shared/contracts'
import { filtersSchema } from '#shared/contracts'
import { parseFilters, filterQuery } from '~/utils/filters'
const route = useRoute()
const router = useRouter()
const store = useFindingsStore()
const { $adminApi } = useNuxtApp()
const invalidQuery = ref(false)
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
  <div class="space-y-7">
    <section>
      <div class="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 class="text-2xl font-bold tracking-tight">Priorisierte Arbeitsliste</h2>
          <p class="mt-1 muted">Befunde filtern, einordnen und im Detail ansehen.</p>
        </div>
        <button
          class="button"
          :disabled="store.loading || invalidQuery"
          @click="store.load($adminApi)"
        >
          <AppIcon name="refresh" :size="16" /> Aktualisieren
        </button>
      </div>
    </section>
    <section class="card p-5">
      <h2 class="mb-4 font-bold">Filter</h2>
      <FilterForm :filters="store.filters" @apply="apply" /><NuxtLink
        v-if="Object.keys(route.query).length"
        to="/findings"
        class="mt-3 inline-block text-sm font-semibold text-fuchsia-700"
        >Filter zurücksetzen</NuxtLink
      >
    </section>
    <div
      v-if="invalidQuery"
      role="alert"
      class="rounded-xl border border-rose-200 bg-rose-50 p-5 text-sm text-rose-800"
    >
      Die URL enthält ungültige Filter oder Seitenzahlen.
      <NuxtLink
        :to="{ path: '/findings', query: filterQuery(filtersSchema.parse({})) }"
        class="font-semibold underline"
        >Filter zurücksetzen</NuxtLink
      >
    </div>
    <RequestState
      :loading="store.loading"
      :error="store.error"
      :has-data="!!store.data"
      :last-success="store.lastSuccess"
      @retry="store.load($adminApi)"
    />
    <section class="card" :aria-busy="store.loading">
      <div class="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 p-5">
        <h2 class="font-bold">
          {{ store.data ? `${metric(store.data.pagination.total)} Befunde` : 'Befunde' }}
        </h2>
        <span class="text-xs text-slate-500">Live-Auswertung · serverseitig priorisiert</span>
      </div>
      <FindingsList v-if="store.data?.items.length" :items="store.data.items" />
      <p v-else class="p-10 text-center text-sm text-slate-500">
        {{
          store.loading
            ? 'Arbeitsliste wird geladen …'
            : store.data
              ? 'Keine Befunde auf dieser Seite. Filter ändern oder zur ersten Seite wechseln.'
              : 'Keine Daten verfügbar. Ein gültiger Admin-Zugang ist erforderlich.'
        }}
      </p>
      <div
        v-if="store.data"
        class="flex flex-wrap items-center justify-between gap-3 border-t border-slate-100 p-4 text-sm"
      >
        <div>
          <span>{{
            store.data.pagination.total === 0
              ? 'Keine Ergebnisse'
              : `Seite ${store.data.pagination.page} von ${store.data.pagination.pages}`
          }}</span
          ><label class="ml-3 inline-flex items-center gap-2"
            ><span class="sr-only">Einträge pro Seite</span
            ><select
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
            </select></label
          >
        </div>
        <nav aria-label="Seitennavigation" class="flex gap-2">
          <button
            class="button"
            :disabled="store.filters.page <= 1 || store.loading"
            @click="page(store.filters.page - 1)"
          >
            <AppIcon name="previous" :size="16" /> Zurück</button
          ><button
            class="button"
            :disabled="store.filters.page >= store.data.pagination.pages || store.loading"
            @click="page(store.filters.page + 1)"
          >
            Weiter <AppIcon name="next" :size="16" />
          </button>
        </nav>
      </div>
    </section>
    <p v-if="store.lastSuccess" class="text-xs text-slate-500">
      Letzter erfolgreicher Abruf: {{ dateTime(store.lastSuccess) }} · Europe/Berlin. Erstfund,
      Reviews und Erledigungshistorie werden noch nicht gespeichert.
    </p>
  </div>
</template>
