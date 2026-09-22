<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref } from 'vue'
import type { Assignment } from '#shared/contracts'
import { asFailure } from '#shared/errors'
import AppModal from './AppModal.vue'
import { adminDateTime, adminLocalInstant, snoozePreset } from '~/utils/admin-time'

const props = withDefaults(
  defineProps<{
    assignment: Assignment
    timezone: string
    disabled?: boolean
    showTimestamp?: boolean
  }>(),
  { showTimestamp: true },
)
const emit = defineEmits<{ updated: [assignment: Assignment]; reload: [] }>()
const { $adminApi } = useNuxtApp()
const modal = ref<InstanceType<typeof AppModal> | null>(null)
const custom = ref('')
const opened = ref(false)
const saving = ref(false)
const error = ref('')
const conflict = ref(false)
let mounted = true
const active = computed(
  () => !!props.assignment.snoozed_until && Date.parse(props.assignment.snoozed_until) > Date.now(),
)
const editable = computed(() => ['open', 'in_progress'].includes(props.assignment.status))
function open() {
  error.value = ''
  conflict.value = false
  custom.value = ''
  opened.value = true
  modal.value?.open()
}
async function save(until: string | null) {
  if (saving.value || props.disabled) return
  if (
    until &&
    (Date.parse(until) <= Date.now() || Date.parse(until) > Date.now() + 365 * 86400000)
  ) {
    error.value = 'Bitte einen zukünftigen Zeitpunkt innerhalb der nächsten 365 Tage wählen.'
    return
  }
  const id = props.assignment.id
  saving.value = true
  error.value = ''
  try {
    const value = await $adminApi.updateAssignment(id, {
      version: props.assignment.version,
      snoozed_until: until,
    })
    if (!mounted || props.assignment.id !== id) return
    saving.value = false
    await nextTick()
    if (!mounted) return
    modal.value?.close()
    emit('updated', value)
  } catch (cause) {
    if (!mounted || props.assignment.id !== id) return
    conflict.value = asFailure(cause).code === 'assignment_conflict'
    error.value = conflict.value
      ? 'Die Aufgabe wurde zwischenzeitlich geändert. Bitte neu laden und erneut entscheiden.'
      : 'Die Wiedervorlage konnte nicht gespeichert werden. Bitte Zeitpunkt und Aufgabenstatus prüfen.'
  } finally {
    if (mounted) saving.value = false
  }
}
function preset(days: 1 | 3 | 7) {
  const until = snoozePreset(days, new Date(), props.timezone)
  if (until) void save(until)
}
function saveCustom() {
  const until = adminLocalInstant(custom.value, props.timezone)
  if (!until) {
    error.value =
      'Dieses lokale Datum oder diese Uhrzeit existiert nicht. Bitte die Zeitumstellung beachten.'
    return
  }
  void save(until)
}
function reload() {
  modal.value?.close()
  emit('reload')
}
onBeforeUnmount(() => {
  mounted = false
})
</script>

<template>
  <div class="min-w-0 space-y-2">
    <p
      v-if="showTimestamp && active && assignment.snoozed_until"
      class="break-words text-sm text-slate-700"
    >
      Wiedervorlage:
      <time :datetime="assignment.snoozed_until">{{
        adminDateTime(assignment.snoozed_until, timezone)
      }}</time>
      ({{ timezone }})
    </p>
    <div v-if="editable" class="flex flex-wrap gap-2">
      <button type="button" class="button min-h-11" :disabled="saving || disabled" @click="open">
        {{ active ? 'Wiedervorlage ändern' : 'Wiedervorlegen' }}
      </button>
      <button
        v-if="active"
        type="button"
        class="button min-h-11"
        :disabled="saving || disabled"
        @click="save(null)"
      >
        Wiedervorlage aufheben
      </button>
    </div>
    <InlineAlert v-if="error && !opened" tone="warning"
      >{{ error }}
      <button v-if="conflict" class="button" type="button" @click="reload">
        Neu laden
      </button></InlineAlert
    >
    <AppModal ref="modal" title="Wiedervorlegen" :close-blocked="saving" @close="opened = false">
      <div class="mt-4 space-y-4">
        <p class="text-sm text-slate-600">
          Die Aufgabe bleibt unerledigt. Kalender-Presets gelten um 09:00 Uhr in {{ timezone }}.
        </p>
        <div class="grid gap-2 sm:grid-cols-3">
          <button
            type="button"
            class="button min-h-11"
            :disabled="saving || conflict"
            @click="preset(1)"
          >
            Morgen
          </button>
          <button
            type="button"
            class="button min-h-11"
            :disabled="saving || conflict"
            @click="preset(3)"
          >
            In 3 Tagen
          </button>
          <button
            type="button"
            class="button min-h-11"
            :disabled="saving || conflict"
            @click="preset(7)"
          >
            Nächste Woche
          </button>
        </div>
        <form class="space-y-3" @submit.prevent="saveCustom">
          <label class="block min-w-0"
            ><span class="label">Datum wählen ({{ timezone }})</span
            ><input
              v-model="custom"
              class="input w-full min-w-0"
              type="datetime-local"
              required
              :disabled="saving || conflict"
          /></label>
          <p class="text-xs text-slate-500">
            Maximal 365 Tage. Eine doppelte Uhrzeit bei der Herbst-Zeitumstellung bezeichnet das
            erste Vorkommen.
          </p>
          <button class="button-primary min-h-11" :disabled="saving || conflict">
            Wiedervorlage speichern
          </button>
        </form>
        <InlineAlert v-if="error" tone="warning"
          >{{ error }}
          <button v-if="conflict" class="button" type="button" @click="reload">
            Neu laden
          </button></InlineAlert
        >
      </div>
    </AppModal>
  </div>
</template>
