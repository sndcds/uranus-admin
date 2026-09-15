<script setup lang="ts">
import { markUpdateSchema } from '#shared/contracts'
import type { MarkDetail, MarkUpdate } from '#shared/contracts'
import { asFailure } from '#shared/errors'
import type { ApiFailure } from '#shared/errors'
import { dateTime } from '~/utils/presentation'
import { markReasons, markStatuses, markUrgencies, markEventLabels } from '~/utils/marks'
const route = useRoute()
const { $adminApi } = useNuxtApp()
const data = ref<MarkDetail | null>(null)
const error = ref<ApiFailure | null>(null)
const loading = ref(false)
const saving = ref(false)
const feedback = ref('')
const saveError = ref<ApiFailure | null>(null)
const reasons = ref<MarkUpdate['reasons']>([])
const reasonDetail = ref('')
const urgency = ref<MarkUpdate['urgency']>('normal')
const status = ref<MarkUpdate['status']>('open')
const note = ref('')
let requestId = 0
function setData(result: MarkDetail) {
  data.value = result
  reasons.value = [...result.reasons]
  reasonDetail.value = result.reason_detail ?? ''
  urgency.value = result.urgency
  status.value = result.status
  note.value = ''
}
async function load() {
  const id = ++requestId
  loading.value = true
  error.value = null
  data.value = null
  feedback.value = ''
  saveError.value = null
  try {
    const result = await $adminApi.mark(String(route.params.id))
    if (id === requestId) setData(result)
  } catch (cause) {
    if (id === requestId) error.value = asFailure(cause)
  } finally {
    if (id === requestId) loading.value = false
  }
}
async function save(event: SubmitEvent) {
  if (!data.value || saving.value) return
  const targetStatus = (event.submitter as HTMLButtonElement | null)?.value || status.value
  const parsed = markUpdateSchema.safeParse({
    version: data.value.version,
    reasons: reasons.value,
    reason_detail: reasonDetail.value.trim() || null,
    urgency: urgency.value,
    status: targetStatus,
    note: note.value.trim() || null,
  })
  feedback.value = ''
  saveError.value = null
  if (!parsed.success) {
    feedback.value = 'Bitte wähle mindestens einen Grund und erläutere „Sonstiges“.'
    return
  }
  saving.value = true
  const id = requestId
  try {
    const result = await $adminApi.updateMark(data.value.id, parsed.data)
    if (id === requestId) {
      setData(result)
      feedback.value = 'Markierung gespeichert.'
    }
  } catch (cause) {
    if (id === requestId) saveError.value = asFailure(cause)
  } finally {
    saving.value = false
  }
}
onMounted(load)
watch(() => route.params.id, load)
watch(
  useState('admin-access-revision', () => 0),
  load,
)
onBeforeUnmount(() => {
  requestId++
})
</script>

<template>
  <section class="space-y-5">
    <h2 class="text-2xl font-bold">Markierung &amp; Notizen</h2>
    <RequestState :loading="loading" :error="error" @retry="load" />
    <template v-if="data">
      <div class="card space-y-3 break-words p-5">
        <h3 class="text-xl font-bold">{{ data.entity_name }}</h3>
        <p>{{ markStatuses[data.status] }} · {{ markUrgencies[data.urgency] }}</p>
        <p class="muted">{{ data.entity_type }} · {{ data.entity_key }}</p>
        <p>Angelegt am {{ dateTime(data.created_at) }} · von {{ data.created_by }}</p>
        <p v-if="data.completed_at" class="rounded-lg bg-emerald-50 p-3 text-emerald-900">
          Erledigt am {{ dateTime(data.completed_at) }} · von {{ data.completed_by }}
        </p>
        <RecordMarkLink :entity-type="data.entity_type" :entity-key="data.entity_key" />
      </div>
      <form class="card p-5" @submit.prevent="save">
        <fieldset :disabled="saving" class="space-y-4">
          <legend class="mb-3 font-bold">Markierung bearbeiten</legend>
          <MarkFields
            v-model:reasons="reasons"
            v-model:reason-detail="reasonDetail"
            v-model:urgency="urgency"
          />
          <label class="block"
            ><span class="label">Bearbeitungsstatus</span
            ><select v-model="status" class="input">
              <option v-for="(label, value) in markStatuses" :key="value" :value="value">
                {{ label }}
              </option>
            </select></label
          >
          <label class="block"
            ><span class="label">Neue Notiz / Abschlussnotiz (optional)</span
            ><textarea v-model="note" class="input w-full" maxlength="4000" />
          </label>
          <p class="muted">
            Notizen bleiben mit Autor und Zeitpunkt im Verlauf erhalten. Beim Erledigen werden Datum
            und Benutzer automatisch erfasst.
          </p>
          <div class="flex flex-wrap gap-3">
            <button class="button-primary">
              {{ saving ? 'Speichert …' : 'Änderungen speichern' }}
            </button>
            <button v-if="data.status !== 'done'" class="button" value="done">
              Als erledigt markieren
            </button>
            <button v-else class="button" value="open">Wieder öffnen</button>
          </div>
        </fieldset>
        <p v-if="feedback" role="status" class="mt-3">{{ feedback }}</p>
        <div v-if="saveError" role="alert" class="mt-3 space-y-2 text-red-700">
          <p>{{ saveError.message }}</p>
          <template v-if="saveError.status === 409"
            ><p>Beim Neuladen werden ungespeicherte Eingaben verworfen.</p>
            <button type="button" class="button" @click="load">
              Aktuellen Stand laden
            </button></template
          >
        </div>
      </form>
      <section class="card p-5" aria-label="Notizen und Verlauf">
        <h3 class="mb-4 text-lg font-bold">Notizen und Verlauf</h3>
        <ol class="space-y-5">
          <li
            v-for="entry in data.events"
            :key="entry.id"
            class="break-words border-l-2 border-fuchsia-200 pl-4"
          >
            <p class="font-semibold">{{ markEventLabels[entry.kind] }}</p>
            <p class="muted">{{ dateTime(entry.created_at) }} · {{ entry.author }}</p>
            <p>
              {{ markStatuses[entry.status] }} · {{ markUrgencies[entry.urgency] }} ·
              {{ entry.reasons.map((reason) => markReasons[reason]).join(' · ') }}
            </p>
            <p v-if="entry.reason_detail" class="whitespace-pre-wrap">{{ entry.reason_detail }}</p>
            <p v-if="entry.note" class="mt-2 whitespace-pre-wrap">{{ entry.note }}</p>
          </li>
        </ol>
      </section>
    </template>
  </section>
</template>
