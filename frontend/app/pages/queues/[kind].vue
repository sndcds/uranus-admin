<script setup lang="ts">
import { queueKindSchema } from '#shared/contracts'
import type { QueuePage } from '#shared/contracts'
import { asFailure } from '#shared/errors'
import type { ApiFailure } from '#shared/errors'
import { dateTime } from '~/utils/presentation'
const route = useRoute()
const router = useRouter()
const { $adminApi } = useNuxtApp()
const data = ref<QueuePage | null>(null)
const error = ref<ApiFailure | null>(null)
const loading = ref(false)
const organization = ref('')
const age = ref('')
const status = ref('')
const titles = {
  partner_requests: 'Partneranfragen',
  team_invitations: 'Teameinladungen',
  user_activation: 'Benutzeraktivierung',
}
const kind = computed(() => queueKindSchema.safeParse(route.params.kind))
let requestId = 0
async function load() {
  const id = ++requestId
  loading.value = true
  data.value = null
  error.value = null
  try {
    if (!kind.value.success) throw new Error('Unknown queue')
    const query: Record<string, string> = {}
    for (const [key, value] of Object.entries(route.query)) {
      if (typeof value !== 'string') throw new Error('Invalid query')
      query[key] = value
    }
    const result = await $adminApi.queue(kind.value.data, query)
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
      organization_id: organization.value || undefined,
      min_age_days: age.value || undefined,
      status: status.value || undefined,
      page: '1',
    },
  })
}
onMounted(load)
watch(() => route.fullPath, load)
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
    <h2 class="text-2xl font-bold">
      {{ kind.success ? titles[kind.data] : 'Unbekannte Arbeitsliste' }}
    </h2>
    <form class="card flex flex-wrap items-end gap-3 p-5" @submit.prevent="apply">
      <label
        ><span class="label">Organisation (UUID)</span><input v-model="organization" class="input"
      /></label>
      <label
        ><span class="label">Mindestalter (Tage)</span
        ><input v-model="age" type="number" min="0" max="36500" class="input"
      /></label>
      <label><span class="label">Status</span><input v-model="status" class="input" /></label>
      <button class="button-primary">Anwenden</button>
    </form>
    <RequestState :loading="loading" :error="error" @retry="load" />
    <template v-if="data">
      <p class="muted">{{ data.pagination.total }} Vorgänge</p>
      <article v-for="item in data.items" :key="item.entity_key" class="card break-words p-5">
        <h3 class="font-bold">{{ item.user_name ?? item.user_id }}</h3>
        <RecordMarkLink
          :entity-type="
            data.kind === 'partner_requests'
              ? 'partner_request'
              : data.kind === 'team_invitations'
                ? 'team_membership'
                : 'user'
          "
          :entity-key="item.entity_key"
        />
        <p v-if="data.kind === 'partner_requests'">
          {{ item.from_organization_name ?? item.from_organization_id }} →
          {{ item.to_organization_name ?? item.to_organization_id }}
        </p>
        <p v-else>{{ item.organization_name ?? 'Keine eindeutige Organisation' }}</p>
        <p>
          Status: {{ item.status }} · Alter:
          {{ item.age_days == null ? 'Nicht verfügbar' : `${item.age_days} Tage` }}
        </p>
        <p>Erstellt: {{ dateTime(item.created_at) }}</p>
        <p v-if="data.kind === 'team_invitations'">
          Eingeladen: {{ dateTime(item.invited_at) }} · Beigetreten:
          {{ item.has_joined ? 'Ja' : 'Nein' }}
        </p>
        <p v-for="check in item.checks" :key="check" class="text-amber-800">{{ check }}</p>
        <NuxtLink :to="item.action.href" class="text-fuchsia-700">Vorgang ansehen</NuxtLink>
      </article>
      <p v-if="!data.items.length">Keine Vorgänge für diese Filter.</p>
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
