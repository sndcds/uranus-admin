<script setup lang="ts">
import type { z } from 'zod'
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
  <section class="space-y-5">
    <h2 class="text-2xl font-bold">Prüfläufe</h2>
    <p class="muted">
      Ein Prüflauf speichert Befunde. Nur erfolgreiche Prüfungen können behobene Befunde schließen.
    </p>
    <button class="button-primary" :disabled="running || loading" @click="run">
      {{ running ? 'Prüfung läuft …' : 'Prüflauf starten' }}
    </button>
    <RequestState :loading="loading" :error="error" @retry="load()" />
    <template v-if="data">
      <article v-for="item in data.items" :key="item.id" class="card p-5">
        <h3 class="font-bold">{{ dateTime(item.started_at) }} · {{ item.status }}</h3>
        <p>
          {{ item.rule_count }} Regeln · {{ item.finding_count }} Befunde · Ende:
          {{ dateTime(item.finished_at) }}
        </p>
        <p v-if="item.status === 'failed'">
          Prüfung fehlgeschlagen. Daraus wurde keine automatische Behebung abgeleitet.
        </p>
      </article>
      <p v-if="!data.items.length">Noch keine gespeicherten Prüfläufe.</p>
      <div class="flex gap-3">
        <button
          v-if="data.pagination.page > 1"
          class="button"
          @click="load(data.pagination.page - 1)"
        >
          Zurück
        </button>
        <button
          v-if="data.pagination.page < data.pagination.pages"
          class="button"
          @click="load(data.pagination.page + 1)"
        >
          Weiter
        </button>
      </div>
    </template>
    <NuxtLink class="button" to="/findings?mode=persisted">Gespeicherte Befunde</NuxtLink>
  </section>
</template>
