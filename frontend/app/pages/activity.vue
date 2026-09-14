<script setup lang="ts">
import { entityTypeSchema } from '#shared/contracts'
import type { ActivityPage } from '#shared/contracts'
import { asFailure } from '#shared/errors'
import type { ApiFailure } from '#shared/errors'
import { dateTime } from '~/utils/presentation'
const route = useRoute()
const router = useRouter()
const { $adminApi } = useNuxtApp()
const data = ref<ActivityPage | null>(null)
const error = ref<ApiFailure | null>(null)
const loading = ref(false)
const entityType = ref(typeof route.query.entity_type === 'string' ? route.query.entity_type : '')
const organization = ref(
  typeof route.query.organization_id === 'string' ? route.query.organization_id : '',
)
const period = ref(typeof route.query.period === 'string' ? route.query.period : '24h')
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
watch(() => route.query, load)
watch(
  useState('admin-access-revision', () => 0),
  load,
)
onBeforeUnmount(() => {
  requestId++
})
</script>

<template>
  <section class="space-y-5">
    <h2 class="text-2xl font-bold">Neue Datensätze</h2>
    <form class="card flex flex-wrap items-end gap-3 p-5" @submit.prevent="apply">
      <label
        ><span class="label">Objektart</span
        ><select v-model="entityType" class="input">
          <option value="">Alle</option>
          <option v-for="kind in entityTypeSchema.options" :key="kind" :value="kind">
            {{ kind }}
          </option>
        </select></label
      >
      <label
        ><span class="label">Organisation (UUID)</span><input v-model="organization" class="input"
      /></label>
      <label
        ><span class="label">Zeitraum</span
        ><select v-model="period" class="input">
          <option value="today">Heute</option>
          <option value="24h">24 Stunden</option>
          <option value="7d">7 Tage</option>
          <option value="unknown">Ohne Zeitstempel</option>
        </select></label
      >
      <button class="button-primary">Anwenden</button>
    </form>
    <RequestState :loading="loading" :error="error" @retry="load" />
    <template v-if="data">
      <p class="muted">
        {{ data.pagination.total }} Datensätze · {{ data.unknown_timestamp_count }} ohne belegten
        Erstellungszeitpunkt
      </p>
      <p v-if="data.timestamp_state === 'unknown'" class="muted">
        Nach Objektschlüssel geordnet; eine zeitliche Reihenfolge ist nicht bekannt.
      </p>
      <article
        v-for="item in data.items"
        :key="`${item.entity_type}:${item.entity_key}`"
        class="card break-words p-5"
      >
        <h3 class="font-bold">{{ item.entity_name }}</h3>
        <p>
          {{ item.entity_type }} · {{ item.organization_name ?? 'Keine eindeutige Organisation' }}
        </p>
        <p>
          Erstellt: {{ dateTime(item.created_at) }} · Status: {{ item.status ?? 'Nicht verfügbar' }}
        </p>
        <NuxtLink v-if="item.action" :to="item.action.href" class="text-fuchsia-700"
          >Datensatz ansehen</NuxtLink
        >
      </article>
      <p v-if="!data.items.length">Keine Datensätze für diese Filter.</p>
      <div class="flex gap-3">
        <NuxtLink
          v-if="data.pagination.page > 1"
          class="button"
          :to="{ query: { ...route.query, page: data.pagination.page - 1 } }"
          >Zurück</NuxtLink
        >
        <NuxtLink
          v-if="data.pagination.page < data.pagination.pages"
          class="button"
          :to="{ query: { ...route.query, page: data.pagination.page + 1 } }"
          >Weiter</NuxtLink
        >
      </div>
    </template>
  </section>
</template>
