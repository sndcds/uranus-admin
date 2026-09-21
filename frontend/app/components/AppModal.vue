<script setup lang="ts">
import { nextTick, onBeforeUnmount, ref, useId } from 'vue'
const props = withDefaults(
  defineProps<{
    closeBlocked?: boolean
    title: string
    closeLabel?: string
    wide?: boolean
    workspace?: boolean
    subtitle?: string
  }>(),
  {
    closeLabel: 'Schließen',
    wide: false,
    workspace: false,
    subtitle: '',
  },
)
const emit = defineEmits<{ close: []; 'close-blocked': [] }>()
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
  if (props.closeBlocked) {
    emit('close-blocked')
    return
  }
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
    class="fixed inset-0 m-auto overflow-y-auto rounded-2xl border-0 bg-white shadow-soft backdrop:bg-slate-900/40"
    :class="[
      wide ? 'max-w-5xl' : 'max-w-xl',
      workspace
        ? 'w-[calc(100vw-2rem)] max-h-[calc(100dvh-2rem)] p-0'
        : 'w-[calc(100%-2rem)] max-h-[90dvh] p-6',
    ]"
    @cancel.prevent="close"
    @close="close"
  >
    <template v-if="opened">
      <div
        class="flex justify-between gap-4"
        :class="
          workspace ? 'items-center border-b border-slate-200 px-4 py-4 sm:px-5' : 'items-start'
        "
      >
        <div class="flex min-w-0 flex-wrap items-center gap-3">
          <slot name="icon" />
          <div class="min-w-0">
            <h2 :id="titleId" class="min-w-0 break-words text-xl font-bold">{{ title }}</h2>
            <p v-if="subtitle" class="text-xs text-slate-500 sm:text-sm">{{ subtitle }}</p>
          </div>
          <slot name="badge" />
        </div>
        <div class="flex shrink-0 items-center gap-3">
          <slot name="actions" />
          <button
            type="button"
            class="shrink-0 rounded-lg p-2"
            :aria-label="closeLabel"
            @click="close"
          >
            <AppIcon name="close" />
          </button>
        </div>
      </div>
      <slot />
    </template>
  </dialog>
</template>
