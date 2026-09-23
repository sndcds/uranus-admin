<script setup lang="ts">
import { qualityRuleLabel } from '~/utils/quality'
import { defineAsyncComponent, onBeforeUnmount, ref, useTemplateRef } from 'vue'
import SqlWorkspaceModal from './SqlWorkspaceModal.vue'
import SqlQueryPanel from './SqlQueryPanel.vue'
import RecordMarkLink from '../RecordMarkLink.vue'
import StatusBadge from '../StatusBadge.vue'
import SeverityBadge from '../SeverityBadge.vue'
import EntityTypeBadge from '../EntityTypeBadge.vue'
import SqlRuleEvaluation from './SqlRuleEvaluation.vue'
import type { Finding, SqlDiagnosticDefinition, SqlDiagnosticResult } from '#shared/contracts'
import { sqlFindingLink } from '~/utils/sql-finding-link'
import { asFailure } from '#shared/errors'
import { dateTime, findingStatusLabels } from '~/utils/presentation'

const SqlConsolePanel = defineAsyncComponent(() => import('./SqlConsolePanel.vue'))
const mode = ref<'persisted' | 'live'>('persisted')
const editing = ref(false),
  consoleBusy = ref(false)
const consolePanel = ref<{ cancel: () => void } | null>(null)
const { $adminApi } = useNuxtApp()
const dialog = useTemplateRef<InstanceType<typeof SqlWorkspaceModal>>('dialog')
const finding = ref<Finding | null>(null)
const definition = ref<SqlDiagnosticDefinition | null>(null)
const result = ref<SqlDiagnosticResult | null>(null)
const loading = ref(false)
const running = ref(false)
const error = ref('')
const tab = ref('SQL Editor')
const navigation = [
  { label: 'SQL Editor', icon: 'code' },
  { label: 'Befund-Details', icon: 'list' },
  { label: 'Regel-Informationen', icon: 'quality' },
  { label: 'Markierungen & Notizen', icon: 'mail' },
  { label: 'Historie', icon: 'history' },
] as const
let revision = 0
function reset() {
  revision++
  editing.value = false
  consoleBusy.value = false
  finding.value = null
  definition.value = null
  result.value = null
  error.value = ''
  tab.value = 'SQL Editor'
  loading.value = false
  running.value = false
}
onBeforeUnmount(reset)
function open(value: Finding, source: 'persisted' | 'live' = 'persisted') {
  reset()
  finding.value = value
  mode.value = source
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
    const value = await (mode.value === 'live'
      ? $adminApi.sqlDiagnostic(id, 'live')
      : $adminApi.sqlDiagnostic(id))
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
    const value = await (mode.value === 'live'
      ? $adminApi.executeSqlDiagnostic(finding.value.id, 'live')
      : $adminApi.executeSqlDiagnostic(finding.value.id))
    if (current === revision) result.value = value
  } catch (cause) {
    if (current === revision) error.value = asFailure(cause).message
  } finally {
    if (current === revision) running.value = false
  }
}
defineExpose({ open })
</script>

<template>
  <SqlWorkspaceModal
    ref="dialog"
    title="SQL Editor"
    subtitle="Analyse und Überprüfung der Datenquelle zu diesem Befund."
    close-label="SQL Editor schließen"
    :busy="consoleBusy"
    @cancel="consolePanel?.cancel()"
    @close="reset"
  >
    <template #actions
      ><a
        v-if="finding"
        :href="sqlFindingLink(finding, mode)"
        target="_blank"
        rel="noopener noreferrer"
        class="button text-xs"
        aria-label="SQL Editor in neuem Tab öffnen"
        ><AppIcon name="external" :size="14" /><span class="hidden sm:inline"
          >In neuem Tab öffnen</span
        ></a
      ></template
    >
    <template #context>
      <section v-if="finding" aria-label="Finding" class="space-y-3">
        <div class="flex flex-wrap items-center gap-2">
          <span
            aria-hidden="true"
            class="size-2.5 rounded-full"
            :class="
              finding.severity === 'error'
                ? 'bg-rose-500'
                : finding.severity === 'warning'
                  ? 'bg-amber-500'
                  : 'bg-sky-500'
            "
          />
          <h3 class="min-w-0 break-words font-semibold text-slate-950">
            {{ finding.entity_name }}
          </h3>
          <SeverityBadge :severity="finding.severity" />
        </div>
        <p class="break-words text-slate-600">{{ finding.message }}</p>
        <dl class="space-y-1 text-xs text-slate-500">
          <div>
            <dt class="inline">Feld:</dt>
            <dd class="ml-1 inline break-all">{{ finding.field }}</dd>
          </div>
          <div>
            <dt class="inline">Quelle:</dt>
            <dd class="ml-1 inline break-words">
              {{ finding.organization_name || 'Keine eindeutige Organisation' }}
            </dd>
          </div>
          <div>
            <dt class="inline">Beobachtet:</dt>
            <dd class="ml-1 inline">{{ dateTime(finding.last_seen_at) }}</dd>
          </div>
          <div>
            <dt class="inline">ID:</dt>
            <dd class="ml-1 inline break-all">{{ finding.entity_key }}</dd>
          </div>
        </dl>
      </section>
    </template>
    <template #navigation>
      <button
        v-for="item in navigation"
        :key="item.label"
        class="sql-nav"
        :aria-current="tab === item.label ? 'page' : undefined"
        @click="tab = item.label"
      >
        <AppIcon :name="item.icon" :size="16" />{{ item.label }}
      </button>
    </template>
    <template v-if="finding">
      <div v-show="tab === 'SQL Editor'">
        <p v-if="loading" role="status">SQL-Diagnose wird geladen…</p>
        <div v-if="error && !definition" role="alert" class="space-y-2">
          <p class="font-semibold">SQL-Diagnose konnte nicht geladen werden.</p>
          <p>{{ error }}</p>
          <button class="button" :disabled="loading" @click="load">Erneut versuchen</button>
        </div>
        <div v-if="definition" class="mb-3 flex flex-wrap gap-2">
          <button
            class="button"
            :disabled="consoleBusy || running"
            :aria-pressed="!editing"
            @click="editing = false"
          >
            Registrierte Diagnose
          </button>
          <button
            class="button"
            :disabled="consoleBusy || running"
            :aria-pressed="editing"
            @click="editing = true"
          >
            SQL bearbeiten
          </button>
        </div>
        <SqlConsolePanel
          v-if="editing && definition"
          ref="consolePanel"
          :sql="definition.console_sql ?? definition.copy_sql"
          :parameters="definition.parameters"
          finding
          @busy="consoleBusy = $event"
        />
        <SqlQueryPanel
          v-if="definition && !editing"
          :key="finding.id"
          :sql="definition.sql"
          :copy-sql="definition.copy_sql"
          description="Die zugrunde liegende SQL-Abfrage für diesen Befund."
          :parameters="definition.parameters"
          executable
          :running="running"
          :error="error"
          :result="result"
          @execute="execute"
        >
          <SqlRuleEvaluation v-if="result" :evaluation="result.evaluation" />
        </SqlQueryPanel>
      </div>
      <section v-if="tab === 'Befund-Details'" class="space-y-4" aria-label="Befund-Details">
        <h3 class="font-semibold">Befund-Details</h3>
        <div class="flex flex-wrap gap-2">
          <EntityTypeBadge :type="finding.entity_type" /><StatusBadge
            v-if="finding.status"
            :label="findingStatusLabels[finding.status] ?? finding.status"
          />
        </div>
        <p>{{ finding.message }}</p>
        <p class="break-all text-xs text-slate-500">Befund-ID: {{ finding.id }}</p>
        <NuxtLink v-if="finding.action" :to="finding.action.href" class="button"
          >Im Admin ansehen</NuxtLink
        >
      </section>
      <section
        v-if="tab === 'Regel-Informationen'"
        class="space-y-4"
        aria-label="Regel-Informationen"
      >
        <h3 class="font-semibold">Regel-Informationen</h3>
        <p class="break-words text-sm">{{ qualityRuleLabel(finding.rule) }}</p>
        <p v-if="definition">{{ definition.explanation }}</p>
        <p v-if="definition" class="text-xs text-slate-500">
          {{ definition.title }} · {{ definition.datasource }}
        </p>
        <SqlRuleEvaluation v-if="result" :evaluation="result.evaluation" />
      </section>
      <section
        v-if="tab === 'Markierungen & Notizen'"
        class="space-y-4"
        aria-label="Markierungen & Notizen"
      >
        <h3 class="font-semibold">Markierungen & Notizen</h3>
        <p>{{ finding.comment || 'Keine Review-Notiz zu diesem Befund.' }}</p>
        <p v-if="finding.exception_reason">{{ finding.exception_reason }}</p>
        <RecordMarkLink :entity-type="finding.entity_type" :entity-key="finding.entity_key" />
      </section>
      <section v-if="tab === 'Historie'" class="space-y-4" aria-label="Historie">
        <h3 class="font-semibold">Historie</h3>
        <dl class="space-y-3">
          <div>
            <dt class="text-xs text-slate-500">Erstmals beobachtet</dt>
            <dd>{{ dateTime(finding.first_seen_at) }}</dd>
          </div>
          <div>
            <dt class="text-xs text-slate-500">Zuletzt beobachtet</dt>
            <dd>{{ dateTime(finding.last_seen_at) }}</dd>
          </div>
          <div>
            <dt class="text-xs text-slate-500">Zuletzt geprüft</dt>
            <dd>{{ dateTime(finding.reviewed_at) }}</dd>
          </div>
          <div>
            <dt class="text-xs text-slate-500">Aufgelöst</dt>
            <dd>{{ dateTime(finding.resolved_at) }}</dd>
          </div>
        </dl>
      </section>
    </template>
  </SqlWorkspaceModal>
</template>
