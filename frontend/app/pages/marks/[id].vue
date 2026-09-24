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
onBeforeUnmount(() => {
  requestId++
})
</script>

<template>
  <section class="space-y-5">
    <PageHeader
      :title="data?.entity_name ?? 'Markierung & Notizen'"
      record
      description="Manuelle Markierung · Status, Notizen und unveränderlicher Verlauf."
    >
      <template v-if="data" #badge
        ><EntityTypeBadge :type="data.entity_type" /><StatusBadge
          :label="markStatuses[data.status]" /><StatusBadge
          :label="markUrgencies[data.urgency]"
          :tone="
            data.urgency === 'urgent' ? 'error' : data.urgency === 'high' ? 'warning' : 'neutral'
          "
      /></template>
      <NuxtLink v-if="data?.action" :to="data.action.href" class="button">Öffnen</NuxtLink>
      <GraphLink
        v-if="data"
        class="min-h-11"
        :entity-type="data.entity_type"
        :entity-key="data.entity_key"
      />
      <NuxtLink to="/marks" class="action-link">Zurück zu Markierungen</NuxtLink>
    </PageHeader>
    <RequestState :loading="loading" :error="error" @retry="load" />
    <template v-if="data">
      <RecordSection title="Markierungsstatus" surface="panel">
        <CompactFacts
          :columns="3"
          missing="omit"
          :items="[
            { label: 'Angelegt', value: dateTime(data.created_at) },
            { label: 'Angelegt von', value: data.created_by },
            { label: 'Status', value: markStatuses[data.status] },
            { label: 'Dringlichkeit', value: markUrgencies[data.urgency] },
            { label: 'Erledigt', value: data.completed_at ? dateTime(data.completed_at) : null },
            { label: 'Erledigt von', value: data.completed_by },
          ]"
        />
        <p v-if="data.completed_at" class="operations-meta">
          Erledigt am
          <time :datetime="data.completed_at" title="Europe/Berlin">{{
            dateTime(data.completed_at)
          }}</time>
          · von {{ data.completed_by }}
        </p>
        <div class="border-t border-slate-200 pt-2 text-sm [overflow-wrap:anywhere]">
          <h4 class="label">Gründe der Markierung</h4>
          <p>{{ data.reasons.map((reason) => markReasons[reason]).join(' · ') }}</p>
          <p v-if="data.reason_detail" class="mt-1 whitespace-pre-wrap text-slate-600">
            {{ data.reason_detail }}
          </p>
        </div>
        <RecordMarkLink
          variant="action"
          :entity-type="data.entity_type"
          :entity-key="data.entity_key"
        />
      </RecordSection>
      <RecordSection title="Markierung bearbeiten" surface="panel">
        <form @submit.prevent="save">
          <fieldset :disabled="saving" class="space-y-4">
            <legend class="sr-only">Markierung bearbeiten</legend>
            <MarkFields
              v-model:reasons="reasons"
              v-model:reason-detail="reasonDetail"
              v-model:urgency="urgency"
            >
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
            </MarkFields>
            <p class="operations-meta">
              Notizen bleiben mit Autor und Zeitpunkt im Verlauf erhalten. Beim Erledigen werden
              Datum und Benutzer automatisch erfasst.
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
      </RecordSection>
      <DataListShell as="section" aria-label="Notizen und Verlauf">
        <div class="list-group-header">
          <h3 class="text-xs font-semibold">Notizen und Verlauf</h3>
        </div>
        <ol class="divide-y divide-slate-100">
          <li
            v-for="entry in data.events"
            :key="entry.id"
            class="operations-row grid gap-x-4 gap-y-1 py-2 text-sm sm:grid-cols-[minmax(0,1fr)_minmax(0,2fr)]"
          >
            <div class="min-w-0">
              <h4 class="type-row-title">{{ markEventLabels[entry.kind] }}</h4>
              <p class="operations-meta">
                <time :datetime="entry.created_at" title="Europe/Berlin">{{
                  dateTime(entry.created_at)
                }}</time>
                · {{ entry.author }}
              </p>
            </div>
            <div class="min-w-0">
              <p>
                {{ markStatuses[entry.status] }} · {{ markUrgencies[entry.urgency] }} ·
                {{ entry.reasons.map((reason) => markReasons[reason]).join(' · ') }}
              </p>
              <p v-if="entry.reason_detail" class="whitespace-pre-wrap">
                {{ entry.reason_detail }}
              </p>
              <p v-if="entry.note" class="mt-2 whitespace-pre-wrap">{{ entry.note }}</p>
            </div>
          </li>
        </ol>
      </DataListShell>
      <TechnicalInfoBar
        :items="[
          { label: 'Mark ID', value: data.id, mono: true, copyable: true },
          { label: 'Entity Key', value: data.entity_key, mono: true, copyable: true },
          {
            label: 'Erstellt am',
            value: dateTime(data.created_at),
            datetime: data.created_at,
            timezone: 'Europe/Berlin',
          },
          { label: 'Version', value: data.version },
          {
            label: 'Erledigt am',
            value: data.completed_at ? dateTime(data.completed_at) : null,
            datetime: data.completed_at ?? undefined,
            timezone: 'Europe/Berlin',
          },
        ]"
      />
    </template>
  </section>
</template>
