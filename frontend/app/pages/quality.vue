<script setup lang="ts">
import type { TechnicalFact } from '~/utils/operations'
const store = useDashboardStore()
const { $adminApi } = useNuxtApp()
const globalData = computed(() => (store.data?.geo_scope_id ? null : store.data))
const sourceLabel = computed(() =>
  globalData.value?.quality.mode === 'live'
    ? 'Live-Diagnose'
    : globalData.value?.quality.mode === 'persisted'
      ? 'Persistierter Bestand'
      : 'Qualitätsbestand',
)
const technicalItems = computed<TechnicalFact[]>(() => [
  {
    label: 'Quelle',
    value:
      globalData.value?.quality.mode === 'persisted'
        ? 'Persistiert'
        : globalData.value?.quality.mode === 'live'
          ? 'Live-Diagnose'
          : null,
  },
  { label: 'Scope', value: 'Systemweit' },
  { label: 'Gelieferte Regeln', value: globalData.value?.quality.rules?.length },
])
onMounted(() => {
  if (!store.data || store.data.geo_scope_id) void store.load($adminApi)
})
</script>

<template>
  <section class="operations-page" aria-labelledby="quality-title">
    <PageHeader
      title="Datenqualität"
      title-id="quality-title"
      description="Regelbasierte Datenprobleme prüfen und priorisieren."
    >
      <NuxtLink to="/checks" class="button">Prüfläufe</NuxtLink>
    </PageHeader>
    <div class="section-subtle flex flex-wrap items-center justify-between gap-3 p-3" role="status">
      <div class="min-w-0">
        <p class="text-sm font-semibold">
          {{ sourceLabel }} · Systemweit · unabhängig vom Dashboard-Zeitraum
        </p>
        <p class="operations-meta mt-1">
          Gespeicherte Zahlen schließen behobene Befunde aus, enthalten aber Zurückstellungen und
          Ausnahmen.
        </p>
      </div>
      <button
        class="button button-compact"
        :disabled="store.loading"
        @click="store.load($adminApi)"
      >
        <AppIcon name="refresh" :size="14" />Aktualisieren
      </button>
    </div>
    <RequestState
      :loading="store.loading"
      :error="store.error"
      :has-data="!!globalData"
      :last-success="store.lastSuccess"
      @retry="store.load($adminApi)"
    />
    <QualityOverview :data="globalData" />
    <TechnicalInfoBar v-if="globalData" :items="technicalItems" :show-title="false" />
  </section>
</template>
