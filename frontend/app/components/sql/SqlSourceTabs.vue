<script setup lang="ts">
import { nextTick, ref, useId } from 'vue'
const props = defineProps<{ sources: { id: string; title: string }[] }>()
const selected = defineModel<string>({ required: true })
const tabs = ref<HTMLDivElement | null>(null)
const prefix = useId()
async function navigate(event: KeyboardEvent, index: number) {
  const last = props.sources.length - 1
  const target =
    event.key === 'ArrowRight'
      ? (index + 1) % props.sources.length
      : event.key === 'ArrowLeft'
        ? (index + last) % props.sources.length
        : event.key === 'Home'
          ? 0
          : event.key === 'End'
            ? last
            : null
  if (target === null) return
  event.preventDefault()
  selected.value = props.sources[target]!.id
  await nextTick()
  tabs.value?.querySelectorAll<HTMLButtonElement>('button')[target]?.focus()
}
</script>
<template>
  <div>
    <div
      ref="tabs"
      class="flex gap-1 overflow-x-auto border-b border-slate-200"
      role="tablist"
      aria-label="Query-Quelle"
    >
      <button
        v-for="(source, index) in sources"
        :id="`${prefix}-tab-${index}`"
        :key="source.id"
        role="tab"
        :aria-selected="selected === source.id"
        :aria-controls="`${prefix}-panel`"
        :tabindex="selected === source.id ? 0 : -1"
        class="shrink-0 border-b-2 px-3 py-2 text-xs font-medium"
        :class="
          selected === source.id
            ? 'border-fuchsia-600 bg-fuchsia-50 text-fuchsia-700'
            : 'border-transparent text-slate-600'
        "
        @click="selected = source.id"
        @keydown="navigate($event, index)"
      >
        {{ source.title }}
      </button>
    </div>
    <div
      :id="`${prefix}-panel`"
      role="tabpanel"
      :aria-labelledby="`${prefix}-tab-${sources.findIndex((source) => source.id === selected)}`"
      class="pt-4"
    >
      <slot />
    </div>
  </div>
</template>
