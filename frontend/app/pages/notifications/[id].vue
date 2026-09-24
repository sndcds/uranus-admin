<script setup lang="ts">
import { computed, watch, onMounted } from 'vue'
import type { NotificationDetail } from '#shared/contracts'
import { useOperationsRequest } from '~/composables/useOperationsRequest'
import { dateTime, adminTimeZone } from '~/utils/presentation'
import { notificationStatuses, notificationTypes, notificationTone } from '~/utils/notifications'
import { qualityRuleLabel } from '~/utils/quality'
import RecordSection from '~/components/RecordSection.vue'
import CompactFacts from '~/components/CompactFacts.vue'
import TechnicalInfoBar from '~/components/TechnicalInfoBar.vue'
import StatusBadge from '~/components/StatusBadge.vue'
import InlineAlert from '~/components/InlineAlert.vue'
import NotificationDeliveryTable from '~/components/NotificationDeliveryTable.vue'
const route = useRoute()
const { $adminApi } = useNuxtApp()
const { data, error, loading, load: request } = useOperationsRequest<NotificationDetail>()
function load() {
  const id = String(route.params.id)
  return request(id, () => $adminApi.notification(id))
}
const technical = computed(() =>
  data.value
    ? [
        { label: 'Notification ID', value: data.value.id, mono: true, copyable: true },
        { label: 'Status', value: data.value.status },
        { label: 'E-Mail-Versand aktiviert', value: data.value.delivery_enabled },
        ...[
          { label: 'Erstmals erkannt', value: data.value.first_detected_at },
          { label: 'Zuletzt erkannt', value: data.value.last_detected_at },
          { label: 'Gelöst', value: data.value.resolved_at },
          { label: 'Abgelaufen', value: data.value.expired_at },
        ]
          .filter((item) => item.value)
          .map((item) => ({
            label: item.label,
            value: dateTime(item.value),
            datetime: item.value!,
            timezone: adminTimeZone,
          })),
      ]
    : [],
)
onMounted(load)
watch(() => route.params.id, load, { flush: 'sync' })
</script>
<template>
  <section class="operations-page [overflow-wrap:anywhere]">
    <PageHeader
      :title="data?.entity_name || 'Benachrichtigung'"
      :description="data?.payload.organization_name || 'Fachlicher Zustand und zugehörige E-Mails.'"
      record
    >
      <template v-if="data" #badge
        ><StatusBadge :label="notificationTypes[data.notification_type]" /><StatusBadge
          :label="notificationStatuses[data.status]"
          :tone="notificationTone(data.status)"
      /></template>
      <NuxtLink to="/notifications" class="button">Alle Benachrichtigungen</NuxtLink>
      <button class="button" :disabled="loading" @click="load">Aktualisieren</button>
    </PageHeader>
    <RequestState :loading="loading" :error="error" :has-data="!!data" @retry="load" />
    <div v-if="data" class="operations-page" :aria-busy="loading">
      <InlineAlert v-if="!data.delivery_enabled" compact
        >E-Mail-Versand ist deaktiviert (Dry Run).</InlineAlert
      >
      <RecordSection title="Fachlicher Zustand" surface="panel">
        <CompactFacts
          :columns="3"
          missing="omit"
          :items="[
            { label: 'Status', value: notificationStatuses[data.status] },
            { label: 'Typ', value: notificationTypes[data.notification_type] },
            { label: 'Organisation', value: data.payload.organization_name },
            { label: 'Erstmals erkannt', value: dateTime(data.first_detected_at) },
            { label: 'Zuletzt erkannt', value: dateTime(data.last_detected_at) },
            { label: 'Gelöst', value: data.resolved_at ? dateTime(data.resolved_at) : null },
            { label: 'Abgelaufen', value: data.expired_at ? dateTime(data.expired_at) : null },
          ]"
        />
        <p v-if="data.rule" class="text-sm">{{ qualityRuleLabel(data.rule) }}</p>
      </RecordSection>
      <RecordSection title="Vorschau" surface="panel">
        <NotificationPreview :key="data.id" :notification-id="data.id" embedded />
      </RecordSection>
      <RecordSection title="Versandhistorie" surface="plain">
        <NotificationDeliveryTable v-if="data.deliveries.length" :items="data.deliveries" />
        <EmptyState
          v-else
          variant="compact"
          message="Noch keine Versandaufträge. Im Dry Run werden keine angelegt."
        />
      </RecordSection>
      <details class="operations-panel group">
        <summary class="min-h-11 cursor-pointer px-4 py-3 text-sm font-semibold">
          Gespeicherte Daten
        </summary>
        <pre
          class="max-h-80 overflow-auto whitespace-pre-wrap break-all border-t border-slate-200 p-3 text-xs"
          >{{ JSON.stringify(data.payload, null, 2) }}</pre>
      </details>
      <TechnicalInfoBar :items="technical" />
    </div>
  </section>
</template>
