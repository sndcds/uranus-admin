<script setup lang="ts">
import type { SemanticExplanation } from '#shared/contracts'
defineProps<{ explanation: SemanticExplanation }>()
</script>
<template>
  <section
    class="min-w-0 space-y-1 break-words text-sm [overflow-wrap:anywhere]"
    aria-label="Warum passt das?"
  >
    <h4 class="font-medium">Warum passt das?</h4>
    <p>{{ explanation.reason }}</p>
    <details class="text-slate-700">
      <summary class="min-h-11 cursor-pointer content-center text-blue-700">Beleg anzeigen</summary>
      <div class="space-y-2 pb-2">
        <p>
          Gefundener Bereich:
          <span class="font-medium">{{ explanation.matched_aspect_label }}</span>
        </p>
        <p>Beleg aus den öffentlichen Daten:</p>
        <blockquote class="whitespace-pre-wrap border-l-2 border-slate-300 pl-3">
          {{ explanation.evidence.text }}
        </blockquote>
        <template v-if="explanation.supporting_evidence.length">
          <h5 class="font-medium">Weitere passende Bereiche</h5>
          <ul class="space-y-2">
            <li v-for="support in explanation.supporting_evidence" :key="support.kind">
              <p class="font-medium">{{ support.label }}</p>
              <p class="whitespace-pre-wrap">{{ support.text }}</p>
            </li>
          </ul>
        </template>
      </div>
    </details>
    <p class="text-xs text-slate-500">Ähnlichkeit: {{ explanation.score.toFixed(3) }}</p>
  </section>
</template>
