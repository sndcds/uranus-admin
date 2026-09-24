<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { inboxFiltersSchema, type InboxFilters, type InboxPage } from '#shared/contracts'
import { asFailure, type ApiFailure } from '#shared/errors'
import { adminDateTime } from '~/utils/admin-time'

const route = useRoute()
const router = useRouter()
const { $adminApi } = useNuxtApp()
const data = ref<InboxPage | null>(null)
const loading = ref(false)
const error = ref<ApiFailure | null>(null)
const invalidQuery = ref(false)
const scope = ref<InboxFilters['scope']>('all')
const attention = ref<InboxFilters['attention']>('all')
const kind = ref<InboxFilters['kind']>()
const entityType = ref('')
let revision = 0

let dataQuery = ''
const countShortcuts = [
  { key: 'critical', label: 'Kritisch', filter: { attention: 'critical' }, tone: 'text-rose-700' },
  { key: 'mine', label: 'Meine', filter: { scope: 'mine' }, tone: 'text-slate-900' },
  {
    key: 'unassigned',
    label: 'Nicht zugewiesen',
    filter: { scope: 'unassigned' },
    tone: 'text-slate-900',
  },
  {
    key: 'due_today',
    label: 'Heute fällig',
    filter: { attention: 'due_today' },
    tone: 'text-amber-800',
  },
  { key: 'overdue', label: 'Überfällig', filter: { attention: 'overdue' }, tone: 'text-rose-700' },
  {
    key: 'snoozed',
    label: 'Wiedervorlagen',
    filter: { attention: 'snoozed' },
    tone: 'text-slate-900',
  },
] as const
function routeFilters(): InboxFilters | null {
  const parsed = inboxFiltersSchema.safeParse(route.query)
  return parsed.success ? parsed.data : null
}
const appliedFilters = computed(routeFilters)
function selected(filter: Partial<InboxFilters>) {
  return Object.entries(filter).every(
    ([key, value]) => appliedFilters.value?.[key as keyof InboxFilters] === value,
  )
}
async function load() {
  const current = ++revision
  const filters = routeFilters()
  error.value = null
  invalidQuery.value = !filters
  if (!filters) {
    data.value = null
    loading.value = false
    return
  }
  scope.value = filters.scope
  attention.value = filters.attention
  kind.value = filters.kind
  entityType.value = filters.entity_type ?? ''
  const query = JSON.stringify(filters)
  if (dataQuery !== query) data.value = null
  loading.value = true
  error.value = null
  try {
    const value = await $adminApi.inbox(filters)
    if (current === revision) {
      data.value = value
      dataQuery = query
    }
  } catch (cause) {
    if (current === revision) {
      error.value = asFailure(cause)
      if ([401, 403].includes(error.value.status)) data.value = null
    }
  } finally {
    if (current === revision) loading.value = false
  }
}

function applyFilters() {
  return apply({
    scope: scope.value,
    attention: attention.value,
    kind: kind.value,
    entity_type: entityType.value || undefined,
  })
}

function resetFilters() {
  return router.push({ query: {} })
}

function apply(changes: Partial<InboxFilters>) {
  const current = routeFilters() ?? inboxFiltersSchema.parse({})
  const next = { ...current, ...changes, page: changes.page ?? 1 }
  return router.push({
    query: Object.fromEntries(
      Object.entries(next).filter(
        ([key, value]) =>
          value !== undefined &&
          !((key === 'scope' || key === 'attention') && value === 'all') &&
          !(key === 'page' && value === 1) &&
          !(key === 'page_size' && value === 25),
      ),
    ),
  })
}

watch(() => route.query, load, { immediate: true })
onBeforeUnmount(() => revision++)
</script>

<template>
  <section class="space-y-5" aria-labelledby="inbox-title">
    <PageHeader
      title="Inbox"
      description="Aktuelle Aufgaben, Zuständigkeiten und Betriebsfälle."
      title-id="inbox-title"
    >
      <button class="button" :disabled="loading || invalidQuery" @click="load">
        <AppIcon name="refresh" :size="16" /> Aktualisieren
      </button>
    </PageHeader>
    <section v-if="data" aria-label="Inbox-Gesamtzahlen" :aria-busy="loading">
      <div class="grid grid-cols-2 gap-2 sm:grid-cols-3 xl:grid-cols-6">
        <button
          v-for="entry in countShortcuts"
          :key="entry.key"
          type="button"
          class="min-h-11 min-w-0 rounded-xl border px-3 py-2 text-left"
          :class="
            selected(entry.filter)
              ? 'border-fuchsia-700 bg-fuchsia-50 ring-1 ring-fuchsia-700'
              : 'border-slate-200 bg-white hover:bg-slate-50'
          "
          :aria-pressed="selected(entry.filter)"
          :aria-label="`${data.counts[entry.key]} ${entry.label}`"
          @click="
            apply(
              selected(entry.filter)
                ? 'scope' in entry.filter
                  ? { scope: 'all' }
                  : { attention: 'all' }
                : entry.filter,
            )
          "
        >
          <span class="block text-xl font-semibold tabular-nums" :class="entry.tone">{{
            data.counts[entry.key]
          }}</span>
          <span class="text-xs text-slate-600">{{ entry.label }}</span>
        </button>
      </div>
      <p class="operations-meta mt-1">
        Systemweite Aufgaben · Schnellfilter kombinieren sich mit der aktuellen Auswahl.
      </p>
    </section>
    <FilterBar compact @apply="applyFilters">
      <label>
        <span class="label">Zuständigkeit</span>
        <select v-model="scope" class="input">
          <option value="all">Alle</option>
          <option value="mine">Meine</option>
          <option value="unassigned">Nicht zugewiesen</option>
        </select>
      </label>
      <label>
        <span class="label">Aufmerksamkeit</span>
        <select v-model="attention" class="input">
          <option value="all">Alle</option>
          <option value="critical">Kritisch</option>
          <option value="due_today">Heute fällig</option>
          <option value="overdue">Überfällig</option>
          <option value="snoozed">Wiedervorlagen</option>
        </select>
      </label>
      <label>
        <span class="label">Aufgabenart</span>
        <select v-model="kind" class="input">
          <option :value="undefined">Alle Aufgabenarten</option>
          <option value="assignment">Zugewiesene Aufgaben</option>
          <option value="finding">Befunde</option>
          <option value="geocode_request">Standortvorschläge</option>
          <option value="notification_delivery">Benachrichtigungen</option>
        </select>
      </label>
      <label>
        <span class="label">Objektart</span>
        <select v-model="entityType" class="input">
          <option value="">Alle Objektarten</option>
          <option value="event">Veranstaltung</option>
          <option value="organization">Organisation</option>
          <option value="venue">Ort</option>
          <option value="space">Raum</option>
          <option value="user">Benutzer</option>
          <option value="image">Bild</option>
        </select>
      </label>
      <template #actions>
        <button class="button-primary" :disabled="loading" type="submit">Anwenden</button>
        <button class="button" :disabled="loading" type="button" @click="resetFilters">
          Filter zurücksetzen
        </button>
      </template>
    </FilterBar>
    <InlineAlert v-if="invalidQuery" tone="error">
      Die URL enthält ungültige Inbox-Filter.
      <NuxtLink to="/inbox" class="font-semibold underline">Filter zurücksetzen</NuxtLink>
    </InlineAlert>
    <RequestState
      :loading="loading"
      :error="error"
      :has-data="!!data"
      :last-success="data?.observed_at"
      @retry="load"
    />
    <template v-if="data">
      <ResultSummary
        :total="data.pagination.total"
        :visible="data.items.length"
        noun="Aufgaben"
        description="Serverseitig dedupliziert und priorisiert"
      />
      <DataListShell
        v-if="data.items.length"
        as="ul"
        dense
        class="divide-y divide-slate-100"
        aria-label="Inbox-Aufgaben"
        :aria-busy="loading"
      >
        <InboxRow
          v-for="item in data.items"
          :key="item.id"
          :item="item"
          :timezone="data.admin_timezone"
          @updated="load"
        />
      </DataListShell>
      <EmptyState
        v-else-if="!error"
        variant="compact"
        :message="
          attention === 'snoozed'
            ? 'Für diese Filter gibt es keine aktiven Wiedervorlagen.'
            : 'Für diese Filter gibt es keine aktiven Aufgaben.'
        "
        ><NuxtLink v-if="Object.keys(route.query).length" to="/inbox" class="action-link"
          >Filter zurücksetzen</NuxtLink
        ></EmptyState
      >
      <PaginationBar
        :pagination="data.pagination"
        :loading="loading"
        label="Inbox-Seitennavigation"
        @change="apply({ page: $event })"
      >
        <label class="inline-flex items-center gap-2">
          <span class="sr-only">Einträge pro Seite</span>
          <select
            :value="routeFilters()?.page_size ?? 25"
            class="input"
            aria-label="Einträge pro Seite"
            @change="apply({ page_size: Number(($event.target as HTMLSelectElement).value) })"
          >
            <option v-for="size in [10, 25, 50, 100]" :key="size" :value="size">
              {{ size }} pro Seite
            </option>
          </select>
        </label>
      </PaginationBar>
      <TechnicalInfoBar
        :items="[
          {
            label: 'Datenstand',
            value: adminDateTime(data.observed_at, data.admin_timezone),
            datetime: data.observed_at,
          },
          { label: 'Admin-Zeitzone', value: data.admin_timezone },
          { label: 'Sichtbare Einträge', value: data.items.length },
          { label: 'Gesamtzahl', value: data.pagination.total },
          { label: 'Einträge pro Seite', value: data.pagination.page_size },
        ]"
      />
    </template>
  </section>
</template>
