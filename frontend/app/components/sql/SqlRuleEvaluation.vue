<script setup lang="ts">
import { computed } from 'vue'
import type { SqlDiagnosticResult } from '#shared/contracts'
const props = defineProps<{ evaluation: SqlDiagnosticResult['evaluation'] }>()
const explanation = computed(() =>
  props.evaluation.matched === true
    ? 'Der aktuelle Datenstand erfüllt weiterhin die Finding-Regel.'
    : props.evaluation.matched === false
      ? 'Der aktuelle Datenstand erfüllt diese Regel nicht mehr.'
      : 'Die Regel konnte für den aktuellen Datenstand nicht ausgewertet werden.',
)
</script>
<template>
  <section aria-label="Regelauswertung" class="space-y-3 border-t border-slate-200 pt-5">
    <div class="flex items-center justify-between gap-2">
      <h3 class="font-semibold">Regelauswertung</h3>
      <span class="text-xs text-slate-500">{{ evaluation.engine }}</span>
    </div>
    <p class="text-slate-700">{{ explanation }}</p>
    <p v-if="evaluation.matched === null && evaluation.message" class="text-xs text-slate-500">
      {{ evaluation.message }}
    </p>
    <ul class="divide-y divide-slate-100 rounded-xl border border-slate-200">
      <li v-for="(check, index) in evaluation.checks" :key="index" class="flex gap-3 p-3">
        <span aria-hidden="true" class="text-slate-500">{{
          check.value === null ? '–' : check.value ? '✓' : '✕'
        }}</span>
        <div class="min-w-0 space-y-1">
          <p class="break-words font-medium">{{ check.label }}</p>
          <p v-if="check.operator" class="break-all font-mono text-xs text-slate-600">
            {{ check.left ?? 'NULL' }} {{ check.operator }} {{ check.right ?? 'NULL' }}
          </p>
          <p class="text-xs text-slate-500">
            Ergebnis: {{ check.value === null ? 'Unbekannt' : check.value ? 'TRUE' : 'FALSE' }}
          </p>
        </div>
      </li>
    </ul>
  </section>
</template>
