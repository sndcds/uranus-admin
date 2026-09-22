<script setup lang="ts">
import SqlProvenanceButton from './sql/SqlProvenanceButton.vue'
defineProps<{ title: string; description?: string; titleId?: string }>()
</script>
<template>
  <header class="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
    <div class="min-w-0">
      <div class="flex flex-wrap items-center gap-3">
        <h2 :id="titleId" class="text-2xl font-bold tracking-tight">{{ title }}</h2>
        <slot name="badge" />
      </div>
      <p v-if="description" class="mt-1 text-sm text-slate-500">{{ description }}</p>
    </div>
    <div
      data-page-header-actions
      class="flex w-full min-w-0 flex-col gap-2 sm:w-auto sm:flex-row sm:flex-wrap sm:items-center sm:justify-end"
    >
      <div class="order-2 flex empty:hidden sm:order-1"><SqlProvenanceButton /></div>
      <div
        data-page-header-primary-actions
        class="order-1 flex min-w-0 flex-wrap items-center gap-2 empty:hidden sm:order-2"
      >
        <slot />
      </div>
    </div>
  </header>
</template>
