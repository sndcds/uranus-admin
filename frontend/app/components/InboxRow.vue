<script setup lang="ts">
import { computed } from 'vue'
import type { InboxPage } from '#shared/contracts'
import { dateTime } from '~/utils/presentation'

type InboxItem = InboxPage['items'][number]

const props = defineProps<{ item: InboxItem }>()

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
const taskStatus = computed(
  () => taskStatusLabels[props.item.assignment?.status ?? props.item.status] ?? props.item.status,
)
const workflowAction = computed(() => {
  const workflowType = props.item.assignment?.workflow_type
  if (props.item.kind === 'geocode_request' || workflowType === 'geocode_request')
    return 'Vorschlag prüfen'
  if (props.item.kind === 'notification_delivery' || workflowType === 'notification_delivery')
    return 'Zustellung ansehen'
  return 'Finding ansehen'
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
    class="data-row grid min-w-0 grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-2 transition-colors lg:grid-cols-[auto_minmax(0,1fr)_auto]"
  >
    <span
      class="mt-0.5 grid size-8 place-items-center rounded-lg bg-slate-100 text-slate-600"
      aria-hidden="true"
    >
      <AppIcon :name="icon" :size="17" />
    </span>
    <div class="min-w-0">
      <div class="flex flex-wrap items-center gap-x-2 gap-y-1">
        <h3 class="min-w-0 break-words text-sm font-semibold text-slate-900">
          {{ item.entity_name }}
        </h3>
        <EntityTypeBadge :type="item.entity_type" />
        <SeverityBadge v-if="item.severity" :severity="item.severity" />
      </div>
      <p v-if="context" class="mt-0.5 break-words text-xs text-slate-500">{{ context }}</p>
      <p class="mt-2 text-sm font-medium text-slate-800">{{ item.title }}</p>
      <p class="mt-0.5 break-words text-sm text-slate-600">
        {{ item.summary }}<template v-if="candidateText"> · {{ candidateText }}</template>
      </p>
      <p class="mt-1.5 break-words text-xs text-slate-500">
        {{
          item.assignment ? `Zuständig: ${item.assignment.assigned_to.login}` : 'Nicht zugewiesen'
        }}
        <template v-if="item.due_at"> · fällig {{ dateTime(item.due_at) }}</template>
        <template v-else> · aktualisiert {{ dateTime(item.occurred_at) }}</template>
      </p>
      <div class="mt-2 flex flex-wrap items-center gap-x-4 gap-y-2 text-xs">
        <NuxtLink
          :to="item.href"
          class="rounded font-semibold text-fuchsia-700 underline-offset-4 hover:underline"
          >{{ workflowAction }} <AppIcon name="arrow" :size="13"
        /></NuxtLink>
        <NuxtLink
          v-if="item.entity_action"
          :to="item.entity_action.href"
          class="rounded text-slate-600 underline-offset-4 hover:text-fuchsia-700 hover:underline"
          >{{ entityAction }}</NuxtLink
        >
      </div>
    </div>
    <div
      class="col-start-2 flex flex-wrap items-center gap-1.5 text-xs lg:col-start-3 lg:row-start-1 lg:max-w-52 lg:justify-end"
    >
      <StatusBadge v-if="workflowStatus" :label="workflowStatus" />
      <StatusBadge :label="taskStatus" />
      <StatusBadge v-if="item.is_overdue" label="Überfällig" tone="error" />
      <StatusBadge v-else-if="item.due_today" label="Heute fällig" tone="warning" />
    </div>
  </li>
</template>
