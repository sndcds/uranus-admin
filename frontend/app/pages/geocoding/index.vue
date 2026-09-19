<script setup lang="ts">
import { ref, watch, onMounted, onBeforeUnmount } from 'vue'
import type { GeocodePage, GeocodeStatus } from '#shared/contracts'
import { geocodeStatusSchema } from '#shared/contracts'
import type { ApiFailure } from '#shared/errors'
import { asFailure } from '#shared/errors'
import { dateTime } from '~/utils/presentation'
import { geocodeStatuses } from '~/utils/geocoding'
const route = useRoute()
const router = useRouter()
const { $adminApi } = useNuxtApp()
const data = ref<GeocodePage | null>(null)
const error = ref<ApiFailure | null>(null)
const loading = ref(false)
const status = ref<GeocodeStatus | ''>('')
const entityType = ref<'organization' | 'venue' | ''>('')
const pageSize = ref(50)
let generation = 0
async function load() {
  const current = ++generation
  loading.value = true
  data.value = null
  error.value = null
  const parsed = geocodeStatusSchema.safeParse(route.query.status)
  status.value = parsed.success ? parsed.data : ''
  entityType.value =
    route.query.entity_type === 'organization' || route.query.entity_type === 'venue'
      ? route.query.entity_type
      : ''
  const page = Number(route.query.page ?? 1)
  pageSize.value = [10, 25, 50, 100].includes(Number(route.query.page_size))
    ? Number(route.query.page_size)
    : 50
  try {
    const value = await $adminApi.geocodeRequests({
      status: status.value || undefined,
      entity_type: entityType.value || undefined,
      page: Number.isInteger(page) && page > 0 && page <= 100000 ? page : 1,
      page_size: pageSize.value,
    })
    if (current === generation) data.value = value
  } catch (cause) {
    if (current === generation) error.value = asFailure(cause)
  } finally {
    if (current === generation) loading.value = false
  }
}
function apply(page = 1) {
  return router.push({
    query: {
      status: status.value || undefined,
      entity_type: entityType.value || undefined,
      page: String(page),
      page_size: String(pageSize.value),
    },
  })
}
onMounted(load)
watch(() => route.query, load)
onBeforeUnmount(() => {
  generation++
})
</script>
<template>
  <section class="space-y-5">
    <PageHeader
      title="Standortvorschläge"
      description="Fehlende Geopositionen prüfen und automatisch ermittelte Vorschläge vergleichen."
    />
    <p class="muted">
      Diese Ansicht ist systemweit. Fehlende Positionen sind keinem Gebiet sicher zuordenbar und
      werden systemweit angezeigt.
    </p>
    <FilterBar @apply="apply()">
      <label
        >Status<select v-model="status" class="input">
          <option value="">Alle</option>
          <option v-for="(label, value) in geocodeStatuses" :key="value" :value="value">
            {{ label }}
          </option>
        </select></label
      >
      <label
        >Entität<select v-model="entityType" class="input">
          <option value="">Alle</option>
          <option value="organization">Organisation</option>
          <option value="venue">Ort</option>
        </select></label
      >
      <label
        >Pro Seite<select v-model="pageSize" class="input">
          <option v-for="size in [10, 25, 50, 100]" :key="size" :value="size">{{ size }}</option>
        </select></label
      >
      <button class="button" :disabled="loading">Filter anwenden</button>
    </FilterBar>
    <RequestState :loading="loading" :error="error" @retry="load" />
    <template v-if="data">
      <dl class="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div v-for="(label, value) in geocodeStatuses" :key="value" class="panel p-3">
          <dt class="muted">{{ label }}</dt>
          <dd class="text-xl font-semibold">{{ data.counts[value] ?? 0 }}</dd>
        </div>
      </dl>
      <p class="muted">
        Statuszahlen und Filter zeigen den zuletzt gespeicherten Prüfstand. Veränderte Quellen
        werden beim Öffnen als veraltet gekennzeichnet.
      </p>
      <ResultSummary
        :total="data.pagination.total"
        :visible="data.items.length"
        noun="Standortprüfungen"
      />
      <DataListShell v-if="data.items.length" as="ul" class="divide-y divide-slate-100">
        <li v-for="item in data.items" :key="item.id" class="data-row space-y-1">
          <div class="flex flex-wrap justify-between gap-2">
            <NuxtLink :to="`/geocoding/${item.id}`" class="font-semibold text-fuchsia-700">{{
              item.entity_name
            }}</NuxtLink
            ><span>{{ geocodeStatuses[item.status] }}</span>
          </div>
          <p>{{ item.source_address || 'Keine Adresse vorhanden' }}</p>
          <p v-if="item.best_candidate">
            {{ item.best_candidate.display_name }} ·
            {{ Math.round(item.best_candidate.match_score * 100) }} %
          </p>
          <p class="muted">
            {{ item.candidate_count }} Kandidaten · Letzte Prüfung: {{ dateTime(item.checked_at) }}
          </p>
        </li>
      </DataListShell>
      <EmptyState v-else message="Keine Standortprüfungen für diese Auswahl." />
      <PaginationBar :pagination="data.pagination" :loading="loading" @change="apply" />
    </template>
  </section>
</template>
