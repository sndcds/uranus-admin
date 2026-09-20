<script setup lang="ts">
import type { SqlDiagnosticResult } from '#shared/contracts'
defineProps<{ evaluation: SqlDiagnosticResult['evaluation'] }>()
</script>
<template>
  <section aria-label="Python-Regelauswertung">
    <h3 class="font-semibold">Python-Regelauswertung</h3>
    <p>{{ evaluation.message }}</p>
    <ul class="mt-2 space-y-1">
      <li v-for="(check, index) in evaluation.checks" :key="index">
        {{ check.label }}:
        <span v-if="check.operator"
          >{{ check.left ?? 'NULL' }} {{ check.operator }} {{ check.right ?? 'NULL' }} →
        </span>
        {{ check.value === null ? 'Unbekannt' : check.value ? 'TRUE' : 'FALSE' }}
      </li>
    </ul>
  </section>
</template>
