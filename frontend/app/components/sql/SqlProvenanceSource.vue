<script setup lang="ts">
import { ref, onBeforeUnmount } from 'vue'
import type {
  ProvenanceSource,
  ProvenanceResult,
  ProvenanceView,
  ProvenanceParams,
} from '#shared/sql-provenance'
import { asFailure } from '#shared/errors'
import SqlQueryPanel from './SqlQueryPanel.vue'
const props = defineProps<{
  source: ProvenanceSource
  view: ProvenanceView
  parameters: ProvenanceParams
}>()
const { $adminApi } = useNuxtApp()
const result = ref<ProvenanceResult | null>(null),
  error = ref(''),
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
</script>
<template>
  <section :aria-label="source.title">
    <SqlQueryPanel
      :sql="source.sql"
      :copy-sql="source.copy_sql"
      :description="source.description"
      :parameters="source.parameters"
      :executable="source.executable"
      :running="running"
      :error="error"
      :result="result"
      @execute="execute"
    >
      <ul v-if="source.dependencies.length" class="space-y-1 text-xs text-slate-500">
        <li v-for="dependency in source.dependencies" :key="dependency">{{ dependency }}</li>
      </ul>
      <p v-if="!source.executable" class="text-xs text-slate-500">
        Abhängiger Query-Schritt: Parameter sind erst aus vorherigen Ergebnissen bekannt.
      </p>
      <p class="break-all text-xs text-slate-500">
        Implementierung: {{ source.implementation_ref }}
      </p>
    </SqlQueryPanel>
  </section>
</template>
