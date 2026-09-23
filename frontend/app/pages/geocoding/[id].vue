<script setup lang="ts">
import { ref, watch, onMounted, onBeforeUnmount } from 'vue'
import type { GeocodeRequestDetail } from '#shared/contracts'
import type { ApiFailure } from '#shared/errors'
import { asFailure } from '#shared/errors'
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
  if (retrying.value && data.value?.id === String(route.params.id)) return
  const current = ++generation
  loading.value = true
  const id = String(route.params.id)
  if (data.value?.id !== id) data.value = null
  error.value = null
  retryError.value = null
  queued.value = false
  retrying.value = false
  try {
    const value = await $adminApi.geocodeRequest(id)
    if (current === generation) data.value = value
  } catch (cause) {
    if (current === generation) {
      error.value = asFailure(cause)
      if ([401, 403, 404].includes(error.value.status)) data.value = null
    }
  } finally {
    if (current === generation) loading.value = false
  }
}
async function retry() {
  if (
    loading.value ||
    retrying.value ||
    !data.value ||
    ['pending', 'checking'].includes(data.value.status)
  )
    return
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
    if (current === generation) {
      retryError.value = asFailure(cause)
      if ([401, 403, 404].includes(retryError.value.status)) {
        error.value = retryError.value
        data.value = null
      }
    }
  } finally {
    if (current === generation) retrying.value = false
  }
}
onMounted(load)
watch(() => route.params.id, load, { flush: 'sync' })
onBeforeUnmount(() => {
  generation++
})
</script>
<template>
  <section class="min-w-0 space-y-4 sm:space-y-6" aria-labelledby="geocoding-title">
    <PageHeader
      title="Standortvorschlag"
      description="Adressabgleich und mögliche Standorte."
      title-id="geocoding-title"
    >
      <NuxtLink to="/geocoding" class="button">Alle Standortvorschläge</NuxtLink>
    </PageHeader>
    <RequestState :loading="loading" :error="error" :has-data="!!data" @retry="load" />
    <div v-if="data" class="min-w-0 space-y-6 sm:space-y-8" :aria-busy="loading">
      <GeocodeSourceSummary :suggestion="data" />
      <LocationSuggestion :suggestion="data" />
      <RecordSection
        title="Bearbeitung"
        description="Zuständigkeit, Bearbeitungsstatus und Fälligkeit."
      >
        <AssignmentEditor
          embedded
          workflow-type="geocode_request"
          :workflow-key="data.id"
          :entity-type="data.entity_type"
          :entity-key="data.entity_key"
        />
      </RecordSection>
      <RecordSection
        title="Weitere Aktionen"
        description="Eine neue Prüfung verwendet erneut die aktuelle Quelladresse."
      >
        <div class="flex flex-wrap items-center gap-3">
          <button
            v-if="!['pending', 'checking'].includes(data.status)"
            class="button"
            :disabled="retrying || loading"
            @click="retry"
          >
            <AppIcon name="refresh" :size="16" />{{
              retrying ? 'Wird eingereiht…' : 'Standort erneut prüfen'
            }}
          </button>
          <button class="action-link" :disabled="loading || retrying" @click="load">
            <AppIcon name="refresh" :size="16" />Prüfstand aktualisieren
          </button>
        </div>
        <InlineAlert v-if="queued" tone="success">Neue Prüfung wurde eingeplant.</InlineAlert>
        <RequestState :loading="false" :error="retryError" @retry="retry" />
      </RecordSection>
      <GeocodeTechnicalMetadata :suggestion="data" />
    </div>
  </section>
</template>
