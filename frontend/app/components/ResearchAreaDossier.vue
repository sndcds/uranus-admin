<script setup lang="ts">
import type { ResearchAreaDossier, ResearchQuery } from '#shared/contracts'
import { z } from '#shared/zod'
import { researchDate, researchHref, researchQuery, researchUrlQuery } from '~/utils/research'
import { dateTime } from '~/utils/presentation'
const route = useRoute()
const { $adminApi } = useNuxtApp()
const { data, loading, error, load } = useOperationsRequest<ResearchAreaDossier>()
const parsed = computed(() => researchQuery(route.query))
const identifier = computed(() => z.uuid().safeParse(route.params.id))
const query = computed<ResearchQuery>(() => ({
  ...(parsed.value.success ? parsed.value.data : {}),
  area_id: identifier.value.success ? identifier.value.data : undefined,
}))
const selected = ref('')
const permalink = ref<string | null>(null)
const categories = ref<{ id: number; name: string }[]>([])
const optionsError = ref(false)
let mounted = false
async function refresh() {
  if (!identifier.value.success || !parsed.value.success) return
  const id = identifier.value.data
  await load(JSON.stringify([id, query.value]), () => $adminApi.researchArea(id, query.value))
}
function apply(next: ResearchQuery) {
  return navigateTo({ path: route.path, query: researchUrlQuery({ ...next, area_id: undefined }) })
}
watch(
  () => route.fullPath,
  () => {
    if (mounted) {
      permalink.value = window.location.href
      void refresh()
    }
  },
)
onMounted(() => {
  mounted = true
  permalink.value = window.location.href
  void refresh()
  void $adminApi
    .researchOptions()
    .then((result) => {
      if (mounted) categories.value = result.categories
    })
    .catch(() => {
      if (mounted) optionsError.value = true
    })
})
onBeforeUnmount(() => {
  mounted = false
})
const maximum = computed(() => Math.max(1, ...(data.value?.months.map((m) => m.event_count) || [])))
const eventColumns = [
  { key: 'name', label: 'Veranstaltung', rowHeader: true },
  { key: 'start_date', label: 'Datum' },
  { key: 'venue_name', label: 'Ort' },
] as const
const usageTitles = {
  category: 'Kategorien',
  venue: 'Häufig genutzte Orte',
  organization: 'Aktive Organisationen',
}
</script>
<template>
  <div class="record-detail space-y-5">
    <NuxtLink :to="{ path: '/research/search', query: researchUrlQuery(query) }" class="action-link"
      >← Recherche mit diesem Gebiet</NuxtLink
    >
    <p v-if="!identifier.success || !parsed.success" role="alert">
      Die Dossier-Adresse oder der Filter ist ungültig.
    </p>
    <RequestState
      :loading="loading"
      :error="error"
      :has-data="!!data"
      :last-success="data?.observed_at"
      @retry="refresh"
    />
    <template v-if="data && identifier.success && parsed.success">
      <PageHeader
        :title="data.area.name"
        :description="
          data.area.country_code === 'DE' ? 'Gemeinde · Deutschland' : 'Kommune · Dänemark'
        "
        record
      >
        <template #actions
          ><CopyValueButton
            :value="permalink"
            label="Dossier-Link"
            button-text="Link kopieren"
            variant="button"
        /></template>
      </PageHeader>
      <p v-if="optionsError" role="status">Kategorien konnten nicht geladen werden.</p>
      <ResearchFilters :query="query" :categories="categories" fixed-area @apply="apply" />
      <div class="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <div
          v-for="stat in [
            { label: 'Veranstaltungen im Filter', value: data.events.pagination.total },
            { label: 'Orte im Filter', value: data.venues.pagination.total },
            {
              label: 'Über Veranstaltungen aktive Organisationen',
              value: data.organizations.pagination.total,
            },
          ]"
          :key="stat.label"
          class="panel p-4"
        >
          <p class="text-3xl font-semibold tabular-nums">{{ stat.value }}</p>
          <p class="type-metadata">{{ stat.label }}</p>
        </div>
      </div>
      <p class="type-metadata">
        Gezählt werden unterschiedliche öffentliche Veranstaltungen. Eine Veranstaltung kann Termine
        in mehreren Gemeinden haben. Organisationen werden über ihre Aktivität zugeordnet, nicht
        über ihren Sitz.
      </p>
      <RecordSection title="Aktivität nach Monat">
        <p v-if="!data.months.length" class="type-metadata">
          Keine öffentlichen Termine im Filter.
        </p>
        <p v-else class="type-metadata">
          Unterschiedliche Veranstaltungen pro Monat · bis zu 120 Monate
        </p>
        <ol class="max-h-80 overflow-y-auto space-y-2">
          <li
            v-for="month in [...data.months].reverse()"
            :key="month.month"
            class="grid grid-cols-[5rem_minmax(0,1fr)_3rem] items-center gap-2 text-sm"
          >
            <span>{{ month.month.slice(0, 7) }}</span>
            <div class="h-3 rounded bg-slate-100">
              <div
                class="h-3 rounded bg-blue-600"
                :style="{ width: `${(month.event_count / maximum) * 100}%` }"
              />
            </div>
            <span class="text-right tabular-nums">{{ month.event_count }}</span>
          </li>
        </ol>
      </RecordSection>
      <ResearchMap
        :area-id="data.area.id"
        :items="data.venues.items"
        :selected="selected"
        :boundary="data.geometry"
        :bbox="data.area.bbox"
        @select="selected = $event"
      />
      <p class="type-metadata">
        Gemeindegrenze und Orte dieser Ergebnisseite; die Grenzgeometrie stammt aus dem
        gespeicherten Import.
      </p>
      <div class="grid min-w-0 gap-4 lg:grid-cols-3">
        <RecordSection
          v-for="kind in ['category', 'venue', 'organization'] as const"
          :key="kind"
          :title="usageTitles[kind]"
        >
          <p v-if="!data.usage.some((item) => item.kind === kind)" class="type-metadata">
            Keine Aktivität im Filter.
          </p>
          <ul class="space-y-2">
            <li
              v-for="item in data.usage.filter((item) => item.kind === kind)"
              :key="item.key"
              class="flex items-center justify-between gap-2"
            >
              <ResearchCategoryBadge
                v-if="kind === 'category'"
                :category="{ id: Number(item.key), name: item.name }"
              />
              <NuxtLink
                v-else
                :to="{ path: researchHref(kind, item.key), query: researchUrlQuery(query) }"
                class="action-link"
                >{{ item.name }}</NuxtLink
              >
              <span class="tabular-nums">{{ item.event_count }}</span>
            </li>
          </ul>
        </RecordSection>
      </div>
      <RecordSection title="Veranstaltungen im Zeitraum">
        <DenseTable
          caption="Veranstaltungen in der Gemeinde / Kommune"
          :rows="data.events.items"
          :columns="eventColumns"
          :row-key="(row) => row.entity_key"
        >
          <template #cell-name="{ row }"
            ><NuxtLink
              :to="{ path: researchHref('event', row.entity_key), query: researchUrlQuery(query) }"
              class="action-link"
              >{{ row.name }}</NuxtLink
            ></template
          >
          <template #cell-start_date="{ row }">{{ researchDate(row.start_date) }}</template>
        </DenseTable>
        <PaginationBar
          :pagination="data.events.pagination"
          @change="apply({ ...query, page: $event })"
        />
        <NuxtLink
          :to="{ path: '/research/events', query: researchUrlQuery({ ...query, page: undefined }) }"
          class="action-link"
          >Alle Veranstaltungen und CSV-Export →</NuxtLink
        >
      </RecordSection>
      <RecordSection title="Orte im Gebiet">
        <ul class="grid gap-2 sm:grid-cols-2">
          <li v-for="venue in data.venues.items" :key="venue.entity_key">
            <NuxtLink
              :to="{
                path: researchHref('venue', venue.entity_key),
                query: researchUrlQuery(query),
              }"
              class="action-link"
              >{{ venue.name }}</NuxtLink
            >
          </li>
        </ul>
        <NuxtLink
          :to="{ path: '/research/venues', query: researchUrlQuery({ ...query, page: undefined }) }"
          class="action-link"
          >Alle Orte im Filter →</NuxtLink
        >
        <NuxtLink
          :to="{
            path: '/research/organizations',
            query: researchUrlQuery({ ...query, page: undefined }),
          }"
          class="action-link ml-3"
          >Alle aktiven Organisationen →</NuxtLink
        >
      </RecordSection>
      <RecordSection v-if="data.area.population" title="Einwohnerzahl">
        <p class="text-2xl font-semibold">
          {{ data.area.population.value.toLocaleString('de-DE') }} Einwohner
        </p>
        <p>
          Stand {{ researchDate(data.area.population.as_of) }} ·
          {{ data.area.population.municipality_name }}
        </p>
        <p class="type-metadata">
          Historischer amtlicher Datenstand; der Gebietsstand kann von der aktuellen OSM-Grenze
          abweichen.
        </p>
        <p class="type-metadata">
          Quelle: ©
          <a
            href="https://www.bkg.bund.de"
            class="action-link"
            target="_blank"
            rel="noopener noreferrer"
            >BKG</a
          >
          ({{ new Date(data.area.population.imported_at).getUTCFullYear() }}) · VG250-EW ·
          <a
            href="https://www.govdata.de/dl-de/by-2-0"
            class="action-link"
            target="_blank"
            rel="noopener noreferrer"
            >dl-de/by-2-0</a
          >
          ·
          <a
            href="https://sgx.geodatenzentrum.de/web_public/gdz/datenquellen/datenquellen_vg_nuts.pdf"
            class="action-link"
            target="_blank"
            rel="noopener noreferrer"
            >Datenquellen</a
          >. Über den amtlichen Gemeindeschlüssel zugeordnet, Zahlen unverändert.
        </p>
      </RecordSection>
      <RecordSection title="Datenstand und Quellen">
        <p>
          Quelle:
          <a
            href="https://www.openstreetmap.org/copyright"
            target="_blank"
            rel="noopener noreferrer"
            class="action-link"
            >© OpenStreetMap-Mitwirkende · ODbL</a
          >
          über nominatim.oklabflensburg.de
        </p>
        <p class="type-metadata">
          Grenze abgerufen: {{ dateTime(data.area.retrieved_at) }} · Inhalt geändert:
          {{ dateTime(data.area.updated_at) }}
        </p>
        <p class="type-metadata">
          Veranstaltungsdaten: Uranus · Rechercheabfrage: {{ dateTime(data.observed_at) }}
        </p>
        <details class="mt-2">
          <summary class="cursor-pointer">Technische Quellenreferenz</summary>
          <a
            :href="`https://www.openstreetmap.org/relation/${data.area.osm_id}`"
            target="_blank"
            rel="noopener noreferrer"
            class="action-link"
            >OSM-Relation {{ data.area.osm_id }}</a
          >
          <p class="type-metadata">
            OSM admin_level {{ data.area.osm_admin_level }} · {{ data.area.region_code }}
          </p>
        </details>
      </RecordSection>
    </template>
  </div>
</template>
