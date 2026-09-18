<script setup lang="ts">
import { ref, watch, onMounted, onBeforeUnmount } from 'vue'
import type { NotificationDeliveryDetail } from '#shared/contracts'
import type { ApiFailure } from '#shared/errors'
import { asFailure } from '#shared/errors'
import { dateTime } from '~/utils/presentation'
import { deliveryStatuses, deliveryKinds } from '~/utils/notifications'
const route = useRoute()
const { $adminApi } = useNuxtApp()
const data = ref<NotificationDeliveryDetail | null>(null)
const error = ref<ApiFailure | null>(null)
const loading = ref(false)
let generation = 0
async function load() {
  const current = ++generation
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
      ><NuxtLink to="/notifications" class="button">Benachrichtigungen</NuxtLink></PageHeader
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
        <p>Nächster Versuch: {{ dateTime(data.next_attempt_at) }}</p>
        <p v-if="data.last_error" class="text-rose-700">{{ data.last_error }}</p>
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
  </section>
</template>
