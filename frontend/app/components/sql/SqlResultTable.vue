<script setup lang="ts">
import type { SqlDiagnosticResult } from '#shared/contracts'
import StatusBadge from '../StatusBadge.vue'
defineProps<{ columns: SqlDiagnosticResult['columns']; rows: SqlDiagnosticResult['rows'] }>()
function display(value: unknown): string {
  return typeof value === 'string' ? value : (JSON.stringify(value) ?? 'NULL')
}
</script>
<template>
  <p
    v-if="!rows.length"
    class="rounded-xl border border-dashed border-slate-200 p-4 text-slate-500"
  >
    Die Abfrage hat keine aktuellen Datensätze zurückgegeben.
  </p>
  <div
    v-else
    class="max-h-80 overflow-auto rounded-xl border border-slate-200"
    tabindex="0"
    role="region"
    aria-label="Ergebnistabelle"
  >
    <table class="admin-table">
      <caption class="sr-only">
        Diagnose-Ergebnis
      </caption>
      <thead class="sticky top-0">
        <tr>
          <th
            v-for="column in columns"
            :key="column"
            scope="col"
            class="whitespace-nowrap font-mono text-xs"
          >
            {{ column }}
          </th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="(row, index) in rows" :key="index">
          <td
            v-for="column in columns"
            :key="column"
            class="max-w-80 break-words font-mono text-xs tabular-nums"
          >
            <StatusBadge v-if="row[column] === null" label="NULL" />
            <StatusBadge
              v-else-if="typeof row[column] === 'boolean'"
              :label="String(row[column])"
            />
            <span v-else class="whitespace-pre-wrap">{{ display(row[column]) }}</span>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
