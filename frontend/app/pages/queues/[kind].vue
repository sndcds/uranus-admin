<script setup lang="ts">
import { membershipStatusSchema, queueKindSchema } from '#shared/contracts'
import type { MembershipStatus, QueuePage, QueueQuery } from '#shared/contracts'
import { asFailure } from '#shared/errors'
import type { ApiFailure } from '#shared/errors'
import { dateTime } from '~/utils/presentation'
import { activityStatus } from '~/utils/activity'
const route = useRoute()
const router = useRouter()
const { $adminApi } = useNuxtApp()
const data = ref<QueuePage | null>(null)
const error = ref<ApiFailure | null>(null)
const loading = ref(false)
const organization = ref('')
const age = ref('')
const status = ref('')
const membershipStatus = ref<MembershipStatus>('invited')
const directMembership = computed(
  () => route.params.kind === 'team_invitations' && typeof route.query.entity_key === 'string',
)
const titles = {
  partner_requests: 'Partneranfragen',
  team_invitations: 'Teameinladungen',
  user_activation: 'Benutzeraktivierung',
}
const descriptions = {
  partner_requests: 'Gerichtete Anfragen zwischen Organisationen; Alter seit Erstellung.',
  team_invitations:
    'Standardmäßig offene Einladungen; beigetretene Mitgliedschaften sind über den Statusfilter sichtbar.',
  user_activation:
    'Noch nicht aktivierte Benutzer; Alter seit Erstellung, keine Aussage zur letzten Aktivität.',
}
const kind = computed(() => queueKindSchema.safeParse(route.params.kind))
let requestId = 0
async function load() {
  organization.value =
    typeof route.query.organization_id === 'string' ? route.query.organization_id : ''
  age.value = typeof route.query.min_age_days === 'string' ? route.query.min_age_days : ''
  status.value = typeof route.query.status === 'string' ? route.query.status : ''
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
    const filters: QueueQuery = query
    if (kind.value.data === 'team_invitations') {
      membershipStatus.value = membershipStatusSchema.parse(query.membership_status ?? 'invited')
      filters.membership_status = membershipStatus.value
    }
    const result = await $adminApi.queue(kind.value.data, filters)
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
      entity_key: directMembership.value ? route.query.entity_key : undefined,
      membership_status:
        kind.value.success && kind.value.data === 'team_invitations'
          ? membershipStatus.value
          : undefined,
      organization_id: organization.value || undefined,
      min_age_days: age.value || undefined,
      status: route.params.kind === 'team_invitations' ? undefined : status.value || undefined,
      page: '1',
    },
  })
}
onMounted(load)
watch(() => route.fullPath, load)
onBeforeUnmount(() => {
  requestId++
})
</script>

<template>
  <section class="space-y-5">
    <PageHeader
      :title="kind.success ? titles[kind.data] : 'Unbekannte Arbeitsliste'"
      :description="kind.success ? descriptions[kind.data] : undefined"
    />
    <p v-if="directMembership" class="text-sm text-slate-600" role="status">
      Direkt aufgerufene Teammitgliedschaft · Status-, Organisations- und Altersfilter werden nicht
      angewendet. „Filter zurücksetzen“ öffnet wieder die Einladungsliste.
    </p>
    <FilterBar @apply="apply">
      <label
        ><span class="label">Organisation (UUID)</span
        ><input v-model="organization" :disabled="directMembership" class="input"
      /></label>
      <label
        ><span class="label">Mindestalter (Tage)</span
        ><input
          v-model="age"
          :disabled="directMembership"
          type="number"
          min="0"
          max="36500"
          class="input"
      /></label>
      <label v-if="kind.success && kind.data === 'team_invitations'">
        <span class="label">Status</span>
        <select v-model="membershipStatus" class="input" :disabled="directMembership">
          <option value="invited">Eingeladen</option>
          <option value="joined">Beigetreten</option>
          <option value="all">Alle</option>
        </select>
      </label>
      <label v-else
        ><span class="label">Status</span><input v-model="status" class="input"
      /></label>
      <div class="flex flex-wrap gap-2">
        <button class="button-primary">Anwenden</button
        ><button type="button" class="button" @click="router.push({ query: {} })">
          Filter zurücksetzen
        </button>
      </div>
    </FilterBar>
    <RequestState :loading="loading" :error="error" @retry="load" />
    <template v-if="data">
      <ResultSummary
        :total="data.pagination.total"
        :visible="data.items.length"
        noun="Vorgänge"
        :observed-at="data.observed_at"
        description="Aktueller Bestand"
      />
      <DataListShell
        v-if="data.items.length"
        as="ul"
        class="divide-y divide-slate-100"
        :aria-busy="loading"
      >
        <li v-for="item in data.items" :key="item.entity_key" class="data-row space-y-2">
          <div class="flex flex-wrap items-start justify-between gap-2">
            <h3 class="min-w-0 text-sm font-semibold">
              <template v-if="data.kind === 'partner_requests'"
                >{{ item.from_organization_name ?? item.from_organization_id }} →
                {{ item.to_organization_name ?? item.to_organization_id }}</template
              ><template v-else>{{ item.user_name ?? item.user_id }}</template>
            </h3>
            <StatusBadge :label="activityStatus(item.status) ?? item.status" />
          </div>
          <p class="text-xs text-slate-500">
            {{
              data.kind === 'partner_requests'
                ? (item.user_name ?? item.user_id)
                : (item.organization_name ?? 'Keine eindeutige Organisation')
            }}
          </p>
          <p class="text-sm text-slate-600">
            Alter: {{ item.age_days == null ? 'Nicht verfügbar' : `${item.age_days} Tage` }} ·
            Basis: {{ item.age_basis === 'invited_at' ? 'Einladungsdatum' : 'Erstellungsdatum' }}
          </p>
          <p class="text-xs text-slate-500">Erstellt: {{ dateTime(item.created_at) }}</p>
          <p v-if="data.kind === 'team_invitations'" class="text-xs text-slate-500">
            Eingeladen: {{ dateTime(item.invited_at) }} · Beigetreten:
            {{ item.has_joined == null ? 'Nicht verfügbar' : item.has_joined ? 'Ja' : 'Nein' }}
          </p>
          <p v-for="check in item.checks" :key="check" class="text-xs text-amber-800">
            {{ check }}
          </p>
          <div
            class="flex flex-wrap items-center gap-x-4 gap-y-2 text-xs [&_a]:mt-0 [&_a]:p-0 [&_a]:border-0 [&_a]:text-xs"
          >
            <NuxtLink :to="item.action.href" class="rounded text-fuchsia-700 hover:underline"
              >Vorgang ansehen</NuxtLink
            >
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
          </div>
        </li>
      </DataListShell>
      <EmptyState v-else message="Keine Vorgänge für diese Filter." />
      <PaginationBar
        :pagination="data.pagination"
        :loading="loading"
        :to="(page) => ({ query: { ...route.query, page } })"
      />
    </template>
  </section>
</template>
