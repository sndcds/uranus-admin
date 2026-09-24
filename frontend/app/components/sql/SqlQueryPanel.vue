<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import CopyValueButton from '../CopyValueButton.vue'
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
const statusLabel = computed(() =>
  props.page && props.status
    ? ({
        Idle: 'Bereit',
        Running: 'Wird ausgeführt',
        Cancelling: 'Wird abgebrochen',
        Cancelled: 'Abgebrochen',
        Completed: 'Abgeschlossen',
        Error: 'Fehler',
      }[props.status] ?? props.status)
    : props.status,
)
const view = ref<'table' | 'json'>('table')
watch(
  () => [props.sql, props.copySql, props.result],
  () => {
    view.value = 'table'
  },
)
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
  <div class="space-y-4" :class="{ 'sql-operations-query': page }">
    <section aria-label="SQL-Abfrage" class="sql-query-section space-y-2">
      <div class="sql-query-heading flex flex-wrap items-center justify-between gap-3">
        <div class="min-w-0">
          <h3 class="font-semibold text-slate-950">SQL Abfrage</h3>
          <p class="mt-1 text-xs text-slate-500">{{ description }}</p>
        </div>
        <SqlCodeEditor
          v-if="page"
          :sql="sql"
          :readonly="!editable"
          :page="page"
          :error-position="errorPosition"
          @update:sql="$emit('update:sql', $event)"
          @execute="$emit('execute')"
          @format="$emit('format')"
        />
        <div class="sql-query-actions ml-auto flex flex-wrap gap-2">
          <slot name="actions" />
          <button
            v-if="editable"
            class="button"
            :disabled="running"
            aria-label="SQL formatieren"
            :class="{ 'sql-tertiary': page }"
            @click="$emit('format')"
          >
            SQL formatieren
          </button>
          <CopyValueButton
            :value="copySql"
            label="SQL"
            button-text="SQL kopieren"
            :variant="page ? 'action' : 'button'"
            :disabled="!copySql"
            :format-value="formatSql"
            :reset-key="sql"
            success-message="SQL kopiert"
            error-message="SQL konnte nicht kopiert werden."
          />
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
            v-if="editable && (!page || running)"
            class="button"
            :disabled="!running || status === 'Cancelling'"
            aria-label="Abbrechen"
            @click="$emit('cancel')"
          >
            ■ Abbrechen
          </button>
        </div>
      </div>
      <p v-if="status" role="status" aria-live="polite" class="text-xs text-slate-600">
        <span
          v-if="running"
          class="mr-2 inline-block size-3 animate-spin rounded-full border-2 border-slate-300 border-t-fuchsia-700"
          aria-hidden="true"
        />{{ statusLabel }}
      </p>
      <SqlCodeEditor
        v-if="!page"
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
    <section aria-label="Ergebnis" class="sql-result-section space-y-3 pt-1" :aria-busy="running">
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
      <div v-else-if="error" role="alert" :class="{ 'sql-query-error': page }">
        <p class="font-semibold">Abfrage konnte nicht ausgeführt werden.</p>
        <p class="mt-1">{{ error }}</p>
        <p v-if="page && errorPosition" class="mt-2 font-mono text-xs">
          SQL-Position: {{ errorPosition }}
        </p>
      </div>
      <p
        v-else-if="!result"
        class="rounded-lg border border-dashed border-slate-200 p-4 text-slate-500"
      >
        {{
          status === 'Cancelled'
            ? 'Abfrage abgebrochen.'
            : executable
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

<style scoped>
.sql-operations-query .sql-query-section {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}
.sql-operations-query .sql-query-heading {
  display: contents;
}
.sql-operations-query :deep(.sql-code) {
  order: 1;
}
.sql-operations-query .sql-query-actions {
  order: 2;
  margin-left: 0;
  align-items: center;
}
.sql-operations-query .sql-query-actions .button-primary {
  order: -1;
}
.sql-operations-query .sql-query-section > [role='status'] {
  order: 3;
}
.sql-operations-query .sql-tertiary {
  border-color: transparent;
  background: transparent;
  color: #a21caf;
}
.sql-operations-query .sql-result-section {
  border-top: 1px solid #e2e8f0;
  padding-top: 0.75rem;
}
.sql-query-error {
  border-left: 3px solid #e11d48;
  background: #fff1f2;
  padding: 0.75rem;
  border-radius: 0.5rem;
}
.sql-operations-query :deep([aria-label='Ergebnisdarstellung'] button),
.sql-operations-query :deep(select) {
  min-height: 44px;
}
</style>
