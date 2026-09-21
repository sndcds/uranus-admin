<script setup lang="ts">
import { ref, onBeforeUnmount, onDeactivated, watch } from 'vue'
import type { SqlDiagnosticDefinition } from '#shared/contracts'
import type { ProvenanceSource } from '#shared/sql-provenance'
import SqlCodeEditor from './SqlCodeEditor.vue'
import SqlParameterTable from './SqlParameterTable.vue'
import SqlResultTable from './SqlResultTable.vue'
import SqlJsonResult from './SqlJsonResult.vue'
import { formatSql } from '~/utils/sql-format'
import { sqlCsv } from '~/utils/sql-csv'
import { dateTime } from '~/utils/presentation'
const props = defineProps<{
  sql: string
  copySql: string | null
  description: string
  parameters: SqlDiagnosticDefinition['parameters'] | ProvenanceSource['parameters']
  executable: boolean
  running: boolean
  error: string
  result: {
    columns: string[]
    rows: Record<string, unknown>[]
    row_count: number
    duration_ms: number
    observed_at: string | null
    truncated?: boolean
  } | null
  editable?: boolean
  page?: boolean
  errorPosition?: number | null
  status?: string
}>()
defineEmits<{ execute: []; cancel: []; format: []; 'update:sql': [value: string] }>()
const feedback = ref(''),
  view = ref<'table' | 'json'>('table')
let revision = 0,
  timer: ReturnType<typeof setTimeout> | undefined
let copyInput: string | null = null,
  formattedCopy: Promise<string> | null = null
function reset() {
  revision++
  feedback.value = ''
  view.value = 'table'
  clearTimeout(timer)
  copyInput = null
  formattedCopy = null
}
watch(() => [props.sql, props.copySql], reset)
watch(
  () => props.result,
  () => {
    view.value = 'table'
  },
)
onBeforeUnmount(reset)
onDeactivated(() => {
  revision++
  clearTimeout(timer)
  feedback.value = ''
})
async function copy() {
  if (!props.copySql) return
  const current = revision
  clearTimeout(timer)
  try {
    if (copyInput !== props.copySql) {
      copyInput = props.copySql
      formattedCopy = formatSql(props.copySql)
    }
    const text = await formattedCopy
    if (current !== revision || text === null) return
    await navigator.clipboard.writeText(text)
    if (current === revision) feedback.value = 'SQL kopiert'
  } catch {
    if (current === revision) feedback.value = 'SQL konnte nicht kopiert werden.'
  }
  if (current === revision)
    timer = setTimeout(() => {
      feedback.value = ''
    }, 2500)
}
function download() {
  if (!props.result) return
  const url = URL.createObjectURL(
    new Blob(['\uFEFF', sqlCsv(props.result.columns, props.result.rows)], {
      type: 'text/csv;charset=utf-8',
    }),
  )
  const link = document.createElement('a')
  link.href = url
  link.download = 'sql-ergebnis.csv'
  link.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
</script>
<template>
  <div class="space-y-4">
    <section aria-label="SQL-Abfrage" class="space-y-2">
      <div class="flex flex-wrap items-center justify-between gap-3">
        <div class="min-w-0">
          <h3 class="font-semibold text-slate-950">SQL Abfrage</h3>
          <p class="mt-1 text-xs text-slate-500">{{ description }}</p>
        </div>
        <div class="ml-auto flex flex-wrap gap-2">
          <slot name="actions" />
          <button
            v-if="editable"
            class="button"
            :disabled="running"
            aria-label="SQL formatieren"
            @click="$emit('format')"
          >
            SQL formatieren
          </button>
          <button class="button" aria-label="SQL kopieren" :disabled="!copySql" @click="copy">
            <AppIcon name="copy" :size="14" />SQL kopieren
          </button>
          <button
            v-if="executable"
            class="button-primary"
            aria-label="Abfrage ausführen"
            :disabled="running"
            @click="$emit('execute')"
          >
            <AppIcon name="play" :size="14" />Abfrage ausführen
          </button>
          <button
            v-if="editable"
            class="button"
            :disabled="!running || status === 'Cancelling'"
            aria-label="Abbrechen"
            @click="$emit('cancel')"
          >
            ■ Abbrechen
          </button>
        </div>
      </div>
      <p v-if="feedback" role="status" class="text-xs text-slate-600">{{ feedback }}</p>
      <p v-if="status" role="status" aria-live="polite" class="text-xs text-slate-600">
        <span
          v-if="running"
          class="mr-2 inline-block size-3 animate-spin rounded-full border-2 border-slate-300 border-t-fuchsia-700"
          aria-hidden="true"
        />{{ status }}
      </p>
      <SqlCodeEditor
        :sql="sql"
        :readonly="!editable"
        :page="page"
        :error-position="errorPosition"
        @update:sql="$emit('update:sql', $event)"
        @execute="$emit('execute')"
        @format="$emit('format')"
      />
    </section>
    <SqlParameterTable
      v-if="Object.keys(parameters).length"
      :parameters="parameters"
      :initial-only="editable"
    />
    <section aria-label="Ergebnis" class="space-y-3 pt-1">
      <div class="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3 class="font-semibold text-slate-950">
            Ergebnis<span v-if="result">
              ({{ result.row_count }} {{ result.row_count === 1 ? 'Zeile' : 'Zeilen' }},
              {{ result.duration_ms }} ms)</span
            >
          </h3>
          <p v-if="result?.observed_at" class="mt-1 text-xs text-slate-500">
            Aktuelle Diagnose: {{ dateTime(result.observed_at) }}
          </p>
          <p
            v-if="typeof parameters.diagnostic_limit === 'number'"
            class="mt-1 text-xs text-slate-500"
          >
            Maximal {{ parameters.diagnostic_limit }} Zeilen werden angezeigt.
          </p>
        </div>
        <div v-if="result" class="flex flex-wrap gap-2">
          <button class="button" @click="download">
            <AppIcon name="download" :size="14" />Als CSV herunterladen
          </button>
          <div
            class="inline-flex rounded-lg border border-slate-200 p-0.5"
            role="group"
            aria-label="Ergebnisdarstellung"
          >
            <button
              class="rounded-md px-2 py-1 text-xs"
              :class="view === 'table' ? 'bg-slate-100 text-slate-900' : 'text-slate-600'"
              :aria-pressed="view === 'table'"
              @click="view = 'table'"
            >
              Tabellarisch
            </button>
            <button
              class="rounded-md px-2 py-1 text-xs"
              :class="view === 'json' ? 'bg-slate-100 text-slate-900' : 'text-slate-600'"
              :aria-pressed="view === 'json'"
              @click="view = 'json'"
            >
              JSON
            </button>
          </div>
        </div>
      </div>
      <p v-if="running" role="status" class="text-slate-600">Abfrage wird ausgeführt…</p>
      <div v-else-if="error" role="alert">
        <p class="font-semibold">Abfrage konnte nicht ausgeführt werden.</p>
        <p class="mt-1">{{ error }}</p>
      </div>
      <p
        v-else-if="!result"
        class="rounded-lg border border-dashed border-slate-200 p-4 text-slate-500"
      >
        {{
          executable
            ? 'Noch keine Abfrage ausgeführt.'
            : 'Diese Datenherkunft ist nur dokumentarisch.'
        }}
      </p>
      <template v-if="result">
        <p v-if="'truncated' in result && result.truncated" class="text-xs text-slate-600">
          Inspektionsgrenze erreicht; möglicherweise weitere Zeilen vorhanden.
        </p>
        <SqlResultTable v-if="view === 'table'" :columns="result.columns" :rows="result.rows" />
        <SqlJsonResult v-else :rows="result.rows" />
      </template>
    </section>
    <slot />
  </div>
</template>
