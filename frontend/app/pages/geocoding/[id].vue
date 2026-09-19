<script setup lang="ts">
import { ref, watch, onMounted, onBeforeUnmount } from 'vue'
import type { GeocodeRequestDetail } from '#shared/contracts'
import type { ApiFailure } from '#shared/errors'
import { asFailure } from '#shared/errors'
import { dateTime } from '~/utils/presentation'
const route = useRoute()
const { $adminApi } = useNuxtApp()
const data = ref<GeocodeRequestDetail | null>(null)
const error = ref<ApiFailure | null>(null)
const retryError = ref<ApiFailure | null>(null)
const loading = ref(false)
const retrying = ref(false)
const queued = ref(false)
let generation = 0
async function load() {
  const current = ++generation
  loading.value = true
  data.value = null
  error.value = null
  retryError.value = null
  queued.value = false
  retrying.value = false
  try {
    const value = await $adminApi.geocodeRequest(String(route.params.id))
    if (current === generation) data.value = value
  } catch (cause) {
    if (current === generation) error.value = asFailure(cause)
  } finally {
    if (current === generation) loading.value = false
  }
}
async function retry() {
  if (retrying.value || !data.value || ['pending', 'checking'].includes(data.value.status)) return
  const current = generation
  retrying.value = true
  retryError.value = null
  try {
    await $adminApi.retryGeocodeRequest(data.value.id)
    if (current !== generation) return
    data.value = {
      ...data.value,
      status: 'pending',
      candidates: [],
      best_candidate: null,
      candidate_count: 0,
    }
    queued.value = true
  } catch (cause) {
    if (current === generation) retryError.value = asFailure(cause)
  } finally {
    if (current === generation) retrying.value = false
  }
}
onMounted(load)
watch(() => route.params.id, load)
onBeforeUnmount(() => {
  generation++
})
</script>
<template>
  <section class="space-y-5">
    <PageHeader title="Standortvorschlag" description="Adressabgleich und mögliche Standorte."
      ><NuxtLink to="/geocoding" class="button">Alle Standortvorschläge</NuxtLink></PageHeader
    >
    <p class="muted">Diese Ansicht ist systemweit.</p>
    <RequestState :loading="loading" :error="error" @retry="load" />
    <template v-if="data">
      <DataListShell class="p-4 space-y-2">
        <h2 class="text-lg font-semibold">{{ data.entity_name }}</h2>
        <p>{{ data.source_address || 'Keine Adresse vorhanden' }}</p>
        <p class="muted">
          Letzte Prüfung: {{ dateTime(data.checked_at) }} · Generation {{ data.generation }}
        </p>
        <NuxtLink
          :to="`/${data.entity_type === 'organization' ? 'organizations' : 'venues'}/${data.entity_key}`"
          class="text-fuchsia-700 underline"
          >{{
            data.entity_type === 'organization' ? 'Organisation öffnen' : 'Ort öffnen'
          }}</NuxtLink
        >
      </DataListShell>
      <LocationSuggestion :suggestion="data" />
      <button
        v-if="!['pending', 'checking'].includes(data.status)"
        class="button"
        :disabled="retrying"
        @click="retry"
      >
        {{ retrying ? 'Wird eingereiht…' : 'Standort erneut prüfen' }}
      </button>
      <button v-else class="button" :disabled="loading" @click="load">
        Prüfstand aktualisieren
      </button>
      <p v-if="queued" role="status">Neue Prüfung wurde eingeplant.</p>
      <RequestState :loading="false" :error="retryError" @retry="retry" />
    </template>
  </section>
</template>
