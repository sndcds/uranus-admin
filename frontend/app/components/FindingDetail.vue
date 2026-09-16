<script setup lang="ts">
import AppModal from './AppModal.vue'
import { dateTime } from '~/utils/presentation'
import type { Finding, ReviewUpdate } from '#shared/contracts'
const finding = ref<Finding | null>(null)
const { $adminApi } = useNuxtApp()
const reviewStatus = ref<ReviewUpdate['status']>('in_progress')
const comment = ref('')
const reason = ref('')
const assignee = ref('')
const snooze = ref('')
const saving = ref(false)
const feedback = ref('')
let detailRevision = 0
async function saveReview() {
  if (!finding.value) return
  const revision = detailRevision
  saving.value = true
  feedback.value = ''
  try {
    const result = await $adminApi.review({
      finding_id: finding.value.id,
      status: reviewStatus.value,
      comment: comment.value || null,
      exception_reason: reason.value || null,
      assigned_to: assignee.value || null,
      snoozed_until: snooze.value ? new Date(snooze.value).toISOString() : null,
    })
    if (revision === detailRevision) {
      finding.value = result
      feedback.value = 'Review gespeichert.'
    }
  } catch {
    if (revision === detailRevision)
      feedback.value = 'Review konnte nicht gespeichert werden. Eingaben und Zugang prüfen.'
  } finally {
    if (revision === detailRevision) saving.value = false
  }
}
const dialog = useTemplateRef<InstanceType<typeof AppModal>>('detail')
function open(value: Finding) {
  detailRevision++
  finding.value = value
  reviewStatus.value =
    value.status === 'open' || value.status === 'snoozed' || value.status === 'exception'
      ? value.status
      : 'in_progress'
  comment.value = value.comment ?? ''
  reason.value = value.exception_reason ?? ''
  assignee.value = value.assigned_to ?? ''
  snooze.value = ''
  feedback.value = ''
  saving.value = false
  void dialog.value?.open()
}
function close() {
  dialog.value?.close()
}
watch(
  useState('admin-access-revision', () => 0),
  () => {
    close()
    finding.value = null
  },
)
defineExpose({ open })
</script>

<template>
  <AppModal
    ref="detail"
    :title="finding?.entity_name ?? 'Befund'"
    close-label="Details schließen"
    @close="detailRevision++"
  >
    <template v-if="finding">
      <div class="mt-3"><SeverityBadge :severity="finding.severity" /></div>
      <p class="mt-4 text-sm text-slate-700">{{ finding.message }}</p>
      <dl class="mt-5 grid gap-4 text-sm">
        <div>
          <dt class="font-semibold">Organisation</dt>
          <dd>{{ finding.organization_name }}</dd>
        </div>
        <div>
          <dt class="font-semibold">Adresse</dt>
          <dd>
            {{
              [
                finding.address.street,
                finding.address.house_number,
                finding.address.postal_code,
                finding.address.city,
                finding.address.country,
              ]
                .filter(Boolean)
                .join(' ') || 'Nicht verfügbar'
            }}
          </dd>
        </div>
        <div>
          <dt class="font-semibold">Kommende Termine</dt>
          <dd>
            {{ finding.upcoming_event_date_count }} · davon
            {{ finding.upcoming_published_event_date_count }} veröffentlicht,
            {{ finding.soon_published_event_date_count }} bald
          </dd>
        </div>
        <div>
          <dt class="font-semibold">Priorität</dt>
          <dd>
            {{ finding.priority }} · Score {{ finding.priority_score }} ·
            {{ finding.priority_reasons.join(', ') }}
          </dd>
        </div>
        <div v-if="finding.reviewed_at">
          <dt class="font-semibold">Letztes Review</dt>
          <dd>
            {{ dateTime(finding.reviewed_at) }} ·
            {{ finding.reviewed_subject ?? finding.reviewed_by ?? 'Nicht verfügbar' }}
          </dd>
        </div>
        <div>
          <dt class="font-semibold">Beobachtet</dt>
          <dd>{{ dateTime(finding.last_seen_at) }}</dd>
        </div>
        <div>
          <dt class="font-semibold">Erstmals gefunden</dt>
          <dd>{{ dateTime(finding.first_seen_at) }}</dd>
        </div>
        <div>
          <dt class="font-semibold">Status</dt>
          <dd>
            {{ finding.status === 'open' ? 'Offen' : (finding.status ?? 'Nicht verfügbar') }}
          </dd>
        </div>
        <div>
          <dt class="font-semibold">Regel / Feld</dt>
          <dd class="break-all">{{ finding.rule }} / {{ finding.field }}</dd>
        </div>
        <div>
          <dt class="font-semibold">Objekt-ID</dt>
          <dd class="break-all text-xs">{{ finding.entity_key }}</dd>
        </div>
      </dl>
      <form
        v-if="finding.first_seen_at && finding.status !== 'resolved'"
        class="mt-5 space-y-3 rounded-xl bg-slate-50 p-4"
        @submit.prevent="saveReview"
      >
        <label
          ><span class="label">Reviewstatus</span
          ><select v-model="reviewStatus" class="input">
            <option value="open">Offen</option>
            <option value="in_progress">In Bearbeitung</option>
            <option value="snoozed">Zurückgestellt</option>
            <option value="exception">Begründete Ausnahme</option>
          </select></label
        >
        <label
          ><span class="label">Zuständig (User-UUID)</span><input v-model="assignee" class="input"
        /></label>
        <label
          ><span class="label">Kommentar</span
          ><textarea v-model="comment" class="input" maxlength="4000" />
        </label>
        <label v-if="reviewStatus === 'exception'"
          ><span class="label">Ausnahmegrund</span
          ><textarea v-model="reason" class="input" maxlength="2000" required />
        </label>
        <label v-if="reviewStatus === 'snoozed'"
          ><span class="label">Zurückstellen bis (lokale Zeit)</span
          ><input v-model="snooze" type="datetime-local" class="input" required
        /></label>
        <button class="button-primary" :disabled="saving">Review speichern</button>
        <p role="status">{{ feedback }}</p>
      </form>
      <p v-else-if="!finding.first_seen_at" class="mt-5 text-sm text-slate-500">
        Für Reviews zuerst einen Prüflauf speichern.
      </p>
      <NuxtLink v-if="finding.action" :to="finding.action.href" class="button mt-4" @click="close"
        >Objekt öffnen</NuxtLink
      >
      <GraphLink :entity-type="finding.entity_type" :entity-key="finding.entity_key" @click="close" />
      <RecordMarkLink
        :entity-type="finding.entity_type"
        :entity-key="finding.entity_key"
        @click="close"
      />
      <button class="button mt-4" @click="close">Schließen</button>
    </template>
  </AppModal>
</template>
