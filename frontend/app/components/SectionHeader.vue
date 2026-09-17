<script setup lang="ts">
withDefaults(
  defineProps<{ title: string; description?: string; titleId?: string; as?: 'h2' | 'h3' }>(),
  { as: 'h3', description: undefined, titleId: undefined },
)
</script>
<template>
  <header class="flex flex-wrap items-start justify-between gap-3">
    <div class="min-w-0">
      <component :is="as" :id="titleId" class="text-lg font-semibold">{{ title }}</component>
      <p v-if="description" class="mt-1 text-sm text-slate-500">{{ description }}</p>
      <slot name="meta" />
    </div>
    <div v-if="$slots.default" class="flex flex-wrap items-center gap-2"><slot /></div>
  </header>
</template>
