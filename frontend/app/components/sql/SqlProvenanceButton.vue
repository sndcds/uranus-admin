<script setup lang="ts">
import { computed, ref, onMounted, onBeforeUnmount, watch } from 'vue'
import SqlProvenanceDrawer from './SqlProvenanceDrawer.vue'
import { provenanceRoute } from '~/utils/provenance'
import { validProvenanceParams, type ProvenanceParams } from '#shared/sql-provenance'
const route = useRoute()
const { $adminApi } = useNuxtApp()
const revision = ref(0)
const drawer = ref<InstanceType<typeof SqlProvenanceDrawer> | null>(null)
const target = computed(() => provenanceRoute(route.path, route.query.view === 'event-content'))
const state = computed(() => {
  void revision.value
  const selected = target.value
  if (!selected) return null
  const read = $adminApi.viewRead(selected.endpoint)
  if (!read || read.pending) return null
  const parameters: ProvenanceParams = {}
  for (const [key, value] of Object.entries(read.query))
    if (value !== undefined) parameters[key] = value
  if (selected.view.endsWith('.detail')) parameters.id = String(route.params.id)
  if (read.dataMode) parameters.mode = read.dataMode
  if (read.observedAt) parameters.as_of = read.observedAt
  if (selected.view === 'dashboard') {
    const preview = $adminApi.viewRead('/api/v1/findings')
    if (preview?.pending) return null
    if (preview?.query.severity) parameters.severity = preview.query.severity
  }
  return { parameters: validProvenanceParams(selected.view, parameters), revision: read.revision }
})
const stateKey = computed(() => JSON.stringify([route.fullPath, state.value]))
watch(stateKey, () => drawer.value?.close())
let unsubscribe: (() => void) | undefined
onMounted(() => {
  unsubscribe = $adminApi.subscribeViewReads(() => {
    revision.value++
  })
  revision.value++
})
onBeforeUnmount(() => unsubscribe?.())
</script>
<template>
  <template v-if="target">
    <button type="button" class="button" :disabled="!state?.parameters" @click="drawer?.open()">
      SQL / Datenherkunft
    </button>
    <SqlProvenanceDrawer
      v-if="state?.parameters"
      ref="drawer"
      :key="stateKey"
      :view="target.view"
      :parameters="state.parameters"
    />
  </template>
</template>
