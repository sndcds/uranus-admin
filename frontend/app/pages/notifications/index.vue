<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import { useOperationsRequest } from '~/composables/useOperationsRequest'
import { notificationQuery } from '~/utils/notification-query'
import DenseTable from '~/components/DenseTable.vue'
import TechnicalInfoBar from '~/components/TechnicalInfoBar.vue'
import StatusBadge from '~/components/StatusBadge.vue'
import InlineAlert from '~/components/InlineAlert.vue'
import OperationTime from '~/components/OperationTime.vue'
import type { NotificationPage, NotificationStatus, NotificationType } from '#shared/contracts'
import { notificationStatuses, notificationTypes, notificationTone } from '~/utils/notifications'
const { $adminApi } = useNuxtApp()
const route = useRoute()
const router = useRouter()
const { data, error, loading, load: request } = useOperationsRequest<NotificationPage>()
const status = ref<NotificationStatus | ''>('')
const type = ref<NotificationType | ''>('')
const organization = ref('')
const days = ref('')
const metrics = [
  { key: 'active', label: 'Aktiv', to: '' },
  { key: 'sent_today', label: 'Heute gesendet', to: '/notifications/deliveries?status=sent' },
  {
    key: 'temporary_failed',
    label: 'Temporär fehlgeschlagen',
    to: '/notifications/deliveries?status=failed',
  },
  {
    key: 'permanent_failed',
    label: 'Dauerhaft fehlgeschlagen',
    to: '/notifications/deliveries?status=permanent_failure',
  },
  { key: 'queued', label: 'Ausstehend', to: '/notifications/deliveries' },
] as const
function textQuery(key: string) {
  return typeof route.query[key] === 'string' ? route.query[key] : ''
}
async function load() {
  status.value = textQuery('status') as NotificationStatus | ''
  type.value = textQuery('notification_type') as NotificationType | ''
  organization.value = textQuery('organization_id')
  days.value = textQuery('days')
  await request(route.fullPath, () => $adminApi.notifications(notificationQuery(route.query)))
}
async function apply() {
  const before = route.fullPath
  await router.push({
    query: {
      status: status.value || undefined,
      notification_type: type.value || undefined,
      organization_id: organization.value || undefined,
      days: days.value || undefined,
      page: '1',
      page_size: route.query.page_size,
    },
  })
  if (before === route.fullPath) await load()
}
onMounted(load)
watch(() => route.fullPath, load, { flush: 'sync' })
const columns = [
  { key: 'entity_name', label: 'Datensatz / Typ', rowHeader: true, width: '32%' },
  { key: 'status', label: 'Fachlicher Zustand', width: '18%' },
  { key: 'organization_id', label: 'Organisation', width: '22%' },
  { key: 'last_detected_at', label: 'Erkannt', width: '28%' },
] as const
</script>
<template>
  <section class="operations-page">
    <PageHeader
      title="Benachrichtigungen"
      description="Fachliche Hinweise, ihr Zustand und zugehörige E-Mail-Versände."
    >
      <NuxtLink to="/notifications/deliveries" class="button">E-Mail-Versände</NuxtLink>
      <button class="button" :disabled="loading" @click="load">Aktualisieren</button>
    </PageHeader>
    <template v-if="data">
      <InlineAlert v-if="!data.health.delivery_enabled" compact
        >E-Mail-Versand ist deaktiviert (Dry Run).</InlineAlert
      >
      <InlineAlert v-if="!data.health.source_capability" compact tone="warning"
        >Notification-Konfiguration ist im Source-Schema nicht verfügbar. Versand bleibt
        deaktiviert.</InlineAlert
      >
      <InlineAlert v-if="data.health.config_issues.length" compact tone="warning"
        ><ul>
          <li v-for="issue in data.health.config_issues" :key="issue.organization_id">
            Ungültige Benachrichtigungskonfiguration: {{ issue.organization_name }}. Kein Versand.
          </li>
        </ul></InlineAlert
      >
      <section
        aria-label="Systemweiter Benachrichtigungs- und Versandbestand"
        class="operations-panel"
      >
        <p class="operations-meta px-3 pt-2">
          Systemweiter Bestand · unabhängig von den Listenfiltern
        </p>
        <dl class="grid grid-cols-2 gap-x-3 px-3 pb-2 sm:grid-cols-3 xl:grid-cols-5">
          <div v-for="metric in metrics" :key="metric.key" class="min-w-0">
            <dt class="operations-meta">
              <NuxtLink v-if="metric.to" :to="metric.to" class="action-link text-xs">{{
                metric.label
              }}</NuxtLink
              ><span v-else class="inline-flex min-h-11 items-center">{{ metric.label }}</span>
            </dt>
            <dd class="text-xl font-semibold tabular-nums">{{ data.summary[metric.key] }}</dd>
            <p v-if="metric.key === 'queued'" class="operations-meta">
              Eingereiht oder wird gesendet
            </p>
          </div>
        </dl>
      </section>
    </template>
    <FilterBar compact @apply="apply">
      <label
        ><span class="label">Status</span
        ><select v-model="status" class="input">
          <option value="">Alle</option>
          <option v-for="(label, value) in notificationStatuses" :key="value" :value="value">
            {{ label }}
          </option>
        </select></label
      >
      <label
        ><span class="label">Typ</span
        ><select v-model="type" class="input">
          <option value="">Alle</option>
          <option v-for="(label, value) in notificationTypes" :key="value" :value="value">
            {{ label }}
          </option>
        </select></label
      >
      <label
        ><span class="label">Organisation (UUID)</span
        ><input v-model="organization" class="input" placeholder="Alle Organisationen"
      /></label>
      <label
        ><span class="label">Zeitraum</span
        ><select v-model="days" class="input">
          <option value="">Gesamter Zeitraum</option>
          <option value="7">Letzte 7 Tage</option>
          <option value="30">Letzte 30 Tage</option>
          <option v-if="days && !['7', '30'].includes(days)" :value="days">
            Letzte {{ days }} Tage
          </option>
        </select></label
      >
      <template #actions
        ><button class="button-primary" :disabled="loading">Filter anwenden</button
        ><button class="button" type="button" @click="router.push({ query: {} })">
          Filter zurücksetzen
        </button></template
      >
    </FilterBar>
    <RequestState :loading="loading" :error="error" :has-data="!!data" @retry="load" />
    <template v-if="data">
      <ResultSummary
        :total="data.pagination.total"
        :visible="data.items.length"
        noun="Benachrichtigungen"
      />
      <DenseTable
        v-if="data.items.length"
        caption="Benachrichtigungen"
        :columns="columns"
        :rows="data.items"
        :row-key="(item) => item.id"
        stack-at="tablet"
        :busy="loading"
      >
        <template #cell-entity_name="{ row }"
          ><NuxtLink class="action-link text-sm" :to="`/notifications/${row.id}`">{{
            row.entity_name || 'Benachrichtigung'
          }}</NuxtLink>
          <p class="operations-meta font-normal">
            {{ notificationTypes[row.notification_type] }}
          </p></template
        >
        <template #cell-status="{ row }"
          ><StatusBadge
            :label="notificationStatuses[row.status]"
            :tone="notificationTone(row.status)" />
          <p v-if="row.resolved_at" class="operations-meta">
            Gelöst: <OperationTime :value="row.resolved_at" />
          </p>
          <p v-if="row.expired_at" class="operations-meta">
            Abgelaufen: <OperationTime :value="row.expired_at" /></p
        ></template>
        <template #cell-organization_id="{ row }">{{ row.payload.organization_name }}</template>
        <template #cell-last_detected_at="{ row }"
          ><p class="text-xs">Erstmals: <OperationTime :value="row.first_detected_at" /></p>
          <p class="operations-meta">Zuletzt: <OperationTime :value="row.last_detected_at" /></p
        ></template>
      </DenseTable>
      <EmptyState
        v-else-if="!error"
        variant="compact"
        message="Keine Benachrichtigungen für diese Auswahl."
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
          { label: 'Gesamtzahl', value: data.pagination.total },
          { label: 'Sichtbare Hinweise', value: data.items.length },
          { label: 'Einträge pro Seite', value: data.pagination.page_size },
          { label: 'E-Mail-Versand aktiviert', value: data.health.delivery_enabled },
        ]"
      />
    </template>
  </section>
</template>
