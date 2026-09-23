<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'
import { inboxFiltersSchema, type InboxFilters, type InboxPage } from '#shared/contracts'
import { asFailure, type ApiFailure } from '#shared/errors'

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

function single(value: unknown) {
  return typeof value === 'string' ? value : undefined
}

function routeFilters(): InboxFilters | null {
  const parsed = inboxFiltersSchema.safeParse({
    scope: single(route.query.scope),
    attention: single(route.query.attention),
    kind: single(route.query.kind),
    entity_type: single(route.query.entity_type),
    page: single(route.query.page),
    page_size: single(route.query.page_size),
  })
  return parsed.success ? parsed.data : null
}

async function load() {
  const filters = routeFilters()
  invalidQuery.value = !filters
  if (!filters) {
    data.value = null
    return
  }
  scope.value = filters.scope
  attention.value = filters.attention
  kind.value = filters.kind
  entityType.value = filters.entity_type ?? ''
  const current = ++revision
  loading.value = true
  error.value = null
  try {
    const value = await $adminApi.inbox(filters)
    if (current === revision) data.value = value
  } catch (cause) {
    if (current === revision) error.value = asFailure(cause)
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
    <FilterBar @apply="applyFilters">
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
          <option value="finding">Findings</option>
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
      <template #help>
        <div class="mt-3 flex flex-wrap gap-2">
          <button class="button-primary" :disabled="loading" type="submit">Anwenden</button>
          <button class="button" :disabled="loading" type="button" @click="resetFilters">
            Filter zurücksetzen
          </button>
        </div>
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
        :observed-at="data.observed_at"
      >
        <StatusBadge :label="`${data.counts.critical} kritisch`" tone="error" />
        <StatusBadge :label="`${data.counts.mine} meine`" />
        <StatusBadge :label="`${data.counts.unassigned} nicht zugewiesen`" />
        <StatusBadge :label="`${data.counts.due_today} heute fällig`" tone="warning" />
        <StatusBadge :label="`${data.counts.overdue} überfällig`" tone="error" />
        <StatusBadge :label="`${data.counts.snoozed} Wiedervorlagen`" />
      </ResultSummary>
      <DataListShell
        v-if="data.items.length"
        as="ul"
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
        v-else
        :message="
          attention === 'snoozed'
            ? 'Für diese Filter gibt es keine aktiven Wiedervorlagen.'
            : 'Für diese Filter gibt es keine aktiven Aufgaben.'
        "
      />
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
    </template>
  </section>
</template>
