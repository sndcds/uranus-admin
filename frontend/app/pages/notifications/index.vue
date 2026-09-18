<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount } from 'vue'
import type { NotificationPage, NotificationStatus, NotificationType } from '#shared/contracts'
import type { ApiFailure } from '#shared/errors'
import { asFailure } from '#shared/errors'
import { dateTime } from '~/utils/presentation'
import { notificationStatuses, notificationTypes } from '~/utils/notifications'
const { $adminApi } = useNuxtApp()
const data = ref<NotificationPage | null>(null)
const error = ref<ApiFailure | null>(null)
const loading = ref(false)
const status = ref<NotificationStatus | ''>('')
const type = ref<NotificationType | ''>('')
const organization = ref('')
const days = ref('')
let generation = 0
async function load(page = 1) {
  const current = ++generation
  loading.value = true
  data.value = null
  error.value = null
  try {
    const value = await $adminApi.notifications({
      status: status.value || undefined,
      notification_type: type.value || undefined,
      organization_id: organization.value || undefined,
      days: days.value || undefined,
      page,
    })
    if (current === generation) data.value = value
  } catch (cause) {
    if (current === generation) error.value = asFailure(cause)
  } finally {
    if (current === generation) loading.value = false
  }
}
onMounted(() => load())
onBeforeUnmount(() => {
  generation++
})
</script>
<template>
  <section class="space-y-5">
    <PageHeader
      title="Benachrichtigungen"
      description="Operative E-Mail-Hinweise und Versandhistorie."
    />
    <FilterBar @apply="load()">
      <label
        >Status<select v-model="status" class="field">
          <option value="">Alle</option>
          <option v-for="(label, value) in notificationStatuses" :key="value" :value="value">
            {{ label }}
          </option>
        </select></label
      >
      <label
        >Typ<select v-model="type" class="field">
          <option value="">Alle</option>
          <option v-for="(label, value) in notificationTypes" :key="value" :value="value">
            {{ label }}
          </option>
        </select></label
      >
      <label
        >Organisation (UUID)<input
          v-model="organization"
          class="field"
          placeholder="Alle Organisationen"
      /></label>
      <label
        >Zeitraum<select v-model="days" class="field">
          <option value="">Gesamter Zeitraum</option>
          <option value="7">Letzte 7 Tage</option>
          <option value="30">Letzte 30 Tage</option>
        </select></label
      >
      <button class="button" :disabled="loading">Filter anwenden</button>
    </FilterBar>
    <RequestState :loading="loading" :error="error" @retry="load()" />
    <template v-if="data">
      <p
        v-if="!data.health.delivery_enabled"
        role="status"
        class="rounded-xl bg-amber-50 p-4 text-amber-900"
      >
        E-Mail-Versand ist deaktiviert (Dry Run).
      </p>
      <p v-if="!data.health.source_capability" role="status" class="rounded-xl bg-amber-50 p-4">
        Notification-Konfiguration ist im Source-Schema nicht verfügbar. Versand bleibt deaktiviert.
      </p>
      <ul v-if="data.health.config_issues.length" class="rounded-xl bg-rose-50 p-4">
        <li v-for="issue in data.health.config_issues" :key="issue.organization_id">
          Ungültige Benachrichtigungskonfiguration: {{ issue.organization_name }}. Kein Versand.
        </li>
      </ul>
      <dl class="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div
          v-for="(label, key) in {
            active: 'Aktiv',
            sent_today: 'Heute gesendet',
            failed: 'Fehlgeschlagen',
            queued: 'Ausstehend',
          }"
          :key="key"
          class="rounded-xl bg-white p-4"
        >
          <dt class="muted">{{ label }}</dt>
          <dd class="text-2xl font-semibold">{{ data.summary[key] }}</dd>
        </div>
      </dl>
      <ResultSummary
        :total="data.pagination.total"
        :visible="data.items.length"
        noun="Benachrichtigungen"
      />
      <DataListShell v-if="data.items.length" as="ul" class="divide-y divide-slate-100">
        <li v-for="item in data.items" :key="item.id" class="data-row">
          <div class="flex flex-wrap gap-2 justify-between">
            <NuxtLink class="font-semibold text-fuchsia-700" :to="`/notifications/${item.id}`">{{
              item.entity_name
            }}</NuxtLink
            ><span>{{ notificationStatuses[item.status] }}</span>
          </div>
          <p>
            {{ item.payload.organization_name }} · {{ notificationTypes[item.notification_type] }}
          </p>
          <p class="muted">Zuletzt erkannt: {{ dateTime(item.last_detected_at) }}</p>
        </li>
      </DataListShell>
      <EmptyState v-else message="Keine Benachrichtigungen für diese Auswahl." />
      <PaginationBar :pagination="data.pagination" :loading="loading" @change="load" />
    </template>
  </section>
</template>
