<script setup lang="ts">
import StatusBadge from '../StatusBadge.vue'
defineProps<{ columns: string[]; rows: Record<string, unknown>[] }>()
function truncated(value: unknown): value is { value: string; truncated: true } {
  return (
    typeof value === 'object' &&
    value !== null &&
    'truncated' in value &&
    value.truncated === true &&
    'value' in value &&
    typeof value.value === 'string'
  )
}
function display(value: unknown): string {
  if (truncated(value)) return `${value.value} … [gekürzt]`
  return typeof value === 'string' ? value : (JSON.stringify(value) ?? 'NULL')
}
</script>
<template>
  <p
    v-if="!rows.length"
    class="rounded-lg border border-dashed border-slate-200 p-4 text-slate-500"
  >
    Die Abfrage hat keine aktuellen Datensätze zurückgegeben.
  </p>
  <div
    v-else
    class="max-h-80 overflow-auto rounded-lg border border-slate-200"
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
          <th v-for="column in columns" :key="column" scope="col" class="whitespace-nowrap text-xs">
            {{ column }}
          </th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="(row, index) in rows" :key="index">
          <td
            v-for="column in columns"
            :key="column"
            class="max-w-48 truncate text-xs tabular-nums"
            :title="display(row[column])"
          >
            <StatusBadge v-if="row[column] === null" label="NULL" />
            <StatusBadge
              v-else-if="typeof row[column] === 'boolean'"
              :label="String(row[column])"
            />
            <span v-else>{{ display(row[column]) }}</span>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
