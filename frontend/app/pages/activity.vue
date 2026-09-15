<script setup lang="ts">
import { entityTypeSchema } from '#shared/contracts'
import type { ActivityPage } from '#shared/contracts'
import { asFailure } from '#shared/errors'
import type { ApiFailure } from '#shared/errors'
import { activityTypes, activityGroups, activityCounts } from '~/utils/activity'
import { dateTime, adminTimeZone } from '~/utils/presentation'
const route = useRoute()
const router = useRouter()
const { $adminApi } = useNuxtApp()
const data = ref<ActivityPage | null>(null)
const error = ref<ApiFailure | null>(null)
const loading = ref(false)
const entityType = ref('')
const organization = ref('')
const period = ref('24h')
const selectedType = computed(() => {
  const parsed = entityTypeSchema.safeParse(route.query.entity_type)
  return parsed.success ? parsed.data : null
})
const title = computed(() =>
  selectedType.value ? `Neue ${activityTypes[selectedType.value].plural}` : 'Neue Datensätze',
)
const description = computed(() => {
  if (!data.value) return 'Neuanlagen nach Objektart und Erstellungszeitpunkt.'
  const count = data.value.pagination.total
  const label = selectedType.value
    ? count === 1
      ? activityTypes[selectedType.value].label
      : activityTypes[selectedType.value].plural
    : count === 1
      ? 'Datensatz'
      : 'Datensätze'
  if (data.value.timestamp_state === 'unknown')
    return `${count} ${label} ohne belegten Erstellungszeitpunkt.`
  if (route.query.entity_key && !route.query.period && !route.query.from_at && !route.query.to_at)
    return `${count} ${label} für diesen Objektschlüssel.`
  const window =
    data.value.from_at && data.value.to_at
      ? `${dateTime(data.value.from_at)} – ${dateTime(data.value.to_at)}`
      : 'gewählte Zeitgrenzen'
  return `${count} ${label} · ${window}`
})
const groups = computed(() => (data.value ? activityGroups(data.value) : []))
const counts = computed(() => activityCounts(data.value?.items ?? []))
function syncFilters() {
  entityType.value = typeof route.query.entity_type === 'string' ? route.query.entity_type : ''
  organization.value =
    typeof route.query.organization_id === 'string' ? route.query.organization_id : ''
  period.value =
    route.query.timestamp_state === 'unknown'
      ? 'unknown'
      : typeof route.query.period === 'string'
        ? route.query.period
        : '24h'
}
syncFilters()
let requestId = 0
async function load() {
  const id = ++requestId
  loading.value = true
  data.value = null
  error.value = null
  try {
    const query: Record<string, string> = {}
    for (const [key, value] of Object.entries(route.query)) {
      if (typeof value !== 'string') throw new Error('Invalid query')
      query[key] = value
    }
    const result = await $adminApi.activity(query)
    if (id === requestId) data.value = result
  } catch (cause) {
    if (id === requestId) error.value = asFailure(cause)
  } finally {
    if (id === requestId) loading.value = false
  }
}
function apply() {
  void router.push({
    query: {
      entity_type: entityType.value || undefined,
      organization_id: organization.value || undefined,
      period: period.value === 'unknown' ? undefined : period.value,
      timestamp_state: period.value === 'unknown' ? 'unknown' : 'known',
      page: '1',
    },
  })
}
onMounted(load)
watch(
  () => route.query,
  () => {
    syncFilters()
    void load()
  },
)
watch(
  useState('admin-access-revision', () => 0),
  load,
)
onBeforeUnmount(() => {
  requestId++
})
</script>

<template>
  <section class="space-y-4" aria-labelledby="activity-title">
    <div>
      <h2 id="activity-title" class="text-2xl font-bold">{{ title }}</h2>
      <p class="mt-1 text-sm text-slate-500">{{ description }}</p>
    </div>
    <form
      class="grid gap-3 rounded-2xl border border-slate-200 bg-white p-4 sm:grid-cols-2 xl:grid-cols-[minmax(10rem,1fr)_minmax(9rem,1fr)_minmax(14rem,1.5fr)_auto]"
      @submit.prevent="apply"
    >
      <label
        ><span class="label">Objektart</span>
        <select v-model="entityType" class="input">
          <option value="">Alle Objektarten</option>
          <option v-for="kind in entityTypeSchema.options" :key="kind" :value="kind">
            {{ activityTypes[kind].label }}
          </option>
        </select>
      </label>
      <label
        ><span class="label">Zeitraum</span>
        <select v-model="period" class="input">
          <option value="today">Heute</option>
          <option value="24h">24 Stunden</option>
          <option value="7d">7 Tage</option>
          <option value="unknown">Ohne Zeitstempel</option>
        </select>
      </label>
      <label
        ><span class="label">Organisation (UUID)</span>
        <input
          v-model="organization"
          class="input"
          placeholder="Alle Organisationen"
          spellcheck="false"
        />
      </label>
      <div class="flex flex-wrap items-end gap-2">
        <button class="button-primary" :disabled="loading">Anwenden</button>
        <button
          type="button"
          class="button"
          :disabled="loading"
          @click="router.push({ query: {} })"
        >
          Filter zurücksetzen
        </button>
      </div>
    </form>
    <RequestState :loading="loading" :error="error" @retry="load" />
    <template v-if="data">
      <div class="space-y-2" aria-label="Zusammenfassung der Aktivität">
        <div class="flex flex-wrap items-baseline justify-between gap-2">
          <p class="text-sm font-semibold">{{ data.pagination.total }} Datensätze insgesamt</p>
          <p class="text-xs text-slate-500">
            {{ data.unknown_timestamp_count }} ohne belegten Erstellungszeitpunkt
            <span v-if="data.timestamp_state === 'known'"> · separate Auswahl</span>
          </p>
        </div>
        <div class="flex flex-wrap items-center gap-x-3 gap-y-1.5 text-xs">
          <span class="font-medium text-slate-600"
            >Auf dieser Seite: {{ data.items.length }} Einträge</span
          >
          <span
            v-for="entry in counts"
            :key="entry.type"
            class="rounded-md px-2 py-0.5"
            :class="activityTypes[entry.type].tone"
          >
            {{ entry.count }}
            {{
              entry.count === 1 ? activityTypes[entry.type].label : activityTypes[entry.type].plural
            }}
          </span>
        </div>
        <p v-if="data.timestamp_state === 'known'" class="text-xs text-slate-500">
          Tagesgruppen auf dieser Seite · Zeiten in {{ adminTimeZone }} · Stand:
          {{ dateTime(data.observed_at) }}
        </p>
      </div>
      <p
        v-if="data.timestamp_state === 'unknown'"
        class="rounded-xl border border-slate-200 bg-slate-100 px-4 py-3 text-sm text-slate-600"
      >
        Nach Objektschlüssel geordnet; eine zeitliche Reihenfolge ist nicht bekannt.
      </p>
      <div
        v-if="data.items.length"
        class="overflow-hidden rounded-2xl border border-slate-200 bg-white"
      >
        <section
          v-for="group in groups"
          :key="group.key"
          :aria-labelledby="group.label ? `activity-day-${group.key}` : undefined"
          :aria-label="group.label ? undefined : 'Datensätze ohne bekannte Reihenfolge'"
        >
          <div
            v-if="group.label"
            class="flex items-center gap-3 border-y border-slate-200 bg-slate-50 px-4 py-2 first:border-t-0 sm:px-5"
          >
            <h3 :id="`activity-day-${group.key}`" class="text-xs font-semibold text-slate-700">
              {{ group.label }}
            </h3>
            <span class="text-xs tabular-nums text-slate-500"
              >{{ group.items.length }}
              {{ group.items.length === 1 ? 'Eintrag' : 'Einträge' }}</span
            >
          </div>
          <ul class="divide-y divide-slate-100">
            <ActivityRow
              v-for="item in group.items"
              :key="`${item.entity_type}:${item.entity_key}`"
              :item="item"
              :observed-at="data.observed_at"
              :grouped="!!group.label"
            />
          </ul>
        </section>
      </div>
      <p
        v-else
        class="rounded-2xl border border-dashed border-slate-300 bg-white px-5 py-8 text-center text-sm text-slate-500"
      >
        Keine Datensätze für diese Filter.
      </p>
      <nav
        v-if="data.pagination.pages > 0"
        class="flex flex-wrap items-center justify-between gap-3"
        aria-label="Activity-Seitennavigation"
      >
        <p class="text-sm text-slate-600">
          Seite {{ data.pagination.page }} von {{ data.pagination.pages }}
        </p>
        <div class="flex gap-2">
          <NuxtLink
            v-if="data.pagination.page > 1"
            class="button"
            rel="prev"
            :to="{ query: { ...route.query, page: data.pagination.page - 1 } }"
            ><AppIcon name="previous" :size="16" />Zurück</NuxtLink
          >
          <button v-else class="button" disabled>
            <AppIcon name="previous" :size="16" />Zurück
          </button>
          <NuxtLink
            v-if="data.pagination.page < data.pagination.pages"
            class="button"
            rel="next"
            :to="{ query: { ...route.query, page: data.pagination.page + 1 } }"
            >Weiter<AppIcon name="next" :size="16"
          /></NuxtLink>
          <button v-else class="button" disabled>Weiter<AppIcon name="next" :size="16" /></button>
        </div>
      </nav>
    </template>
  </section>
</template>
