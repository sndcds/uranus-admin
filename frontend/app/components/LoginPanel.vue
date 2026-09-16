<script setup lang="ts">
import { ref, onMounted, watch, nextTick } from 'vue'
import type { AdminSession } from '#shared/contracts'
import { asFailure } from '#shared/errors'

defineProps<{ compact?: boolean }>()
const emit = defineEmits<{ changed: [] }>()
const { $adminApi } = useNuxtApp()
const revision = useState('admin-auth-status', () => 0)
const identity = ref<AdminSession | null>(null)
const login = ref('')
const password = ref('')
const busy = ref(false)
const ready = ref(false)
const message = ref('')

async function checkSession() {
  try {
    identity.value = await $adminApi.session()
  } catch {
    identity.value = null
  } finally {
    ready.value = true
  }
}
onMounted(checkSession)
watch(revision, (status) => {
  if (status === 401) identity.value = null
  if (status === 403 && identity.value) identity.value = { ...identity.value, system_admin: false }
})
async function signIn() {
  busy.value = true
  message.value = ''
  $adminApi.clearCredential()
  try {
    const session = await $adminApi.login(login.value, password.value)
    emit('changed')
    await nextTick()
    identity.value = session
    if (!session.system_admin) message.value = 'Angemeldet, aber ohne System-Admin-Berechtigung.'
  } catch (error) {
    message.value = asFailure(error).message
  } finally {
    password.value = ''
    busy.value = false
  }
}
async function signOut() {
  busy.value = true
  try {
    await $adminApi.logout()
    identity.value = null
    message.value = 'Abgemeldet.'
    $adminApi.clearCredential()
    emit('changed')
  } catch (error) {
    message.value = asFailure(error).message
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <section
    class="rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm"
    :class="[
      identity ? 'flex flex-wrap items-center gap-x-4 gap-y-2' : '',
      { 'statistics-login': compact && identity },
    ]"
    :aria-busy="busy"
    aria-labelledby="admin-login-title"
  >
    <h2 id="admin-login-title" :class="compact && identity ? 'sr-only' : 'font-semibold'">
      Admin-Anmeldung
    </h2>
    <form v-if="!identity" class="mt-3 flex flex-wrap items-end gap-3" @submit.prevent="signIn">
      <div>
        <label for="admin-login" class="label">Benutzername</label>
        <input
          id="admin-login"
          v-model="login"
          class="input"
          autocomplete="username"
          maxlength="254"
          :disabled="!ready || busy"
          required
        />
      </div>
      <div>
        <label for="admin-password" class="label">Passwort</label>
        <input
          id="admin-password"
          v-model="password"
          class="input"
          type="password"
          autocomplete="current-password"
          maxlength="1024"
          :disabled="!ready || busy"
          required
        />
      </div>
      <button class="button-primary" :disabled="!ready || busy">Anmelden</button>
    </form>
    <div v-else class="flex flex-1 flex-wrap items-center justify-between gap-3">
      <p class="text-xs text-slate-500">
        {{
          identity.system_admin
            ? compact
              ? 'System-Administrator'
              : 'Als System-Administrator angemeldet.'
            : 'Keine System-Admin-Berechtigung.'
        }}
      </p>
      <button class="button" :disabled="busy" @click="signOut">Abmelden</button>
    </div>
    <p v-if="message" class="w-full text-sm" role="status">{{ message }}</p>
  </section>
</template>

<style scoped>
.statistics-login {
  border: 0;
  padding: 0;
  background: transparent;
}
.statistics-login button {
  font-size: 11px;
  padding: 6px 10px;
  border-radius: 7px;
}
</style>
