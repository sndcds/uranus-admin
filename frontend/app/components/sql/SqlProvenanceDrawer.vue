<script setup lang="ts">
import { ref, onBeforeUnmount } from 'vue'
import AppModal from '../AppModal.vue'
import SqlProvenanceSource from './SqlProvenanceSource.vue'
import type { ProvenanceDefinition, ProvenanceView, ProvenanceParams } from '#shared/sql-provenance'
import { asFailure } from '#shared/errors'
const props = defineProps<{ view: ProvenanceView; parameters: ProvenanceParams }>()
const { $adminApi } = useNuxtApp()
const modal = ref<InstanceType<typeof AppModal> | null>(null)
const definition = ref<ProvenanceDefinition | null>(null),
  error = ref(''),
  loading = ref(false)
let revision = 0
function clear() {
  revision++
  definition.value = null
  error.value = ''
  loading.value = false
}
function close() {
  modal.value?.close()
  clear()
}
async function open() {
  clear()
  const current = revision
  await modal.value?.open()
  if (current !== revision) return
  loading.value = true
  try {
    const value = await $adminApi.provenance(props.view, props.parameters)
    if (current === revision) definition.value = value
  } catch (cause) {
    if (current === revision) error.value = asFailure(cause).message
  } finally {
    if (current === revision) loading.value = false
  }
}
onBeforeUnmount(clear)
defineExpose({ open, close })
</script>
<template>
  <AppModal ref="modal" title="SQL / Datenherkunft" wide @close="clear">
    <p class="my-3 text-sm">
      Diese Ansicht wird aus mehreren Datenbankabfragen und zusätzlicher Anwendungslogik aufgebaut.
    </p>
    <p v-if="loading" role="status">Datenherkunft laden…</p>
    <p v-if="error" role="alert">{{ error }}</p>
    <div v-if="definition" class="space-y-4">
      <p class="break-all text-xs">API: GET {{ definition.endpoint }}</p>
      <p class="text-xs">Zeitbezug: {{ definition.observed_at }}</p>
      <SqlProvenanceSource
        v-for="source in definition.sources"
        :key="source.id"
        :source="source"
        :view="view"
        :parameters="definition.parameters"
      />
      <section aria-label="Weitere Datenverarbeitung">
        <h3 class="font-semibold">Postprocessing / weitere Datenverarbeitung</h3>
        <ul class="list-disc space-y-2 pl-5 text-sm">
          <li v-for="item in definition.post_processing" :key="item">{{ item }}</li>
        </ul>
      </section>
      <ul class="space-y-2 text-xs text-slate-500">
        <li v-for="note in definition.notes" :key="note">{{ note }}</li>
      </ul>
    </div>
  </AppModal>
</template>
