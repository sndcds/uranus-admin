<script setup lang="ts">
import type { ResearchPage, ResearchQuery, ResearchType } from '#shared/contracts'
import { asFailure } from '#shared/errors'
import {
  researchHref,
  researchKey,
  researchLabels,
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
const term = ref('')
const categories = ref<{ id: number; name: string }[]>([])
const optionError = ref('')
const selected = ref('')
const selectedItem = computed(() =>
  data.value?.items.find((item) => researchKey(item) === selected.value),
)
const filterModal = useTemplateRef('filterModal')
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
let timer: ReturnType<typeof setTimeout> | undefined
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
    term.value = query.value.q ?? ''
    if (mounted) void load()
  },
  { immediate: true },
)
watch(term, (value) => {
  clearTimeout(timer)
  if (value === (query.value.q ?? '')) return
  timer = setTimeout(() => {
    void setQuery({ ...query.value, q: value, page: undefined })
  }, 300)
})
const chips = computed(() =>
  Object.entries(query.value)
    .filter(
      ([key, value]) =>
        value !== undefined &&
        value !== '' &&
        !['page', 'page_size', 'sort', 'entity_type'].includes(key),
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
)
function remove(key: string) {
  const next = { ...query.value, page: undefined }
  const filtered = Object.fromEntries(Object.entries(next).filter(([name]) => name !== key))
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
  clearTimeout(timer)
})
const columns = [
  { key: 'name', label: 'Treffer', rowHeader: true },
  { key: 'start_date', label: 'Datum' },
  { key: 'venue_name', label: 'Ort' },
  { key: 'organization_name', label: 'Organisation' },
  { key: 'city', label: 'Stadt' },
  { key: 'status', label: 'Status' },
] as const
</script>
<template>
  <div class="space-y-4">
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
    <label class="block"
      ><span class="sr-only">Treffer durchsuchen</span
      ><input
        v-model="term"
        class="input"
        type="search"
        maxlength="120"
        placeholder="Veranstaltungen, Orte, Organisationen …"
        aria-label="Treffer durchsuchen"
    /></label>
    <p v-if="!parsed.success" role="alert" class="text-sm text-rose-700">
      Die Filter-URL ist ungültig. Bitte setze die Filter zurück.
    </p>
    <div class="hidden lg:block">
      <ResearchFilters :query="query" :categories="categories" :types="!kind" @apply="apply" />
    </div>
    <button class="button lg:hidden" @click="filterModal?.open()">
      <AppIcon name="settings" />Filter öffnen
    </button>
    <AppModal ref="filterModal" title="Recherche filtern"
      ><ResearchFilters :query="query" :categories="categories" :types="!kind" @apply="apply"
    /></AppModal>
    <p v-if="optionError" role="alert" class="type-metadata">{{ optionError }}</p>
    <div class="flex flex-wrap items-center gap-2" aria-label="Aktive Filter">
      <button
        v-for="chip in chips"
        :key="chip.key"
        class="button button-compact"
        :aria-label="`${chip.label} entfernen`"
        @click="remove(chip.key)"
      >
        {{ chip.label }}<AppIcon name="close" :size="14" /></button
      ><button class="action-link" @click="setQuery({})">Alle Filter zurücksetzen</button>
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
          :visible="data.items.length"
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
          <div class="flex gap-1" aria-label="Ergebnisansicht">
            <button
              v-for="choice in [
                { value: 'list', label: 'Liste' },
                { value: 'map', label: 'Karte' },
                { value: 'table', label: 'Tabelle' },
              ]"
              :key="choice.value"
              class="button"
              :aria-pressed="view === choice.value"
              @click="switchView(choice.value)"
            >
              {{ choice.label }}
            </button>
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
          }}</template></DenseTable
        >
        <div
          v-else
          class="grid min-w-0 gap-4"
          :class="
            ['map', 'split'].includes(view) ? 'xl:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]' : ''
          "
        >
          <div class="space-y-2" :class="view === 'map' ? 'hidden xl:block' : ''">
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
            :class="view === 'split' ? 'hidden xl:block' : ''"
            :key="data.observed_at"
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
        <RecordSection v-if="selectedItem" title="Ausgewählter Treffer" surface="panel">
          <div class="grid gap-4 md:grid-cols-[12rem_minmax(0,1fr)_14rem]">
            <img
              v-if="selectedItem.image_url"
              :src="selectedItem.image_url"
              alt=""
              class="max-h-48 w-full rounded-lg object-contain"
              loading="lazy"
              referrerpolicy="no-referrer"
            />
            <div v-else class="hidden place-items-center rounded-lg bg-slate-50 md:grid">
              <AppIcon
                :name="selectedItem.entity_type === 'event' ? 'calendar' : 'pin'"
                :size="40"
              />
            </div>
            <div class="space-y-3">
              <div class="flex flex-wrap gap-2">
                <h3 class="type-section-title">{{ selectedItem.name }}</h3>
                <StatusBadge :label="researchLabels[selectedItem.entity_type]" /><StatusBadge
                  v-if="selectedItem.status"
                  :label="researchStatuses[selectedItem.status]"
                />
              </div>
              <p class="type-body">
                {{ selectedItem.address || selectedItem.venue_name || selectedItem.city }}
              </p>
              <div
                v-if="selectedItem.entity_type === 'event' && selectedItem.description"
                class="max-h-28 overflow-hidden"
              >
                <MarkdownContent :source="selectedItem.description" />
              </div>
              <p v-else class="type-body line-clamp-4">
                {{ selectedItem.description || 'Keine Beschreibung vorhanden.' }}
              </p>
              <NuxtLink
                class="button-primary"
                :to="{
                  path: researchHref(selectedItem.entity_type, selectedItem.entity_key),
                  query: researchUrlQuery({ from_date: query.from_date, to_date: query.to_date }),
                }"
                >Vollständige Details</NuxtLink
              >
            </div>
            <div
              class="flex flex-col items-start gap-1 border-t border-slate-200 pt-3 md:border-l md:border-t-0 md:pl-4 md:pt-0"
            >
              <h4 class="type-row-title">Schnellzugriff</h4>
              <button v-if="selectedItem.location" class="action-link" @click="switchView('map')">
                Auf Karte anzeigen</button
              ><NuxtLink
                v-if="selectedItem.organization_id"
                class="action-link"
                :to="researchHref('organization', selectedItem.organization_id)"
                >Organisation anzeigen</NuxtLink
              ><NuxtLink
                v-if="selectedItem.venue_id"
                class="action-link"
                :to="researchHref('venue', selectedItem.venue_id)"
                >Ort anzeigen</NuxtLink
              ><NuxtLink
                class="action-link"
                :to="researchHref(selectedItem.entity_type, selectedItem.entity_key) + '#timeline'"
                >Änderungszeitpunkte</NuxtLink
              >
            </div>
          </div>
        </RecordSection>
      </template>
    </template>
    <div class="panel flex flex-wrap items-center justify-between gap-3 p-4">
      <p class="type-metadata">
        Alle Filter sind in der URL enthalten. Du kannst diese Recherche als Link teilen.
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
