<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import type { z } from '#shared/zod'
import type { checkRunPageSchema } from '#shared/contracts'
import { asFailure } from '#shared/errors'
import type { ApiFailure } from '#shared/errors'
import { dateTime, checkStatusLabels } from '~/utils/presentation'
import { checkDuration } from '~/utils/check-runs'
import DenseTable from '~/components/DenseTable.vue'
import TechnicalInfoBar from '~/components/TechnicalInfoBar.vue'
import CompactFacts from '~/components/CompactFacts.vue'
import RecordSection from '~/components/RecordSection.vue'
import OperationTime from '~/components/OperationTime.vue'
const { $adminApi } = useNuxtApp()
const data = ref<z.infer<typeof checkRunPageSchema> | null>(null)
const error = ref<ApiFailure | null>(null)
const loading = ref(false)
const running = ref(false)
const currentPage = ref(1)
const polling = ref(false)
const activeRun = computed(() =>
  data.value?.items.find((item) => ['queued', 'running'].includes(item.status)),
)
const pending = computed(
  () => data.value?.items.some((item) => ['queued', 'running'].includes(item.status)) ?? false,
)
let requestId = 0
let disposed = false
let timer: ReturnType<typeof setTimeout> | undefined
function stopPolling() {
  clearTimeout(timer)
  timer = undefined
  polling.value = false
}
async function load(page = currentPage.value, background = false) {
  stopPolling()
  const id = ++requestId
  loading.value = !background
  if (page !== currentPage.value) data.value = null
  currentPage.value = page
  error.value = null
  try {
    const result = await $adminApi.checkRuns(page)
    if (id !== requestId || disposed) return
    data.value = result
    if (pending.value) {
      polling.value = true
      timer = setTimeout(() => void load(page, true), 2000)
    }
  } catch (cause) {
    if (id === requestId && !disposed) {
      error.value = asFailure(cause)
      if ([401, 403, 404, 422].includes(error.value.status)) data.value = null
    }
  } finally {
    if (id === requestId && !disposed) loading.value = false
  }
}
async function run() {
  if (running.value || loading.value || pending.value) return
  stopPolling()
  const id = ++requestId
  running.value = true
  error.value = null
  try {
    await $adminApi.runCheck()
    if (id !== requestId || disposed) return
    running.value = false
    await load(1)
  } catch (cause) {
    if (id === requestId && !disposed) {
      running.value = false
      error.value = asFailure(cause)
      if ([401, 403, 404].includes(error.value.status)) data.value = null
    }
  }
}
onMounted(() => load())
onBeforeUnmount(() => {
  disposed = true
  requestId++
  stopPolling()
})
const columns = [
  { key: 'status', label: 'Status', rowHeader: true, width: '15%' },
  { key: 'started_at', label: 'Eingereiht / Start', width: '19%' },
  { key: 'finished_at', label: 'Ende / Dauer', width: '22%' },
  { key: 'rule_count', label: 'Regeln / Befunde', width: '15%' },
  { key: 'error_message', label: 'Ergebnis', width: '29%' },
] as const
</script>

<template>
  <section class="operations-page">
    <PageHeader title="Prüfläufe" description="Gespeicherte Prüfungen und Regelabdeckung.">
      <button class="button-primary" :disabled="running || loading || pending" @click="run">
        {{ running || pending ? 'Prüfung läuft …' : 'Prüflauf starten' }}
      </button>
      <button class="button" :disabled="loading || running" @click="load()">Aktualisieren</button>
      <NuxtLink class="button" to="/findings?mode=persisted">Gespeicherte Befunde</NuxtLink>
    </PageHeader>
    <p class="muted">
      Prüfläufe werden im Hintergrund verarbeitet; der Status wird automatisch aktualisiert. Nur
      erfolgreiche Prüfungen können behobene Befunde schließen.
    </p>
    <RequestState :loading="loading" :error="error" :has-data="!!data" @retry="load()" />
    <RecordSection v-if="activeRun" title="Aktueller Lauf" surface="subtle">
      <CompactFacts
        :columns="4"
        :items="[
          { label: 'Status', value: checkStatusLabels[activeRun.status] },
          { label: 'Eingereiht', value: dateTime(activeRun.started_at) },
          { label: 'Regeln', value: activeRun.rule_count },
          { label: 'Befunde', value: activeRun.finding_count },
        ]"
      />
    </RecordSection>
    <template v-if="data">
      <ResultSummary
        :total="data.pagination.total"
        :visible="data.items.length"
        noun="Prüfläufe"
        description="Gespeicherte Historie · unabhängig vom Dashboard-Zeitraum"
      />
      <DenseTable
        v-if="data.items.length"
        caption="Prüflaufhistorie"
        :columns="columns"
        :rows="data.items"
        :row-key="(item) => item.id"
        stack-at="tablet"
        :busy="loading"
      >
        <template #cell-status="{ row }"
          ><StatusBadge
            :label="checkStatusLabels[row.status]"
            :tone="
              row.status === 'failed' ? 'error' : row.status === 'success' ? 'success' : 'neutral'
            "
        /></template>
        <template #cell-started_at="{ row }"><OperationTime :value="row.started_at" /></template>
        <template #cell-finished_at="{ row }"
          ><OperationTime :value="row.finished_at" />
          <p v-if="checkDuration(row.started_at, row.finished_at)" class="operations-meta">
            {{ checkDuration(row.started_at, row.finished_at) }} · inkl. Wartezeit
          </p></template
        >
        <template #cell-rule_count="{ row }"
          ><p>{{ row.rule_count }} Regeln</p>
          <p class="operations-meta">{{ row.finding_count }} Befunde</p></template
        >
        <template #cell-error_message="{ row }"
          ><p v-if="row.status === 'failed'" class="text-xs text-rose-700">
            Prüfung fehlgeschlagen. Daraus wurde keine automatische Behebung abgeleitet.
          </p>
          <p v-else-if="row.status === 'success'" class="operations-meta">Prüfung abgeschlossen.</p>
          <p v-else class="operations-meta">Ergebnis steht noch aus.</p></template
        >
      </DenseTable>
      <EmptyState
        v-else-if="!error"
        variant="compact"
        message="Noch keine gespeicherten Prüfläufe."
      />
      <PaginationBar :pagination="data.pagination" :loading="loading || running" @change="load" />
      <TechnicalInfoBar
        :show-title="false"
        :items="[
          { label: 'Gesamtzahl', value: data.pagination.total },
          { label: 'Sichtbare Läufe', value: data.items.length },
          { label: 'Einträge pro Seite', value: data.pagination.page_size },
          {
            label: 'Automatische Aktualisierung (UI)',
            value: polling ? 'Aktiv · alle 2 Sekunden' : 'Inaktiv',
          },
          {
            label: 'Neuester Lauf auf dieser Seite',
            value: data.items[0]?.id,
            mono: true,
            copyable: true,
          },
        ]"
      />
    </template>
  </section>
</template>
