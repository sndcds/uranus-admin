<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, useId, watch } from 'vue'
import type {
  EntitySearchItem,
  EntitySearchType,
  TemporalFilter,
  SharedPeriod,
} from '#shared/contracts'
import { supportsGeoEntity } from '~/utils/geo'
import { entityTypes } from '~/utils/entityPresentation'
import { entitySearchPlaceholders, supportsTemporal } from '~/utils/entities'

const query = defineModel<string>({ required: true })
const props = defineProps<{
  geoScopeId?: string
  entityType: EntitySearchType
  organizationId?: string
  status?: string
  temporal?: TemporalFilter | ''
  period?: SharedPeriod | ''
}>()
const emit = defineEmits<{ apply: []; select: [item: EntitySearchItem] }>()
const { $adminApi } = useNuxtApp()
const root = ref<HTMLElement | null>(null)
const id = useId()
const resultsId = `${id}-results`
const results = ref<EntitySearchItem[]>([])
const open = ref(false)
const focused = ref(false)
const loading = ref(false)
const error = ref(false)
const active = ref(-1)
const visible = computed(() => open.value && query.value.trim().length >= 2)
let generation = 0
let timer: ReturnType<typeof setTimeout> | undefined

function cancel() {
  generation++
  clearTimeout(timer)
  loading.value = false
}
function close() {
  cancel()
  open.value = false
  active.value = -1
}
function focus() {
  focused.value = true
  schedule()
}
function schedule() {
  cancel()
  results.value = []
  active.value = -1
  error.value = false
  open.value = focused.value && query.value.trim().length >= 2
  if (!open.value) return
  loading.value = true
  const request = generation
  const params = {
    q: query.value.trim(),
    ...(supportsGeoEntity(props.entityType) && props.geoScopeId
      ? { geo_scope_id: props.geoScopeId }
      : {}),
    period: props.period || undefined,
    entity_type: props.entityType,
    organization_id: props.organizationId || undefined,
    status: props.status || undefined,
    temporal: supportsTemporal(props.entityType) ? props.temporal || undefined : undefined,
    limit: 10,
  }
  timer = setTimeout(async () => {
    try {
      const data = await $adminApi.entitySearch(params)
      if (request === generation) results.value = data.items
    } catch {
      if (request === generation) error.value = true
    } finally {
      if (request === generation) loading.value = false
    }
  }, 275)
}
watch(
  [
    query,
    () => props.entityType,
    () => props.organizationId,
    () => props.status,
    () => props.temporal,
    () => props.period,
    () => props.geoScopeId,
  ],
  schedule,
)
function select(item: EntitySearchItem) {
  close()
  emit('select', item)
}
function keydown(event: KeyboardEvent) {
  if (event.isComposing) return
  if (event.key === 'Escape') {
    event.preventDefault()
    event.stopPropagation()
    query.value = ''
    close()
  } else if (event.key === 'Enter') {
    event.preventDefault()
    const item = visible.value ? results.value[active.value] : undefined
    if (item) select(item)
    else {
      close()
      emit('apply')
    }
  } else if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
    event.preventDefault()
    if (!visible.value) {
      schedule()
      return
    }
    if (!results.value.length) return
    const direction = event.key === 'ArrowDown' ? 1 : -1
    active.value =
      active.value < 0
        ? direction === 1
          ? 0
          : results.value.length - 1
        : (active.value + direction + results.value.length) % results.value.length
    void nextTick(() => {
      root.value?.querySelector('[aria-selected="true"]')?.scrollIntoView?.({ block: 'nearest' })
    })
  }
}
function outside(event: PointerEvent) {
  if (!root.value?.contains(event.target as Node)) close()
}
function blur(event: FocusEvent) {
  if (!root.value?.contains(event.relatedTarget as Node | null)) {
    focused.value = false
    close()
  }
}
onMounted(() => document.addEventListener('pointerdown', outside))
onBeforeUnmount(() => {
  cancel()
  document.removeEventListener('pointerdown', outside)
})
</script>
<template>
  <div ref="root" class="min-w-0 sm:col-span-2 xl:col-span-1" @focusout="blur">
    <label :for="id" class="label">Suche</label>
    <div class="relative min-w-0">
      <AppIcon
        name="search"
        :size="16"
        class="pointer-events-none absolute left-3 top-3 text-slate-400"
      />
      <input
        :id="id"
        v-model="query"
        type="search"
        class="input w-full pl-9"
        :placeholder="entitySearchPlaceholders[entityType]"
        maxlength="200"
        autocomplete="off"
        role="combobox"
        aria-autocomplete="list"
        :aria-expanded="visible"
        :aria-controls="resultsId"
        :aria-activedescendant="visible && active >= 0 ? `${id}-option-${active}` : undefined"
        @focus="focus"
        @keydown="keydown"
      />
      <div
        v-if="visible"
        class="absolute left-0 top-full z-20 mt-2 max-h-80 w-full min-w-0 overflow-auto rounded-xl border border-slate-200 bg-white p-1 shadow-lg"
      >
        <p v-if="loading" class="p-3 text-xs text-slate-500" role="status">Suche läuft …</p>
        <p v-else-if="error" class="p-3 text-xs text-slate-500" role="status">
          Suche konnte nicht geladen werden.
        </p>
        <p v-else-if="!results.length" class="p-3 text-xs text-slate-500" role="status">
          Keine passenden Datensätze gefunden.
        </p>
        <ul :id="resultsId" role="listbox" aria-label="Suchergebnisse" :aria-busy="loading">
          <li
            v-for="(item, index) in results"
            :id="`${id}-option-${index}`"
            :key="item.entity_key"
            role="option"
            :aria-selected="active === index"
            class="flex w-full cursor-pointer items-center gap-3 rounded-lg p-3 text-left hover:bg-fuchsia-50"
            :class="{ 'bg-fuchsia-50': active === index }"
            @pointerdown.prevent
            @click="select(item)"
          >
            <AppIcon
              :name="entityTypes[item.entity_type].icon"
              :style="{ color: entityTypes[item.entity_type].color }"
              class="shrink-0"
            />
            <span class="min-w-0">
              <span class="block truncate text-sm font-medium">{{ item.label }}</span>
              <span v-if="item.subtitle" class="block break-words text-xs text-slate-500">{{
                item.subtitle
              }}</span>
              <span class="block text-xs text-slate-500">{{
                entityTypes[item.entity_type].label
              }}</span>
            </span>
          </li>
        </ul>
      </div>
    </div>
  </div>
</template>
