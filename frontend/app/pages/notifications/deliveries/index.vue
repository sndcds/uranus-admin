<script setup lang="ts">
import { ref, watch, onMounted } from 'vue'
import { useOperationsRequest } from '~/composables/useOperationsRequest'
import { notificationQuery } from '~/utils/notification-query'
import NotificationDeliveryTable from '~/components/NotificationDeliveryTable.vue'
import TechnicalInfoBar from '~/components/TechnicalInfoBar.vue'
import InlineAlert from '~/components/InlineAlert.vue'
import { notificationDeliveryStatusSchema, notificationDeliveryKindSchema } from '#shared/contracts'
import type {
  NotificationDeliveryPage,
  NotificationDeliveryStatus,
  NotificationDeliveryKind,
} from '#shared/contracts'
import { deliveryKinds, deliveryStatuses } from '~/utils/notifications'
const route = useRoute()
const router = useRouter()
const { $adminApi } = useNuxtApp()
const { data, error, loading, load: request } = useOperationsRequest<NotificationDeliveryPage>()
const status = ref<NotificationDeliveryStatus | ''>('')
const kind = ref<NotificationDeliveryKind | ''>('')
const organization = ref('')
const days = ref('')
function textQuery(key: string) {
  const value = route.query[key]
  return typeof value === 'string' ? value : ''
}
async function load() {
  status.value = notificationDeliveryStatusSchema.safeParse(textQuery('status')).data ?? ''
  kind.value = notificationDeliveryKindSchema.safeParse(textQuery('delivery_kind')).data ?? ''
  organization.value = textQuery('organization_id')
  days.value = textQuery('days')
  await request(route.fullPath, () =>
    $adminApi.notificationDeliveries(notificationQuery(route.query, true)),
  )
}
async function apply(page = 1) {
  const before = route.fullPath
  await router.push({
    query: {
      status: status.value || undefined,
      delivery_kind: kind.value || undefined,
      organization_id: organization.value || undefined,
      days: days.value || undefined,
      page: String(page),
      page_size: route.query.page_size,
    },
  })
  if (route.fullPath === before) await load()
}
onMounted(load)
watch(() => route.fullPath, load, { flush: 'sync' })
</script>
<template>
  <section class="operations-page">
    <PageHeader
      title="E-Mail-Versände"
      description="Versandstatus, Fehler und erneute Zustellversuche prüfen."
    >
      <NuxtLink to="/notifications" class="button">Benachrichtigungen</NuxtLink>
      <button class="button" :disabled="loading" @click="load">Aktualisieren</button>
    </PageHeader>
    <FilterBar compact @apply="apply()">
      <label
        ><span class="label">Status</span
        ><select v-model="status" class="input">
          <option value="">Alle</option>
          <option v-for="(label, value) in deliveryStatuses" :key="value" :value="value">
            {{ label }}
          </option>
        </select></label
      >
      <label
        ><span class="label">Art</span
        ><select v-model="kind" class="input">
          <option value="">Alle</option>
          <option v-for="(label, value) in deliveryKinds" :key="value" :value="value">
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
        ><button type="button" class="button" @click="router.push({ query: {} })">
          Filter zurücksetzen
        </button></template
      >
    </FilterBar>
    <RequestState :loading="loading" :error="error" :has-data="!!data" @retry="load" />
    <template v-if="data">
      <InlineAlert v-if="!data.delivery_enabled" compact
        >E-Mail-Versand ist deaktiviert (Dry Run).</InlineAlert
      >
      <ResultSummary
        :total="data.pagination.total"
        :visible="data.items.length"
        noun="E-Mail-Versände"
      />
      <NotificationDeliveryTable v-if="data.items.length" :items="data.items" :busy="loading" />
      <EmptyState
        v-else-if="!error"
        variant="compact"
        message="Keine E-Mail-Versände für diese Auswahl."
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
          { label: 'Sichtbare Versände', value: data.items.length },
          { label: 'Einträge pro Seite', value: data.pagination.page_size },
          { label: 'E-Mail-Versand aktiviert', value: data.delivery_enabled },
        ]"
      />
    </template>
  </section>
</template>
