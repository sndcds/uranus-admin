<script setup lang="ts">
import { computed, ref, watch, onMounted, onBeforeUnmount } from 'vue'
import type { GeocodeRequestDetail } from '#shared/contracts'
import type { ApiFailure } from '#shared/errors'
import { asFailure } from '#shared/errors'
import { dateTime } from '~/utils/presentation'
import { geocodeStatuses } from '~/utils/geocoding'
const route = useRoute()
const { $adminApi } = useNuxtApp()
const data = ref<GeocodeRequestDetail | null>(null)
const error = ref<ApiFailure | null>(null)
const retryError = ref<ApiFailure | null>(null)
const loading = ref(false)
const retrying = ref(false)
const queued = ref(false)
let generation = 0
const entityHref = computed(() =>
  data.value
    ? `/${data.value.entity_type === 'organization' ? 'organizations' : 'venues'}/${data.value.entity_key}`
    : '/geocoding',
)
const facts = computed(() =>
  data.value
    ? [
        {
          label: 'Adresse in Kulturbytes',
          value: data.value.source_address || 'Keine Adresse vorhanden',
        },
        {
          label: 'Letzte Prüfung',
          value: data.value.checked_at ? dateTime(data.value.checked_at) : 'Noch nicht geprüft',
        },
        { label: 'Generation', value: data.value.generation },
        { label: 'Prüfversuche', value: data.value.attempt_count },
      ]
    : [],
)
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
  <section class="space-y-5" aria-labelledby="geocoding-title">
    <PageHeader
      title="Standortvorschlag"
      description="Adressabgleich und mögliche Standorte."
      title-id="geocoding-title"
    >
      <NuxtLink to="/geocoding" class="button">Alle Standortvorschläge</NuxtLink>
    </PageHeader>
    <RequestState :loading="loading" :error="error" @retry="load" />
    <template v-if="data">
      <section class="space-y-3" aria-labelledby="source-heading">
        <SectionHeader
          title="Datensatz und Quelladresse"
          title-id="source-heading"
          description="Der Abgleich bleibt lesend; Vorschläge verändern keine Kulturbytes-Koordinaten."
          as="h2"
        />
        <div class="panel p-4 sm:p-5">
          <div class="flex flex-wrap items-start justify-between gap-3">
            <div class="min-w-0">
              <div class="flex flex-wrap items-center gap-2">
                <h2 class="break-words text-xl font-semibold text-slate-900">
                  {{ data.entity_name }}
                </h2>
                <EntityTypeBadge :type="data.entity_type" />
              </div>
            </div>
            <StatusBadge :label="geocodeStatuses[data.status]" />
          </div>
          <div class="mt-3 flex flex-wrap items-center gap-3 text-sm">
            <NuxtLink :to="entityHref" class="button">
              {{ data.entity_type === 'organization' ? 'Organisation öffnen' : 'Ort öffnen' }}
            </NuxtLink>
            <GraphLink :entity-type="data.entity_type" :entity-key="data.entity_key" />
            <RecordMarkLink :entity-type="data.entity_type" :entity-key="data.entity_key" />
          </div>
        </div>
        <DetailFacts :items="facts" />
      </section>
      <LocationSuggestion :suggestion="data" />
      <AssignmentEditor
        workflow-type="geocode_request"
        :workflow-key="data.id"
        :entity-type="data.entity_type"
        :entity-key="data.entity_key"
      />
      <section class="space-y-3" aria-labelledby="workflow-heading">
        <SectionHeader
          title="Prüfworkflow"
          title-id="workflow-heading"
          description="Neue Prüfungen verwenden erneut die aktuelle, unveränderte Quelladresse."
          as="h2"
        />
        <div class="panel flex flex-wrap items-center gap-3 p-4 sm:p-5">
          <button
            v-if="!['pending', 'checking'].includes(data.status)"
            class="button-primary"
            :disabled="retrying"
            @click="retry"
          >
            <AppIcon name="refresh" :size="16" />
            {{ retrying ? 'Wird eingereiht…' : 'Standort erneut prüfen' }}
          </button>
          <button v-else class="button-primary" :disabled="loading" @click="load">
            <AppIcon name="refresh" :size="16" /> Prüfstand aktualisieren
          </button>
          <span class="text-xs text-slate-500">Generation {{ data.generation }}</span>
        </div>
        <InlineAlert v-if="queued" tone="success">Neue Prüfung wurde eingeplant.</InlineAlert>
        <RequestState :loading="false" :error="retryError" @retry="retry" />
      </section>
    </template>
  </section>
</template>
