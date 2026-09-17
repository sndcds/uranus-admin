<script setup lang="ts">
import { ref, nextTick, onMounted } from 'vue'
import { asFailure } from '#shared/errors'
import { returnTarget } from '~/utils/auth-redirect'

const auth = useAuthStore()
const route = useRoute()
const username = ref('')
const password = ref('')
const passwordInput = ref<HTMLInputElement | null>(null)
const busy = ref(false)
const ready = ref(false)
onMounted(() => {
  ready.value = true
})
const message = ref('')
async function signIn() {
  if (busy.value) return
  busy.value = true
  message.value = ''
  try {
    await auth.login(username.value, password.value)
    if (auth.isAdmin)
      await navigateTo(returnTarget(route.query.redirect, route.hash), { replace: true })
  } catch (cause) {
    const detail = asFailure(cause)
    message.value = detail.status === 401 ? 'Anmeldung fehlgeschlagen.' : detail.message
  } finally {
    password.value = ''
    busy.value = false
    if (message.value) {
      await nextTick()
      passwordInput.value?.focus()
    }
  }
}
</script>

<template>
  <section :aria-busy="busy" aria-labelledby="admin-login-title">
    <h1 id="admin-login-title" class="text-xl font-semibold">Anmeldung</h1>
    <p class="mt-2 text-sm text-slate-600">Bitte mit deinem Admin-Konto anmelden.</p>
    <form class="mt-6 space-y-4" @submit.prevent="signIn">
      <div>
        <label for="admin-login" class="label">Benutzername</label>
        <input
          id="admin-login"
          v-model="username"
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
          ref="passwordInput"
          v-model="password"
          class="input"
          type="password"
          autocomplete="current-password"
          maxlength="1024"
          :disabled="!ready || busy"
          required
        />
      </div>
      <button class="button-primary w-full" type="submit" :disabled="!ready || busy">
        {{ busy ? 'Anmeldung läuft …' : 'Anmelden' }}
      </button>
    </form>
    <p v-if="message || auth.error" class="mt-4 text-sm text-red-700" role="alert">
      {{ message || auth.error?.message }}
    </p>
  </section>
</template>
