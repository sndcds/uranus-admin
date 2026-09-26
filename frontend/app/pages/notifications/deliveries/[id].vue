<script setup lang="ts">
import { ref, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import type { NotificationDeliveryDetail } from '#shared/contracts'
import type { ApiFailure } from '#shared/errors'
import { asFailure } from '#shared/errors'
import { dateTime, adminTimeZone } from '~/utils/presentation'
import AppModal from '~/components/AppModal.vue'
import {
  deliveryStatuses,
  deliveryKinds,
  deliveryTone,
  notificationStatuses,
  notificationTypes,
  smtpErrorLabel,
} from '~/utils/notifications'
import RecordSection from '~/components/RecordSection.vue'
import CompactFacts from '~/components/CompactFacts.vue'
import TechnicalInfoBar from '~/components/TechnicalInfoBar.vue'
import StatusBadge from '~/components/StatusBadge.vue'
import InlineAlert from '~/components/InlineAlert.vue'
import OperationTime from '~/components/OperationTime.vue'
const route = useRoute()
const { $adminApi } = useNuxtApp()
const data = ref<NotificationDeliveryDetail | null>(null)
const error = ref<ApiFailure | null>(null)
const loading = ref(false)
const modal = ref<InstanceType<typeof AppModal> | null>(null)
const retrying = ref(false)
const retryError = ref<ApiFailure | null>(null)
let generation = 0
const canRetry = computed(
  () =>
    data.value?.status === 'permanent_failure' &&
    !data.value.retries.some((attempt) => attempt.status !== 'cancelled'),
)
async function retry() {
  if (loading.value || error.value || retrying.value || !data.value || !canRetry.value) return
  const current = generation
  retrying.value = true
  retryError.value = null
  try {
    const result = await $adminApi.retryNotificationDelivery(data.value.id)
    if (generation !== current) return
    modal.value?.close()
    await navigateTo(`/notifications/deliveries/${result.delivery_id}`)
  } catch (cause) {
    if (generation === current) {
      retryError.value = asFailure(cause)
      if ([401, 403, 404].includes(retryError.value.status)) {
        error.value = retryError.value
        data.value = null
        modal.value?.close()
      }
    }
  } finally {
    if (generation === current) retrying.value = false
  }
}
async function load() {
  const current = ++generation
  retryError.value = null
  retrying.value = false
  modal.value?.close()
  loading.value = true
  const id = String(route.params.id)
  if (data.value?.id !== id) data.value = null
  error.value = null
  try {
    const value = await $adminApi.notificationDelivery(String(route.params.id))
    if (current === generation) data.value = value
  } catch (cause) {
    if (current === generation) {
      error.value = asFailure(cause)
      if ([401, 403, 404, 422].includes(error.value.status)) data.value = null
    }
  } finally {
    if (current === generation) loading.value = false
  }
}
onMounted(load)
watch(() => route.params.id, load, { flush: 'sync' })
onBeforeUnmount(() => {
  generation++
})
const technical = computed(() =>
  data.value
    ? [
        { label: 'Delivery ID', value: data.value.id, mono: true, copyable: true },
        {
          label: 'Organisation UUID',
          value: data.value.organization_id,
          mono: true,
          copyable: true,
        },
        {
          label: 'Vorherige Delivery ID',
          value: data.value.retry_of_delivery_id,
          mono: true,
          copyable: true,
        },
        { label: 'Versuche', value: data.value.attempt_count },
        ...[
          { label: 'Eingereiht', value: data.value.queued_at },
          { label: 'Gesendet', value: data.value.sent_at },
          { label: 'Nächster Versuch', value: data.value.next_attempt_at },
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
</script>
<template>
  <section class="operations-page [overflow-wrap:anywhere]">
    <PageHeader
      stack-actions
      :title="data?.subject || 'E-Mail-Versand'"
      :description="data?.recipient || 'Ein Versandauftrag mit unveränderlicher Historie.'"
      record
    >
      <template v-if="data" #badge
        ><StatusBadge
          :label="deliveryStatuses[data.status]"
          :tone="deliveryTone(data.status)" /><StatusBadge
          :label="deliveryKinds[data.delivery_kind]" /><StatusBadge
          :label="data.locale.toUpperCase()"
      /></template>
      <GraphLink
        v-if="data"
        entity-type="organization"
        :entity-key="data.organization_id"
        variant="compact"
      />
      <EntityInspectorLink
        v-if="data"
        entity-type="organization"
        :entity-key="data.organization_id"
      />
      <NuxtLink to="/notifications/deliveries" class="button">E-Mail-Versände</NuxtLink>
      <button class="button" :disabled="loading || retrying" @click="load">Aktualisieren</button>
    </PageHeader>
    <RequestState :loading="loading" :error="error" :has-data="!!data" @retry="load" />
    <div v-if="data" class="operations-page" :aria-busy="loading">
      <InlineAlert v-if="data.retry_of_delivery_id && data.status === 'queued'" compact
        >Neuer Versand wurde eingereiht. Der Worker verarbeitet ihn beim nächsten zulässigen
        Lauf.</InlineAlert
      >
      <RecordSection title="Versandinformationen" surface="panel">
        <CompactFacts
          :columns="3"
          missing="omit"
          :items="[
            { label: 'Art', value: deliveryKinds[data.delivery_kind] },
            { label: 'Sprache', value: data.locale.toUpperCase() },
            { label: 'Status', value: deliveryStatuses[data.status] },
            { label: 'Versuche', value: data.attempt_count },
            { label: 'Eingereiht', value: data.queued_at ? dateTime(data.queued_at) : null },
            { label: 'Gesendet', value: data.sent_at ? dateTime(data.sent_at) : null },
            {
              label: 'Nächster Versuch',
              value: data.next_attempt_at ? dateTime(data.next_attempt_at) : null,
            },
          ]"
        />
      </RecordSection>
      <RecordSection
        v-if="data.last_error || ['failed', 'permanent_failure'].includes(data.status)"
        title="Fehler und Wiederholung"
        surface="panel"
      >
        <InlineAlert
          v-if="data.last_error"
          compact
          :tone="data.status === 'permanent_failure' ? 'warning' : 'info'"
        >
          <p>{{ smtpErrorLabel(data.last_error) }}</p>
          <code class="block break-all text-xs">{{ data.last_error }}</code>
        </InlineAlert>
        <p v-if="data.status === 'failed'" class="text-sm">
          Automatischer neuer Versuch: <OperationTime :value="data.next_attempt_at" />
        </p>
        <p v-if="data.status === 'permanent_failure'" class="text-sm">
          Der automatische Versand wurde beendet.
        </p>
        <button
          v-if="canRetry"
          class="button-primary"
          :disabled="retrying || loading || !!error"
          @click="modal?.open()"
        >
          Erneut versuchen
        </button>
        <p v-else-if="data.status === 'permanent_failure'" class="operations-meta">
          Ein weiterer Versandauftrag besteht bereits. Prüfe die Versandkette.
        </p>
      </RecordSection>
      <RecordSection
        title="Zuständigkeit"
        description="Operative Bearbeitung, Zuständigkeit und Fälligkeit."
        surface="panel"
      >
        <AssignmentEditor
          :key="data.id"
          embedded
          workflow-type="notification_delivery"
          :workflow-key="data.id"
          entity-type="organization"
          :entity-key="data.organization_id"
        />
      </RecordSection>
      <RecordSection title="Enthaltene Hinweise">
        <DataListShell v-if="data.notifications.length" as="ul" dense>
          <li
            v-for="item in data.notifications"
            :key="item.id"
            class="data-row flex flex-wrap items-center justify-between gap-x-3"
          >
            <div class="min-w-0">
              <NuxtLink :to="`/notifications/${item.id}`" class="action-link">{{
                item.entity_name || 'Benachrichtigung'
              }}</NuxtLink>
              <p class="operations-meta">{{ notificationTypes[item.notification_type] }}</p>
            </div>
            <StatusBadge :label="notificationStatuses[item.status]" />
          </li>
        </DataListShell>
        <EmptyState v-else variant="compact" message="Keine enthaltenen Hinweise verfügbar." />
      </RecordSection>
      <RecordSection
        v-if="data.retry_of_delivery_id || data.retries.length"
        title="Versandkette"
        surface="panel"
      >
        <NuxtLink
          v-if="data.retry_of_delivery_id"
          :to="`/notifications/deliveries/${data.retry_of_delivery_id}`"
          class="action-link"
          >Vorheriger Versand</NuxtLink
        >
        <DataListShell v-if="data.retries.length" as="ul" dense>
          <li
            v-for="attempt in data.retries"
            :key="attempt.id"
            class="data-row flex flex-wrap items-center justify-between gap-x-3"
          >
            <NuxtLink :to="`/notifications/deliveries/${attempt.id}`" class="action-link"
              >Weiterer Versuch: {{ deliveryStatuses[attempt.status] }}</NuxtLink
            >
            <span class="operations-meta"
              >Eingereiht: <OperationTime :value="attempt.queued_at" /> · Versuche:
              {{ attempt.attempt_count }}</span
            >
          </li>
        </DataListShell>
      </RecordSection>
      <TechnicalInfoBar :items="technical" />
    </div>
    <AppModal ref="modal" title="Erneut versuchen?">
      <p class="my-4">
        Der aktuelle Zustand wird erneut geprüft und ein neuer Versandauftrag erstellt. Bitte kläre
        zuvor die SMTP-Ursache.
      </p>
      <InlineAlert v-if="retryError" compact tone="error" class="my-4">{{
        retryError.message
      }}</InlineAlert>
      <button class="button-primary" :disabled="retrying" @click="retry">
        {{ retrying ? 'Wird eingereiht…' : 'Versand erneut einreihen' }}
      </button>
    </AppModal>
  </section>
</template>
