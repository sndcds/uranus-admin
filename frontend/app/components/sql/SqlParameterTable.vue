<script setup lang="ts">
import type { SqlDiagnosticDefinition } from '#shared/contracts'
defineProps<{ parameters: SqlDiagnosticDefinition['parameters'] }>()
function parameterType(value: unknown): string {
  if (value === null) return 'NULL'
  if (typeof value === 'boolean') return 'Boolean'
  if (typeof value === 'number') return Number.isInteger(value) ? 'Integer' : 'Number'
  if (typeof value !== 'string') return 'JSON'
  if (/^[\da-f]{8}(?:-[\da-f]{4}){3}-[\da-f]{12}$/i.test(value)) return 'UUID'
  if (
    /^\d{4}-\d{2}-\d{2}$/.test(value) &&
    Number.isFinite(Date.parse(value)) &&
    new Date(value).toISOString().slice(0, 10) === value
  )
    return 'Date'
  if (/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}/.test(value) && Number.isFinite(Date.parse(value)))
    return 'DateTime'
  return 'String'
}
function display(value: unknown): string {
  return typeof value === 'string' ? value : (JSON.stringify(value) ?? 'NULL')
}
</script>

<template>
  <section aria-label="Parameter" class="space-y-3">
    <h3 class="font-semibold">Parameter</h3>
    <div class="overflow-x-auto rounded-xl border border-slate-200">
      <table class="admin-table">
        <caption class="sr-only">
          Gebundene SQL-Parameter
        </caption>
        <thead>
          <tr>
            <th scope="col">Name</th>
            <th scope="col">Typ</th>
            <th scope="col">Wert</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(value, name) in parameters" :key="name">
            <th scope="row" class="font-mono text-xs break-all">{{ name }}</th>
            <td class="text-xs">{{ parameterType(value) }}</td>
            <td class="font-mono text-xs break-all">
              {{ value === null ? 'NULL' : display(value) }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>
