<script setup lang="ts">
import { computed, nextTick, onMounted, useTemplateRef, watch } from 'vue'

const question = defineModel<string>({ required: true })
const props = defineProps<{
  disabled: boolean
  busy: boolean
  invalid: boolean
  expanded: boolean
  activeSuggestion: number
}>()
const emit = defineEmits<{
  submit: []
  keydown: [event: KeyboardEvent]
  input: []
  focus: []
  blur: []
}>()
const input = useTemplateRef('input')
const canSubmit = computed(() => !props.disabled && !props.busy && !!question.value.trim())
function resize() {
  const element = input.value
  if (!element) return
  element.style.height = 'auto'
  element.style.height = `${element.scrollHeight}px`
}
watch(question, async () => {
  await nextTick()
  resize()
})
onMounted(resize)
function submit() {
  if (canSubmit.value) emit('submit')
}
function keydown(event: KeyboardEvent) {
  if (event.isComposing || event.keyCode === 229) return
  // The owner handles listbox navigation first; selection consumes Enter.
  emit('keydown', event)
  if (event.defaultPrevented) return
  if (event.key === 'Enter' && (!event.shiftKey || event.ctrlKey || event.metaKey)) {
    event.preventDefault()
    submit()
  }
}
defineExpose({ focus: () => input.value?.focus() })
</script>

<template>
  <form
    class="research-composer relative rounded-2xl border border-slate-200 bg-white"
    :aria-busy="busy"
    @submit.prevent="submit"
  >
    <label for="research-question" class="sr-only">Deine Recherchefrage</label>
    <textarea
      id="research-question"
      ref="input"
      v-model="question"
      class="research-composer-input block w-full resize-none border-0 bg-transparent text-base leading-6 text-slate-900 placeholder:text-slate-500"
      rows="1"
      maxlength="2000"
      required
      placeholder="Stelle eine Frage zu Kultur in deiner Region …"
      role="combobox"
      aria-autocomplete="list"
      aria-controls="research-suggestion-list"
      :aria-expanded="expanded"
      :aria-activedescendant="
        activeSuggestion >= 0 ? `research-suggestion-${activeSuggestion}` : undefined
      "
      :disabled="disabled"
      :aria-invalid="invalid"
      :aria-describedby="
        invalid ? 'research-question-help research-question-error' : 'research-question-help'
      "
      @input="emit('input')"
      @focus="emit('focus')"
      @blur="emit('blur')"
      @keydown="keydown"
    />
    <div
      class="research-composer-count text-right text-xs tabular-nums text-slate-500"
      aria-hidden="true"
    >
      {{ question.length.toLocaleString('de-DE') }}/2.000
    </div>
    <button
      type="submit"
      class="research-send absolute bottom-4 right-4 inline-flex h-12 w-12 items-center justify-center rounded-xl bg-blue-700 text-white shadow-soft hover:bg-blue-800 disabled:cursor-not-allowed"
      :disabled="!canSubmit"
      :aria-busy="busy"
      aria-label="Antwort anzeigen"
    >
      <AppIcon :name="busy ? 'refresh' : 'send'" :size="20" />
      <span class="sr-only">{{ busy ? 'Wird ausgewertet …' : 'Antwort anzeigen' }}</span>
    </button>
  </form>
</template>

<style scoped>
@reference '../assets/css/main.css';
.research-composer {
  padding: 12px 84px 12px 16px;
  box-shadow: 0 4px 16px color-mix(in srgb, var(--color-blue-200) 22%, transparent);
}
.research-composer-input {
  min-height: 32px;
  max-height: min(12rem, 25dvh);
  overflow-y: auto;
  padding: 0;
}
.research-composer-input:focus-visible {
  outline: 1px solid var(--color-blue-300);
  outline-offset: 2px;
  border-radius: 4px;
}
.research-composer-count {
  height: 20px;
  line-height: 20px;
  margin-top: 4px;
}
.research-composer:focus-within {
  @apply border-blue-300;
}
</style>
