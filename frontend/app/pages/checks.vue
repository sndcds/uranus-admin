<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import type { z } from '#shared/zod'
import type { checkRunPageSchema } from '#shared/contracts'
import { asFailure } from '#shared/errors'
import type { ApiFailure } from '#shared/errors'
import { dateTime, checkStatusLabels } from '~/utils/presentation'
const { $adminApi } = useNuxtApp()
const data = ref<z.infer<typeof checkRunPageSchema> | null>(null)
const error = ref<ApiFailure | null>(null)
const loading = ref(false)
const running = ref(false)
const pending = computed(
  () => data.value?.items.some((item) => ['queued', 'running'].includes(item.status)) ?? false,
)
let requestId = 0
let disposed = false
let timer: ReturnType<typeof setTimeout> | undefined
function stopPolling() {
  clearTimeout(timer)
  timer = undefined
}
async function load(page = 1, background = false) {
  stopPolling()
  const id = ++requestId
  loading.value = !background
  if (!background) data.value = null
  error.value = null
  try {
    const result = await $adminApi.checkRuns(page)
    if (id !== requestId || disposed) return
    data.value = result
    if (pending.value) timer = setTimeout(() => void load(page, true), 2000)
  } catch (cause) {
    if (id === requestId && !disposed) {
      data.value = null
      error.value = asFailure(cause)
    }
  } finally {
    if (id === requestId && !disposed) loading.value = false
  }
}
async function run() {
  stopPolling()
  const id = ++requestId
  running.value = true
  error.value = null
  try {
    await $adminApi.runCheck()
    if (id !== requestId || disposed) return
    running.value = false
    await load()
  } catch (cause) {
    if (id === requestId && !disposed) {
      running.value = false
      error.value = asFailure(cause)
    }
  }
}
onMounted(() => load())
onBeforeUnmount(() => {
  disposed = true
  requestId++
  stopPolling()
})
</script>

<template>
  <section class="space-y-5">
    <PageHeader title="Prüfläufe" description="Gespeicherte Prüfungen und Regelabdeckung.">
      <button class="button-primary" :disabled="running || loading || pending" @click="run">
        {{ running || pending ? 'Prüfung läuft …' : 'Prüflauf starten' }}
      </button>
      <NuxtLink class="button" to="/findings?mode=persisted">Gespeicherte Befunde</NuxtLink>
    </PageHeader>
    <p class="muted">
      Prüfläufe werden im Hintergrund verarbeitet; der Status wird automatisch aktualisiert. Nur
      erfolgreiche Prüfungen können behobene Befunde schließen.
    </p>
    <RequestState :loading="loading" :error="error" @retry="load()" />
    <template v-if="data">
      <ResultSummary
        :total="data.pagination.total"
        :visible="data.items.length"
        noun="Prüfläufe"
        description="Gespeicherte Historie · unabhängig vom Dashboard-Zeitraum"
      />
      <DataListShell
        v-if="data.items.length"
        as="ul"
        class="divide-y divide-slate-100"
        :aria-busy="loading"
      >
        <li v-for="item in data.items" :key="item.id" class="data-row">
          <div class="flex flex-wrap items-center justify-between gap-2">
            <h3 class="text-sm font-semibold">Eingereiht: {{ dateTime(item.started_at) }}</h3>
            <StatusBadge
              :label="checkStatusLabels[item.status]"
              :tone="
                item.status === 'failed'
                  ? 'error'
                  : item.status === 'success'
                    ? 'success'
                    : 'neutral'
              "
            />
          </div>
          <p class="mt-2 text-sm text-slate-600">
            {{ item.rule_count }} Regeln · {{ item.finding_count }} Befunde · Ende:
            {{ dateTime(item.finished_at) }}
          </p>
          <p v-if="item.status === 'failed'" class="mt-2 text-xs text-rose-700">
            Prüfung fehlgeschlagen. Daraus wurde keine automatische Behebung abgeleitet.
          </p>
        </li>
      </DataListShell>
      <EmptyState v-else message="Noch keine gespeicherten Prüfläufe." />
      <PaginationBar :pagination="data.pagination" :loading="loading || running" @change="load" />
    </template>
  </section>
</template>
