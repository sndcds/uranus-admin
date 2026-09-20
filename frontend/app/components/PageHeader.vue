<script setup lang="ts">
import SqlProvenanceButton from './sql/SqlProvenanceButton.vue'
defineProps<{ title: string; description?: string; titleId?: string }>()
</script>
<template>
  <header class="flex flex-wrap items-start justify-between gap-3">
    <div class="min-w-0">
      <div class="flex flex-wrap items-center gap-3">
        <h2 :id="titleId" class="text-2xl font-bold tracking-tight">{{ title }}</h2>
        <slot name="badge" />
      </div>
      <p v-if="description" class="mt-1 text-sm text-slate-500">{{ description }}</p>
    </div>
    <div class="flex flex-wrap items-center gap-2"><SqlProvenanceButton /><slot /></div>
  </header>
</template>
