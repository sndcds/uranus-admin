<script setup lang="ts">
defineProps<{ title: string; description?: string; titleId?: string }>()
</script>
<template>
  <header class="flex flex-wrap items-start justify-between gap-3">
    <div class="min-w-0">
      <h2 :id="titleId" class="text-2xl font-bold tracking-tight">{{ title }}</h2>
      <p v-if="description" class="mt-1 text-sm text-slate-500">{{ description }}</p>
    </div>
    <div v-if="$slots.default" class="flex flex-wrap items-center gap-2"><slot /></div>
  </header>
</template>
