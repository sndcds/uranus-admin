<script setup lang="ts">
import { researchCategoryColor } from '~/utils/research-categories'
defineProps<{ category: { id: number; name: string } }>()
</script>

<template>
  <span
    class="research-category inline-flex max-w-full items-center gap-1.5 rounded-md bg-slate-50 px-2 py-0.5 text-xs font-medium text-slate-800"
  >
    <span
      aria-hidden="true"
      class="size-2.5 shrink-0 rounded-full"
      :style="{ backgroundColor: researchCategoryColor(category.id) }"
    />
    <span class="break-words">{{ category.name }}</span>
  </span>
</template>
