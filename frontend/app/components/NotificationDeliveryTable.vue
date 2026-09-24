<script setup lang="ts">
import { computed } from 'vue'
import type { NotificationDelivery } from '#shared/contracts'
import {
  deliveryKinds,
  deliveryStatuses,
  deliveryTone,
  smtpErrorLabel,
} from '~/utils/notifications'
import DenseTable from './DenseTable.vue'
import StatusBadge from './StatusBadge.vue'
import OperationTime from './OperationTime.vue'
defineProps<{
  items: readonly (NotificationDelivery & { organization_name?: string })[]
  busy?: boolean
}>()
const columns = computed(
  () =>
    [
      { key: 'status', label: 'Status', width: '19%' },
      { key: 'subject', label: 'Betreff / Empfänger', rowHeader: true, width: '29%' },
      { key: 'delivery_kind', label: 'Art / Versuche', width: '16%' },
      { key: 'queued_at', label: 'Versand / Wiederversuch', width: '23%' },
    ] as const,
)
</script>
<template>
  <DenseTable
    caption="E-Mail-Versände"
    :rows="items"
    :columns="columns"
    :row-key="(item) => item.id"
    stack-at="tablet"
    :busy="busy"
  >
    <template #cell-status="{ row }">
      <StatusBadge :label="deliveryStatuses[row.status]" :tone="deliveryTone(row.status)" />
      <p v-if="row.last_error" class="mt-1 operations-meta">
        {{ smtpErrorLabel(row.last_error) }}
        <code class="block break-all">{{ row.last_error }}</code>
      </p>
    </template>
    <template #cell-subject="{ row }">
      <NuxtLink :to="`/notifications/deliveries/${row.id}`" class="action-link text-sm">{{
        row.subject || 'E-Mail-Versand'
      }}</NuxtLink>
      <p class="text-xs font-normal break-all">{{ row.recipient }}</p>
      <p v-if="row.organization_name" class="operations-meta font-normal">
        {{ row.organization_name }}
      </p>
    </template>
    <template #cell-delivery_kind="{ row }">
      <p>{{ deliveryKinds[row.delivery_kind] }}</p>
      <p class="operations-meta">
        {{ row.locale.toUpperCase() }} · Versuche: {{ row.attempt_count }}
      </p>
    </template>
    <template #cell-queued_at="{ row }">
      <p v-if="row.sent_at" class="operations-meta">
        Gesendet: <OperationTime :value="row.sent_at" />
      </p>
      <p v-else class="operations-meta">Eingereiht: <OperationTime :value="row.queued_at" /></p>
      <p v-if="row.status === 'failed'" class="operations-meta">
        Automatischer neuer Versuch: <OperationTime :value="row.next_attempt_at" />
      </p>
      <p v-if="row.status === 'permanent_failure'" class="operations-meta">
        Automatischer Versand beendet.
      </p>
    </template>
    <template #actions="{ row }">
      <NuxtLink
        :to="`/notifications/deliveries/${row.id}`"
        class="action-link"
        :aria-label="`Versand öffnen: ${row.recipient}`"
        >Versand öffnen</NuxtLink
      >
    </template>
  </DenseTable>
</template>
