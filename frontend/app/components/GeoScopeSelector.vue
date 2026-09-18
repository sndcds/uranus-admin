<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, useId, watch } from 'vue'
import type { GeoAreaSearchItem } from '#shared/contracts'
import { asFailure } from '#shared/errors'
import AppModal from './AppModal.vue'
import { geoAreaLabel, supportsGeoScope } from '~/utils/geo'
import { useFilterPreferencesStore } from '~/stores/filter-preferences'

const preferences = useFilterPreferencesStore()
const auth = useAuthStore()
const route = useRoute()
const router = useRouter()
const { $adminApi } = useNuxtApp()
const modal = ref<InstanceType<typeof AppModal> | null>(null)
const query = ref('')
const items = ref<GeoAreaSearchItem[]>([])
const loading = ref(false)
const importing = ref(false)
const interactive = ref(false)
onMounted(() => {
  interactive.value = true
})
const error = ref('')
const active = ref(-1)
const id = useId()
const resultsId = `${id}-results`
const selected = computed(() => preferences.sharedGeoScope)
let timer: ReturnType<typeof setTimeout> | undefined
let controller: AbortController | undefined
let generation = 0
function cancel() {
  generation++
  clearTimeout(timer)
  controller?.abort()
  loading.value = false
}
function close() {
  cancel()
  query.value = ''
  items.value = []
  active.value = -1
}
watch(query, () => {
  cancel()
  items.value = []
  active.value = -1
  error.value = ''
  if (query.value.trim().length < 2) return
  loading.value = true
  const current = generation
  controller = new AbortController()
  const signal = controller.signal
  timer = setTimeout(async () => {
    try {
      const result = await $adminApi.searchGeoAreas(query.value.trim(), signal)
      if (current === generation)
        items.value = result.items.filter((item) => item.eligible_for_scope)
    } catch (cause) {
      if (current === generation) error.value = asFailure(cause).message
    } finally {
      if (current === generation) loading.value = false
    }
  }, 300)
})
async function apply(item: GeoAreaSearchItem) {
  if (importing.value) return
  importing.value = true
  error.value = ''
  const revision = auth.revision
  try {
    const area = await $adminApi.importGeoArea({
      source: item.provider,
      source_type: item.osm_type,
      source_id: item.osm_id,
    })
    if (!auth.isAdmin || auth.revision !== revision) return
    preferences.setGeoScope(area)
    if (supportsGeoScope(route.path))
      await router.push({
        query: { ...route.query, geo_scope_id: area.id, page: '1' },
        hash: route.hash,
      })
    modal.value?.close()
  } catch (cause) {
    error.value = asFailure(cause).message
  } finally {
    importing.value = false
  }
}
async function clear() {
  preferences.setGeoScope(null)
  const next = { ...route.query }
  delete next.geo_scope_id
  if (supportsGeoScope(route.path)) next.page = '1'
  await router.push({ query: next, hash: route.hash })
}
function keydown(event: KeyboardEvent) {
  if (event.isComposing || importing.value) return
  if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
    event.preventDefault()
    if (items.value.length)
      active.value =
        active.value < 0
          ? event.key === 'ArrowDown'
            ? 0
            : items.value.length - 1
          : (active.value + (event.key === 'ArrowDown' ? 1 : -1) + items.value.length) %
            items.value.length
  } else if (event.key === 'Enter') {
    event.preventDefault()
    const item = items.value[active.value]
    if (item) void apply(item)
  } else if (event.key === 'Escape') {
    event.preventDefault()
    modal.value?.close()
  }
}
onBeforeUnmount(cancel)
</script>
<template>
  <div class="flex min-w-0 max-w-full flex-wrap items-center gap-2">
    <button
      type="button"
      class="button max-w-full min-w-0"
      :disabled="!interactive"
      :title="selected ? geoAreaLabel(selected) : 'Gebiet auswählen'"
      @click="modal?.open()"
    >
      <span class="max-w-60 truncate">Gebiet: {{ selected?.name ?? 'Alle' }}</span>
      <span class="sr-only"> – Gebiet auswählen</span>
    </button>
    <button
      v-if="selected"
      type="button"
      class="button"
      aria-label="Gebiet zurücksetzen"
      :disabled="!interactive"
      @click="clear"
    >
      ×
    </button>
    <AppModal ref="modal" title="Gebiet auswählen" @close="close">
      <div class="mt-4 space-y-3">
        <label :for="id" class="label">Administratives Gebiet suchen</label>
        <input
          :id="id"
          v-model="query"
          autofocus
          class="input w-full"
          type="search"
          maxlength="120"
          autocomplete="off"
          placeholder="z. B. Flensburg oder Aarhus Kommune"
          role="combobox"
          aria-autocomplete="list"
          :aria-controls="resultsId"
          :aria-expanded="query.trim().length >= 2"
          :aria-activedescendant="active >= 0 ? `${id}-${active}` : undefined"
          :disabled="importing"
          @keydown="keydown"
        />
        <p v-if="loading || importing" role="status" class="muted">
          {{ importing ? 'Gebiet wird gespeichert …' : 'Gebiete werden gesucht …' }}
        </p>
        <p v-if="error" role="alert" class="text-sm text-red-700">{{ error }}</p>
        <p
          v-else-if="query.trim().length >= 2 && !loading && !items.length"
          role="status"
          class="muted"
        >
          Keine passenden Gebiete gefunden.
        </p>
        <ul
          :id="resultsId"
          role="listbox"
          aria-label="Gebiete"
          :aria-busy="loading || importing"
          class="max-h-72 overflow-auto"
        >
          <li
            v-for="(item, index) in items"
            :id="`${id}-${index}`"
            :key="item.osm_id"
            role="option"
            :aria-selected="index === active"
          >
            <button
              type="button"
              class="w-full rounded-lg p-3 text-left hover:bg-fuchsia-50"
              :class="{ 'bg-fuchsia-50': index === active }"
              :disabled="importing"
              @click="apply(item)"
            >
              <span class="block break-words font-semibold">{{ item.name }}</span>
              <span class="block break-words text-sm text-slate-600">{{ geoAreaLabel(item) }}</span>
            </button>
          </li>
        </ul>
        <p class="text-xs text-slate-500">
          Grenzen: OpenStreetMap. Die Suchabdeckung hängt vom Datenbestand des eingerichteten
          Dienstes ab.
        </p>
      </div>
    </AppModal>
  </div>
</template>
