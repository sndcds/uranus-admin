<script setup lang="ts">
import { ref, watch, onMounted, onBeforeUnmount } from 'vue'
import type { NotificationDetail } from '#shared/contracts'
import type { ApiFailure } from '#shared/errors'
import { asFailure } from '#shared/errors'
import { dateTime } from '~/utils/presentation'
import {
  notificationStatuses,
  notificationTypes,
  deliveryStatuses,
  deliveryKinds,
} from '~/utils/notifications'
const route = useRoute()
const { $adminApi } = useNuxtApp()
const data = ref<NotificationDetail | null>(null)
const error = ref<ApiFailure | null>(null)
const loading = ref(false)
let generation = 0
async function load() {
  const current = ++generation
  loading.value = true
  data.value = null
  error.value = null
  try {
    const value = await $adminApi.notification(String(route.params.id))
    if (current === generation) data.value = value
  } catch (cause) {
    if (current === generation) error.value = asFailure(cause)
  } finally {
    if (current === generation) loading.value = false
  }
}
onMounted(load)
watch(() => route.params.id, load)
onBeforeUnmount(() => {
  generation++
})
</script>
<template>
  <section class="space-y-5">
    <PageHeader title="Benachrichtigung" description="Fachlicher Zustand und zugehörige E-Mails."
      ><NuxtLink to="/notifications" class="button">Alle Benachrichtigungen</NuxtLink></PageHeader
    >
    <RequestState :loading="loading" :error="error" @retry="load" />
    <template v-if="data">
      <p v-if="!data.delivery_enabled" role="status" class="rounded-xl bg-amber-50 p-4">
        E-Mail-Versand ist deaktiviert (Dry Run).
      </p>
      <DataListShell class="p-4 space-y-2">
        <h2 class="text-lg font-semibold">{{ data.entity_name }}</h2>
        <p>
          {{ data.payload.organization_name }} · {{ notificationTypes[data.notification_type] }} ·
          {{ notificationStatuses[data.status] }}
        </p>
        <p>Erstmals erkannt: {{ dateTime(data.first_detected_at) }}</p>
        <p>Zuletzt erkannt: {{ dateTime(data.last_detected_at) }}</p>
        <p v-if="data.resolved_at">Gelöst: {{ dateTime(data.resolved_at) }}</p>
        <p v-if="data.expired_at">Abgelaufen: {{ dateTime(data.expired_at) }}</p>
        <details>
          <summary>Gespeicherte Daten</summary>
          <pre class="whitespace-pre-wrap break-all">{{
            JSON.stringify(data.payload, null, 2)
          }}</pre>
        </details>
      </DataListShell>
      <NotificationPreview :notification-id="data.id" />
      <h2 class="text-lg font-semibold">Versandhistorie</h2>
      <DataListShell v-if="data.deliveries.length" as="ul" class="divide-y divide-slate-100">
        <li v-for="item in data.deliveries" :key="item.id" class="data-row break-words">
          <NuxtLink
            :to="`/notifications/deliveries/${item.id}`"
            class="font-semibold text-fuchsia-700"
            >{{ deliveryStatuses[item.status] }} · {{ item.recipient }}</NuxtLink
          >
          <p>
            {{ item.locale.toUpperCase() }} · {{ deliveryKinds[item.delivery_kind] }} · Versuche:
            {{ item.attempt_count }}
          </p>
          <p>
            Gesendet: {{ dateTime(item.sent_at) }} · Nächster Versuch:
            {{ dateTime(item.next_attempt_at) }}
          </p>
          <p v-if="item.last_error" class="text-rose-700">{{ item.last_error }}</p>
        </li>
      </DataListShell>
      <EmptyState v-else message="Noch keine Versandaufträge. Im Dry Run werden keine angelegt." />
    </template>
  </section>
</template>
