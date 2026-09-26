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
        route.path === link.to ||
        route.path.startsWith(link.to + '/') ||
        (route.path === '/research' && link.to === '/research/search')
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
      class="research-nav-link mt-8 border-t border-slate-200 text-sm"
      @click="$emit('navigate')"
    >
      <AppIcon name="settings" />Operations
    </NuxtLink>
  </nav>
</template>

<style scoped>
@reference '../assets/css/main.css';
.research-nav-link {
  @apply flex min-h-11 items-center gap-3 rounded-md border-l-2 border-transparent px-3 py-3 text-sm text-slate-600 hover:bg-slate-100;
}
.research-nav-link[aria-current='page'] {
  @apply border-blue-600 bg-blue-50 font-medium text-blue-700;
}
</style>
