<script setup lang="ts">
import type { ResearchPage, ResearchQuery, ResearchType } from '#shared/contracts'
import { asFailure } from '#shared/errors'
import {
  researchHref,
  researchKey,
  researchDate,
  researchQuery,
  researchStatuses,
  researchUrlQuery,
} from '~/utils/research'
import { sqlCsv } from '~/utils/sql-csv'
const props = defineProps<{ kind?: ResearchType; map?: boolean }>()
const route = useRoute()
const { $adminApi } = useNuxtApp()
const request = useOperationsRequest<ResearchPage>()
const { data, error, loading } = request
const parsed = computed(() => researchQuery(route.query))
const query = computed<ResearchQuery>(() => ({
  ...(parsed.value.success ? parsed.value.data : {}),
  ...(props.kind ? { entity_type: props.kind } : {}),
}))
const title = computed(() =>
  props.map
    ? 'Karte'
    : props.kind
      ? { event: 'Veranstaltungen', venue: 'Orte', organization: 'Organisationen' }[props.kind]
      : 'Suche',
)
const categories = ref<{ id: number; name: string }[]>([])
const optionError = ref('')
const selected = ref('')
const selectedItem = computed(() =>
  data.value?.items.find((item) => researchKey(item) === selected.value),
)
const filterModal = useTemplateRef('filterModal')
const mapPanel = useTemplateRef('mapPanel')
const view = computed(() =>
  route.query.view === 'table'
    ? 'table'
    : route.query.view === 'list'
      ? 'list'
      : route.query.view === 'map' || props.map
        ? 'map'
        : 'split',
)
const exportBusy = ref(false)
const exportMessage = ref('')
const permalink = ref<string | null>(null)
const selectedPermalink = computed(() => {
  if (!selectedItem.value || !permalink.value) return null
  const url = new URL(
    researchHref(selectedItem.value.entity_type, selectedItem.value.entity_key),
    permalink.value,
  )
  url.search = new URLSearchParams(
    researchUrlQuery({ from_date: query.value.from_date, to_date: query.value.to_date }),
  ).toString()
  return url.href
})
async function showOnMap() {
  await switchView('map')
  await nextTick()
  mapPanel.value?.reveal()
}
let mounted = false
async function load() {
  selected.value = ''
  exportMessage.value = ''
  if (!parsed.value.success) return
  await request.load(JSON.stringify(query.value), () => $adminApi.researchSearch(query.value))
  if (data.value) selected.value = data.value.items[0] ? researchKey(data.value.items[0]) : ''
}
function setQuery(next: ResearchQuery) {
  return navigateTo({
    path: route.path,
    query: {
      ...researchUrlQuery(next),
      ...(route.query.view ? { view: String(route.query.view) } : {}),
    },
  })
}
function apply(next: ResearchQuery) {
  filterModal.value?.close()
  return setQuery(next)
}
function switchView(next: string) {
  return navigateTo({ path: route.path, query: { ...route.query, view: next } })
}
watch(
  () => route.fullPath,
  () => {
    if (mounted) permalink.value = window.location.href
  },
)
watch(
  () => JSON.stringify([parsed.value.success, query.value]),
  () => {
    if (mounted) void load()
  },
  { immediate: true },
)
const chips = computed(() => [
  ...(query.value.from_date || query.value.to_date
    ? [
        {
          key: 'period',
          label: `Zeitraum: ${query.value.from_date?.split('-').reverse().join('.') || 'offen'} – ${query.value.to_date?.split('-').reverse().join('.') || 'offen'}`,
        },
      ]
    : []),
  ...Object.entries(query.value)
    .filter(
      ([key, value]) =>
        value !== undefined &&
        value !== '' &&
        !['page', 'page_size', 'sort', 'entity_type', 'from_date', 'to_date'].includes(key),
    )
    .map(([key, value]) => {
      const labels: Record<string, string> = {
        q: 'Suche',
        from_date: 'Von',
        to_date: 'Bis',
        city: 'Stadt',
        category: 'Kategorie',
        status: 'Status',
        organization_id: 'Organisation',
        venue_id: 'Ort',
      }
      const display =
        key === 'category'
          ? (categories.value.find((c) => c.id === value)?.name ?? `Kategorie ${value}`)
          : key === 'status'
            ? researchStatuses[value as keyof typeof researchStatuses]
            : ['organization_id', 'venue_id'].includes(key)
              ? 'ausgewählt'
              : String(value)
      return { key, label: `${labels[key]}: ${display}` }
    }),
])
function remove(key: string) {
  const next = { ...query.value, page: undefined }
  const filtered = Object.fromEntries(
    Object.entries(next).filter(([name]) =>
      key === 'period' ? !['from_date', 'to_date'].includes(name) : name !== key,
    ),
  )
  return setQuery(filtered)
}
async function exportCsv() {
  if (exportBusy.value) return
  exportBusy.value = true
  exportMessage.value = ''
  const selection = JSON.stringify(query.value)
  try {
    const result = await $adminApi.researchExport(query.value)
    if (!mounted || selection !== JSON.stringify(query.value)) return
    const blob = new Blob(['\ufeff' + sqlCsv(result.columns, result.rows)], {
      type: 'text/csv;charset=utf-8',
    })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'kulturbytes-recherche.csv'
    a.click()
    setTimeout(() => URL.revokeObjectURL(url), 1000)
    exportMessage.value = `${result.total} Treffer exportiert.`
  } catch (cause) {
    if (mounted && selection === JSON.stringify(query.value))
      exportMessage.value = asFailure(cause).message
  } finally {
    if (mounted) exportBusy.value = false
  }
}
onMounted(() => {
  mounted = true
  permalink.value = window.location.href
  void load()
  void $adminApi
    .researchOptions()
    .then((result) => {
      if (mounted) categories.value = result.categories
    })
    .catch(() => {
      if (mounted) optionError.value = 'Kategorieauswahl konnte nicht geladen werden.'
    })
})
onBeforeUnmount(() => {
  mounted = false
})
const columns = [
  { key: 'name', label: 'Treffer', rowHeader: true },
  { key: 'start_date', label: 'Datum', width: '11%' },
  { key: 'venue_name', label: 'Ort', width: '15%' },
  { key: 'organization_name', label: 'Organisation', width: '20%' },
  { key: 'city', label: 'Stadt', width: '13%' },
  { key: 'status', label: 'Status', width: '11%' },
] as const
</script>
<template>
  <div class="space-y-3">
    <PageHeader
      :title="title"
      description="Finde Veranstaltungen, Orte und Organisationen in der Kulturregion."
      compact-actions
    >
      <template #actions
        ><button
          class="button"
          :disabled="loading || exportBusy || !parsed.success"
          @click="exportCsv"
        >
          <AppIcon name="download" />{{ exportBusy ? 'Export läuft …' : 'CSV exportieren' }}</button
        ><CopyValueButton
          :value="permalink"
          label="Recherche-Link"
          button-text="Link kopieren"
          variant="button"
      /></template>
    </PageHeader>
    <p v-if="exportMessage" role="status" class="type-metadata">{{ exportMessage }}</p>
    <p v-if="!parsed.success" role="alert" class="text-sm text-rose-700">
      Die Filter-URL ist ungültig. Bitte setze die Filter zurück.
    </p>
    <div class="hidden lg:block">
      <ResearchFilters
        compact
        :query="query"
        :categories="categories"
        :types="!kind"
        @apply="apply"
      />
    </div>
    <button class="button lg:hidden" @click="filterModal?.open()">
      <AppIcon name="filter" />Filter öffnen
    </button>
    <AppModal ref="filterModal" title="Recherche filtern"
      ><ResearchFilters :query="query" :categories="categories" :types="!kind" @apply="apply"
    /></AppModal>
    <p v-if="optionError" role="alert" class="type-metadata">{{ optionError }}</p>
    <div class="flex flex-wrap items-center gap-2" aria-label="Aktive Filter">
      <button
        v-for="chip in chips"
        :key="chip.key"
        class="research-chip"
        :aria-label="`${chip.label} entfernen`"
        @click="remove(chip.key)"
      >
        <span>{{ chip.label }}<AppIcon name="close" :size="14" /></span></button
      ><button class="action-link text-xs font-normal" @click="setQuery({})">
        Alle Filter zurücksetzen
      </button>
    </div>
    <RequestState
      :loading="loading"
      :error="error"
      :has-data="!!data"
      :last-success="data?.observed_at"
      @retry="load"
    />
    <template v-if="data && parsed.success">
      <div class="flex flex-wrap items-end justify-between gap-3">
        <ResultSummary
          :total="data.pagination.total"
          class="research-result-summary"
          noun="Ergebnisse"
        />
        <div class="flex flex-wrap gap-2">
          <label class="sr-only" for="research-sort">Sortierung</label
          ><select
            id="research-sort"
            class="input w-auto"
            :value="query.sort || 'date'"
            @change="
              setQuery({
                ...query,
                sort: ($event.target as HTMLSelectElement).value as 'date' | 'name',
                page: undefined,
              })
            "
          >
            <option value="date">Datum (aufsteigend)</option>
            <option value="name">Name (A–Z)</option>
          </select>
          <div
            v-for="screen in ['mobile', 'desktop']"
            :key="screen"
            :class="screen === 'mobile' ? 'xl:hidden' : 'hidden xl:block'"
          >
            <div class="research-toggle" aria-label="Ergebnisansicht">
              <button
                v-for="choice in [
                  { value: 'list', label: 'Liste', icon: 'list' as const },
                  { value: 'map', label: 'Karte', icon: 'map' as const },
                  { value: 'table', label: 'Tabelle', icon: 'table' as const },
                ]"
                :key="choice.value"
                :aria-pressed="
                  view === choice.value ||
                  (view === 'split' && choice.value === (screen === 'mobile' ? 'list' : 'map'))
                "
                @click="switchView(choice.value)"
              >
                <AppIcon :name="choice.icon" :size="17" />{{ choice.label }}
              </button>
            </div>
          </div>
        </div>
      </div>
      <EmptyState
        v-if="!data.items.length"
        message="Keine Treffer für diese Filter. Ändere den Zeitraum oder entferne einzelne Filter."
      />
      <template v-else>
        <DenseTable
          v-if="view === 'table'"
          class="research-results-table"
          caption="Recherche-Ergebnisse"
          :columns="columns"
          :rows="data.items"
          :row-key="researchKey"
          ><template #cell-name="{ row }"
            ><NuxtLink
              :to="{
                path: researchHref(row.entity_type, row.entity_key),
                query: researchUrlQuery({ from_date: query.from_date, to_date: query.to_date }),
              }"
              >{{ row.name }}</NuxtLink
            ></template
          ><template #cell-status="{ row }">{{
            row.status ? researchStatuses[row.status] : '—'
          }}</template>
          <template #actions="{ row }">
            <button
              class="research-icon-button text-blue-700"
              :aria-label="`Vorschau: ${row.name}`"
              :aria-pressed="selected === researchKey(row)"
              @click="selected = researchKey(row)"
            >
              <AppIcon name="next" :size="17" />
            </button>
          </template>
        </DenseTable>
        <div
          v-else
          class="grid min-w-0 items-start gap-3"
          :class="
            ['map', 'split'].includes(view) ? 'xl:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]' : ''
          "
        >
          <div
            class="space-y-2"
            :class="[
              view === 'map' ? 'hidden xl:block' : '',
              ['map', 'split'].includes(view) ? 'xl:max-h-[29rem] xl:overflow-y-auto xl:pr-1' : '',
            ]"
          >
            <ResearchResult
              v-for="item in data.items"
              :key="researchKey(item)"
              :item="item"
              :query="query"
              :selected="selected === researchKey(item)"
              @select="selected = researchKey(item)"
            />
          </div>
          <ResearchMap
            v-if="view === 'map' || view === 'split'"
            :key="data.observed_at"
            ref="mapPanel"
            :class="view === 'split' ? 'hidden xl:block' : ''"
            :items="data.items"
            :selected="selected"
            @select="selected = $event"
          />
        </div>
        <PaginationBar
          :pagination="data.pagination"
          :loading="loading"
          @change="setQuery({ ...query, page: $event })"
        />
        <section
          v-if="selectedItem"
          class="rounded-lg border border-slate-200 p-4"
          aria-label="Ausgewählter Treffer"
        >
          <div
            class="grid items-start gap-5"
            :class="
              selectedItem.image_url
                ? 'lg:grid-cols-[12rem_minmax(0,1fr)_13rem]'
                : 'lg:grid-cols-[minmax(0,1fr)_13rem]'
            "
          >
            <img
              v-if="selectedItem.image_url"
              :src="selectedItem.image_url"
              alt=""
              class="h-44 w-full rounded-md object-cover sm:w-40 lg:h-48 lg:w-full"
              loading="lazy"
              referrerpolicy="no-referrer"
            />
            <div class="min-w-0 space-y-3">
              <div class="flex flex-wrap items-center gap-2">
                <h3 class="mr-2 text-xl font-semibold">{{ selectedItem.name }}</h3>
                <ResearchBadges :item="selectedItem" />
              </div>
              <div class="flex flex-wrap gap-x-6 gap-y-3 text-xs text-slate-600">
                <div v-if="selectedItem.entity_type === 'event'" class="flex items-start gap-2">
                  <AppIcon name="calendar" class="shrink-0" :size="18" />
                  <div>
                    <p class="font-medium text-slate-800">
                      {{ researchDate(selectedItem.start_date) }}
                    </p>
                    <p class="mt-1">
                      {{
                        selectedItem.all_day
                          ? 'Ganztägig'
                          : selectedItem.start_time
                            ? selectedItem.start_time.slice(0, 5) +
                              (selectedItem.end_time
                                ? ' – ' + selectedItem.end_time.slice(0, 5)
                                : '')
                            : 'Uhrzeit unbekannt'
                      }}
                    </p>
                  </div>
                </div>
                <div
                  v-if="selectedItem.venue_name || selectedItem.address || selectedItem.city"
                  class="flex items-start gap-2"
                >
                  <AppIcon name="pin" class="shrink-0" :size="18" />
                  <div>
                    <p class="font-medium text-slate-800">
                      {{ selectedItem.venue_name || selectedItem.city }}
                    </p>
                    <p class="mt-1">{{ selectedItem.address }}</p>
                  </div>
                </div>
                <div v-if="selectedItem.organization_name" class="flex items-start gap-2">
                  <AppIcon name="organization" class="shrink-0" :size="18" />
                  <p class="font-medium text-slate-800">{{ selectedItem.organization_name }}</p>
                </div>
              </div>
              <div
                v-if="selectedItem.entity_type === 'event' && selectedItem.description"
                class="research-preview-description max-h-24 overflow-hidden"
              >
                <MarkdownContent :source="selectedItem.description" />
              </div>
              <p v-else class="type-body line-clamp-3">
                {{ selectedItem.description || 'Keine Beschreibung vorhanden.' }}
              </p>
              <div class="flex flex-wrap gap-2">
                <NuxtLink
                  class="button-primary"
                  :to="{
                    path: researchHref(selectedItem.entity_type, selectedItem.entity_key),
                    query: researchUrlQuery({ from_date: query.from_date, to_date: query.to_date }),
                  }"
                  ><AppIcon name="external" :size="17" />Vollständige Details</NuxtLink
                >
                <button v-if="selectedItem.location" class="button" @click="showOnMap">
                  <AppIcon name="map" :size="17" />Auf Karte anzeigen
                </button>
                <CopyValueButton
                  :value="selectedPermalink"
                  label="Treffer-Link"
                  button-text="Teilen"
                  variant="button"
                />
              </div>
            </div>
            <nav
              class="research-quick-links border-t border-slate-200 pt-3 lg:border-l lg:border-t-0 lg:pl-4 lg:pt-0"
              aria-label="Schnellzugriff zum Treffer"
            >
              <h4 class="mb-2 text-sm font-semibold">Schnellzugriff</h4>
              <NuxtLink
                v-if="selectedItem.organization_id"
                :to="researchHref('organization', selectedItem.organization_id)"
                ><AppIcon name="organization" :size="16" />Organisation anzeigen<AppIcon
                  name="next"
                  :size="14"
              /></NuxtLink>
              <NuxtLink
                v-if="selectedItem.venue_id"
                :to="researchHref('venue', selectedItem.venue_id)"
                ><AppIcon name="pin" :size="16" />Ort anzeigen<AppIcon name="next" :size="14"
              /></NuxtLink>
              <NuxtLink
                v-if="selectedItem.venue_id"
                :to="{
                  path: '/research/events',
                  query: researchUrlQuery({
                    from_date: query.from_date,
                    to_date: query.to_date,
                    venue_id: selectedItem.venue_id,
                  }),
                }"
                ><AppIcon name="calendar" :size="16" />Weitere Events am Ort<AppIcon
                  name="next"
                  :size="14"
              /></NuxtLink>
              <NuxtLink
                :to="researchHref(selectedItem.entity_type, selectedItem.entity_key) + '#timeline'"
                ><AppIcon name="history" :size="16" />Änderungszeitpunkte<AppIcon
                  name="next"
                  :size="14"
              /></NuxtLink>
            </nav>
          </div>
        </section>
      </template>
    </template>
    <div class="research-info">
      <p class="flex items-start gap-3 text-sm">
        <AppIcon name="info" class="shrink-0 text-blue-600" /><span>
          Alle Filter sind in der URL enthalten. Du kannst diese Recherche als Link teilen.
        </span>
      </p>
      <CopyValueButton
        :value="permalink"
        label="Filter-Link"
        button-text="Link kopieren"
        variant="button"
      />
    </div>
  </div>
</template>

<style scoped>
@reference '../assets/css/main.css';
.research-results-table :deep(.operations-table) {
  @apply text-xs;
}
.research-results-table :deep(tbody tr:has(button[aria-pressed='true'])) {
  @apply bg-blue-50;
}
.research-results-table :deep(tbody tr:hover) {
  @apply bg-blue-50/50;
}
.research-results-table :deep(tbody th a) {
  @apply inline-flex min-h-11 items-center font-semibold text-blue-950 hover:underline;
}
@media (min-width: 640px) {
  .research-results-table :deep(tbody :is(th, td)) {
    @apply px-3 py-0;
  }
  .research-results-table :deep(thead th) {
    @apply bg-slate-50 py-2 font-medium;
  }
  .research-results-table :deep(col:last-child) {
    width: 5rem;
  }
}

.research-result-summary :deep(p.font-semibold) {
  @apply text-lg;
}
.research-preview-description :deep(.prose-admin) {
  @apply text-sm leading-6;
}
.research-preview-description :deep(.prose-admin > * + *) {
  @apply mt-2;
}
.research-quick-links a {
  @apply grid min-h-11 grid-cols-[1rem_minmax(0,1fr)_0.875rem] items-center gap-2 rounded text-xs text-slate-600 hover:text-blue-700;
}
</style>
