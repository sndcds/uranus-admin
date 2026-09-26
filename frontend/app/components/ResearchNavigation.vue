<script setup lang="ts">
import { researchNavigation } from '~/utils/research'
defineEmits<{ navigate: [] }>()
const route = useRoute()
const auth = useAuthStore()
</script>
<template>
  <nav aria-label="Recherche-Navigation" class="space-y-1 p-3">
    <NuxtLink
      v-for="link in researchNavigation"
      :key="link.to"
      :to="link.to"
      :aria-current="
        route.path === link.to || route.path.startsWith(link.to + '/') ? 'page' : undefined
      "
      class="button w-full justify-start"
      @click="$emit('navigate')"
    >
      <AppIcon :name="link.icon" />{{ link.label }}
    </NuxtLink>
    <NuxtLink
      v-if="auth.isAdmin"
      to="/"
      class="button mt-6 w-full justify-start"
      @click="$emit('navigate')"
    >
      <AppIcon name="settings" />Operations
    </NuxtLink>
  </nav>
</template>
