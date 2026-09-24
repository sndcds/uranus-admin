<script setup lang="ts">
import { computed } from 'vue'
import type { InboxPage } from '#shared/contracts'
import AssignmentSnooze from './AssignmentSnooze.vue'
import { adminDateTime } from '~/utils/admin-time'
import { findingStatusLabels } from '~/utils/presentation'

type InboxItem = InboxPage['items'][number]

const props = defineProps<{ item: InboxItem; timezone: string }>()
const emit = defineEmits<{ updated: [] }>()

const workflowLabels: Record<string, string> = {
  candidate: 'Standortvorschlag vorhanden',
  ambiguous: 'Mehrere mögliche Standorte',
  not_found: 'Kein Geocoding-Ergebnis',
  insufficient_input: 'Zu wenig Adressdaten',
  failed: 'Fehlgeschlagen',
  permanent_failure: 'Dauerhaft fehlgeschlagen',
}
const taskStatusLabels: Record<string, string> = {
  open: 'Offen',
  in_progress: 'In Bearbeitung',
  done: 'Erledigt',
  cancelled: 'Aufgehoben',
}
const actionLabels: Record<string, string> = {
  event: 'Veranstaltung ansehen',
  organization: 'Organisation ansehen',
  venue: 'Ort ansehen',
  space: 'Raum ansehen',
  user: 'Benutzer ansehen',
  image: 'Bild ansehen',
}

const workflowStatus = computed(() =>
  props.item.workflow_status ? workflowLabels[props.item.workflow_status] : null,
)
const taskStatus = computed(() => {
  if (!props.item.assignment && props.item.status === 'snoozed')
    return props.item.snoozed_until
      ? 'Fachlich zurückgestellt'
      : 'Fachliche Zurückstellung abgelaufen'
  return (
    taskStatusLabels[
      props.item.assignment?.status ?? findingStatusLabels[props.item.status] ?? props.item.status
    ] ??
    findingStatusLabels[props.item.status] ??
    props.item.status
  )
})
const workflowAction = computed(() => {
  const workflowType = props.item.assignment?.workflow_type
  if (props.item.kind === 'geocode_request' || workflowType === 'geocode_request')
    return 'Vorschlag prüfen'
  if (props.item.kind === 'notification_delivery' || workflowType === 'notification_delivery')
    return 'Zustellung ansehen'
  return 'Befund ansehen'
})
const entityAction = computed(() => actionLabels[props.item.entity_type] ?? 'Datensatz ansehen')
const context = computed(() => {
  const organization = props.item.organization_name?.trim()
  return organization && organization !== props.item.entity_name ? organization : null
})
const candidateText = computed(() => {
  const count = props.item.candidate_count
  if (!count) return null
  return `${count} ${count === 1 ? 'Kandidat' : 'Kandidaten'}`
})
const icon = computed<'pin' | 'mail' | 'quality' | 'list'>(() => {
  const workflowType = props.item.assignment?.workflow_type
  if (props.item.kind === 'geocode_request' || workflowType === 'geocode_request') return 'pin'
  if (props.item.kind === 'notification_delivery' || workflowType === 'notification_delivery')
    return 'mail'
  return props.item.kind === 'finding' ? 'quality' : 'list'
})
</script>

<template>
  <li
    class="data-row grid min-w-0 grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-1 xl:grid-cols-[auto_minmax(0,1fr)_minmax(12rem,0.45fr)]"
  >
    <span
      class="mt-2 grid size-8 place-items-center rounded-lg bg-slate-100 text-slate-600"
      aria-hidden="true"
    >
      <AppIcon :name="icon" :size="17" />
    </span>
    <div class="min-w-0 py-1">
      <div class="flex flex-wrap items-baseline gap-x-2">
        <h3 class="type-row-title">{{ item.entity_name }}</h3>
        <span class="operations-meta">{{ item.title }}</span>
      </div>
      <p class="text-sm text-slate-700">
        {{ item.summary }}<template v-if="candidateText"> · {{ candidateText }}</template>
      </p>
      <p v-if="context" class="operations-meta">{{ context }}</p>
      <div class="mt-1 flex flex-wrap items-center gap-1">
        <EntityTypeBadge :type="item.entity_type" />
        <SeverityBadge v-if="item.severity" :severity="item.severity" />
        <StatusBadge :label="taskStatus" />
        <span v-if="workflowStatus && workflowStatus !== item.summary" class="operations-meta">{{
          workflowStatus
        }}</span>
      </div>
      <div class="flex flex-wrap items-center gap-x-4">
        <NuxtLink :to="item.href" class="action-link text-xs"
          >{{ workflowAction }} <AppIcon name="arrow" :size="13"
        /></NuxtLink>
        <NuxtLink
          v-if="item.entity_action"
          :to="item.entity_action.href"
          class="action-link text-xs"
          >{{ entityAction }}</NuxtLink
        >
      </div>
    </div>
    <div class="col-start-2 min-w-0 pb-1 xl:col-start-3 xl:row-start-1 xl:py-1">
      <div class="mb-1 flex flex-wrap gap-1">
        <StatusBadge v-if="item.is_overdue" label="Überfällig" tone="error" />
        <StatusBadge v-else-if="item.due_today" label="Heute fällig" tone="warning" />
        <StatusBadge v-if="item.snoozed_until" label="Wiedervorlage" />
      </div>
      <p class="text-xs font-medium text-slate-800">
        {{
          item.assignment ? `Zuständig: ${item.assignment.assigned_to.login}` : 'Nicht zugewiesen'
        }}
      </p>
      <p v-if="item.due_at" class="operations-meta">
        Fällig:
        <time :datetime="item.due_at" :title="timezone">{{
          adminDateTime(item.due_at, timezone)
        }}</time>
      </p>
      <p v-else class="operations-meta">
        Aktualisiert:
        <time :datetime="item.occurred_at" :title="timezone">{{
          adminDateTime(item.occurred_at, timezone)
        }}</time>
      </p>
      <p v-if="item.snoozed_until" class="operations-meta">
        Rückkehr in die Inbox:
        <time :datetime="item.snoozed_until">{{
          adminDateTime(item.snoozed_until, timezone)
        }}</time>
        ({{ timezone }})
      </p>
      <p
        v-if="
          item.finding_snoozed_until &&
          item.snoozed_until &&
          Date.parse(item.finding_snoozed_until) > Date.now()
        "
        class="operations-meta"
      >
        Fachliche Zurückstellung bis
        <time :datetime="item.finding_snoozed_until">{{
          adminDateTime(item.finding_snoozed_until, timezone)
        }}</time
        >. Unabhängig von der operativen Wiedervorlage.
      </p>
      <AssignmentSnooze
        v-if="item.assignment"
        compact
        :assignment="item.assignment"
        :show-timestamp="false"
        :timezone="timezone"
        @updated="emit('updated')"
        @reload="emit('updated')"
      />
    </div>
  </li>
</template>
