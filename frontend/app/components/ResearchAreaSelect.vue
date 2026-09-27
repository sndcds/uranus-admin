<script setup lang="ts">
import { researchRegionLabels } from '~/utils/research'
import type { ResearchArea } from '#shared/contracts'
const props = defineProps<{ modelValue?: string }>()
const emit = defineEmits<{ 'update:modelValue': [value: string | undefined] }>()
const { $adminApi } = useNuxtApp()
const auth = useAuthStore()
const term = ref('')
const selected = ref<ResearchArea | null>(null)
const items = ref<ResearchArea[]>([])
const message = ref('')
const id = useId()
let timer: ReturnType<typeof setTimeout> | undefined
let generation = 0
let selectionGeneration = 0
let controller: AbortController | undefined
const countries = { DE: 'Deutschland', DK: 'Dänemark' }
function clear() {
  generation++
  clearTimeout(timer)
  controller?.abort()
  items.value = []
  message.value = ''
}
watch(term, (q) => {
  clear()
  const current = generation
  if (q.trim().length < 2) return
  timer = setTimeout(async () => {
    controller = new AbortController()
    try {
      const result = await $adminApi.researchAreas({ q, page_size: 10 }, controller.signal)
      if (current !== generation) return
      items.value = result.items
      if (!items.value.length) message.value = 'Keine importierten Gemeinden / Kommunen gefunden.'
    } catch {
      if (current === generation) message.value = 'Gebiete konnten nicht geladen werden.'
    }
  }, 300)
})
async function loadSelection(value?: string) {
  const current = ++selectionGeneration
  selected.value = null
  if (!value) return
  try {
    const result = await $adminApi.researchAreas({ q: value, page_size: 1 })
    if (current === selectionGeneration)
      selected.value = result.items.find((item) => item.id === value) || null
  } catch {
    if (current === selectionGeneration) message.value = 'Ausgewähltes Gebiet nicht verfügbar.'
  }
}
watch(() => props.modelValue, loadSelection)
onMounted(() => void loadSelection(props.modelValue))
watch(
  () => auth.session,
  () => {
    clear()
    selectionGeneration++
    selected.value = null
  },
)
function choose(item: ResearchArea) {
  clear()
  term.value = ''
  emit('update:modelValue', item.id)
}
onBeforeUnmount(() => {
  clear()
  selectionGeneration++
})
</script>
<template>
  <div class="min-w-0">
    <label :for="id" class="label">Gemeinde / Kommune</label>
    <input
      :id="id"
      v-model="term"
      class="input mt-1"
      type="search"
      maxlength="120"
      autocomplete="off"
      placeholder="Ab zwei Zeichen suchen …"
    />
    <div v-if="modelValue" class="flex flex-wrap gap-2 text-sm">
      <NuxtLink :to="`/research/areas/${modelValue}`" class="action-link">
        {{ selected?.name || 'Ausgewähltes Gebiet' }}
      </NuxtLink>
      <button type="button" class="action-link" @click="emit('update:modelValue', undefined)">
        Gebiet entfernen
      </button>
    </div>
    <ul
      v-if="items.length"
      class="panel mt-1 max-h-60 overflow-y-auto p-1"
      aria-label="Gemeinden / Kommunen"
    >
      <li v-for="item in items" :key="item.id">
        <button
          type="button"
          class="button w-full flex-col items-start text-left"
          @click="choose(item)"
        >
          {{ item.name
          }}<span class="font-normal text-sm"
            >{{ countries[item.country_code] }} · {{ researchRegionLabels[item.region_code] }}</span
          >
        </button>
      </li>
    </ul>
    <p v-if="message" role="status" class="type-metadata">{{ message }}</p>
  </div>
</template>
