<script setup lang="ts">
import type { RouteLocationRaw } from 'vue-router'
withDefaults(
  defineProps<{
    pagination: { page: number; pages: number }
    loading?: boolean
    to?: (page: number) => RouteLocationRaw
    label?: string
  }>(),
  { loading: false, label: 'Seitennavigation', to: undefined },
)
defineEmits<{ change: [page: number] }>()
</script>
<template>
  <nav class="flex flex-wrap items-center justify-between gap-3" :aria-label="label">
    <div class="flex flex-wrap items-center gap-3 text-sm text-slate-600">
      <p>
        {{
          pagination.pages ? `Seite ${pagination.page} von ${pagination.pages}` : 'Keine Ergebnisse'
        }}
      </p>
      <slot />
    </div>
    <div class="flex gap-2">
      <template v-for="direction in [-1, 1]" :key="direction">
        <NuxtLink
          v-if="
            to &&
            !loading &&
            (direction < 0 ? pagination.page > 1 : pagination.page < pagination.pages)
          "
          class="button"
          :rel="direction < 0 ? 'prev' : 'next'"
          :to="to(pagination.page + direction)"
          >{{ direction < 0 ? 'Zurück' : 'Weiter' }}</NuxtLink
        >
        <button
          v-else
          type="button"
          class="button"
          :disabled="
            loading || (direction < 0 ? pagination.page <= 1 : pagination.page >= pagination.pages)
          "
          @click="$emit('change', pagination.page + direction)"
        >
          {{ direction < 0 ? 'Zurück' : 'Weiter' }}
        </button>
      </template>
    </div>
  </nav>
</template>
