<script setup lang="ts">
import { qualityRuleLabel } from '~/utils/quality'
import { membershipStatusSchema, queueKindSchema } from '#shared/contracts'
import type { MembershipStatus, QueuePage, QueueQuery } from '#shared/contracts'
import { AdminApiError, failure } from '#shared/errors'
import { useOperationsRequest } from '~/composables/useOperationsRequest'
import { ref, computed, onMounted, watch } from 'vue'
import { dateTime } from '~/utils/presentation'
import { activityStatus } from '~/utils/activity'
import DenseTable from '~/components/DenseTable.vue'
import TechnicalInfoBar from '~/components/TechnicalInfoBar.vue'
import OperationTime from '~/components/OperationTime.vue'
const route = useRoute()
const router = useRouter()
const { $adminApi } = useNuxtApp()
const { data, error, loading, load: request } = useOperationsRequest<QueuePage>()
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
async function load() {
  organization.value =
    typeof route.query.organization_id === 'string' ? route.query.organization_id : ''
  age.value = typeof route.query.min_age_days === 'string' ? route.query.min_age_days : ''
  status.value = typeof route.query.status === 'string' ? route.query.status : ''
  await request(route.fullPath, async () => {
    if (!kind.value.success) throw new AdminApiError(failure(422))
    const query: Record<string, string> = {}
    for (const [key, value] of Object.entries(route.query)) {
      if (typeof value !== 'string') throw new AdminApiError(failure(422))
      query[key] = value
    }
    const filters: QueueQuery = query
    if (kind.value.data === 'team_invitations') {
      const parsed = membershipStatusSchema.safeParse(query.membership_status ?? 'invited')
      if (!parsed.success) throw new AdminApiError(failure(422))
      membershipStatus.value = parsed.data
      filters.membership_status = parsed.data
    }
    return $adminApi.queue(kind.value.data, filters)
  })
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
watch(() => route.fullPath, load, { flush: 'sync' })
const columns = [
  { key: 'entity_key', label: 'Vorgang / Kontext', rowHeader: true, width: '38%' },
  { key: 'status', label: 'Status', width: '15%' },
  { key: 'age_days', label: 'Alter', width: '13%' },
  { key: 'created_at', label: 'Zeitpunkte', width: '18%' },
] as const
</script>

<template>
  <section class="operations-page">
    <PageHeader
      stack-actions
      :title="kind.success ? titles[kind.data] : 'Unbekannte Arbeitsliste'"
      :description="kind.success ? descriptions[kind.data] : undefined"
      ><button class="button" :disabled="loading" @click="load">Aktualisieren</button></PageHeader
    >
    <p v-if="directMembership" class="text-sm text-slate-600" role="status">
      Direkt aufgerufene Teammitgliedschaft · Status-, Organisations- und Altersfilter werden nicht
      angewendet. „Filter zurücksetzen“ öffnet wieder die Einladungsliste.
    </p>
    <FilterBar compact :columns="3" @apply="apply">
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
      <template #actions>
        <button class="button-primary">Anwenden</button
        ><button type="button" class="button" @click="router.push({ query: {} })">
          Filter zurücksetzen
        </button>
      </template>
    </FilterBar>
    <RequestState :loading="loading" :error="error" :has-data="!!data" @retry="load" />
    <template v-if="data">
      <ResultSummary
        :total="data.pagination.total"
        :visible="data.items.length"
        noun="Vorgänge"
        description="Aktueller Bestand"
      />
      <DenseTable
        v-if="data.items.length"
        caption="Vorgänge"
        :columns="columns"
        :rows="data.items"
        :row-key="(item) => item.entity_key"
        :busy="loading"
        stack-at="tablet"
      >
        <template #cell-entity_key="{ row: item }">
          <h3 class="type-row-title">
            <template v-if="data.kind === 'partner_requests'"
              >{{
                item.from_organization_name?.trim() || 'Anfragende Organisation nicht verfügbar'
              }}
              →
              {{
                item.to_organization_name?.trim() || 'Zielorganisation nicht verfügbar'
              }}</template
            >
            <template v-else>{{ item.user_name ?? item.user_id }}</template>
          </h3>
          <p class="operations-meta font-normal">
            {{
              data.kind === 'partner_requests'
                ? (item.user_name ?? item.user_id)
                : (item.organization_name ?? 'Keine eindeutige Organisation')
            }}
          </p>
          <dl v-if="data.kind === 'partner_requests'" class="operations-meta font-normal">
            <div v-if="!item.from_organization_name?.trim() && item.from_organization_id">
              <dt>UUID der anfragenden Organisation:</dt>
              <dd class="flex flex-wrap items-center gap-x-2">
                <code class="break-all">{{ item.from_organization_id }}</code
                ><CopyValueButton
                  :value="item.from_organization_id"
                  label="UUID der anfragenden Organisation"
                />
              </dd>
            </div>
            <div v-if="!item.to_organization_name?.trim() && item.to_organization_id">
              <dt>UUID der Zielorganisation:</dt>
              <dd class="flex flex-wrap items-center gap-x-2">
                <code class="break-all">{{ item.to_organization_id }}</code
                ><CopyValueButton
                  :value="item.to_organization_id"
                  label="UUID der Zielorganisation"
                />
              </dd>
            </div>
          </dl>
          <p v-for="check in item.checks" :key="check" class="text-xs font-normal text-amber-800">
            {{ qualityRuleLabel(check) }}
          </p>
        </template>
        <template #cell-status="{ row: item }">
          <StatusBadge :label="activityStatus(item.status) ?? item.status" />
          <p v-if="data.kind === 'team_invitations'" class="operations-meta">
            Beigetreten:
            {{ item.has_joined == null ? 'Nicht verfügbar' : item.has_joined ? 'Ja' : 'Nein' }}
          </p>
        </template>
        <template #cell-age_days="{ row: item }">
          <span class="tabular-nums">{{
            item.age_days == null ? 'Nicht verfügbar' : `${item.age_days} Tage`
          }}</span>
          <p class="operations-meta">
            Basis: {{ item.age_basis === 'invited_at' ? 'Einladungsdatum' : 'Erstellungsdatum' }}
          </p>
        </template>
        <template #cell-created_at="{ row: item }">
          <div v-if="data.kind === 'team_invitations'" class="text-xs">
            Eingeladen: <OperationTime :value="item.invited_at" />
          </div>
          <div class="operations-meta">Erstellt: <OperationTime :value="item.created_at" /></div>
        </template>
        <template #actions="{ row: item }">
          <div class="flex flex-col items-start">
            <NuxtLink
              :to="item.action.href"
              class="action-link"
              :aria-label="`Vorgang ansehen: ${item.user_name ?? item.user_id}`"
              >Vorgang ansehen</NuxtLink
            >
            <GraphLink
              :entity-type="
                data.kind === 'team_invitations'
                  ? 'team_membership'
                  : data.kind === 'user_activation'
                    ? 'user'
                    : 'partner_request'
              "
              :entity-key="item.entity_key"
            />
            <EntityInspectorLink
              :entity-type="
                data.kind === 'team_invitations'
                  ? 'team_membership'
                  : data.kind === 'user_activation'
                    ? 'user'
                    : 'partner_request'
              "
              :entity-key="item.entity_key"
            />
            <RecordMarkLink
              variant="action"
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
        </template>
      </DenseTable>
      <EmptyState v-else-if="!error" variant="compact" message="Keine Vorgänge für diese Auswahl."
        ><button class="action-link" @click="router.push({ query: {} })">
          Filter zurücksetzen
        </button></EmptyState
      >
      <PaginationBar
        :pagination="data.pagination"
        :loading="loading"
        :to="(page) => ({ query: { ...route.query, page } })"
      />
      <TechnicalInfoBar
        :show-title="false"
        :items="[
          {
            label: 'Datenstand',
            value: dateTime(data.observed_at),
            datetime: data.observed_at,
            timezone: 'Europe/Berlin',
          },
          { label: 'Gesamtzahl', value: data.pagination.total },
          { label: 'Sichtbare Einträge', value: data.items.length },
          { label: 'Einträge pro Seite', value: data.pagination.page_size },
          { label: 'Queue-Typ', value: data.kind, mono: true },
          {
            label: 'Mitgliedschaftsauswahl',
            value:
              data.kind === 'team_invitations'
                ? directMembership
                  ? 'Direktaufruf (Filter nicht angewendet)'
                  : route.query.membership_status === 'all'
                    ? 'Alle'
                    : activityStatus(
                        typeof route.query.membership_status === 'string'
                          ? route.query.membership_status
                          : 'invited',
                      )
                : null,
          },
        ]"
      />
    </template>
  </section>
</template>
