<script setup lang="ts">
import { onBeforeUnmount, onDeactivated, ref, watch } from 'vue'
import AppIcon from './AppIcon.vue'

const props = withDefaults(
  defineProps<{
    value: string | null
    label: string
    buttonText?: string
    variant?: 'action' | 'button'
    disabled?: boolean
    successMessage?: string
    errorMessage?: string
    formatValue?: (value: string) => string | Promise<string>
    resetKey?: string | number
  }>(),
  {
    buttonText: 'Kopieren',
    variant: 'action',
    successMessage: 'Kopiert.',
    errorMessage: 'Kopieren nicht verfügbar. Der Wert kann als Text ausgewählt werden.',
  },
)
const feedback = ref('')
let revision = 0
let timer: ReturnType<typeof setTimeout> | undefined
let formattedValue: Promise<string> | null = null
function reset() {
  revision++
  feedback.value = ''
  clearTimeout(timer)
  formattedValue = null
}
watch(() => [props.value, props.label, props.disabled, props.formatValue, props.resetKey], reset, {
  flush: 'sync',
})
onBeforeUnmount(reset)
onDeactivated(reset)
async function copy() {
  if (props.disabled || props.value === null) return
  const current = ++revision
  feedback.value = ''
  clearTimeout(timer)
  try {
    let text = props.value
    if (props.formatValue) {
      formattedValue ??= Promise.resolve(props.formatValue(text))
      text = await formattedValue
      if (current !== revision) return
    }
    await navigator.clipboard.writeText(text)
    if (current === revision) feedback.value = props.successMessage
  } catch {
    if (current === revision) feedback.value = props.errorMessage
  }
  if (current === revision) {
    timer = setTimeout(() => {
      feedback.value = ''
    }, 2500)
  }
}
</script>

<template>
  <span class="inline-flex min-w-0 flex-wrap items-center gap-x-2">
    <button
      type="button"
      class="shrink-0"
      :class="variant === 'button' ? 'button' : 'action-link text-xs'"
      :aria-label="`${label} kopieren`"
      :disabled="disabled || value === null"
      @click="copy"
    >
      <AppIcon name="copy" :size="14" />{{ buttonText }}
    </button>
    <span role="status" class="text-xs text-slate-600" :class="feedback ? '' : 'sr-only'">{{
      feedback
    }}</span>
  </span>
</template>
