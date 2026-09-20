<script setup lang="ts">
import { ref, onBeforeUnmount } from 'vue'
import type {
  ProvenanceSource,
  ProvenanceResult,
  ProvenanceView,
  ProvenanceParams,
} from '#shared/sql-provenance'
import { asFailure } from '#shared/errors'
import SqlCodeBlock from './SqlCodeBlock.vue'
import SqlResultTable from './SqlResultTable.vue'
const props = defineProps<{
  source: ProvenanceSource
  view: ProvenanceView
  parameters: ProvenanceParams
}>()
const { $adminApi } = useNuxtApp()
const result = ref<ProvenanceResult | null>(null),
  error = ref(''),
  feedback = ref(''),
  running = ref(false)
let revision = 0
onBeforeUnmount(() => {
  revision++
})
async function execute() {
  if (running.value || !props.source.executable) return
  const current = ++revision
  running.value = true
  error.value = ''
  result.value = null
  try {
    const value = await $adminApi.executeProvenance(props.view, props.source.id, props.parameters)
    if (current === revision) result.value = value
  } catch (cause) {
    if (current === revision) error.value = asFailure(cause).message
  } finally {
    if (current === revision) running.value = false
  }
}
async function copy() {
  if (!props.source.copy_sql) return
  const current = revision
  try {
    await navigator.clipboard.writeText(props.source.copy_sql)
    if (current === revision) feedback.value = 'SQL kopiert'
  } catch {
    if (current === revision) feedback.value = 'SQL konnte nicht kopiert werden.'
  }
}
</script>
<template>
  <section class="space-y-3 rounded-xl border border-slate-200 p-4" :aria-label="source.title">
    <h3 class="font-semibold">{{ source.title }}</h3>
    <p class="text-xs font-semibold">
      {{ source.datasource === 'uranus' ? 'Uranus' : 'Admin' }} · READ ONLY
    </p>
    <p class="text-sm">{{ source.description }}</p>
    <SqlCodeBlock :sql="source.sql" />
    <h4 class="text-sm font-semibold">Parameter</h4>
    <dl class="text-xs">
      <div v-for="(value, key) in source.parameters" :key="key" class="break-all">
        <dt class="inline font-mono">{{ key }}</dt>
        =
        <dd class="inline">{{ JSON.stringify(value) }}</dd>
      </div>
    </dl>
    <ul v-if="source.dependencies.length" class="text-sm">
      <li v-for="dependency in source.dependencies" :key="dependency">{{ dependency }}</li>
    </ul>
    <p v-if="!source.executable" class="text-sm">
      Abhängiger Query-Schritt: Parameter sind erst aus vorherigen Ergebnissen bekannt. Keine
      Ausführung mit erfundenen Werten.
    </p>
    <div class="flex flex-wrap gap-2">
      <button type="button" class="button" :disabled="!source.copy_sql" @click="copy">
        SQL kopieren</button
      ><button
        type="button"
        class="button"
        :disabled="running || !source.executable"
        @click="execute"
      >
        Ausführen
      </button>
    </div>
    <p v-if="feedback" role="status">{{ feedback }}</p>
    <p v-if="running" role="status">Prüfung läuft…</p>
    <p v-if="error" role="alert">{{ error }}</p>
    <template v-if="result"
      ><p role="status">
        {{ result.row_count }} Zeilen · {{ result.duration_ms }} ms · {{ result.observed_at }}
      </p>
      <p v-if="result.truncated">
        Inspektionsgrenze erreicht; möglicherweise weitere Zeilen vorhanden.
      </p>
      <SqlResultTable :columns="result.columns" :rows="result.rows"
    /></template>
    <p class="break-all text-xs text-slate-500">Implementierung: {{ source.implementation_ref }}</p>
  </section>
</template>
