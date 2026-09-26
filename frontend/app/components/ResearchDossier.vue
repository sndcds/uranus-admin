<script setup lang="ts">
import type { ResearchDetail, ResearchQuery, ResearchType, ResearchRecord } from '#shared/contracts'
import {
  researchDate,
  researchHref,
  researchLabels,
  researchQuery,
  researchSections,
  researchStatuses,
  researchUrlQuery,
} from '~/utils/research'
import { dateTime } from '~/utils/presentation'
import { z } from '#shared/zod'
const props = defineProps<{ kind: ResearchType }>()
const route = useRoute()
const { $adminApi } = useNuxtApp()
const { data, loading, error, load } = useOperationsRequest<ResearchDetail>()
const parsed = computed(() => researchQuery(route.query))
const query = computed<ResearchQuery>(() => (parsed.value.success ? parsed.value.data : {}))
const identifier = computed(() => z.uuid().safeParse(route.params.id))
const selected = ref('')
const permalink = ref<string | null>(null)
const filterModal = useTemplateRef('filterModal')
const optionsError = ref(false)
const categories = ref<{ id: number; name: string }[]>([])
let mounted = false
async function refresh() {
  if (!identifier.value.success || !parsed.value.success) return
  const id = identifier.value.data
  await load(JSON.stringify([id, props.kind, query.value]), () =>
    $adminApi.researchDetail(researchSections[props.kind], id, query.value),
  )
}
function apply(next: ResearchQuery) {
  filterModal.value?.close()
  return navigateTo({ path: route.path, query: researchUrlQuery(next), hash: route.hash })
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
    .then((r) => {
      if (mounted) categories.value = r.categories
    })
    .catch(() => {
      if (mounted) optionsError.value = true
    })
})
onBeforeUnmount(() => {
  mounted = false
})
const points = computed<ResearchRecord[]>(() => {
  if (!data.value) return []
  if (props.kind !== 'event') return [data.value.item, ...data.value.events.items]
  const venues = new Map<string, ResearchRecord>()
  for (const date of data.value.dates.items) {
    if (date.venue_id && date.venue_name)
      venues.set(date.venue_id, {
        ...data.value.item,
        entity_type: 'venue',
        entity_key: date.venue_id,
        name: date.venue_name,
        address: date.address,
        city: date.city,
        location: date.location,
        status: null,
        image_url: null,
        event_count: null,
      })
  }
  return [...venues.values()]
})
const dateColumns = [
  { key: 'start_date', label: 'Datum', rowHeader: true },
  { key: 'start_time', label: 'Uhrzeit' },
  { key: 'venue_name', label: 'Ort' },
  { key: 'space_name', label: 'Raum' },
  { key: 'status', label: 'Status' },
] as const
const eventColumns = [
  { key: 'name', label: 'Veranstaltung', rowHeader: true },
  { key: 'start_date', label: 'Datum' },
  { key: 'start_time', label: 'Uhrzeit' },
  { key: 'venue_name', label: 'Ort' },
  { key: 'organization_name', label: 'Organisation' },
  { key: 'status', label: 'Status' },
] as const
const monthMaximum = computed(() =>
  Math.max(1, ...(data.value?.months.map((item) => item.event_count) || [])),
)
const monthColumns = [
  { key: 'month', label: 'Monat', rowHeader: true },
  { key: 'event_count', label: 'Veranstaltungen' },
] as const
</script>
<template>
  <div class="research-dossier record-detail">
    <NuxtLink :to="`/research/${researchSections[kind]}`" class="action-link"
      >←
      {{
        { event: 'Veranstaltungen', venue: 'Orte', organization: 'Organisationen' }[kind]
      }}</NuxtLink
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
        :title="data.item.name"
        :description="researchLabels[kind]"
        record
        compact-actions
      >
        <template #badge><ResearchBadges :item="data.item" /></template>
        <template #actions
          ><CopyValueButton
            :value="permalink"
            label="Dossier-Link"
            button-text="Link kopieren"
            variant="button"
          /><button class="button" @click="filterModal?.open()">
            <AppIcon name="calendar" />Zeitraum und Filter
          </button></template
        >
      </PageHeader>
      <AppModal ref="filterModal" title="Dossier filtern">
        <p v-if="optionsError" role="status">Kategorien konnten nicht geladen werden.</p>
        <ResearchFilters :query="query" :categories="categories" @apply="apply"
      /></AppModal>
      <p class="type-metadata">
        {{
          query.from_date || query.to_date
            ? `Zeitraum: ${query.from_date || 'offen'} bis ${query.to_date || 'offen'}`
            : 'Alle vorhandenen Termine'
        }}
        · {{ data.events.timezone
        }}<button v-if="Object.keys(query).length" class="action-link ml-3" @click="apply({})">
          Filter zurücksetzen
        </button>
      </p>
      <div class="research-dossier-grid">
        <div
          class="research-overview-row grid items-start gap-3 xl:grid-cols-[minmax(0,1.8fr)_minmax(0,1fr)]"
        >
          <RecordSection
            title="Überblick"
            surface="plain"
            class="research-section research-overview"
          >
            <div
              class="grid items-start gap-5"
              :class="data.item.image_url ? 'sm:grid-cols-[minmax(0,0.9fr)_minmax(0,1.2fr)]' : ''"
            >
              <img
                v-if="data.item.image_url"
                :src="data.item.image_url"
                alt=""
                class="max-h-[28rem] w-full rounded-md object-cover"
                loading="lazy"
                referrerpolicy="no-referrer"
              />
              <div class="space-y-4">
                <MarkdownContent
                  v-if="kind === 'event' && data.item.description"
                  :source="data.item.description"
                />
                <p v-else class="type-body whitespace-pre-line">
                  {{ data.item.description || 'Keine Beschreibung vorhanden.' }}
                </p>
                <CompactFacts
                  :items="[
                    { label: 'Sprache des Inhalts', value: data.item.language },
                    { label: 'Adresse', value: data.item.address },
                    ...(kind === 'event'
                      ? []
                      : [
                          {
                            label: 'Veranstaltungen im Filter',
                            value: data.events.pagination.total,
                          },
                        ]),
                  ]"
                />
              </div>
            </div>
          </RecordSection>
          <div class="research-context research-section space-y-4 bg-slate-50/50">
            <RecordSection v-if="data.item.organization_id" title="Organisation" surface="plain"
              ><NuxtLink
                :to="{
                  path: researchHref('organization', data.item.organization_id),
                  query: researchUrlQuery({ from_date: query.from_date, to_date: query.to_date }),
                }"
                class="action-link"
                >{{ data.item.organization_name }}</NuxtLink
              ></RecordSection
            >
            <RecordSection
              v-if="data.item.venue_id"
              title="Ort des ersten öffentlichen Termins"
              surface="plain"
              ><NuxtLink :to="researchHref('venue', data.item.venue_id)" class="action-link">{{
                data.item.venue_name
              }}</NuxtLink>
              <p class="type-body">{{ data.item.address }}</p>
              <p v-if="data.item.space_name" class="type-metadata">
                Raum: {{ data.item.space_name }}
              </p></RecordSection
            >
            <RecordSection title="Schnellzugriff" surface="plain">
              <div class="flex flex-col items-start">
                <a href="#research-events" class="action-link research-context-link"
                  ><AppIcon name="calendar" />{{ kind === 'event' ? 'Termine' : 'Veranstaltungen'
                  }}<AppIcon name="next" :size="14" /></a
                ><a href="#relations" class="action-link research-context-link"
                  ><AppIcon name="graph" />Beziehungen<AppIcon name="next" :size="14" /></a
                ><a href="#timeline" class="action-link research-context-link"
                  ><AppIcon name="history" />Änderungszeitpunkte<AppIcon
                    name="next"
                    :size="14" /></a
                ><NuxtLink
                  :to="{
                    path: '/research/events',
                    query: researchUrlQuery({
                      ...query,
                      ...(kind === 'venue'
                        ? { venue_id: data.item.entity_key }
                        : kind === 'organization'
                          ? { organization_id: data.item.entity_key }
                          : { organization_id: data.item.organization_id || undefined }),
                      page: undefined,
                    }),
                  }"
                  class="action-link"
                  >Weitere Veranstaltungen recherchieren →</NuxtLink
                >
              </div>
            </RecordSection>
          </div>
        </div>
        <div
          class="research-dossier-events grid min-w-0 items-start gap-3"
          :class="points.length ? 'xl:grid-cols-[minmax(0,1.8fr)_minmax(0,1fr)]' : ''"
        >
          <RecordSection
            id="research-events"
            class="research-section"
            :title="kind === 'event' ? 'Termine' : 'Veranstaltungen'"
            surface="plain"
          >
            <template #icon><AppIcon name="calendar" class="text-blue-600" /></template>
            <template v-if="kind === 'event'"
              ><p class="type-metadata">
                {{ data.dates.pagination.total }} öffentliche Termine im Filter. Abweichende Orte
                und Räume stehen direkt am Termin.
              </p>
              <DenseTable
                caption="Veranstaltungstermine"
                :rows="data.dates.items"
                :columns="dateColumns"
                :row-key="(row) => row.id"
                ><template #cell-start_date="{ row }">{{ researchDate(row.start_date) }}</template
                ><template #cell-start_time="{ row }"
                  >{{ row.all_day ? 'Ganztägig' : row.start_time?.slice(0, 5) || 'Unbekannt'
                  }}<span v-if="row.end_time"> – {{ row.end_time.slice(0, 5) }}</span></template
                ><template #cell-venue_name="{ row }"
                  ><NuxtLink v-if="row.venue_id" :to="researchHref('venue', row.venue_id)">{{
                    row.venue_name
                  }}</NuxtLink
                  ><span v-else>Unbekannt</span></template
                ><template #cell-status="{ row }"
                  ><StatusBadge
                    :label="researchStatuses[row.status]"
                    :tone="
                      row.status === 'released'
                        ? 'success'
                        : row.status === 'cancelled'
                          ? 'error'
                          : 'warning'
                    " /></template></DenseTable
              ><PaginationBar
                :pagination="data.dates.pagination"
                :loading="loading"
                @change="apply({ ...query, page: $event })"
            /></template>
            <template v-else
              ><ResultSummary
                :total="data.events.pagination.total"
                :visible="data.events.items.length"
                noun="Veranstaltungen" /><EmptyState
                v-if="!data.events.items.length"
                message="Keine Veranstaltungen im gewählten Filter."
                compact /><DenseTable
                v-else
                caption="Veranstaltungen im Filter"
                :rows="data.events.items"
                :columns="eventColumns"
                :row-key="(row) => row.entity_key"
              >
                <template #cell-name="{ row }">
                  <NuxtLink
                    :to="{
                      path: researchHref('event', row.entity_key),
                      query: researchUrlQuery({
                        from_date: query.from_date,
                        to_date: query.to_date,
                      }),
                    }"
                    class="action-link"
                    >{{ row.name }}</NuxtLink
                  >
                </template>
                <template #cell-start_date="{ row }">{{ researchDate(row.start_date) }}</template>
                <template #cell-start_time="{ row }">{{
                  row.all_day ? 'Ganztägig' : row.start_time?.slice(0, 5) || 'Unbekannt'
                }}</template>
                <template #cell-status="{ row }"
                  ><StatusBadge
                    v-if="row.status"
                    :label="researchStatuses[row.status]"
                    :tone="
                      row.status === 'released'
                        ? 'success'
                        : row.status === 'cancelled'
                          ? 'error'
                          : 'warning'
                    "
                /></template> </DenseTable
              ><PaginationBar
                :pagination="data.events.pagination"
                :loading="loading"
                @change="apply({ ...query, page: $event })"
            /></template>
          </RecordSection>
          <RecordSection
            v-if="points.length"
            :title="kind === 'event' ? 'Veranstaltungsorte' : 'Karte'"
            class="research-section research-dossier-map"
          >
            <template #icon><AppIcon name="pin" class="text-blue-600" /></template>
            <ResearchMap
              :key="data.observed_at"
              :items="points"
              :selected="selected"
              @select="selected = $event"
            />
          </RecordSection>
        </div>
        <RecordSection
          v-if="kind !== 'event'"
          title="Aktivität nach Monat"
          class="research-section"
          surface="plain"
          description="Unterschiedliche Veranstaltungen je Terminmonat, bis zu 120 belegte Monate. Eine Veranstaltung mit Terminen in mehreren Monaten zählt in jedem dieser Monate."
        >
          <template #icon><AppIcon name="chart" class="text-blue-600" /></template>
          <div v-if="data.months.length" class="overflow-x-auto">
            <div
              class="flex h-44 items-end gap-3 border-b border-slate-200 pt-6"
              aria-label="Veranstaltungen je belegtem Monat"
            >
              <div
                v-for="month in data.months"
                :key="month.month"
                class="flex h-full min-w-12 flex-1 flex-col items-center justify-end gap-1 text-xs text-slate-600"
              >
                <span class="tabular-nums">{{ month.event_count }}</span>
                <div
                  class="w-full max-w-12 rounded-t-sm bg-blue-300"
                  :style="{ height: `${(month.event_count / monthMaximum) * 70}%` }"
                  aria-hidden="true"
                />
                <span class="whitespace-nowrap pb-2">{{ month.month.slice(0, 7) }}</span>
              </div>
            </div>
          </div>
          <p v-else class="type-metadata">Keine belegten Monate im Filter.</p>
          <details>
            <summary class="action-link cursor-pointer">Alle Monatswerte</summary>
            <DenseTable
              caption="Veranstaltungen pro Monat"
              :columns="monthColumns"
              :rows="data.months"
              :row-key="(row) => row.month"
              ><template #cell-month="{ row }">{{ row.month.slice(0, 7) }}</template></DenseTable
            >
          </details>
        </RecordSection>
        <RecordSection
          v-if="kind !== 'event'"
          title="Nutzung im gewählten Zeitraum"
          class="research-section"
          surface="plain"
          description="Bis zu zehn häufigste Orte, Veranstalter und Kategorien. Die Zahlen berücksichtigen alle passenden Termine, unabhängig von der sichtbaren Seite."
        >
          <template #icon><AppIcon name="tag" class="text-blue-600" /></template>
          <div class="grid gap-5">
            <section
              v-for="group in [
                { kind: 'venue', label: 'Genutzte Orte' },
                { kind: 'organization', label: 'Veranstalter' },
                { kind: 'category', label: 'Kategorien' },
              ] as const"
              :key="group.kind"
              class="space-y-2"
            >
              <h4 class="type-row-title">{{ group.label }}</h4>
              <ul class="space-y-1">
                <li
                  v-for="entry in data.usage.filter((item) => item.kind === group.kind)"
                  :key="entry.key"
                  class="flex items-baseline justify-between gap-2 text-sm"
                >
                  <NuxtLink
                    v-if="entry.kind !== 'category'"
                    :to="researchHref(entry.kind, entry.key)"
                    class="action-link"
                    >{{ entry.name }}</NuxtLink
                  ><span v-else>{{ entry.name }}</span
                  ><span>{{ entry.event_count }}</span>
                </li>
              </ul>
              <p v-if="!data.usage.some((item) => item.kind === group.kind)" class="type-metadata">
                Keine belegte Nutzung im Filter.
              </p>
            </section>
          </div>
        </RecordSection>
        <ResearchRelations
          id="relations"
          class="research-section research-dossier-relations"
          :detail="data"
        />
        <RecordSection
          id="timeline"
          title="Timeline / Änderungen"
          class="research-section"
          surface="plain"
          description="Die Quelle liefert Anlagezeit und letzten Änderungszeitpunkt. Eine vollständige Änderungshistorie und frühere Feldwerte sind nicht verfügbar."
        >
          <template #icon><AppIcon name="clock" class="text-blue-600" /></template>
          <ol class="research-timeline space-y-5 border-l-2 border-blue-100 pl-5">
            <li>
              <p class="type-row-title">Datensatz angelegt</p>
              <p class="type-metadata">
                {{ data.item.created_at ? dateTime(data.item.created_at) : 'Zeitpunkt unbekannt' }}
              </p>
            </li>
            <li>
              <p class="type-row-title">Zuletzt aktualisiert</p>
              <p class="type-metadata">
                {{
                  data.item.modified_at
                    ? dateTime(data.item.modified_at)
                    : 'Kein Änderungszeitpunkt vorhanden'
                }}
              </p>
              <p class="type-body">Welche Felder geändert wurden, ist nicht belegt.</p>
            </li>
          </ol>
        </RecordSection>
        <RecordSection title="Datenstand / Quellen" surface="plain" class="research-section">
          <template #icon><AppIcon name="database" class="text-blue-600" /></template>
          <CompactFacts
            :items="[
              { label: 'Quelle', value: 'Kulturbytes / Uranus' },
              { label: 'Daten abgerufen', value: dateTime(data.observed_at) },
              {
                label: 'Letzte Aktualisierung der Quelle',
                value: data.item.modified_at ? dateTime(data.item.modified_at) : null,
              },
            ]"
          /><a
            v-if="data.item.source_url"
            :href="data.item.source_url"
            target="_blank"
            rel="noopener noreferrer"
            referrerpolicy="no-referrer"
            class="action-link"
            >Original-Link öffnen <AppIcon name="external" /><span class="sr-only"
              >(neuer Tab)</span
            ></a
          >
          <p v-else class="type-metadata">Kein sicherer Original-Link vorhanden.</p>
          <ul class="type-metadata list-disc pl-5">
            <li v-if="!data.item.description">Beschreibung fehlt.</li>
            <li v-if="kind === 'event' && !data.item.categories.length">
              Keine Kategorie zugeordnet.
            </li>
            <li v-if="!points.some((item) => item.location)">
              Für die sichtbare Auswahl sind keine Koordinaten verfügbar.
            </li>
            <li>Fehlende Werte sind unbekannt; interne Qualitätsbefunde werden nicht verwendet.</li>
          </ul>
          <details class="type-metadata">
            <summary class="cursor-pointer py-2">Technische Referenz</summary>
            <p class="break-all">UUID: {{ data.item.entity_key }}</p>
          </details></RecordSection
        >
      </div>
    </template>
  </div>
</template>

<style scoped>
@reference '../assets/css/main.css';
.research-dossier-grid {
  @apply grid min-w-0 gap-3 xl:grid-cols-2;
}
.research-overview-row,
.research-dossier-events,
.research-dossier-relations {
  @apply xl:col-span-2;
}
.research-section {
  @apply min-w-0 rounded-lg border border-slate-200 p-4;
}
.research-dossier .research-section :deep(.type-section-title) {
  @apply text-base;
}
.research-dossier .research-overview :deep(> header .type-section-title) {
  @apply text-xs font-medium uppercase tracking-wide text-slate-500;
}
.research-context > .section-plain {
  @apply space-y-1;
}
.research-context .research-context-link {
  @apply grid w-full grid-cols-[1.25rem_minmax(0,1fr)_1rem] gap-2;
}
.research-context > .section-plain + .section-plain {
  @apply border-t border-slate-200 pt-4;
}
.research-dossier-map :deep(.research-map) {
  @apply border-0;
}
.research-dossier-map :deep(.candidate-map-canvas) {
  height: 20rem;
}
.research-dossier .research-context :deep(.type-section-title) {
  @apply text-sm font-semibold;
}
.research-dossier .research-context :deep(.action-link) {
  @apply text-sm font-normal;
}
.research-timeline li {
  @apply relative;
}
.research-timeline li::before {
  content: '';
  @apply absolute -left-[1.6875rem] top-1 h-3 w-3 rounded-full border-2 border-white bg-blue-500;
}
</style>
