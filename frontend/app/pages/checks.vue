<script setup lang="ts">
import type { z } from '#shared/zod'
import type { checkRunPageSchema } from '#shared/contracts'
import { asFailure } from '#shared/errors'
import type { ApiFailure } from '#shared/errors'
import { dateTime } from '~/utils/presentation'
const { $adminApi } = useNuxtApp()
const data = ref<z.infer<typeof checkRunPageSchema> | null>(null)
const error = ref<ApiFailure | null>(null)
const loading = ref(false)
const running = ref(false)
let requestId = 0
async function load(page = 1) {
  const id = ++requestId
  loading.value = true
  data.value = null
  error.value = null
  try {
    const result = await $adminApi.checkRuns(page)
    if (id === requestId) data.value = result
  } catch (cause) {
    if (id === requestId) error.value = asFailure(cause)
  } finally {
    if (id === requestId) loading.value = false
  }
}
async function run() {
  running.value = true
  error.value = null
  try {
    await $adminApi.runCheck()
    await load()
  } catch (cause) {
    error.value = asFailure(cause)
  } finally {
    running.value = false
  }
}
onMounted(() => load())
watch(
  useState('admin-access-revision', () => 0),
  () => load(),
)
onBeforeUnmount(() => {
  requestId++
})
</script>

<template>
  <section class="space-y-4">
    <PageHeader title="Prüfläufe" description="Gespeicherte Prüfungen und Regelabdeckung.">
      <button class="button-primary" :disabled="running || loading" @click="run">
        {{ running ? 'Prüfung läuft …' : 'Prüflauf starten' }}
      </button>
      <NuxtLink class="button" to="/findings?mode=persisted">Gespeicherte Befunde</NuxtLink>
    </PageHeader>
    <p class="muted">
      Ein Prüflauf speichert Befunde. Nur erfolgreiche Prüfungen können behobene Befunde schließen.
    </p>
    <RequestState :loading="loading" :error="error" @retry="load()" />
    <template v-if="data">
      <ResultSummary
        :total="data.pagination.total"
        :visible="data.items.length"
        noun="Prüfläufe"
        description="Gespeicherte Historie · unabhängig vom Dashboard-Zeitraum"
      />
      <ul v-if="data.items.length" class="data-list divide-y divide-slate-100" :aria-busy="loading">
        <li v-for="item in data.items" :key="item.id" class="data-row">
          <div class="flex flex-wrap items-center justify-between gap-2">
            <h3 class="text-sm font-semibold">Start: {{ dateTime(item.started_at) }}</h3>
            <StatusBadge
              :label="
                { running: 'Läuft', success: 'Erfolgreich', failed: 'Fehlgeschlagen' }[item.status]
              "
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
      </ul>
      <EmptyState v-else message="Noch keine gespeicherten Prüfläufe." />
      <PaginationBar :pagination="data.pagination" :loading="loading || running" @change="load" />
    </template>
  </section>
</template>
