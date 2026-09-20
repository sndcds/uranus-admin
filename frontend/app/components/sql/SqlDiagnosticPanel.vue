<script setup lang="ts">
import SqlCodeBlock from './SqlCodeBlock.vue'
import SqlResultTable from './SqlResultTable.vue'
import SqlRuleEvaluation from './SqlRuleEvaluation.vue'
import type { SqlDiagnosticDefinition, SqlDiagnosticResult } from '#shared/contracts'
import { asFailure } from '#shared/errors'
import { dateTime } from '~/utils/presentation'
const props = defineProps<{ findingId: string }>()
const { $adminApi } = useNuxtApp()
const definition = ref<SqlDiagnosticDefinition | null>(null)
const result = ref<SqlDiagnosticResult | null>(null)
const loading = ref(false)
const running = ref(false)
const error = ref('')
const copyFeedback = ref('')
let revision = 0
onBeforeUnmount(() => {
  revision++
})
async function load() {
  if (loading.value || definition.value) return
  const current = ++revision
  loading.value = true
  error.value = ''
  try {
    const value = await $adminApi.sqlDiagnostic(props.findingId)
    if (current === revision) definition.value = value
  } catch (cause) {
    if (current === revision) error.value = asFailure(cause).message
  } finally {
    if (current === revision) loading.value = false
  }
}
function toggle(event: Event) {
  if ((event.target as HTMLDetailsElement).open) void load()
}
async function execute() {
  if (running.value || !definition.value) return
  const current = revision
  running.value = true
  error.value = ''
  result.value = null
  try {
    const value = await $adminApi.executeSqlDiagnostic(props.findingId)
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
  try {
    await navigator.clipboard.writeText(definition.value.copy_sql)
    if (current === revision) copyFeedback.value = 'SQL kopiert'
  } catch {
    if (current === revision) copyFeedback.value = 'SQL konnte nicht kopiert werden.'
  }
}
</script>

<template>
  <details class="mt-5 rounded-xl border border-slate-200 p-4" @toggle="toggle">
    <summary class="cursor-pointer font-semibold">
      SQL-Diagnose <span class="ml-2 text-xs text-slate-500">READ ONLY</span>
    </summary>
    <p v-if="loading" role="status" class="mt-3">Diagnose laden…</p>
    <p v-if="error" role="alert" class="mt-3">{{ error }}</p>
    <button v-if="error && !definition && !loading" class="button mt-2" @click="load">
      Erneut laden
    </button>
    <div v-if="definition" class="mt-4 space-y-4 text-sm">
      <dl>
        <dt class="font-semibold">Prüfung</dt>
        <dd>{{ definition.title }}</dd>
        <dt class="mt-2 font-semibold">Quelle</dt>
        <dd>{{ definition.datasource }} · nur lesend</dd>
      </dl>
      <SqlCodeBlock :sql="definition.sql" />
      <div>
        <h3 class="font-semibold">Parameter</h3>
        <dl>
          <div v-for="(value, name) in definition.parameters" :key="name" class="break-all">
            <dt class="inline font-mono">{{ name }}</dt>
            =
            <dd class="inline">{{ value }}</dd>
          </div>
        </dl>
      </div>
      <p>{{ definition.explanation }}</p>
      <div class="flex flex-wrap gap-2">
        <button class="button" @click="copy">SQL kopieren</button>
        <button class="button" :disabled="running" @click="execute">Prüfen</button>
      </div>
      <p v-if="copyFeedback" role="status">{{ copyFeedback }}</p>
      <p v-if="running" role="status">Prüfung läuft…</p>
      <p>Finding zuletzt beobachtet: {{ dateTime(definition.last_seen_at) }}</p>
      <template v-if="result">
        <p>
          Aktuelle Diagnose: {{ dateTime(result.observed_at) }} · {{ result.row_count }} Zeilen ·
          {{ result.duration_ms }} ms
        </p>
        <SqlResultTable :columns="result.columns" :rows="result.rows" />
        <SqlRuleEvaluation :evaluation="result.evaluation" />
      </template>
    </div>
  </details>
</template>
