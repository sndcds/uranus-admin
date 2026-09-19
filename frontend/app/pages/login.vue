<script setup lang="ts">
definePageMeta({ layout: 'auth', public: true })
useHead({ title: 'Anmeldung · Kulturbytes Admin' })
const auth = useAuthStore()
const interactive = ref(false)
onMounted(() => {
  interactive.value = true
})
</script>

<template>
  <div>
    <template v-if="auth.status === 'authenticated' && !auth.isAdmin">
      <h1 class="text-xl font-semibold">Zugriff gesperrt</h1>
      <p class="my-4" role="alert">Dein Konto hat keine System-Admin-Berechtigung.</p>
      <button class="button" :disabled="!interactive" @click="auth.logout()">Abmelden</button>
    </template>
    <LoginPanel v-else />
    <p v-if="auth.logoutWarning" class="mt-4 text-sm" role="alert">{{ auth.logoutWarning }}</p>
  </div>
</template>
