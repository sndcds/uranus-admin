<script setup lang="ts">
import { computed, ref, onBeforeUnmount } from 'vue'
import SqlWorkspaceModal from './SqlWorkspaceModal.vue'
import SqlSourceTabs from './SqlSourceTabs.vue'
import SqlProvenanceSource from './SqlProvenanceSource.vue'
import type { ProvenanceDefinition, ProvenanceView, ProvenanceParams } from '#shared/sql-provenance'
import { asFailure } from '#shared/errors'
const props = defineProps<{ view: ProvenanceView; parameters: ProvenanceParams }>()
const { $adminApi } = useNuxtApp()
const modal = ref<InstanceType<typeof SqlWorkspaceModal> | null>(null)
const definition = ref<ProvenanceDefinition | null>(null),
  error = ref(''),
  loading = ref(false)
const selected = ref('')
const section = ref('SQL / Datenherkunft')
const source = computed(() => definition.value?.sources.find((item) => item.id === selected.value))
const navigation = [
  'SQL / Datenherkunft',
  'Query Details',
  'Parameter',
  'Verarbeitung',
  'Metadaten',
]
let revision = 0
function clear() {
  revision++
  selected.value = ''
  section.value = 'SQL / Datenherkunft'
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
    if (current === revision) {
      definition.value = value
      selected.value = value.sources[0]?.id ?? ''
    }
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
  <SqlWorkspaceModal
    ref="modal"
    title="SQL / Datenherkunft"
    subtitle="Nachvollziehbare Datenquellen und Abfragen dieser Ansicht."
    @close="clear"
  >
    <template #context>
      <section v-if="definition" class="space-y-3" aria-label="Datenherkunft-Kontext">
        <h3 class="font-semibold text-slate-950">{{ definition.title }}</h3>
        <p class="text-xs text-slate-500">
          Diese Ansicht wird aus Datenbankabfragen und zusätzlicher Anwendungslogik aufgebaut.
        </p>
        <p v-if="source" class="text-xs font-semibold text-slate-600">
          {{ source.datasource === 'uranus' ? 'Uranus' : 'Admin' }} · READ ONLY
        </p>
        <dl class="space-y-2 text-xs text-slate-500">
          <div>
            <dt>API</dt>
            <dd class="break-all">GET {{ definition.endpoint }}</dd>
          </div>
          <div>
            <dt>Query Source</dt>
            <dd class="break-words">{{ source?.title }}</dd>
          </div>
          <div>
            <dt>Zeitbezug</dt>
            <dd>{{ definition.observed_at }}</dd>
          </div>
        </dl>
      </section>
    </template>
    <template #navigation
      ><button
        v-for="item in navigation"
        :key="item"
        class="sql-nav"
        :aria-current="section === item ? 'page' : undefined"
        @click="section = item"
      >
        <AppIcon :name="item === 'SQL / Datenherkunft' ? 'code' : 'list'" :size="16" />{{ item }}
      </button></template
    >
    <p v-if="loading" role="status">Datenherkunft laden…</p>
    <div v-if="error" role="alert">
      <p>{{ error }}</p>
      <button class="button mt-3" @click="open">Erneut versuchen</button>
    </div>
    <template v-if="definition">
      <div v-show="section === 'SQL / Datenherkunft'">
        <SqlSourceTabs v-model="selected" :sources="definition.sources">
          <KeepAlive
            ><SqlProvenanceSource
              v-if="source"
              :key="source.id"
              :source="source"
              :view="view"
              :parameters="definition.parameters"
          /></KeepAlive>
        </SqlSourceTabs>
        <section
          aria-label="Weitere Datenverarbeitung"
          class="mt-5 space-y-3 border-t border-slate-200 pt-4"
        >
          <h3 class="font-semibold">Nachbearbeitung</h3>
          <ul class="list-disc space-y-2 pl-5 text-xs text-slate-600">
            <li v-for="item in definition.post_processing" :key="item">{{ item }}</li>
          </ul>
        </section>
      </div>
      <section v-if="section === 'Query Details'" class="space-y-4">
        <h3 class="font-semibold">Query Details</h3>
        <p>{{ source?.description }}</p>
        <p class="break-all text-xs text-slate-500">{{ source?.implementation_ref }}</p>
        <ul class="space-y-2">
          <li v-for="item in source?.dependencies" :key="item">{{ item }}</li>
        </ul>
      </section>
      <section v-if="section === 'Parameter'" class="space-y-4">
        <h3 class="font-semibold">Filter dieser Ansicht</h3>
        <dl class="space-y-2 text-xs">
          <div v-for="(value, key) in definition.parameters" :key="key">
            <dt class="font-semibold">{{ key }}</dt>
            <dd class="break-all">{{ value }}</dd>
          </div>
        </dl>
        <p v-if="!Object.keys(definition.parameters).length" class="text-slate-500">
          Keine zusätzlichen Filter.
        </p>
      </section>
      <section v-if="section === 'Verarbeitung'" class="space-y-4">
        <h3 class="font-semibold">Nachbearbeitung</h3>
        <ul class="list-disc space-y-2 pl-5">
          <li v-for="item in definition.post_processing" :key="item">{{ item }}</li>
        </ul>
      </section>
      <section v-if="section === 'Metadaten'" class="space-y-4">
        <h3 class="font-semibold">Datenherkunft & Metadaten</h3>
        <p class="break-all text-xs">API: GET {{ definition.endpoint }}</p>
        <p class="text-xs">Zeitbezug: {{ definition.observed_at }}</p>
        <ul class="space-y-2 text-xs text-slate-500">
          <li v-for="note in definition.notes" :key="note">{{ note }}</li>
        </ul>
      </section>
    </template>
  </SqlWorkspaceModal>
</template>
