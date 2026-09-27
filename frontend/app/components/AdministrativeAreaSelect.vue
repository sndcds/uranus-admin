<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, useId, watch } from 'vue'
import type { ResearchArea } from '#shared/contracts'
import { asFailure } from '#shared/errors'
import { researchAreaLabel } from '~/utils/research'

const props = withDefaults(
  defineProps<{
    modelValue?: string
    label?: string
    workspace?: 'research' | 'operations'
    dossierLink?: boolean
  }>(),
  { modelValue: undefined, label: 'Gemeinde / Kommune', workspace: 'research', dossierLink: false },
)
const emit = defineEmits<{
  'update:modelValue': [value: string | undefined]
  select: [area: ResearchArea]
  close: []
}>()
const { $adminApi } = useNuxtApp()
const auth = useAuthStore()
const id = useId()
const resultsId = `${id}-results`
const term = ref('')
const items = ref<ResearchArea[]>([])
const selected = ref<ResearchArea | null>(null)
const loading = ref(false)
const error = ref('')
const selectionError = ref('')
const active = ref(-1)
const open = ref(false)
watch(active, async (index) => {
  if (index < 0) return
  await nextTick()
  document.getElementById(`${id}-${index}`)?.scrollIntoView?.({ block: 'nearest' })
})
let timer: ReturnType<typeof setTimeout> | undefined
let controller: AbortController | undefined
let selectionController: AbortController | undefined
let generation = 0
let selectionGeneration = 0
function cancelSearch() {
  generation++
  clearTimeout(timer)
  controller?.abort()
  loading.value = false
  items.value = []
  active.value = -1
  error.value = ''
}
function close() {
  cancelSearch()
  open.value = false
  emit('close')
}
watch(term, (value) => {
  cancelSearch()
  open.value = value.trim().length >= 2
  if (!open.value || !auth.canResearch) return
  const current = generation
  controller = new AbortController()
  const signal = controller.signal
  loading.value = true
  timer = setTimeout(async () => {
    try {
      const page = await $adminApi.researchAreas({ q: value.trim(), page_size: 10 }, signal)
      if (current === generation) items.value = page.items
    } catch (cause) {
      if (current === generation) error.value = asFailure(cause).message
    } finally {
      if (current === generation) loading.value = false
    }
  }, 300)
})
async function hydrate(value?: string) {
  const current = ++selectionGeneration
  selectionController?.abort()
  selected.value = null
  selectionError.value = ''
  if (!value || !auth.canResearch) return
  selectionController = new AbortController()
  try {
    const area = await $adminApi.researchAreaMetadata(value, selectionController.signal)
    if (current === selectionGeneration) selected.value = area
  } catch (cause) {
    if (current === selectionGeneration) selectionError.value = asFailure(cause).message
  }
}
watch(() => props.modelValue, hydrate)
onMounted(() => void hydrate(props.modelValue))
watch(
  () => auth.revision,
  () => {
    cancelSearch()
    selectionGeneration++
    selectionController?.abort()
    selected.value = null
    selectionError.value = ''
    term.value = ''
    open.value = false
  },
)
function choose(area: ResearchArea) {
  if (!auth.canResearch) return
  cancelSearch()
  term.value = ''
  open.value = false
  selected.value = area
  emit('update:modelValue', area.id)
  emit('select', area)
}
function clear() {
  close()
  term.value = ''
  selectionGeneration++
  selectionController?.abort()
  selected.value = null
  selectionError.value = ''
  emit('update:modelValue', undefined)
}
function keydown(event: KeyboardEvent) {
  if (event.isComposing) return
  if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
    event.preventDefault()
    if (!items.value.length) return
    open.value = true
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
    if (open.value && item) choose(item)
  } else if (event.key === 'Escape') {
    event.preventDefault()
    close()
  }
}
onBeforeUnmount(() => {
  cancelSearch()
  selectionGeneration++
  selectionController?.abort()
})
defineExpose({
  reset() {
    cancelSearch()
    term.value = ''
    open.value = false
  },
})
</script>
<template>
  <div class="min-w-0">
    <label :for="id" class="label">{{ label }}</label>
    <input
      :id="id"
      v-model="term"
      class="input mt-1 w-full"
      type="search"
      maxlength="120"
      autocomplete="off"
      :autofocus="workspace === 'operations'"
      placeholder="Ab zwei Zeichen suchen …"
      role="combobox"
      aria-autocomplete="list"
      :aria-controls="resultsId"
      :aria-expanded="open"
      :aria-activedescendant="open && active >= 0 ? `${id}-${active}` : undefined"
      @keydown="keydown"
    />
    <div v-if="modelValue" class="flex flex-wrap gap-2 text-sm">
      <NuxtLink v-if="dossierLink" :to="`/research/areas/${modelValue}`" class="action-link">
        {{ selected?.name || 'Ausgewähltes Gebiet' }}
      </NuxtLink>
      <span v-else>{{ selected?.name || 'Ausgewähltes Gebiet' }}</span>
      <button type="button" class="action-link" @click="clear">Gebiet entfernen</button>
    </div>
    <p v-if="loading" role="status" class="muted">Gebiete werden gesucht …</p>
    <p v-if="error || selectionError" role="alert" class="text-sm text-red-700">
      {{ error || selectionError }}
    </p>
    <p v-else-if="open && !loading && !items.length" role="status" class="muted">
      Keine importierten Gemeinden / Kommunen gefunden.
    </p>
    <ul
      v-show="open"
      :id="resultsId"
      role="listbox"
      aria-label="Gemeinden / Kommunen"
      :aria-busy="loading"
      class="mt-1 max-h-72 overflow-auto"
    >
      <li
        v-for="(item, index) in items"
        :id="`${id}-${index}`"
        :key="item.id"
        role="option"
        :aria-selected="index === active"
      >
        <button
          type="button"
          tabindex="-1"
          class="w-full rounded-lg p-3 text-left"
          :class="
            workspace === 'research'
              ? ['hover:bg-blue-50', { 'bg-blue-50': index === active }]
              : ['hover:bg-fuchsia-50', { 'bg-fuchsia-50': index === active }]
          "
          @click="choose(item)"
        >
          <span class="block break-words font-semibold">{{ item.name }}</span>
          <span class="block break-words text-sm text-slate-600">{{
            researchAreaLabel(item)
          }}</span>
        </button>
      </li>
    </ul>
  </div>
</template>
