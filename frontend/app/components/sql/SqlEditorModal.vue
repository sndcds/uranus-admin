<script setup lang="ts">
import { onBeforeUnmount, ref, useTemplateRef } from 'vue'
import AppModal from '../AppModal.vue'
import StatusBadge from '../StatusBadge.vue'
import SeverityBadge from '../SeverityBadge.vue'
import EntityTypeBadge from '../EntityTypeBadge.vue'
import SqlCodeEditor from './SqlCodeEditor.vue'
import SqlParameterTable from './SqlParameterTable.vue'
import SqlResultTable from './SqlResultTable.vue'
import SqlRuleEvaluation from './SqlRuleEvaluation.vue'
import type { Finding, SqlDiagnosticDefinition, SqlDiagnosticResult } from '#shared/contracts'
import { asFailure } from '#shared/errors'
import { dateTime, findingStatusLabels } from '~/utils/presentation'

const { $adminApi } = useNuxtApp()
const dialog = useTemplateRef<InstanceType<typeof AppModal>>('dialog')
const finding = ref<Finding | null>(null)
const definition = ref<SqlDiagnosticDefinition | null>(null)
const result = ref<SqlDiagnosticResult | null>(null)
const loading = ref(false)
const running = ref(false)
const error = ref('')
const copyFeedback = ref('')
let revision = 0
let copyTimer: ReturnType<typeof setTimeout> | undefined
function reset() {
  revision++
  clearTimeout(copyTimer)
  finding.value = null
  definition.value = null
  result.value = null
  error.value = ''
  copyFeedback.value = ''
  loading.value = false
  running.value = false
}
onBeforeUnmount(reset)
function open(value: Finding) {
  reset()
  finding.value = value
  void dialog.value?.open()
  void load()
}
async function load() {
  if (!finding.value || loading.value) return
  const current = ++revision
  const id = finding.value.id
  loading.value = true
  error.value = ''
  try {
    const value = await $adminApi.sqlDiagnostic(id)
    if (current === revision) definition.value = value
  } catch (cause) {
    if (current === revision) error.value = asFailure(cause).message
  } finally {
    if (current === revision) loading.value = false
  }
}
async function execute() {
  if (!finding.value || running.value || !definition.value) return
  const current = revision
  running.value = true
  error.value = ''
  result.value = null
  try {
    const value = await $adminApi.executeSqlDiagnostic(finding.value.id)
    if (current === revision) result.value = value
  } catch (cause) {
    if (current === revision) error.value = asFailure(cause).message
  } finally {
    if (current === revision) running.value = false
  }
}
async function copy() {
  if (!definition.value) return
  const current = revision
  clearTimeout(copyTimer)
  try {
    await navigator.clipboard.writeText(definition.value.copy_sql)
    if (current === revision) copyFeedback.value = 'SQL kopiert'
  } catch {
    if (current === revision) copyFeedback.value = 'SQL konnte nicht kopiert werden.'
  }
  if (current === revision)
    copyTimer = setTimeout(() => {
      copyFeedback.value = ''
    }, 2500)
}
defineExpose({ open })
</script>

<template>
  <AppModal ref="dialog" title="SQL Editor" wide close-label="SQL Editor schließen" @close="reset">
    <template #badge><StatusBadge label="READ ONLY" /></template>
    <p class="mt-1 text-sm text-slate-600">
      Analyse und Überprüfung der Datenquelle zu diesem Befund.
    </p>
    <p class="mt-1 text-xs text-slate-500">Die Abfrage wird ausschließlich lesend ausgeführt.</p>
    <div v-if="finding" class="mt-6 min-w-0 space-y-6 text-sm">
      <section aria-label="Finding" class="rounded-xl border border-slate-200 bg-slate-50 p-4">
        <p class="text-xs font-semibold text-slate-500">Finding</p>
        <div class="mt-2 flex flex-wrap items-center gap-2">
          <h3 class="min-w-0 break-words text-base font-semibold">{{ finding.entity_name }}</h3>
          <SeverityBadge :severity="finding.severity" />
          <EntityTypeBadge :type="finding.entity_type" />
          <StatusBadge
            v-if="finding.status"
            :label="findingStatusLabels[finding.status] ?? finding.status"
          />
        </div>
        <p class="mt-2 break-words text-slate-700">{{ finding.message }}</p>
        <dl class="mt-4 grid gap-x-6 gap-y-3 sm:grid-cols-2">
          <div>
            <dt class="text-xs text-slate-500">Feld</dt>
            <dd class="mt-1 break-all font-mono text-xs">{{ finding.field }}</dd>
          </div>
          <div>
            <dt class="text-xs text-slate-500">Organisation</dt>
            <dd class="mt-1 break-words">
              {{ finding.organization_name || 'Keine eindeutige Organisation' }}
            </dd>
          </div>
          <div>
            <dt class="text-xs text-slate-500">Objekt-ID</dt>
            <dd class="mt-1 break-all font-mono text-xs">{{ finding.entity_key }}</dd>
          </div>
          <div>
            <dt class="text-xs text-slate-500">Finding zuletzt beobachtet</dt>
            <dd class="mt-1">{{ dateTime(finding.last_seen_at) }}</dd>
          </div>
        </dl>
      </section>
      <p v-if="loading" role="status" class="text-slate-600">SQL-Diagnose wird geladen…</p>
      <div v-if="error && !definition" role="alert" class="space-y-2">
        <p class="font-semibold">SQL-Diagnose konnte nicht geladen werden.</p>
        <p>{{ error }}</p>
        <button class="button" :disabled="loading" @click="load">Erneut versuchen</button>
      </div>
      <template v-if="definition">
        <section aria-label="SQL-Abfrage" class="space-y-3">
          <div class="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h3 class="font-semibold">SQL-Abfrage</h3>
              <p class="mt-1 text-xs text-slate-500">
                {{ definition.title }} · {{ definition.datasource }}
              </p>
            </div>
            <div class="flex flex-wrap gap-2">
              <button class="button" @click="copy">SQL kopieren</button>
              <button class="button-primary" :disabled="running" @click="execute">
                Abfrage ausführen
              </button>
            </div>
          </div>
          <p v-if="copyFeedback" role="status" class="text-xs text-slate-600">{{ copyFeedback }}</p>
          <SqlCodeEditor :sql="definition.sql" readonly />
          <p class="text-xs text-slate-500">{{ definition.explanation }}</p>
        </section>
        <SqlParameterTable :parameters="definition.parameters" />
        <section aria-label="Ergebnis" class="space-y-3">
          <div class="flex flex-wrap items-center justify-between gap-2">
            <h3 class="font-semibold">Ergebnis</h3>
            <p v-if="result" class="text-xs tabular-nums text-slate-500">
              {{ result.row_count }} {{ result.row_count === 1 ? 'Zeile' : 'Zeilen' }} ·
              {{ result.duration_ms }} ms
            </p>
          </div>
          <p v-if="running" role="status" class="text-slate-600">Abfrage wird ausgeführt…</p>
          <div v-else-if="error" role="alert">
            <p class="font-semibold">Abfrage konnte nicht ausgeführt werden.</p>
            <p class="mt-1">{{ error }}</p>
          </div>
          <p
            v-else-if="!result"
            class="rounded-xl border border-dashed border-slate-200 p-4 text-slate-500"
          >
            Noch keine Abfrage ausgeführt.
          </p>
          <template v-if="result">
            <p class="text-xs text-slate-500">
              Aktuelle Diagnose: {{ dateTime(result.observed_at) }}
            </p>
            <SqlResultTable :columns="result.columns" :rows="result.rows" />
          </template>
          <p
            v-if="typeof definition.parameters.diagnostic_limit === 'number'"
            class="text-xs text-slate-500"
          >
            Maximal {{ definition.parameters.diagnostic_limit }} Zeilen werden angezeigt.
          </p>
        </section>
        <SqlRuleEvaluation v-if="result" :evaluation="result.evaluation" />
      </template>
    </div>
  </AppModal>
</template>
