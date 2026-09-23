<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import type { AdminOption, Assignment, AssignmentStatus } from '#shared/contracts'
import { useAuthStore } from '~/stores/auth'
import AssignmentSnooze from './AssignmentSnooze.vue'
import { berlinDate, berlinDueAt } from '~/utils/admin-time'

const props = defineProps<
  | {
      findingId: string
      workflowType?: never
      workflowKey?: never
      entityType?: never
      entityKey?: never
    }
  | {
      findingId?: never
      workflowType: 'geocode_request' | 'notification_delivery'
      workflowKey: string
      entityType: string
      entityKey: string
    }
>()
const { $adminApi } = useNuxtApp()
const auth = useAuthStore()
const selfId = computed(() => {
  const subject = auth.session?.subject ?? ''
  const id = subject.startsWith('admin:') ? subject.slice(6) : ''
  return admins.value.some((admin) => admin.id === id) ? id : ''
})
const timezone = ref('Europe/Berlin')
const admins = ref<AdminOption[]>([])
const assignment = ref<Assignment | null>(null)
const assignee = ref('')
const status = ref<AssignmentStatus>('open')
const due = ref('')
const loading = ref(true)
const saving = ref(false)
const loadError = ref(false)
const feedback = ref<{ message: string; tone: 'success' | 'warning' } | null>(null)
let revision = 0

function sync(value: Assignment | null) {
  assignment.value = value
  assignee.value = value?.assigned_to.id ?? admins.value[0]?.id ?? ''
  status.value = value?.status ?? 'open'
  due.value = berlinDate(value?.due_at ?? null)
}

async function load() {
  const current = ++revision
  loading.value = true
  saving.value = false
  loadError.value = false
  feedback.value = null
  const assignmentRequest = props.findingId
    ? $adminApi.assignmentForFinding(props.findingId)
    : props.workflowType && props.workflowKey
      ? $adminApi.assignmentForWorkflow(props.workflowType, props.workflowKey)
      : Promise.reject(new Error('Incomplete assignment identity'))
  const [options, value] = await Promise.allSettled([$adminApi.admins(), assignmentRequest])
  if (current !== revision) return
  if (options.status === 'rejected' || value.status === 'rejected') {
    admins.value = []
    assignment.value = null
    loadError.value = true
  } else {
    admins.value = options.value.items
    timezone.value = options.value.admin_timezone
    sync(value.value)
  }
  loading.value = false
}

function assignToMe() {
  assignee.value = selfId.value
  void save()
}

async function save() {
  if (!assignee.value || saving.value || loading.value) return
  const dueAt = due.value ? berlinDueAt(due.value) : null
  if (due.value && !dueAt) {
    feedback.value = { message: 'Das Fälligkeitsdatum ist ungültig.', tone: 'warning' }
    return
  }
  const current = revision
  saving.value = true
  feedback.value = null
  try {
    const value = assignment.value
      ? await $adminApi.updateAssignment(assignment.value.id, {
          version: assignment.value.version,
          assigned_to_admin_id: assignee.value,
          status: status.value,
          due_at: dueAt,
        })
      : await $adminApi.createAssignment({
          ...(props.findingId
            ? { finding_id: props.findingId }
            : {
                workflow_type: props.workflowType,
                workflow_key: props.workflowKey,
                entity_type: props.entityType,
                entity_key: props.entityKey,
              }),
          assigned_to_admin_id: assignee.value,
          status: status.value === 'in_progress' ? 'in_progress' : 'open',
          due_at: dueAt,
        })
    if (current !== revision) return
    sync(value)
    feedback.value = { message: 'Zuständigkeit gespeichert.', tone: 'success' }
  } catch {
    if (current !== revision) return
    feedback.value = {
      message:
        'Zuständigkeit wurde zwischenzeitlich geändert oder konnte nicht gespeichert werden.',
      tone: 'warning',
    }
  } finally {
    if (current === revision) saving.value = false
  }
}

watch(() => [props.findingId, props.workflowKey], load, { immediate: true })
onBeforeUnmount(() => revision++)
</script>

<template>
  <section class="space-y-3" aria-labelledby="assignment-heading">
    <SectionHeader
      title="Zuständigkeit"
      title-id="assignment-heading"
      description="Admin-Zuweisung, Bearbeitungsstatus und Fälligkeit."
      as="h2"
    />
    <p v-if="loading" class="text-sm text-slate-500" role="status">Wird geladen …</p>
    <InlineAlert v-else-if="loadError" tone="warning">
      Zuständigkeit konnte nicht geladen werden.
    </InlineAlert>
    <form
      v-else-if="admins.length"
      class="panel grid gap-3 p-4 sm:grid-cols-3 sm:p-5"
      @submit.prevent="save"
    >
      <label>
        <span class="label">Zuständig</span>
        <select v-model="assignee" class="input" required>
          <option v-for="admin in admins" :key="admin.id" :value="admin.id">
            {{ admin.login }}
          </option>
        </select>
      </label>
      <label>
        <span class="label">Status</span>
        <select v-model="status" class="input">
          <option value="open">Offen</option>
          <option value="in_progress">In Bearbeitung</option>
          <option v-if="assignment" value="done">Erledigt</option>
          <option v-if="assignment" value="cancelled">Aufgehoben</option>
        </select>
      </label>
      <label>
        <span class="label">Fällig (Europe/Berlin)</span>
        <input v-model="due" type="date" class="input" />
      </label>
      <div class="flex flex-wrap gap-2 sm:col-span-3">
        <button class="button-primary" :disabled="saving || !assignee">
          {{ assignment ? 'Zuständigkeit aktualisieren' : 'Aufgabe zuweisen' }}
        </button>
        <button
          v-if="(selfId && assignee !== selfId) || (selfId && !assignment)"
          class="button"
          type="button"
          :disabled="saving"
          @click="assignToMe"
        >
          Mir zuweisen
        </button>
      </div>
    </form>
    <InlineAlert v-else tone="info">
      Derzeit ist kein aktiver Systemadministrator für eine Zuweisung verfügbar.
    </InlineAlert>
    <AssignmentSnooze
      v-if="assignment && !loading && !loadError"
      :assignment="assignment"
      :timezone="timezone"
      :disabled="saving"
      @updated="sync"
      @reload="load"
    />
    <InlineAlert v-if="feedback" :tone="feedback.tone">{{ feedback.message }}</InlineAlert>
  </section>
</template>
