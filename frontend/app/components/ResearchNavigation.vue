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
        (
          link.to === '/research'
            ? route.path === '/research' || route.path === '/research/search'
            : route.path === link.to || route.path.startsWith(link.to + '/')
        )
          ? 'page'
          : undefined
      "
      class="research-nav-link"
      @click="$emit('navigate')"
    >
      <AppIcon :name="link.icon" />{{ link.label }}
    </NuxtLink>
    <NuxtLink
      v-if="auth.isAdmin"
      to="/"
      class="research-nav-link relative mt-8 text-sm before:absolute before:inset-x-0 before:-top-4 before:border-t before:border-slate-200"
      @click="$emit('navigate')"
    >
      <AppIcon name="settings" />Operations
    </NuxtLink>
  </nav>
</template>

<style scoped>
@reference '../assets/css/main.css';
.research-nav-link {
  @apply flex min-h-11 items-center gap-4 rounded-md border-l-2 border-transparent px-3 py-3.5 text-sm text-slate-600 hover:bg-slate-100;
}
.research-nav-link[aria-current='page'] {
  @apply border-blue-600 bg-blue-50 font-medium text-blue-700;
}
</style>
