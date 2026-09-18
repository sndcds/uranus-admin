<script setup lang="ts">
import { ref, watch, onMounted, onBeforeUnmount } from 'vue'
import { notificationDeliveryStatusSchema, notificationDeliveryKindSchema } from '#shared/contracts'
import type {
  NotificationDeliveryPage,
  NotificationDeliveryStatus,
  NotificationDeliveryKind,
} from '#shared/contracts'
import { asFailure } from '#shared/errors'
import type { ApiFailure } from '#shared/errors'
import { dateTime } from '~/utils/presentation'
import { deliveryKinds, deliveryStatuses, smtpErrorLabel } from '~/utils/notifications'
const route = useRoute()
const router = useRouter()
const { $adminApi } = useNuxtApp()
const data = ref<NotificationDeliveryPage | null>(null)
const error = ref<ApiFailure | null>(null)
const loading = ref(false)
const status = ref<NotificationDeliveryStatus | ''>('')
const kind = ref<NotificationDeliveryKind | ''>('')
const organization = ref('')
const days = ref('')
let generation = 0
function textQuery(key: string) {
  const value = route.query[key]
  return typeof value === 'string' ? value : ''
}
async function load() {
  status.value = notificationDeliveryStatusSchema.safeParse(textQuery('status')).data ?? ''
  kind.value = notificationDeliveryKindSchema.safeParse(textQuery('delivery_kind')).data ?? ''
  organization.value = textQuery('organization_id')
  days.value = textQuery('days')
  const current = ++generation
  loading.value = true
  data.value = null
  error.value = null
  try {
    const result = await $adminApi.notificationDeliveries({
      status: status.value || undefined,
      delivery_kind: kind.value || undefined,
      organization_id: organization.value || undefined,
      days: days.value || undefined,
      page: textQuery('page') || 1,
    })
    if (generation === current) data.value = result
  } catch (cause) {
    if (generation === current) error.value = asFailure(cause)
  } finally {
    if (generation === current) loading.value = false
  }
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
    },
  })
  if (route.fullPath === before) await load()
}
onMounted(load)
watch(() => route.fullPath, load)
onBeforeUnmount(() => {
  generation++
})
</script>
<template>
  <section class="space-y-5">
    <PageHeader
      title="E-Mail-Versände"
      description="Versandstatus, Fehler und erneute Zustellversuche prüfen."
    >
      <NuxtLink to="/notifications" class="button">Benachrichtigungen</NuxtLink>
    </PageHeader>
    <FilterBar @apply="apply()">
      <label
        >Status<select v-model="status" class="input">
          <option value="">Alle</option>
          <option v-for="(label, value) in deliveryStatuses" :key="value" :value="value">
            {{ label }}
          </option>
        </select></label
      >
      <label
        >Art<select v-model="kind" class="input">
          <option value="">Alle</option>
          <option v-for="(label, value) in deliveryKinds" :key="value" :value="value">
            {{ label }}
          </option>
        </select></label
      >
      <label
        >Organisation (UUID)<input
          v-model="organization"
          class="input"
          placeholder="Alle Organisationen"
      /></label>
      <label
        >Zeitraum<select v-model="days" class="input">
          <option value="">Gesamter Zeitraum</option>
          <option value="7">Letzte 7 Tage</option>
          <option value="30">Letzte 30 Tage</option>
        </select></label
      >
      <button class="button" :disabled="loading">Filter anwenden</button>
    </FilterBar>
    <RequestState :loading="loading" :error="error" @retry="load" />
    <template v-if="data">
      <p
        v-if="!data.delivery_enabled"
        role="status"
        class="rounded-xl bg-amber-50 p-4 text-amber-900"
      >
        E-Mail-Versand ist deaktiviert (Dry Run).
      </p>
      <ResultSummary
        :total="data.pagination.total"
        :visible="data.items.length"
        noun="E-Mail-Versände"
      />
      <DataListShell v-if="data.items.length" as="ul" class="divide-y divide-slate-100">
        <li v-for="item in data.items" :key="item.id" class="data-row break-words">
          <NuxtLink
            :to="`/notifications/deliveries/${item.id}`"
            class="font-semibold text-fuchsia-700"
            >{{ item.subject || 'E-Mail-Versand' }}</NuxtLink
          >
          <p>
            {{ item.recipient }} · {{ item.locale.toUpperCase() }} · {{ item.organization_name }}
          </p>
          <p>
            {{ deliveryKinds[item.delivery_kind] }} · {{ deliveryStatuses[item.status] }} ·
            Versuche: {{ item.attempt_count }}
          </p>
          <p class="muted">
            Eingereiht: {{ dateTime(item.queued_at) }} · Gesendet: {{ dateTime(item.sent_at) }}
          </p>
          <p v-if="item.status === 'failed'">
            Automatischer neuer Versuch: {{ dateTime(item.next_attempt_at) }}
          </p>
          <p v-if="item.last_error">
            {{ smtpErrorLabel(item.last_error) }} <code>{{ item.last_error }}</code>
          </p>
        </li>
      </DataListShell>
      <EmptyState v-else message="Keine E-Mail-Versände für diese Auswahl." />
      <PaginationBar :pagination="data.pagination" :loading="loading" @change="apply" />
    </template>
  </section>
</template>
