<script setup lang="ts">
const emit = defineEmits<{ changed: [] }>()
const config = useRuntimeConfig()
const { $adminApi } = useNuxtApp()
const token = ref('')
const entered = ref(false)
const enabled = import.meta.dev && String(config.public.allowDevTokenEntry) === 'true'
function apply() {
  $adminApi.setCredential(token.value)
  token.value = ''
  entered.value = true
  emit('changed')
}
function clear() {
  $adminApi.clearCredential()
  token.value = ''
  entered.value = false
  emit('changed')
}
</script>

<template>
  <details v-if="enabled" class="rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm">
    <summary class="font-semibold text-slate-700">Lokaler Entwicklungszugang</summary>
    <p class="my-3 text-slate-600">
      Manuell bereitgestellten Development-Token verwenden. Die API prüft jeden Aufruf. Nach einem
      Neuladen muss der Token erneut eingegeben werden.
    </p>
    <form class="flex flex-wrap items-end gap-3" @submit.prevent="apply">
      <div class="min-w-0 flex-1">
        <label for="dev-token" class="label">Development-Token</label
        ><input
          id="dev-token"
          v-model="token"
          class="input"
          type="password"
          autocomplete="off"
          required
          maxlength="8192"
        />
      </div>
      <button class="button-primary" type="submit">Zugang verwenden</button>
      <button v-if="entered" class="button" type="button" @click="clear">Zugang entfernen</button>
    </form>
    <p v-if="entered" class="mt-2 text-slate-500" role="status">
      Zugang nur für diese geöffnete Seite gesetzt; Berechtigung wird beim Abruf geprüft.
    </p>
  </details>
</template>
