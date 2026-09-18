<script setup lang="ts">
import { ref, watch, onMounted, onBeforeUnmount } from 'vue'
import type { NotificationDeliveryDetail } from '#shared/contracts'
import type { ApiFailure } from '#shared/errors'
import { asFailure } from '#shared/errors'
import { dateTime } from '~/utils/presentation'
import AppModal from '~/components/AppModal.vue'
import { deliveryStatuses, deliveryKinds, smtpErrorLabel } from '~/utils/notifications'
const route = useRoute()
const { $adminApi } = useNuxtApp()
const data = ref<NotificationDeliveryDetail | null>(null)
const error = ref<ApiFailure | null>(null)
const loading = ref(false)
const modal = ref<InstanceType<typeof AppModal> | null>(null)
const retrying = ref(false)
const retryError = ref<ApiFailure | null>(null)
let generation = 0
async function retry() {
  if (retrying.value || !data.value || data.value.status !== 'permanent_failure') return
  const current = generation
  retrying.value = true
  retryError.value = null
  try {
    const result = await $adminApi.retryNotificationDelivery(data.value.id)
    if (generation !== current) return
    modal.value?.close()
    await navigateTo(`/notifications/deliveries/${result.delivery_id}`)
  } catch (cause) {
    if (generation === current) retryError.value = asFailure(cause)
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
  data.value = null
  error.value = null
  try {
    const value = await $adminApi.notificationDelivery(String(route.params.id))
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
    <PageHeader
      title="E-Mail-Versand"
      description="Ein Versandauftrag mit unveränderlicher Historie."
      ><NuxtLink to="/notifications/deliveries" class="button"
        >E-Mail-Versände</NuxtLink
      ></PageHeader
    >
    <RequestState :loading="loading" :error="error" @retry="load" />
    <template v-if="data">
      <DataListShell class="p-4 space-y-2 break-words">
        <h2 class="text-lg font-semibold">{{ data.subject }}</h2>
        <p>{{ data.recipient }} · {{ data.locale.toUpperCase() }}</p>
        <p>
          {{ deliveryKinds[data.delivery_kind] }} · {{ deliveryStatuses[data.status] }} · Versuche:
          {{ data.attempt_count }}
        </p>
        <p>Eingereiht: {{ dateTime(data.queued_at) }}</p>
        <p>Gesendet: {{ dateTime(data.sent_at) }}</p>
        <p v-if="data.status === 'failed'">
          Automatischer neuer Versuch: {{ dateTime(data.next_attempt_at) }}
        </p>
        <p v-if="data.status === 'permanent_failure'">Der automatische Versand wurde beendet.</p>
        <p v-if="data.last_error">
          {{ smtpErrorLabel(data.last_error) }} <code>{{ data.last_error }}</code>
        </p>
        <p v-if="data.retry_of_delivery_id">
          Erneuter Versuch von:
          <NuxtLink
            :to="`/notifications/deliveries/${data.retry_of_delivery_id}`"
            class="text-fuchsia-700 underline"
            >Vorheriger Versand</NuxtLink
          >
        </p>
        <p v-if="data.retry_of_delivery_id && data.status === 'queued'" role="status">
          Neuer Versand wurde eingereiht. Der Worker verarbeitet ihn beim nächsten zulässigen Lauf.
        </p>
        <p v-for="attempt in data.retries" :key="attempt.id">
          Weiterer Versuch:
          <NuxtLink
            :to="`/notifications/deliveries/${attempt.id}`"
            class="text-fuchsia-700 underline"
            >{{ deliveryStatuses[attempt.status] }}</NuxtLink
          >
        </p>
        <button
          v-if="
            data.status === 'permanent_failure' &&
            !data.retries.some((attempt) => attempt.status !== 'cancelled')
          "
          class="button"
          :disabled="retrying"
          @click="modal?.open()"
        >
          Erneut versuchen
        </button>
      </DataListShell>
      <h2 class="text-lg font-semibold">Enthaltene Hinweise</h2>
      <DataListShell as="ul"
        ><li v-for="item in data.notifications" :key="item.id" class="data-row">
          <NuxtLink :to="`/notifications/${item.id}`" class="text-fuchsia-700">{{
            item.entity_name
          }}</NuxtLink>
        </li></DataListShell
      >
    </template>
    <AppModal ref="modal" title="Erneut versuchen?">
      <p class="my-4">
        Der aktuelle Zustand wird erneut geprüft und ein neuer Versandauftrag erstellt. Bitte kläre
        zuvor die SMTP-Ursache.
      </p>
      <p v-if="retryError" role="alert" class="my-4 text-rose-700">{{ retryError.message }}</p>
      <button class="button" :disabled="retrying" @click="retry">
        {{ retrying ? 'Wird eingereiht…' : 'Versand erneut einreihen' }}
      </button>
    </AppModal>
  </section>
</template>
