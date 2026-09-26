<script setup lang="ts">
import type { ResearchRecord } from '#shared/contracts'
const props = defineProps<{ kind: 'venue' | 'organization'; label: string; modelValue?: string }>()
const emit = defineEmits<{ 'update:modelValue': [value: string | undefined] }>()
const { $adminApi } = useNuxtApp()
const term = ref('')
const items = ref<ResearchRecord[]>([])
const message = ref('')
const id = useId()
let timer: ReturnType<typeof setTimeout> | undefined
let generation = 0
watch(term, (q) => {
  clearTimeout(timer)
  const current = ++generation
  items.value = []
  message.value = ''
  if (q.trim().length < 2) return
  timer = setTimeout(async () => {
    try {
      const result = await $adminApi.researchSearch({ q, entity_type: props.kind, page_size: 10 })
      if (current === generation) {
        items.value = result.items
        if (!result.items.length) message.value = 'Keine Treffer.'
      }
    } catch {
      if (current === generation) message.value = 'Auswahl konnte nicht geladen werden.'
    }
  }, 300)
})
function choose(item: ResearchRecord) {
  emit('update:modelValue', item.entity_key)
  term.value = ''
  items.value = []
}
onBeforeUnmount(() => {
  generation++
  clearTimeout(timer)
})
</script>
<template>
  <div class="min-w-0">
    <label :for="id" class="label">{{ label }}</label>
    <input
      :id="id"
      v-model="term"
      class="input"
      type="search"
      maxlength="120"
      :placeholder="modelValue ? 'Auswahl ändern …' : 'Ab zwei Zeichen suchen …'"
    />
    <button
      v-if="modelValue"
      type="button"
      class="action-link"
      @click="$emit('update:modelValue', undefined)"
    >
      {{ label }} ausgewählt · entfernen
    </button>
    <ul v-if="items.length" class="panel mt-1 max-h-52 overflow-y-auto p-1">
      <li v-for="item in items" :key="item.entity_key">
        <button type="button" class="button w-full justify-start text-left" @click="choose(item)">
          {{ item.name }}<span v-if="item.city" class="font-normal">· {{ item.city }}</span>
        </button>
      </li>
    </ul>
    <p v-if="message" role="status" class="type-metadata">{{ message }}</p>
  </div>
</template>
