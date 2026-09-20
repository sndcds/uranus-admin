<script setup lang="ts">
import { nextTick, onBeforeUnmount, ref, useId } from 'vue'
withDefaults(defineProps<{ title: string; closeLabel?: string; wide?: boolean }>(), {
  closeLabel: 'Schließen',
  wide: false,
})
const emit = defineEmits<{ close: [] }>()
const titleId = useId()
const dialog = ref<HTMLDialogElement | null>(null)
const opened = ref(false)
let trigger: HTMLElement | null = null
async function open() {
  if (opened.value) return
  trigger = document.activeElement instanceof HTMLElement ? document.activeElement : null
  opened.value = true
  await nextTick()
  if (opened.value) dialog.value?.showModal()
}
function close() {
  if (!opened.value) return
  opened.value = false
  dialog.value?.close()
  if (trigger?.isConnected) trigger.focus()
  trigger = null
  emit('close')
}
onBeforeUnmount(close)
defineExpose({ open, close })
</script>

<template>
  <dialog
    ref="dialog"
    aria-modal="true"
    :aria-labelledby="titleId"
    class="fixed inset-0 m-auto max-h-[90dvh] w-[calc(100%-2rem)] overflow-y-auto rounded-2xl border-0 bg-white p-6 shadow-soft backdrop:bg-slate-900/40"
    :class="wide ? 'max-w-5xl' : 'max-w-xl'"
    @cancel.prevent="close"
    @close="close"
  >
    <template v-if="opened">
      <div class="flex items-start justify-between gap-4">
        <div class="flex min-w-0 flex-wrap items-center gap-3">
          <h2 :id="titleId" class="min-w-0 break-words text-xl font-bold">{{ title }}</h2>
          <slot name="badge" />
        </div>
        <button
          type="button"
          class="shrink-0 rounded-lg p-2"
          :aria-label="closeLabel"
          @click="close"
        >
          <AppIcon name="close" />
        </button>
      </div>
      <slot />
    </template>
  </dialog>
</template>
