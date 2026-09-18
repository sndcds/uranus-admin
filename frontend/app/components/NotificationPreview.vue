<script setup lang="ts">
import { ref, computed, watch, onBeforeUnmount } from 'vue'
import type { NotificationPreview } from '#shared/contracts'
import type { ApiFailure } from '#shared/errors'
import { asFailure } from '#shared/errors'
const props = defineProps<{ notificationId: string }>()
const { $adminApi } = useNuxtApp()
const locale = ref<'de' | 'da' | 'en'>('de')
const tab = ref<'html' | 'text'>('html')
const preview = ref<NotificationPreview | null>(null)
const error = ref<ApiFailure | null>(null)
const loading = ref(false)
let generation = 0
// A sandboxed, opaque-origin document with an additional restrictive CSP. Never v-html.
const document = computed(
  () =>
    preview.value?.html.replace(
      '<head>',
      '<head><meta http-equiv="Content-Security-Policy" content="default-src &apos;none&apos;; form-action &apos;none&apos;; base-uri &apos;none&apos;">',
    ) ?? '',
)
async function load() {
  const current = ++generation
  loading.value = true
  preview.value = null
  error.value = null
  try {
    const value = await $adminApi.notificationPreview(props.notificationId, locale.value)
    if (current === generation) preview.value = value
  } catch (cause) {
    if (current === generation) error.value = asFailure(cause)
  } finally {
    if (current === generation) loading.value = false
  }
}
watch([() => props.notificationId, locale], () => {
  if (preview.value || loading.value) void load()
})
onBeforeUnmount(() => {
  generation++
})
</script>
<template>
  <section class="space-y-3" aria-label="E-Mail-Vorschau">
    <h2 class="text-lg font-semibold">E-Mail-Vorschau</h2>
    <p class="muted">Vorschau des gespeicherten Hinweises. Es wird keine E-Mail gesendet.</p>
    <div class="flex flex-wrap gap-3 items-end">
      <label
        >Sprache<select v-model="locale" class="field">
          <option value="de">Deutsch</option>
          <option value="da">Dansk</option>
          <option value="en">English</option>
        </select></label
      >
      <button class="button" :disabled="loading" @click="load">Vorschau laden</button>
    </div>
    <RequestState :loading="loading" :error="error" @retry="load" />
    <template v-if="preview">
      <h3 class="font-semibold">{{ preview.subject }}</h3>
      <div class="flex gap-2" role="group" aria-label="Vorschauformat">
        <button class="button" :aria-pressed="tab === 'html'" @click="tab = 'html'">HTML</button>
        <button class="button" :aria-pressed="tab === 'text'" @click="tab = 'text'">Text</button>
      </div>
      <iframe
        v-if="tab === 'html'"
        title="HTML-E-Mail-Vorschau"
        sandbox=""
        referrerpolicy="no-referrer"
        :srcdoc="document"
        class="w-full h-96 border rounded-xl bg-white"
      />
      <pre
        v-else
        class="whitespace-pre-wrap break-words rounded-xl bg-white p-4"
        :lang="preview.locale"
        >{{ preview.text }}</pre>
    </template>
  </section>
</template>
