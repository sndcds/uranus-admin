<script setup lang="ts">
defineProps<{
  message: string
  title?: string
  variant?: 'default' | 'compact'
  compact?: boolean
}>()
</script>
<template>
  <div
    class="rounded-xl border border-dashed border-slate-300 bg-white text-center text-sm text-slate-600"
    :class="
      (variant ? variant === 'compact' : compact)
        ? 'flex min-h-16 flex-col items-center justify-center gap-1 px-3 py-3'
        : 'px-5 py-8'
    "
  >
    <p v-if="title" class="font-semibold text-slate-900">{{ title }}</p>
    <p>{{ message }}</p>
    <slot name="actions"><slot /></slot>
  </div>
</template>
