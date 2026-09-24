<script setup lang="ts">
import { computed, onBeforeUnmount, ref, useTemplateRef } from 'vue'
import AppModal from './AppModal.vue'
import type { Finding, ReviewUpdate } from '#shared/contracts'
import { asFailure } from '#shared/errors'
import { adminTimeZone, dateTime, findingStatusLabels } from '~/utils/presentation'
import { adminLocalInstant } from '~/utils/admin-time'
import { findingRecordName, findingPriorityReason } from '~/utils/finding-presentation'
import { qualityRuleLabel } from '~/utils/quality'

const emit = defineEmits<{ refresh: []; sql: [finding: Finding, mode: 'persisted' | 'live'] }>()
const { $adminApi } = useNuxtApp()
const dialog = useTemplateRef<InstanceType<typeof AppModal>>('dialog')
const finding = ref<Finding | null>(null)
const mode = ref<'persisted' | 'live'>('persisted')
const reviewStatus = ref<ReviewUpdate['status']>('open')
const comment = ref(''),
  reason = ref(''),
  snooze = ref('')
const saving = ref(false),
  feedback = ref(''),
  error = ref('')
let revision = 0
let changed = false
let active = true
const editable = computed(() => mode.value === 'persisted' && finding.value?.status !== 'resolved')
const address = computed(() =>
  finding.value ? Object.values(finding.value.address).filter(Boolean).join(' ') : '',
)
function open(value: Finding, source: 'persisted' | 'live') {
  revision++
  finding.value = value
  mode.value = source
  reviewStatus.value = ['open', 'in_progress', 'snoozed', 'exception'].includes(value.status ?? '')
    ? (value.status as ReviewUpdate['status'])
    : 'in_progress'
  comment.value = value.comment ?? ''
  reason.value = value.exception_reason ?? ''
  // A persisted instant is kept exactly unless the operator chooses a replacement.
  snooze.value = ''
  saving.value = false
  feedback.value = ''
  error.value = ''
  changed = false
  void dialog.value?.open()
}
function reset() {
  revision++
  finding.value = null
  saving.value = false
  if (changed && active) emit('refresh')
  changed = false
}
onBeforeUnmount(() => {
  active = false
  revision++
})
async function saveReview() {
  if (!finding.value || !editable.value || saving.value) return
  error.value = ''
  feedback.value = ''
  const until =
    reviewStatus.value === 'snoozed'
      ? snooze.value
        ? adminLocalInstant(snooze.value, adminTimeZone)
        : finding.value.snoozed_until
      : null
  if (reviewStatus.value === 'snoozed' && (!until || Date.parse(until) <= Date.now())) {
    error.value = 'Bitte einen gültigen zukünftigen Zeitpunkt in Europe/Berlin wählen.'
    return
  }
  if (reviewStatus.value === 'exception' && !reason.value.trim()) {
    error.value = 'Bitte die Ausnahme begründen.'
    return
  }
  const current = revision
  saving.value = true
  try {
    const result = await $adminApi.review({
      finding_id: finding.value.id,
      status: reviewStatus.value,
      comment: comment.value || null,
      exception_reason: reviewStatus.value === 'exception' ? reason.value.trim() : null,
      snoozed_until: until ?? null,
    })
    if (current !== revision || !finding.value) return
    // Review responses contain workflow state, but not the list's source enrichments.
    finding.value = {
      ...finding.value,
      status: result.status,
      comment: result.comment,
      exception_reason: result.exception_reason,
      snoozed_until: result.snoozed_until,
      reviewed_at: result.reviewed_at,
      reviewed_by: result.reviewed_by,
      reviewed_subject: result.reviewed_subject,
    }
    changed = true
    feedback.value = 'Review gespeichert.'
  } catch (cause) {
    if (current === revision) error.value = asFailure(cause).message
  } finally {
    if (current === revision) saving.value = false
  }
}
function openSql() {
  if (!finding.value) return
  const value = finding.value,
    source = mode.value
  dialog.value?.close()
  emit('sql', value, source)
}
defineExpose({ open })
</script>

<template>
  <AppModal
    ref="dialog"
    wide
    workspace
    :title="finding ? findingRecordName(finding) : 'Befund'"
    close-label="Befund schließen"
    @close="reset"
  >
    <template v-if="finding" #icon><ActivityThumbnail :item="finding" compact /></template>
    <template v-if="finding" #badge>
      <div class="flex flex-wrap items-center gap-2">
        <EntityTypeBadge :type="finding.entity_type" />
        <SeverityBadge :severity="finding.severity" />
        <StatusBadge
          v-if="mode === 'persisted' && finding.status"
          :label="findingStatusLabels[finding.status] ?? finding.status"
        />
        <StatusBadge v-else-if="mode === 'live'" label="Live-Diagnose" />
        <span
          class="rounded bg-slate-900 px-2 py-1 text-xs font-semibold text-white"
          :aria-label="`Priorität ${finding.priority}`"
          >P{{ finding.priority }}</span
        >
      </div>
    </template>
    <div v-if="finding" class="min-w-0 space-y-4 p-4 sm:p-5 [overflow-wrap:anywhere]">
      <div class="grid min-w-0 gap-4 md:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        <RecordSection title="Evidenz" surface="panel">
          <p class="font-semibold">{{ qualityRuleLabel(finding.rule) }}</p>
          <p class="text-sm leading-6 text-slate-700">{{ finding.message }}</p>
          <CompactFacts
            :items="[
              { label: 'Feld', value: finding.field },
              { label: 'Organisation', value: finding.organization_name },
              { label: 'Adresse', value: address || null },
              {
                label: 'Kommende Termine',
                value: finding.upcoming_event_date_count,
                description: `${finding.upcoming_published_event_date_count} veröffentlicht · ${finding.soon_published_event_date_count} bald`,
              },
            ]"
          />
          <dl class="grid gap-3 text-xs sm:grid-cols-2">
            <div v-if="mode === 'persisted'">
              <dt class="operations-meta">Erstmals gefunden</dt>
              <dd>
                <time v-if="finding.first_seen_at" :datetime="finding.first_seen_at">{{
                  dateTime(finding.first_seen_at)
                }}</time
                ><span v-else>Nicht verfügbar</span>
              </dd>
            </div>
            <div>
              <dt class="operations-meta">Zuletzt beobachtet · Europe/Berlin</dt>
              <dd>
                <time :datetime="finding.last_seen_at">{{ dateTime(finding.last_seen_at) }}</time>
              </dd>
            </div>
          </dl>
        </RecordSection>
        <RecordSection title="Priorisierung" surface="subtle">
          <div class="flex items-center gap-3">
            <span class="rounded bg-slate-900 px-2 py-1 font-semibold text-white"
              >P{{ finding.priority }}</span
            ><span class="operations-meta">Score {{ finding.priority_score }}</span>
          </div>
          <ul v-if="finding.priority_reasons.length" class="space-y-2 text-sm text-slate-700">
            <li v-for="item in finding.priority_reasons" :key="item">
              {{ findingPriorityReason(item) }}
            </li>
          </ul>
        </RecordSection>
      </div>
      <RecordSection
        title="Fachliche Bewertung"
        description="Bewertung des Datenqualitätsbefunds."
        surface="panel"
      >
        <p v-if="mode === 'live'" class="text-sm text-slate-600">
          Live-Diagnose ohne gespeicherten Review. Für die fachliche Bewertung und Zuständigkeit
          einen gespeicherten Befund öffnen.
        </p>
        <template v-else>
          <form v-if="editable" class="grid gap-3 sm:grid-cols-2" @submit.prevent="saveReview">
            <label
              ><span class="label">Reviewstatus</span
              ><select v-model="reviewStatus" class="input">
                <option value="open">Offen</option>
                <option value="in_progress">In Bearbeitung</option>
                <option value="snoozed">Zurückgestellt</option>
                <option value="exception">Begründete Ausnahme</option>
              </select></label
            >
            <label class="sm:row-span-2"
              ><span class="label">Kommentar</span
              ><textarea v-model="comment" class="input" rows="3" maxlength="4000" />
            </label>
            <label v-if="reviewStatus === 'exception'"
              ><span class="label">Ausnahmegrund</span
              ><textarea v-model="reason" class="input" rows="2" maxlength="2000" required />
            </label>
            <label v-if="reviewStatus === 'snoozed'"
              ><span class="label">Zurückstellen bis (Europe/Berlin)</span
              ><input
                v-model="snooze"
                class="input"
                type="datetime-local"
                :required="!finding.snoozed_until"
              /><span v-if="finding.snoozed_until" class="operations-meta"
                >Aktuell:
                <time :datetime="finding.snoozed_until">{{ dateTime(finding.snoozed_until) }}</time
                >. Leer lassen zum Beibehalten.</span
              ></label
            >
            <div class="flex flex-wrap items-center gap-3 sm:col-span-2">
              <button class="button-primary min-h-11" :disabled="saving">
                {{ saving ? 'Wird gespeichert…' : 'Review speichern' }}
              </button>
              <p role="status" class="text-sm text-emerald-800">{{ feedback }}</p>
            </div>
            <p v-if="error" role="alert" class="text-sm text-rose-700 sm:col-span-2">{{ error }}</p>
          </form>
          <template v-else
            ><p class="text-sm">
              Dieser Befund ist behoben. Nur ein erneuter Prüflauf kann ihn wieder öffnen.
            </p>
            <p v-if="finding.comment" class="text-sm">{{ finding.comment }}</p>
            <p v-if="finding.exception_reason" class="text-sm">
              {{ finding.exception_reason }}
            </p></template
          >
        </template>
      </RecordSection>
      <RecordSection
        v-if="editable"
        title="Zuständigkeit"
        description="Operative Bearbeitung, Zuständigkeit und Fälligkeit."
        surface="panel"
      >
        <p class="operations-meta">
          Eine operative Wiedervorlage ändert die fachliche Bewertung nicht.
        </p>
        <AssignmentEditor :key="finding.id" :finding-id="finding.id" embedded />
      </RecordSection>
      <RecordSection title="Werkzeuge" surface="panel">
        <div class="flex flex-wrap items-center gap-x-4 gap-y-1 [&_a]:min-h-11">
          <button v-if="finding.sql_diagnostic_available" class="button min-h-11" @click="openSql">
            SQL Editor
          </button>
          <NuxtLink
            v-if="finding.action"
            :to="finding.action.href"
            class="action-link"
            @click="dialog?.close()"
            >Im Admin ansehen</NuxtLink
          >
          <NuxtLink
            v-if="finding.location_suggestion_request_id"
            :to="`/geocoding/${finding.location_suggestion_request_id}`"
            class="action-link"
            @click="dialog?.close()"
            >Standortvorschlag prüfen</NuxtLink
          >
          <GraphLink
            :entity-type="finding.entity_type"
            :entity-key="finding.entity_key"
            @click="dialog?.close()"
          />
          <RecordMarkLink
            :entity-type="finding.entity_type"
            :entity-key="finding.entity_key"
            variant="action"
            @click="dialog?.close()"
          />
        </div>
      </RecordSection>
      <TechnicalInfoBar
        :items="[
          { label: 'Finding ID', value: finding.id, mono: true, copyable: true },
          { label: 'Entity Key', value: finding.entity_key, mono: true, copyable: true },
          { label: 'Regelcode', value: finding.rule, mono: true },
          {
            label: 'first_seen_at',
            value: mode === 'persisted' ? finding.first_seen_at : null,
            datetime: finding.first_seen_at ?? undefined,
          },
          { label: 'last_seen_at', value: finding.last_seen_at, datetime: finding.last_seen_at },
          {
            label: 'reviewed_at',
            value: mode === 'persisted' ? finding.reviewed_at : null,
            datetime: finding.reviewed_at ?? undefined,
          },
          { label: 'Modus', value: mode },
        ]"
      />
    </div>
  </AppModal>
</template>
