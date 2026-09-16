<script setup lang="ts">
defineEmits<{ apply: [] }>()
</script>
<template>
  <form
    class="rounded-2xl border border-slate-200 bg-white p-4 [&_label]:min-w-0 [&_select]:w-full [&_input]:w-full"
    aria-label="Filter"
    @submit.prevent="$emit('apply')"
  >
    <div class="grid items-end gap-3 sm:grid-cols-2 xl:grid-cols-4"><slot /></div>
    <slot name="help" />
  </form>
</template>
